"""Living Companion Entry —— AOS 的 3D 生命体伙伴入口。

把交互式 3D 适配器（ThreejsAdapter）从「一次性生成场景」升级为
「持久、有生命感的伙伴 / 生命体」：

- Companion：身份（名字 / 人设 / 视觉种子）+ 状态（心情 / 能量 / 注意力），
  跨会话持久化。双域记忆：user 域（用户偏好/事实）+ agent 域（伙伴自身经验）。
- build_living_home_html：GET / 返回的整页 —— 伙伴的「身体」(3D 场景) +
  HUD（名字/心情）+ 输入浮层 + 语音按钮 + 在场感 JS（呼吸 / 随光标转头 / 消息脉冲）。
- route_intent：自然语言 → 路由到 AOS 真实能力（media.3d / web.search / inference.llm）。
- handle_companion_message：编排「感知→记忆→规划→执行→回应」，更新伙伴状态并持久化。

设计原则（对齐阶跃 Step AOS / Amoo 发布会，映射真实 AOS）：
- 伙伴 = 入口（NUI 结果交互），不是聊天框。对着「它」说话，它去调原子能力。
- 双域记忆：user 域 + agent 域（落盘 JSON；mem0 是升级路径，见 MEM0 注释）。
- 端云合作：意图路由复用 FabricHub 路由层；云端用不了就本地（3D 永远本地可用）。
- 纯增量、零新依赖：只生成 HTML + JSON，服务端不建重型内核即可跑。
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .adapters.threejs_adapter import build_scene_html
from . import persona as _persona

logger = logging.getLogger(__name__)

# 伙伴状态落盘目录（双域记忆的轻量实现；mem0 是未来的语义记忆升级路径）。
_COMPANION_DIR = Path(
    os.environ.get(
        "AOS_COMPANION_DIR",
        str(Path(__file__).resolve().parents[3] / ".companion"),
    )
)
# 设为 1 时，chat 意图会真走 FabricHub 路由层（需云端 LLM key / 本地模型）；
# 默认 0：离线时伙伴用「用心听、用身体回应」的本地回执，保证任何环境都能跑。
_LLM_ROUTING = os.environ.get("AOS_COMPANION_LLM", "0") == "1"

MOOD_EMOJI = {
    "calm": "🌙", "happy": "✨", "curious": "🔍",
    "thinking": "💭", "sad": "🌧", "excited": "⚡",
}


@dataclass
class Companion:
    """一个持久、有状态的 3D 生命体伙伴。"""

    user_id: str = "default"
    identity: dict = field(default_factory=dict)
    state: dict = field(default_factory=dict)
    user_domain: dict = field(default_factory=dict)
    agent_domain: dict = field(default_factory=dict)
    _path: Optional[Path] = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # 跨实例的文件访问锁：Windows 下并发读写 .json 会触发 WinError 32
    # （另一个线程正打开该文件），用类级锁串行化所有读写即可消除。
    _STORE_LOCK = threading.Lock()

    # ---- 默认人设（人设配置化：谁用谁设；见 persona.py）----
    # identity 现在 = persona（人设配置文件）。优先级：
    #   用户专属 personas/{user_id}.yaml > personas/default.yaml > 代码内置默认
    # 这里仅保留「无任何人设文件时的代码兜底」，真实来源是 persona.load_persona。
    @staticmethod
    def _default_identity() -> dict:
        return _persona.load_persona("default")

    @staticmethod
    def _default_state() -> dict:
        return {"mood": "calm", "energy": 1.0, "attention": 0.5,
                "turns": 0, "created_at": time.time(), "last_seen": time.time()}

    # ---- 加载 / 持久化（双域记忆落盘）----
    @classmethod
    def load(cls, user_id: str = "default") -> "Companion":
        # 人设（identity）以 persona 配置文件为权威来源；companion JSON 只存
        # state + 双域记忆。这样「改人设文件」立即生效，且不会被旧 JSON 冲掉。
        identity = _persona.load_persona(user_id)
        path = _COMPANION_DIR / f"{user_id}.json"
        with cls._STORE_LOCK:
            if path.exists():
                # 并发读写可能读到半截文件：重试几次再放弃（放弃则重新初始化）。
                for _ in range(3):
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                        c = cls(
                            user_id=user_id,
                            identity=identity,
                            state=data.get("state", cls._default_state()),
                            user_domain=data.get("user_domain", {}),
                            agent_domain=data.get("agent_domain", {}),
                        )
                        c._path = path
                        return c
                    except Exception as e:  # noqa: BLE001
                        logger.warning("companion load 重试: %s", e)
                        time.sleep(0.05)
            c = cls(user_id=user_id, identity=identity,
                    state=cls._default_state(), user_domain={"prefs": {}, "facts": []},
                    agent_domain={"experiences": [], "self_notes": []})
            c._path = path
            c._write()
            return c

    def save(self) -> None:
        with self._STORE_LOCK:
            self._write()

    def _write(self) -> None:
        self.state["last_seen"] = time.time()
        self._path = self._path or (_COMPANION_DIR / f"{self.user_id}.json")
        _COMPANION_DIR.mkdir(parents=True, exist_ok=True)
        # 直接覆盖写；类级 _STORE_LOCK 已串行化，读方有重试，无需 temp+replace
        # （Windows 下 os.replace 对正被打开的文件会 WinError 32）。
        self._path.write_text(
            json.dumps({
                "identity": self.identity,
                "state": self.state,
                "user_domain": self.user_domain,
                "agent_domain": self.agent_domain,
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # ---- 属性 ----
    @property
    def name(self) -> str:
        return self.identity.get("name", "小元")

    @property
    def mood(self) -> str:
        return self.state.get("mood", "calm")

    @property
    def mood_emoji(self) -> str:
        # 人设可自定义心情→emoji 映射；缺省回退默认表
        custom = (self.identity or {}).get("mood_emojis") or {}
        return custom.get(self.mood) or MOOD_EMOJI.get(self.mood, "🌙")

    def is_returning(self) -> bool:
        return self.state.get("turns", 0) > 0

    # ---- 行为的「生命感」----
    def greet(self) -> str:
        # 人设驱动：greeting 模板支持 {name} 占位；回头客带一句「想念」
        tmpl = self.identity.get("greeting") or "你好，我是 {name}。"
        base = tmpl.replace("{name}", self.name)
        if self.is_returning():
            base = f"{self.mood_emoji} 你回来啦，{self.name} 一直在想你上次说的那些事～"
        cp = (self.identity.get("catchphrase") or "").strip()
        if cp and not base.endswith(cp):
            base = f"{base} {cp}"
        return base

    # ---- 人设配置化：谁用谁设（写盘 + 热重载）----
    def set_persona(self, patch: dict) -> dict:
        """合并 patch 写盘为用户专属人设，并热重载本实例 identity。"""
        merged = _persona.save_persona(self.user_id, patch)
        self.identity = merged
        return merged

    def reset_persona(self) -> dict:
        merged = _persona.reset_persona(self.user_id)
        self.identity = merged
        return merged

    def react(self, mood: str) -> None:
        if mood in MOOD_EMOJI:
            self.state["mood"] = mood
        self.state["turns"] = self.state.get("turns", 0) + 1

    def remember_user(self, text: str) -> None:
        facts = self.user_domain.setdefault("facts", [])
        if text and text not in facts:
            facts.append(text)
            if len(facts) > 50:
                facts.pop(0)
        # 双域增强：user 域镜像到 mem0（隔离子进程，失败自动退回本地）
        _Mem0Bridge.store("user", text, self.user_id)

    def note_experience(self, kind: str, detail: str) -> None:
        exp = self.agent_domain.setdefault("experiences", [])
        exp.append({"kind": kind, "detail": detail, "ts": time.time()})
        if len(exp) > 50:
            exp.pop(0)
        # 双域增强：agent 域镜像到 mem0（命名空间 __agent__{user_id}）
        _Mem0Bridge.store("agent", f"[{kind}] {detail}", self.user_id)

    def recall_user_memories(self, query: str = "") -> list[str]:
        """召回 user 域记忆（mem0 优先，不可用退回本地 JSON 扫描）。"""
        mem = _Mem0Bridge.recall("user", self.user_id, query=query)
        if mem is not None:
            return mem
        return list(self.user_domain.get("facts", [])[-5:])

    def recall_agent_memories(self, query: str = "") -> list[str]:
        mem = _Mem0Bridge.recall("agent", self.user_id, query=query)
        if mem is not None:
            return mem
        return [f"[{e['kind']}] {e['detail']}"
                for e in self.agent_domain.get("experiences", [])[-5:]]

    # ---- 意图识别（自然语言 → AOS 真实能力）----
    def route_intent(self, text: str) -> dict:
        t = text.lower()
        # 3D / 场景意图（核心能力，本地永远可用）
        if re.search(r"3d|三维|三維|场景|宇宙|粒子|星河|银河|星球|地球|行星|"
                     r"城市|城市|建模|模型|纽结|立方体|做个|生成|建个|画个|来个|捏个|"
                     r"立体|三维|渲染", t):
            return {"kind": "3d", "payload": {"prompt": text},
                    "reaction": "excited", "reply_hint": "给你做了个场景，点开看看～"}
        # 搜索意图
        if re.search(r"搜索|搜一下|查一下|查查|最新|新闻|资讯|what|who|when|怎么查|"
                     r"百科|资料", t):
            return {"kind": "search", "payload": {"query": text},
                    "reaction": "curious", "reply_hint": "我帮你查查～"}
        # 时间序列 / 预测意图 → LNN（液态神经网络，AOS 轻量动态推理芯粒）
        if re.search(r"预测|forecast|时间序列|趋势|走势|推断|算算后面", t):
            nums = re.findall(r"-?\d+(?:\.\d+)?", text)
            series = [float(n) for n in nums] if nums else None
            return {"kind": "lnn", "payload": {"series": series},
                    "reaction": "curious", "reply_hint": "我用量化液态网络帮你预测～"}
        # 默认：对话
        return {"kind": "chat", "payload": {"prompt": text},
                "reaction": "thinking", "reply_hint": None}


# ============================================================================
# 意图执行（复用 AOS 真实能力，端云合作 + 优雅降级）
# ============================================================================

def _invoke_3d(prompt: str) -> dict:
    """直连 ThreejsAdapter（不经重型 hub，秒回、零依赖）。"""
    from .adapters.threejs_adapter import ThreejsAdapter
    from .adapter import InvokeRequest
    r = ThreejsAdapter().invoke(InvokeRequest(
        capability="media.3d", payload={"prompt": prompt}))
    if not r.ok:
        return {"ok": False, "error": r.error}
    return {"ok": True, "html": r.data["html"], "scene_type": r.data["scene_type"]}


def _route_hub(capability: str, payload: dict) -> dict:
    """经 FabricHub 路由层（端云合作）。仅 chat/search 用；3D 不走这里。"""
    try:
        from mcp.protocol import _get_hub
        hub = _get_hub()
        res = hub.route(capability, payload)
        if res and getattr(res, "ok", False):
            return {"ok": True, "data": getattr(res, "data", None)}
        return {"ok": False, "error": getattr(res, "error", "hub 返回不可用")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"hub 路由失败: {e}"}


def handle_companion_message(text: str, user_id: str = "default",
                             voice: bool = False) -> dict:
    """编排：感知 → 记忆 → 规划（意图） → 执行（AOS 能力） → 回应。

    voice=True 时，若服务端有可用 TTS 引擎（kokoro/edge-tts/XTTS），额外合成
    audio_url 让前端播放；否则 audio_url=None，前端自动改用浏览器
    speechSynthesis 朗读（诚实降级，全链路不崩）。
    """
    text = (text or "").strip()
    companion = Companion.load(user_id)
    companion.react("thinking")  # 先进入「思考」态

    if not text:
        companion.save()
        return {"ok": True, "reply": companion.greet(), "mood": companion.mood,
                "companion": _companion_view(companion)}

    intent = companion.route_intent(text)
    reply = ""
    scene_id = None
    scene_html = None
    recalled: list[str] = []

    if intent["kind"] == "3d":
        res = _invoke_3d(text)
        if res["ok"]:
            scene_id = _store_scene(res["html"])
            reply = f"做好了 ✨ 这是一个「{res['scene_type']}」场景，点开就能拖着玩。"
            companion.react("excited")
            companion.note_experience("3d", f"{res['scene_type']}: {text[:40]}")
        else:
            reply = f"想给你做 3D，但生成失败了：{res.get('error')}。要不要换个说法？"
            companion.react("sad")

    elif intent["kind"] == "search":
        if _LLM_ROUTING:
            res = _route_hub("web.search", {"query": text})
            if res["ok"]:
                reply = _summarize(res["data"])
                companion.react("curious")
            else:
                reply = "我现在的联网检索暂时连不上，但你的问题我记下了，连上就帮你查。"
                companion.react("sad")
        else:
            reply = "想帮你查，不过我的联网检索在云端～你这问题我记下了，连上网就办。"
            companion.react("curious")
        companion.remember_user(text)

    elif intent["kind"] == "lnn":
        series = intent["payload"].get("series")
        payload = {"horizon": 5}
        if series:
            payload["series"] = series
        else:
            payload["demo"] = True
        res = _route_hub("inference.lnn", payload)
        if res["ok"]:
            fc = (res.get("data") or {}).get("forecast", [])
            reply = (f"我用液态神经网络(LNN)做了预测 ✨ 接下来 {len(fc)} 步："
                     f"{fc}。LNN 擅长这种动态趋势，比硬算更稳。")
            companion.react("curious")
            companion.note_experience("lnn", f"forecast horizon={len(fc)}")
        else:
            reply = (f"想用 LNN 帮你预测，但芯粒暂时连不上：{res.get('error')}。"
                     f"你换个说法或稍后再试？")
            companion.react("sad")

    else:  # chat
        if _LLM_ROUTING:
            res = _route_hub("inference.llm", {"prompt": text})
            if res["ok"]:
                reply = _extract_reply(res["data"]) or companion.greet()
                companion.react("happy")
            else:
                reply = _local_ack(companion, text)
                companion.react("calm")
        else:
            reply = _local_ack(companion, text)
            companion.react("calm")
        companion.remember_user(text)
        # 双域：召回相关用户记忆，丰富离线回应（mem0 不可用则退回本地扫描）
        recalled = companion.recall_user_memories(text)
        if recalled and reply == _local_ack(companion, text):
            snippet = recalled[-1]
            reply = (f"{reply} 对了，我记得你之前提过：「{snippet[:40]}」。"
                     f"等我的语言中枢连上，咱们接着聊。")

    companion.save()
    # 语音：可选合成（优雅降级）；人设 tts_voice 驱动嗓音
    audio_url = None
    tts_engine = None
    if voice:
        audio_url, tts_engine = _tts_if_wanted(reply, companion)
    return {
        "ok": True,
        "reply": reply,
        "mood": companion.mood,
        "mood_emoji": companion.mood_emoji,
        "scene_id": scene_id,
        "audio_url": audio_url,
        "tts_engine": tts_engine,
        "recalled_user_facts": recalled,
        "companion": _companion_view(companion),
    }


def _tts_if_wanted(reply: str, companion: "Companion | None" = None):
    """尝试服务端 TTS；不可用则 (None, None) 让前端浏览器朗读兜底。

    companion 提供人设 tts_voice（如 edge-tts 的 zh-CN-XiaoxiaoNeural），
    留空则 TTS 适配器自选默认嗓音。
    """
    try:
        from .adapters.tts_adapter import TTSAdapter
        from .adapter import InvokeRequest
        payload = {"text": reply}
        if companion is not None:
            voice = (companion.identity or {}).get("tts_voice")
            if voice:
                payload["voice"] = voice
        r = TTSAdapter().invoke(InvokeRequest(
            capability="voice.tts", payload=payload))
        if r.ok:
            return r.data.get("audio_url"), r.data.get("engine")
    except Exception as e:  # noqa: BLE001
        logger.warning("伴侣语音合成降级到浏览器: %s", e)
    return None, None


# ---- 小工具 ----
# 场景存储的唯一真相源（companion 拥有，http_server 的 _serve_scene 懒读取它）。
_SCENES: dict = {}


def _store_scene(html: str) -> str:
    import hashlib
    sid = hashlib.sha1(html.encode("utf-8")).hexdigest()[:12]
    _SCENES[sid] = html
    return sid


def _extract_reply(data: Any) -> str:
    if isinstance(data, dict):
        for k in ("content", "text", "response", "reply"):
            if isinstance(data.get(k), str) and data[k].strip():
                return data[k]
    if isinstance(data, str):
        return data
    return ""


def _summarize(data: Any) -> str:
    if isinstance(data, dict):
        for k in ("summary", "content", "text", "answer"):
            if isinstance(data.get(k), str) and data[k].strip():
                return data[k][:600]
    return "查到了一些结果，但格式不太标准，你联网看看？"


def _local_ack(companion: Companion, text: str) -> str:
    # 离线时：用心听、用身体回应（诚实，不谎报云端能力）
    return (f"{companion.mood_emoji} 我听到你说的了：「{text[:40]}」。"
            f"我的语言中枢在云端，离线时我用心记着、用身体回应你——"
            f"连上网络或本地模型后，我就能真正和你聊起来。")


# ============================================================================
# mem0 双域记忆桥（user 域 + agent 域）
# ----------------------------------------------------------------------------
# 设计原则（诚实 + 隔离优先，契合 AOS chiplet 哲学）：
# - 铁底 = 本地 JSON（user_domain / agent_domain），零依赖、任何环境都工作。
# - 增强 = mem0 语义记忆，作为「可选升级层」，默认关闭（AOS_MEM0_BRIDGE=1 开）。
# - 隔离 = mem0 调用跑在**独立子进程**里：本沙箱实测 ollama 抽取事实会硬崩子进程
#   （段错，Python 不可捕获），子进程崩了主服务毫发无伤，自动退回本地 JSON。
# - 双域 = user 域用真实 user_id；agent 域用 `__agent__{user_id}` 命名空间隔离，
#   互不串扰（mem0 2.0.11 的 add 不接受 category，故用 user_id 区分）。
# ============================================================================
class _Mem0Bridge:
    """进程内管理的 mem0 双域记忆桥；store/recall 全部走隔离子进程。"""

    _DISABLED = False          # 熔断：连续失败超阈值则本进程禁用
    _CONSEC_FAIL = 0
    _FAIL_LIMIT = 5
    _LOCK = threading.Lock()

    @classmethod
    def enabled(cls) -> bool:
        import os
        if os.environ.get("AOS_MEM0_BRIDGE") != "1":
            return False
        with cls._LOCK:
            if cls._DISABLED:
                return False
        # 轻量健康探测（子进程）：import 成 + 后端可达
        out = cls._run({"action": "health"})
        return bool(out and out.get("ok"))

    @classmethod
    def _domain_user_id(cls, user_id: str, domain: str) -> str:
        return user_id if domain == "user" else f"__agent__{user_id}"

    @classmethod
    def store(cls, domain: str, text: str, user_id: str = "default") -> bool:
        if not cls.enabled() or not text:
            return False
        out = cls._run({
            "action": "add",
            "text": text,
            "opts": {"user_id": cls._domain_user_id(user_id, domain)},
        })
        ok = bool(out and out.get("ok"))
        cls._note_result(ok)
        return ok

    @classmethod
    def recall(cls, domain: str, user_id: str = "default",
               query: str = "", limit: int = 5) -> list[str] | None:
        if not cls.enabled():
            return None
        out = cls._run({
            "action": "search",
            "query": query or ("用户偏好" if domain == "user" else "伙伴经验"),
            "opts": {"user_id": cls._domain_user_id(user_id, domain), "limit": limit},
        })
        if not out or not out.get("ok"):
            cls._note_result(False)
            return None
        cls._note_result(True)
        return out.get("texts") or []

    @classmethod
    def _note_result(cls, ok: bool) -> None:
        with cls._LOCK:
            if ok:
                cls._CONSEC_FAIL = 0
            else:
                cls._CONSEC_FAIL += 1
                if cls._CONSEC_FAIL >= cls._FAIL_LIMIT:
                    cls._DISABLED = True
                    logger.error("mem0 桥连续失败 %d 次，本进程熔断禁用（退回本地 JSON）",
                                 cls._CONSEC_FAIL)

    @classmethod
    def _run(cls, cmd: dict) -> dict | None:
        """在隔离子进程里跑 mem0 操作；子进程崩了（段错）父进程安全返回 None。"""
        import json as _json
        import subprocess
        import sys as _sys
        # repo root = src/core/fabric/companion.py 向上 3 级
        repo_root = Path(__file__).resolve().parents[3]
        script = (
            "import os,sys,json\n"
            "os.environ['AOS_MEM0_LOCAL']='1'\n"
            "try:\n"
            "  from core.fabric.adapters.mem0_adapter import Mem0Adapter\n"
            "  from core.fabric.adapter import InvokeRequest\n"
            "  a=Mem0Adapter()\n"
            "  if cmd['action']=='health':\n"
            "    print(json.dumps({'ok':bool(a.health()),'detail':a.health_detail()})); sys.exit(0)\n"
            "  if not a.health():\n"
            "    print(json.dumps({'ok':False,'error':'mem0 not healthy'})); sys.exit(0)\n"
            "  if cmd['action']=='add':\n"
            "    r=a.invoke(InvokeRequest(capability='memory.semantic',payload={'action':'add','text':cmd['text'],'opts':cmd.get('opts',{})}))\n"
            "    print(json.dumps({'ok':r.ok,'error':r.error})); sys.exit(0)\n"
            "  # search\n"
            "  r=a.invoke(InvokeRequest(capability='memory.semantic',payload={'action':'search','query':cmd.get('query'),'opts':cmd.get('opts',{})}))\n"
            "  texts=[]\n"
            "  if r.ok:\n"
            "    res=r.data.get('result') if isinstance(r.data,dict) else r.data\n"
            "    items=res if isinstance(res,list) else []\n"
            "    for it in items:\n"
            "      if isinstance(it,dict):\n"
            "        t=it.get('memory') or it.get('text') or it.get('data')\n"
            "        if isinstance(t,str) and t.strip(): texts.append(t.strip())\n"
            "      elif isinstance(it,str) and it.strip(): texts.append(it.strip())\n"
            "  print(json.dumps({'ok':r.ok,'texts':texts,'error':r.error}))\n"
            "except Exception as e:\n"
            "  print(json.dumps({'ok':False,'error':repr(e)})); sys.exit(0)\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = str(repo_root / "src")
        env["AOS_MEM0_LOCAL"] = "1"
        try:
            res = subprocess.run(
                [_sys.executable, "-c", script, _json.dumps(cmd)],
                capture_output=True, text=True, timeout=120, env=env,
                cwd=str(repo_root),
            )
            if res.returncode != 0:
                logger.warning("mem0 子进程异常退出 rc=%s: %s",
                               res.returncode, (res.stderr or "")[:200])
                return None
            for line in reversed(res.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    return _json.loads(line)
        except Exception as e:  # noqa: BLE001
            logger.warning("mem0 子进程调用失败: %s", e)
        return None


def _companion_view(c: Companion) -> dict:
    idn = c.identity or {}
    return {
        "name": c.name,
        "persona": idn.get("persona", ""),
        "avatar": idn.get("avatar", "🌟"),
        "tone": idn.get("tone", "warm"),
        "tts_voice": idn.get("tts_voice", ""),
        "catchphrase": idn.get("catchphrase", ""),
        "body_prompt": idn.get("body_prompt", ""),
        "mood": c.mood,
        "mood_emoji": c.mood_emoji,
        "energy": c.state.get("energy", 1.0),
        "turns": c.state.get("turns", 0),
        "is_returning": c.is_returning(),
        "memory": {
            "user_facts": len(c.user_domain.get("facts", [])),
            "agent_experiences": len(c.agent_domain.get("experiences", [])),
            # 双域增强层状态：mem0 是否桥接（默认关，AOS_MEM0_BRIDGE=1 开）
            "mem0_bridge": _Mem0Bridge.enabled(),
            "mem0_note": ("mem0 语义记忆已桥接（user/agent 双域）"
                          if _Mem0Bridge.enabled()
                          else "本地 JSON 双域记忆（设 AOS_MEM0_BRIDGE=1 启用 mem0 语义增强）"),
        },
    }


# ============================================================================
# 生命体首页（GET /）：伙伴的身体 + HUD + 输入浮层 + 语音 + 在场感
# ============================================================================

def build_living_home_html(companion: Companion) -> str:
    """返回整页：3D 伙伴身体 + 叠加的 HUD / 输入 / 语音 / 在场感。"""
    body_html = build_scene_html(companion.identity.get("body_prompt", "生命体核心 纽结"),
                                  "companion")
    # 去掉 body_html 自带的 <html>/<head>/<body> 与样式，只取 <script type=module> 场景块
    scene_script = _extract_scene_script(body_html)
    name = companion.name
    persona = companion.identity.get("persona", "")
    avatar = companion.identity.get("avatar", "🌟")
    greet = companion.greet()
    mood = companion.mood_emoji

    page = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__NAME__ · 生命体伙伴</title>
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#0a0a12;
    font-family:-apple-system,system-ui,'PingFang SC',sans-serif;color:#cfe}
  #hud{position:fixed;left:14px;top:14px;background:rgba(10,12,24,.5);backdrop-filter:blur(6px);
    padding:10px 14px;border-radius:12px;max-width:62vw;pointer-events:none;line-height:1.5}
  #hud .nm{font-size:17px;font-weight:700;color:#fff}
  #hud .ps{font-size:12px;color:#9ab;margin-top:2px}
  #hud .mo{font-size:13px;margin-top:6px;color:#fb6}
  #bubble{position:fixed;left:50%;top:18%;transform:translateX(-50%);
    max-width:70vw;background:rgba(20,24,44,.82);border:1px solid #2a3a6a;border-radius:16px;
    padding:12px 18px;font-size:15px;color:#eaf;opacity:0;transition:opacity .4s;pointer-events:none;text-align:center}
  #bubble.show{opacity:1}
  #dock{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);display:flex;gap:8px;
    width:min(680px,92vw);background:rgba(12,14,28,.7);backdrop-filter:blur(8px);
    padding:8px 10px;border-radius:18px;border:1px solid #243056}
  #say{flex:1;background:#0c0f1e;border:1px solid #2a3a6a;border-radius:12px;color:#dff;
    padding:11px 14px;font-size:15px;outline:none}
  #say::placeholder{color:#567}
  #send,#mic,#speak{background:#2a6cff;border:none;color:#fff;border-radius:12px;padding:0 16px;
    font-size:15px;cursor:pointer}
  #mic{background:#3a2a6c}
  #mic.on{background:#c0392b}
  #wake{background:#1d6c4a;font-size:15px}
  #wake.on{background:#16a34a;box-shadow:0 0 12px #16a34a}
  #planLbl{display:flex;align-items:center;gap:3px;color:#9fb3d9;font-size:13px;
    cursor:pointer;user-select:none;padding:0 6px}
  #planLbl input{accent-color:#2a6cff}
  #speak{background:#2a4a6c}
  #speak.off{opacity:.45}
  #sceneModal{position:fixed;inset:0;display:none;background:#05060c;z-index:50}
  #sceneModal.show{display:block}
  #sceneModal iframe{width:100%;height:100%;border:0}
  #sceneClose{position:fixed;right:18px;top:18px;z-index:51;background:#c0392b;border:none;
    color:#fff;border-radius:10px;padding:8px 14px;font-size:14px;cursor:pointer;display:none}
  #sceneClose.show{display:block}
  #err{position:fixed;inset:0;display:none;align-items:center;justify-content:center;
    color:#f99;font-size:15px;text-align:center;padding:20px}
  #gear{background:#3a3060;font-size:15px}
  #gear.on{background:#7c4dff;box-shadow:0 0 12px #7c4dff}
  #settingsModal{position:fixed;inset:0;display:none;background:rgba(4,6,12,.78);
    z-index:60;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
  #settingsModal.show{display:flex}
  #settingsCard{width:min(520px,92vw);max-height:88vh;overflow:auto;background:#0e1224;
    border:1px solid #2a3a6a;border-radius:18px;padding:20px 22px;color:#dff}
  #settingsCard h3{margin:0 0 4px;font-size:18px;color:#fff}
  #settingsCard .sub{font-size:12px;color:#8aa;margin-bottom:14px}
  #settingsCard label{display:block;font-size:12px;color:#9fb3d9;margin:12px 0 4px}
  #settingsCard input,#settingsCard textarea{width:100%;background:#0c0f1e;border:1px solid #2a3a6a;
    border-radius:10px;color:#dff;padding:9px 11px;font-size:14px;outline:none;box-sizing:border-box}
  #settingsCard textarea{resize:vertical;min-height:54px}
  #settingsCard .row{display:flex;gap:10px}
  #settingsCard .row>div{flex:1}
  #settingsCard .acts{display:flex;gap:10px;margin-top:18px}
  #settingsCard .acts button{flex:1;border:none;border-radius:12px;padding:11px;font-size:15px;cursor:pointer}
  #savePersona{background:#2a6cff;color:#fff}
  #resetPersona{background:#333a55;color:#cdd}
  #closeSettings{background:#222a44;color:#cdd}
  #personaMsg{font-size:12px;margin-top:10px;min-height:16px;color:#6f6}
</style>
</head>
<body>
<div id="hud">
  <div class="nm">__AVATAR__ __MOOD__ __NAME__</div>
  <div class="ps">__PERSONA__</div>
  <div class="mo" id="moodLine">状态：在呼吸，在听着…</div>
</div>
<div id="bubble"></div>
<div id="dock">
  <input id="say" placeholder="对着 __NAME__ 说点什么…（试试「做个宇宙粒子星河」）" autocomplete="off">
  <label id="planLbl" title="深度规划：走 ag2 把任务拆成多步执行"><input type="checkbox" id="plan">🧠</label>
  <button id="mic" title="语音输入">🎤</button>
  <button id="speak" title="语音播报">🔊</button>
  <button id="wake" title="常驻聆听（自动唤醒，说话即触发）">🔅</button>
  <button id="gear" title="人设设置（谁用谁自己设）">⚙️</button>
  <button id="send">发送</button>
</div>
<div id="sceneModal"><iframe id="sceneFrame" src=""></iframe></div>
<button id="sceneClose">关闭 ✕</button>
<div id="err">无法加载 Three.js（需浏览器联网访问 CDN）。<br>请联网后重试，或部署本地 three.js。</div>

<!-- 人设设置面板（谁用谁自己设）-->
<div id="settingsModal">
  <div id="settingsCard">
    <h3>⚙️ 人设设置</h3>
    <div class="sub">这份人设只属于当前用户，改完立即生效。也可以直接编辑 <code>.companion/personas/&lt;user_id&gt;.yaml</code>。</div>
    <label>名字 / 显示名</label>
    <input id="pName" placeholder="小元">
    <div class="row">
      <div><label>头像 emoji</label><input id="pAvatar" placeholder="🌟"></div>
      <div><label>语气 tone</label><input id="pTone" placeholder="warm"></div>
    </div>
    <label>一句话人设（HUD 副标题）</label>
    <textarea id="pPersona" placeholder="一个由 AOS 内核孕育的数字生命体…"></textarea>
    <label>3D 身体提示词（决定长相）</label>
    <input id="pBody" placeholder="发光的生命体核心 纽结 呼吸">
    <div class="row">
      <div><label>TTS 嗓音（如 zh-CN-XiaoxiaoNeural）</label><input id="pVoice" placeholder="留空=默认"></div>
      <div><label>口头禅</label><input id="pCatch" placeholder="（可选）"></div>
    </div>
    <label>问候语（支持 {name} 占位）</label>
    <textarea id="pGreet" placeholder="你好，我是 {name}…"></textarea>
    <div class="acts">
      <button id="savePersona">保存</button>
      <button id="resetPersona">恢复默认</button>
      <button id="closeSettings">关闭</button>
    </div>
    <div id="personaMsg"></div>
  </div>
</div>

__SCENE_SCRIPT__

<script>
// ===== 生命体在场感：呼吸 / 随光标转头 / 消息脉冲 =====
const S = () => window.AOS_SCENE;
function presence(){
  const s = S(); if(!s||!s.main) return;
  const t = s.t ? s.t.v : 0;
  // 呼吸：轻微缩放
  const b = 1 + Math.sin(t*1.1)*0.04;
  s.main.scale.setScalar(b);
  // 随光标转头：main 朝向指针方向轻微偏转
  const ptr = window.__ptr;
  const mx = (ptr&&ptr.clientX!=null)? (ptr.clientX/innerWidth-0.5):0;
  const my = (ptr&&ptr.clientY!=null)? (ptr.clientY/innerHeight-0.5):0;
  s.main.rotation.x += (my*0.6 - s.main.rotation.x)*0.05;
  s.main.rotation.z += (-mx*0.4 - s.main.rotation.z)*0.05;
}
addEventListener('mousemove', e=>{ window.__ptr=e; });
const _anim = (window.AOS_SCENE && window.AOS_SCENE.scene) ? null : null;
// 把 presence 挂进渲染循环（通过覆盖 animate 前的钩子）
window.__aosOnSceneReady = (s)=>{ const baseAnim = ()=>{}; 
  const tick = ()=>{ presence(); };
  const orig = s.controls; 
  const loop = ()=>{ tick(); };
  // 注入到 setAnimationLoop 之后：用 requestAnimationFrame 叠加
  (function raf(){ requestAnimationFrame(raf); tick(); })();
};
if(window.AOS_SCENE) window.__aosOnSceneReady(window.AOS_SCENE);

// ===== 对话：把话传给伙伴，它去调能力 =====
const bubble=document.getElementById('bubble');
const moodLine=document.getElementById('moodLine');
// 语音播报：优先播放服务端合成的 audio_url；否则用浏览器 speechSynthesis 朗读。
const synth = window.speechSynthesis;
let voiceOn = !!synth;
const speakBtn=document.getElementById('speak');
function syncSpeakBtn(){ speakBtn.classList.toggle('off', !voiceOn); }
speakBtn.onclick=()=>{ voiceOn=!voiceOn; if(!voiceOn&&synth) synth.cancel(); syncSpeakBtn(); };
syncSpeakBtn();
function voiceOut(d){
  if(d.audio_url){ const a=new Audio(d.audio_url); a.play().catch(()=>{}); return; }
  if(voiceOn && synth && d.reply){ try{ synth.cancel(); const u=new SpeechSynthesisUtterance(d.reply); u.lang='zh-CN'; u.rate=1.0; synth.speak(u);}catch(e){} }
}
function say(text){
  if(!text.trim()) return;
  bubble.textContent='💭 思考中…'; bubble.classList.add('show');
  moodLine.textContent='状态：思考中…';
  const plan = document.getElementById('plan').checked;
  fetch('/api/voice/turn',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({transcript:text, plan:plan})})
    .then(r=>r.json()).then(d=>{
      bubble.textContent=d.reply||'…'; bubble.classList.add('show');
      if(d.planner_used) moodLine.textContent='状态：已用 '+d.planner_used+' 规划多步执行';
      else moodLine.textContent='状态：回应中';
      if(d.scene_id){ setTimeout(()=>openScene(d.scene_id), 600); }
      voiceOut(d);
    }).catch(e=>{ bubble.textContent='哎呀，和伙伴的连接抖了一下：'+e; bubble.classList.add('show'); });
}
function openScene(id){
  document.getElementById('sceneFrame').src='/scene/'+id;
  document.getElementById('sceneModal').classList.add('show');
  document.getElementById('sceneClose').classList.add('show');
}
document.getElementById('sceneClose').onclick=()=>{
  document.getElementById('sceneModal').classList.remove('show');
  document.getElementById('sceneClose').classList.remove('show');
  document.getElementById('sceneFrame').src='';
};
document.getElementById('send').onclick=()=>{ const i=document.getElementById('say'); say(i.value); i.value=''; };
document.getElementById('say').addEventListener('keydown',e=>{ if(e.key==='Enter'){ say(e.target.value); e.target.value=''; }});

// ===== 语音输入 NUI（Web Speech API，纯浏览器）=====
const mic=document.getElementById('mic'); let rec=null;
if('webkitSpeechRecognition' in window || 'SpeechRecognition' in window){
  const SR = window.SpeechRecognition||window.webkitSpeechRecognition;
  rec=new SR(); rec.lang='zh-CN'; rec.interimResults=false;
  rec.onresult=e=>{ const t=e.results[0][0].transcript; say(t); };
  mic.onclick=()=>{ if(rec.recording){ rec.stop(); mic.classList.remove('on'); } else { rec.start(); mic.classList.add('on'); } };
} else { mic.style.display='none'; }

// ===== 常驻唤醒（前端 Web Audio VAD，零服务端麦克风依赖）=====
// 思路：用 AudioContext 实时算麦克风能量(RMS)，超阈值即认为「在说话」，
// 自动拉起 Web Speech 识别；识别完再回到监听。形成「说话即唤醒」的常驻循环。
// 这是 0.3 秒级唤醒的浏览器侧实现（无需服务端有声卡）。
const wakeBtn=document.getElementById('wake');
let wakeOn=false, wakeStream=null, wakeRAF=null, wakeCtx=null, wakeAnalyser=null;
function wakeVAD(){
  if(!wakeOn||!wakeAnalyser) return;
  const buf=new Uint8Array(wakeAnalyser.frequencyBinCount);
  wakeAnalyser.getByteTimeDomainData(buf);
  let sum=0; for(let i=0;i<buf.length;i++){ const v=(buf[i]-128)/128; sum+=v*v; }
  const rms=Math.sqrt(sum/buf.length);
  if(rms>0.045 && rec && !rec.recording){ try{ rec.start(); }catch(e){} }
  wakeRAF=requestAnimationFrame(wakeVAD);
}
wakeBtn.onclick=async()=>{
  if(wakeOn){
    wakeOn=false; wakeBtn.classList.remove('on');
    if(wakeRAF) cancelAnimationFrame(wakeRAF);
    if(wakeStream){ wakeStream.getTracks().forEach(t=>t.stop()); wakeStream=null; }
    if(rec&&rec.recording){ try{rec.stop();}catch(e){} }
    moodLine.textContent='状态：常驻聆听已关';
    return;
  }
  if(!rec){ alert('当前浏览器不支持语音识别，无法常驻聆听'); return; }
  try{
    wakeStream=await navigator.mediaDevices.getUserMedia({audio:true});
    wakeCtx=new (window.AudioContext||window.webkitAudioContext)();
    const src=wakeCtx.createMediaStreamSource(wakeStream);
    wakeAnalyser=wakeCtx.createAnalyser(); wakeAnalyser.fftSize=512;
    src.connect(wakeAnalyser);
    wakeOn=true; wakeBtn.classList.add('on');
    moodLine.textContent='状态：常驻聆听中…（说话即唤醒）';
    wakeVAD();
  }catch(e){ alert('无法访问麦克风：'+e); }
};

// ===== 人设设置面板（谁用谁自己设）=====
const gearBtn=document.getElementById('gear');
const setModal=document.getElementById('settingsModal');
const pMsg=document.getElementById('personaMsg');
const USER_ID='default';
function openSettings(){
  gearBtn.classList.add('on');
  setModal.classList.add('show');
  pMsg.textContent='';
  fetch('/api/companion/'+USER_ID+'/persona').then(r=>r.json()).then(d=>{
    const p=d.persona||{};
    document.getElementById('pName').value=p.name||'';
    document.getElementById('pAvatar').value=p.avatar||'';
    document.getElementById('pTone').value=p.tone||'';
    document.getElementById('pPersona').value=p.persona||'';
    document.getElementById('pBody').value=p.body_prompt||'';
    document.getElementById('pVoice').value=p.tts_voice||'';
    document.getElementById('pCatch').value=p.catchphrase||'';
    document.getElementById('pGreet').value=p.greeting||'';
  }).catch(e=>{ pMsg.style.color='#f99'; pMsg.textContent='载入人设失败：'+e; });
}
function closeSettings(){ setModal.classList.remove('show'); gearBtn.classList.remove('on'); }
gearBtn.onclick=()=>{ if(setModal.classList.contains('show')) closeSettings(); else openSettings(); };
document.getElementById('closeSettings').onclick=closeSettings;
document.getElementById('resetPersona').onclick=()=>{
  fetch('/api/companion/'+USER_ID+'/persona',{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({__reset__:true})}).then(r=>r.json()).then(d=>{
    if(d.ok){ pMsg.style.color='#6f6'; pMsg.textContent='已恢复默认人设，刷新首页生效。'; openSettings(); }
    else { pMsg.style.color='#f99'; pMsg.textContent='恢复失败：'+(d.error||''); }
  });
};
document.getElementById('savePersona').onclick=()=>{
  const patch={
    name:document.getElementById('pName').value.trim(),
    avatar:document.getElementById('pAvatar').value.trim(),
    tone:document.getElementById('pTone').value.trim(),
    persona:document.getElementById('pPersona').value.trim(),
    body_prompt:document.getElementById('pBody').value.trim(),
    tts_voice:document.getElementById('pVoice').value.trim(),
    catchphrase:document.getElementById('pCatch').value.trim(),
    greeting:document.getElementById('pGreet').value.trim(),
  };
  // 空字段不覆盖（保持现有值）
  for(const k of Object.keys(patch)) if(!patch[k]) delete patch[k];
  fetch('/api/companion/'+USER_ID+'/persona',{method:'PUT',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(patch)}).then(r=>r.json()).then(d=>{
    if(d.ok){
      pMsg.style.color='#6f6'; pMsg.textContent='✅ 人设已保存并热重载';
      // 立即更新 HUD
      const nm=document.querySelector('#hud .nm');
      if(nm && d.persona){ nm.textContent=(d.persona.avatar||'🌟')+' '+(d.persona.name||'伙伴'); }
    } else { pMsg.style.color='#f99'; pMsg.textContent='保存失败：'+(d.error||''); }
  }).catch(e=>{ pMsg.style.color='#f99'; pMsg.textContent='保存失败：'+e; });
};

// 欢迎语
bubble.textContent=__GREET__; bubble.classList.add('show');
</script>
</body>
</html>"""
    return (page
            .replace("__NAME__", _esc(name))
            .replace("__PERSONA__", _esc(persona))
            .replace("__AVATAR__", _esc(avatar))
            .replace("__MOOD__", mood)
            .replace("__GREET__", json.dumps(greet, ensure_ascii=False))
            .replace("__SCENE_SCRIPT__", scene_script))


def _extract_scene_script(body_html: str) -> str:
    """从 ThreejsAdapter 产出的整页里，抽取 <script type="module"> 场景块。"""
    m = re.search(r'<script type="module">.*?</script>', body_html, re.S)
    return m.group(0) if m else ""


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def get_companion_view(user_id: str = "default") -> dict:
    return _companion_view(Companion.load(user_id))
