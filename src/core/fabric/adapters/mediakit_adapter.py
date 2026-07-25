"""火山引擎音视频后期处理适配器（media.process）—— 单创OS 内容营销岗的可插拔芯粒。

本适配器是 AOS 与 `@volcengine/mediakit-cli` 之间的薄胶水层（opt-in 借鉴）。
Mediakit CLI 是字节跳动火山引擎出品的音视频处理命令行，提供 100+ 音视频
原子能力（剪辑17/音频2/图像AI 5/视频AI 14/通用2），支持 `--local`/`--cloud`
双模态逐命令切换；云端模式需火山 API Key（`mediakit-cli init` 配置或 env）。

与 AOS 现有生成式媒体能力正交：
- MEDIA_VIDEO（ComfyUI/MediaGen/VideoMaker）= 文生视频/图生视频（「生成」）
- MEDIA_PROCESS（本适配器）= 后期处理流水线（「加工已有素材」：剪辑/特效/音频/视频AI增强）

设计原则（对齐 AOS 九大理念 + MEMORY § XII 铁律）：
- **opt-in 默认关闭**：必须 `AOS_MEDIAKIT_ENABLED=1` 才参与路由；未开启时
  `health()=False`，彻底不污染主流程（与 img2threejs 同样的内核保护语法）。
- **薄胶水**：AOS 不重造音视频引擎，只标准化「怎么调 mediakit-cli」。真正的
  子命令（如 `video cut`/`image enhance`）由调用方（内容营销岗 loop / host
  agent）按官方能力声明传入，adapter 不臆造 CLI 接口。
- **诚实降级（理念6）**：CLI 未装 / 未开 / 云端缺 Key 时 `invoke()` 返回
  `ok=False` 并说明原因，绝不谎报处理成功。
- **引擎无关 + 可插拔**：Node/npx 缺失即降级；便于未来换本地 ffmpeg 流水线。

能力契约（invoke payload）：
- action:   "run"（默认）执行一条 mediakit 子命令；"help" 探测 CLI 能力清单
- mode:     "local"（默认，免 Key）或 "cloud"（需火山 API Key）；可被
            env `AOS_MEDIAKIT_MODE` 覆盖
- command:  子命令及其参数（str 或 list[str]），如 ["video","cut","--input","a.mp4"]
- api_key:  云端模式密钥（可选，默认读 env `VOLCENGINE_API_KEY`/`MEDIAKIT_API_KEY`）
- timeout:  命令超时秒数（默认 600）
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)

# opt-in 开关：默认关闭，需显式置 1 才参与路由（MEMORY § XII 只借鉴+opt-in）
_ENV_ENABLED = "AOS_MEDIAKIT_ENABLED"
_ENV_MODE = "AOS_MEDIAKIT_MODE"
_ENV_API_KEY = ("VOLCENGINE_API_KEY", "MEDIAKIT_API_KEY", "ARK_API_KEY")


def _enabled() -> bool:
    return os.environ.get(_ENV_ENABLED, "0").strip() == "1"


def _default_mode() -> str:
    return os.environ.get(_ENV_MODE, "local").strip().lower() or "local"


def _api_key_present() -> bool:
    return any(os.environ.get(k, "").strip() for k in _ENV_API_KEY)


class MediakitAdapter(BaseAgentAdapter):
    """火山引擎音视频后期处理适配器：把 media.process 调用翻译为 `npx mediakit-cli`。

    Mediakit CLI 经 npx 调用；opt-in（默认关闭）。CLI 未装/未开/云端缺 Key 时
    诚实失败（ok=False），由调用方降级（内容营销岗回退本地 VideoMaker/ffmpeg）。
    """

    @property
    def engine_id(self) -> str:
        return "mediakit"

    # ── 可注入的子类钩子：便于离线测试时替换 subprocess 调用 ──
    def _run(self, cmd: list, timeout: int, env: dict | None) -> subprocess.CompletedProcess:
        """执行 mediakit 命令。默认走真实 subprocess；测试可 monkeypatch。"""
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env,
        )

    def advertise_capabilities(self) -> list:
        return [Capability.MEDIA_PROCESS.value]

    def tier(self) -> str:
        # 云端火山引擎音视频后期（质量优、有成本、依赖 Key）→ 中档
        return "medium"

    def health(self) -> bool:
        """opt-in 开关 + npx 探测。

        - 未开 AOS_MEDIAKIT_ENABLED → False（不污染主流程）
        - npx 不可用 → False（CLI 跑不起来）
        注：npx 存在 ≠ 已装 mediakit-cli；真正的「能否执行」在 invoke 时判定。
        """
        if not _enabled():
            return False
        return shutil.which("npx") is not None

    def health_detail(self) -> dict:
        npx = shutil.which("npx")
        enabled = _enabled()
        mode = _default_mode()
        key_ok = _api_key_present()
        available = enabled and (npx is not None)
        notes = []
        if not enabled:
            notes.append("opt-in 未开启：设置 AOS_MEDIAKIT_ENABLED=1 后参与路由。")
        if npx is None:
            notes.append("未检测到 npx（需 Node>=18）：npm install -g @volcengine/mediakit-cli 前请先装 Node。")
        if mode == "cloud" and not key_ok:
            notes.append("云端模式需火山 API Key：配置 VOLCENGINE_API_KEY 或 mediakit-cli init。")
        return {
            "engine_id": self.engine_id,
            "available": available,
            "enabled": enabled,
            "npx_path": npx,
            "default_mode": mode,
            "api_key_present": key_ok,
            "advertises": self.advertise_capabilities(),
            "note": " ".join(notes) or "就绪：可经 npx mediakit-cli 执行音视频后期处理。",
        }

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self.health():
            detail = self.health_detail()
            return InvokeResult(
                ok=False,
                error=("Mediakit CLI 不可用：" + detail["note"]).strip(),
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        action = (payload.get("action") or "run").strip().lower()

        # 解析运行模态：payload > env 默认
        mode = (payload.get("mode") or _default_mode()).strip().lower()
        if mode not in ("local", "cloud"):
            mode = "local"

        # 云端模式必须持有 API Key（诚实失败，不静默降级到无 Key 云端）
        api_key = payload.get("api_key") or next(
            (os.environ.get(k, "") for k in _ENV_API_KEY if os.environ.get(k, "").strip()),
            "",
        )
        if mode == "cloud" and not api_key.strip():
            return InvokeResult(
                ok=False,
                error="云端模式需火山 API Key：配置 VOLCENGINE_API_KEY / MEDIAKIT_API_KEY，或改用 mode=local。",
                engine_id=self.engine_id,
            )

        # 组装子进程环境变量（Key 只进 env，绝不进 argv，避免泄露到日志/进程列表）
        run_env = dict(os.environ)
        if api_key.strip():
            run_env["VOLCENGINE_API_KEY"] = api_key.strip()

        if action == "help":
            cmd = ["npx", "mediakit-cli", "--help"]
            sub_desc = "能力清单探测"
        elif action == "run":
            command = payload.get("command")
            if isinstance(command, str):
                command = command.split()
            if not isinstance(command, (list, tuple)) or not command:
                return InvokeResult(
                    ok=False,
                    error="缺少 command（mediakit 子命令，如 ['video','cut','--input','a.mp4']）",
                    engine_id=self.engine_id,
                )
            cmd = ["npx", "mediakit-cli", mode, *list(command)]
            sub_desc = " ".join(str(c) for c in command)
        else:
            return InvokeResult(
                ok=False,
                error=f"不支持的 action: {action}（仅支持 run / help）",
                engine_id=self.engine_id,
            )

        timeout = int(payload.get("timeout") or 600)
        try:
            proc = self._run(cmd, timeout=timeout, env=run_env)
        except subprocess.TimeoutExpired:
            return InvokeResult(ok=False, error=f"命令超时（>{timeout}s）: {' '.join(cmd)}",
                                engine_id=self.engine_id)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"命令执行异常: {e}", engine_id=self.engine_id)

        if proc.returncode != 0:
            stderr = (proc.stderr or "")[:2000]
            return InvokeResult(
                ok=False,
                error=f"mediakit-cli 执行失败（exit={proc.returncode}）: {stderr}",
                engine_id=self.engine_id,
            )

        return InvokeResult(
            ok=True,
            data={
                "mode": mode,
                "action": action,
                "command": sub_desc,
                "stdout": (proc.stdout or "")[:8000],
                "returncode": proc.returncode,
            },
            engine_id=self.engine_id,
        )
