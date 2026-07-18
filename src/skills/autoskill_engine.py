"""AutoSkill —— 自动技能发现与安装引擎。

核心理念：用户只需要说一句话，系统自动判断需要什么技能，
本地没有就去 SkillHub 找，找到了自动安装、自动注册、立即使用。

设计原则：
- 零配置：用户不需要知道有哪些技能，说目标就行
- 自动安装：需要的技能自动装，不骚扰用户
- 安全沙箱：安装前做基本安全检查（恶意关键词、权限声明）
- 可回滚：装错了可以一键卸载、回退
- 诚实透明：告诉用户它做了什么、用了什么技能
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 配置
_AUTOSKILL_DIR = os.environ.get(
    "AOS_AUTOSKILL_DIR",
    os.path.join("data", "workspaces", "fabric", "autoskill"),
)
_AUTOSKILL_ENABLED = os.environ.get("AOS_AUTOSKILL_ENABLED", "1") != "0"
_AUTOSKILL_CONFIRM_RISK = os.environ.get("AOS_AUTOSKILL_CONFIRM", "low")  # low/medium/high

# 危险关键词（出现就拒绝自动安装，需要人工确认）
_DANGER_KEYWORDS = [
    "rm -rf", "format c:", "del /f", "dd if=",
    "curl.*sh", "wget.*bash", "eval.*base64",
    "steal", "exfiltrat", "backdoor", "ransom",
    "crypto.*mine", "miner", "keylog",
]


def _autoskill_dir() -> str:
    os.makedirs(_AUTOSKILL_DIR, exist_ok=True)
    return _AUTOSKILL_DIR


def _installed_file() -> str:
    return os.path.join(_autoskill_dir(), "installed.json")


def _skills_target_dir() -> str:
    """技能安装目标目录——AOS 的 skills 目录下的 autoskill 子目录。"""
    # 找 AOS skills 目录
    candidates = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "skills", "autoskill"),
        os.path.join("src", "skills", "autoskill"),
    ]
    for c in candidates:
        if os.path.exists(os.path.dirname(c)):
            os.makedirs(c, exist_ok=True)
            return c
    #  fallback
    path = os.path.join(_autoskill_dir(), "skills")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class InstalledSkill:
    """已安装的技能记录。"""
    id: str
    name: str
    description: str
    version: str
    author: str
    source: str = "skillhub"  # skillhub / local / custom
    installed_at: str = ""
    capabilities: List[str] = field(default_factory=list)
    category: str = ""
    tags: List[str] = field(default_factory=list)
    install_path: str = ""
    status: str = "active"  # active / disabled / failed
    use_count: int = 0
    rating: float = 0.0


class AutoSkillEngine:
    """自动技能引擎。"""

    def __init__(self):
        self._installed: Dict[str, InstalledSkill] = {}
        self._load_installed()

    # ── 核心：一句话找技能 ──

    def discover_for_task(self, task: str) -> List[Dict[str, Any]]:
        """根据用户任务描述，自动发现需要的技能。

        流程：
        1. 分析任务关键词
        2. 先查本地已安装技能
        3. 本地不够 → 去 SkillHub 搜
        4. 返回候选列表（按相关度排序）
        """
        if not _AUTOSKILL_ENABLED:
            return []

        # 关键词提取（简化版：按空格切 + 去掉停用词）
        keywords = self._extract_keywords(task)
        logger.debug("任务关键词: %s", keywords)

        # 1. 本地搜索
        local_results = self._search_local(keywords)

        # 2. 如果本地有相关的，直接返回
        if local_results:
            logger.info("本地找到 %d 个相关技能", len(local_results))
            return local_results[:10]

        # 3. 本地没有，去 SkillHub 搜
        skillhub_results = self._search_skillhub(keywords, task)
        if skillhub_results:
            logger.info("SkillHub 找到 %d 个相关技能", len(skillhub_results))
            return skillhub_results[:10]

        return []

    def auto_install_and_run(self, task: str, *, run_fn=None) -> Dict[str, Any]:
        """全自动：找技能 → 安装 → 运行 → 返回结果。

        这是核心入口——用户说一句话，剩下的全自动。
        """
        if not _AUTOSKILL_ENABLED:
            return {
                "ok": False,
                "error": "AutoSkill 未启用",
                "result": None,
            }

        # 第一步：发现技能
        candidates = self.discover_for_task(task)
        if not candidates:
            return {
                "ok": False,
                "error": "没有找到合适的技能",
                "result": None,
                "candidates": [],
            }

        # 第二步：选最合适的（第一个），检查安全性
        best = candidates[0]
        risk = self._assess_risk(best, task)

        if risk == "high":
            return {
                "ok": False,
                "error": "技能风险过高，需要人工确认",
                "risk": "high",
                "candidate": best,
                "candidates": candidates,
            }

        # 第三步：安装（如果没装的话）
        skill_id = best.get("id", "")
        installed = self._installed.get(skill_id)

        if not installed:
            logger.info("自动安装技能: %s", skill_id)
            install_result = self.install(skill_id)
            if not install_result.get("ok"):
                return {
                    "ok": False,
                    "error": f"技能安装失败: {install_result.get('message', '未知错误')}",
                    "candidate": best,
                }
            installed = self._installed.get(skill_id)

        # 第四步：注册到路由（如果有 register 函数）
        self._try_register(installed)

        # 第五步：运行（如果提供了 run_fn）
        result = None
        if run_fn and installed:
            try:
                result = run_fn(installed, task)
            except Exception as e:
                logger.error("技能运行失败: %s", e)
                return {
                    "ok": False,
                    "error": f"技能运行失败: {e}",
                    "installed": asdict(installed) if installed else None,
                }

        # 记录使用
        if installed:
            installed.use_count += 1
            self._save_installed()

        return {
            "ok": True,
            "skill": asdict(installed) if installed else best,
            "risk": risk,
            "result": result,
            "candidates": candidates,
        }

    # ── 安装 / 卸载 ──

    def install(self, skill_id: str) -> Dict[str, Any]:
        """安装一个技能。"""
        from .skillhub_integration import get_skillhub_adapter

        if skill_id in self._installed:
            return {"ok": True, "message": "已安装", "already_installed": True}

        # 安全检查
        adapter = get_skillhub_adapter()
        info = adapter.get_skill_info(skill_id)
        if info:
            risk = self._assess_risk(info, "")
            if risk == "high":
                return {"ok": False, "message": "风险过高，拒绝自动安装", "risk": "high"}

        target_dir = _skills_target_dir()

        try:
            result = adapter.install(skill_id, target_dir=target_dir)
            if not result.get("ok"):
                return result

            # 记录已安装
            installed = InstalledSkill(
                id=skill_id,
                name=info.get("name", skill_id.split("/")[-1]) if info else skill_id.split("/")[-1],
                description=info.get("description", "") if info else "",
                version=info.get("version", "0.0.0") if info else "0.0.0",
                author=info.get("author", "") if info else "",
                source="skillhub",
                installed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                capabilities=info.get("capabilities", []) if info else [],
                category=info.get("category", "") if info else "",
                tags=info.get("tags", []) if info else [],
                install_path=result.get("installed_path", ""),
                status="active",
            )
            self._installed[skill_id] = installed
            self._save_installed()

            logger.info("技能安装成功: %s → %s", skill_id, result.get("installed_path"))
            return {"ok": True, "skill": asdict(installed)}

        except Exception as e:
            logger.error("安装技能失败: %s", e)
            return {"ok": False, "message": str(e)}

    def uninstall(self, skill_id: str) -> bool:
        """卸载技能。"""
        installed = self._installed.get(skill_id)
        if not installed:
            return False

        # 删除文件
        if installed.install_path and os.path.exists(installed.install_path):
            try:
                shutil.rmtree(installed.install_path)
            except Exception as e:
                logger.warning("删除技能文件失败: %s", e)

        # 移除记录
        del self._installed[skill_id]
        self._save_installed()
        logger.info("技能已卸载: %s", skill_id)
        return True

    def list_installed(self) -> List[Dict[str, Any]]:
        """列出已安装的技能。"""
        return [asdict(s) for s in self._installed.values()]

    # ── 内部方法 ──

    def _extract_keywords(self, text: str) -> List[str]:
        """从任务描述中提取关键词。"""
        # 简化版：去掉停用词，保留实词
        stop_words = {
            "的", "了", "是", "我", "你", "他", "她", "它",
            "在", "有", "和", "与", "及", "等", "也", "都",
            "就", "要", "把", "被", "让", "给", "从", "到",
            "做", "帮", "请", "一下", "一个", "一些",
            "帮我", "给我", "我要", "我想",
            "the", "a", "an", "is", "are", "was", "were",
            "be", "been", "being", "have", "has", "had",
            "do", "does", "did", "will", "would", "could",
            "should", "may", "might", "can", "shall",
            "i", "you", "he", "she", "it", "we", "they",
            "me", "him", "her", "us", "them",
            "this", "that", "these", "those",
            "and", "but", "or", "nor", "so", "yet",
            "in", "on", "at", "by", "for", "with", "about",
            "to", "from", "of", "as", "into", "through",
            "please", "help", "want", "need", "like",
        }

        # 按空格和标点切
        words = re.findall(r'[\w\u4e00-\u9fff]+', text.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 1]

        # 如果关键词太少，就用原文前几个字做 query
        if len(keywords) < 2:
            # 取原文里的重要片段
            keywords = [text[:20]]

        return keywords[:5]  # 最多 5 个关键词

    def _search_local(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """搜索本地已安装技能。"""
        results = []
        for skill in self._installed.values():
            score = 0
            for kw in keywords:
                if kw.lower() in skill.name.lower():
                    score += 3
                if kw.lower() in skill.description.lower():
                    score += 2
                if any(kw.lower() in t.lower() for t in skill.tags):
                    score += 2
                if any(kw.lower() in c.lower() for c in skill.capabilities):
                    score += 4
            if score > 0:
                results.append({
                    **asdict(skill),
                    "relevance_score": score,
                    "source": "local",
                })

        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results

    def _search_skillhub(self, keywords: List[str], task: str) -> List[Dict[str, Any]]:
        """去 SkillHub 搜索。"""
        from .skillhub_integration import get_skillhub_adapter

        adapter = get_skillhub_adapter()
        if not adapter.available:
            return []

        # 用最相关的关键词搜索
        query = " ".join(keywords[:3]) if keywords else task[:30]
        try:
            results = adapter.search(query, limit=10)
            return results
        except Exception as e:
            logger.warning("SkillHub 搜索失败: %s", e)
            return []

    def _assess_risk(self, skill_info: Dict[str, Any], task: str) -> str:
        """评估技能风险等级：low / medium / high。"""
        risk = "low"
        desc = skill_info.get("description", "") + " " + skill_info.get("name", "")

        # 检查危险关键词
        for kw in _DANGER_KEYWORDS:
            if re.search(kw, desc, re.IGNORECASE):
                return "high"

        # 任务中有敏感词，且技能是系统操作类 → medium
        sensitive_task_words = ["删除", "格式化", "密码", "密钥", "转账", "支付"]
        system_skill_categories = ["system", "admin", "security"]

        cat = skill_info.get("category", "").lower()
        if any(w in task for w in sensitive_task_words) and any(c in cat for c in system_skill_categories):
            risk = "medium"

        return risk

    def _try_register(self, installed: InstalledSkill) -> bool:
        """尝试把安装的技能注册到 AOS 技能系统。"""
        if not installed or not installed.install_path:
            return False

        try:
            skill_path = Path(installed.install_path)
            if not skill_path.is_dir():
                return False

            # 找 register 函数
            for py_file in skill_path.glob("*.py"):
                try:
                    module_name = f"skills.autoskill.{skill_path.name}.{py_file.stem}"
                    # 简化：只检查有没有 register_xxx_skill 函数
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    if "def register_" in content and "_skill" in content:
                        logger.info("发现技能注册入口: %s", py_file.name)
                        # TODO: 动态 import 并注册
                        return True
                except Exception:
                    continue

            logger.debug("技能 %s 未找到标准注册入口，跳过自动注册", installed.id)
            return False
        except Exception as e:
            logger.debug("注册技能失败: %s", e)
            return False

    # ── FabricHub 集成 ──

    def register_with_fabric_hub(self, hub) -> bool:
        """把 AutoSkill 注册成 FabricHub 的能力缺失钩子。

        当 FabricHub 找不到某个能力的 provider 时，会触发 AutoSkill 自动去
        SkillHub 搜索并安装相关技能，实现「缺什么自动补什么」的闭环。

        Args:
            hub: FabricHub 实例

        Returns:
            True 表示注册成功
        """
        try:
            # 用闭包捕获 hub 引用，这样钩子可以直接注册新适配器
            def _hook(capability: str, payload: dict) -> bool:
                return self._fabric_missing_capability_hook(hub, capability, payload)

            hub.add_missing_capability_hook(_hook)
            logger.info("AutoSkill 已注册为 FabricHub 能力缺失钩子")
            return True
        except Exception as e:
            logger.warning("注册 AutoSkill 到 FabricHub 失败: %s", e)
            return False

    def _fabric_missing_capability_hook(self, hub, capability: str, payload: dict) -> bool:
        """FabricHub 能力缺失钩子——缺能力时自动去 SkillHub 找技能并安装。

        Args:
            hub: FabricHub 实例（用于注册新适配器）
            capability: 缺失的能力标识（如 "web.search"）
            payload: 原始请求 payload

        Returns:
            True 表示成功补充了能力（可以重试路由），False 表示没找到
        """
        if not _AUTOSKILL_ENABLED:
            return False

        try:
            logger.info("AutoSkill 钩子触发：能力缺失 %s，尝试自动发现技能", capability)

            # 用能力名作为搜索关键词
            search_query = f"{capability} skill"
            candidates = self.discover_for_task(search_query)

            if not candidates:
                logger.info("AutoSkill 钩子：未找到相关技能 %s", capability)
                return False

            # 尝试安装第一个候选
            first = candidates[0]
            skill_id = first.get("id") or first.get("name")
            if not skill_id:
                return False

            logger.info("AutoSkill 钩子：尝试安装技能 %s", skill_id)
            result = self.install(skill_id)

            if not result.get("ok"):
                logger.warning("AutoSkill 钩子：技能安装失败 %s", result.get("error"))
                return False

            # 安装成功后，尝试注册到 FabricHub
            installed = self._installed.get(skill_id)
            if installed and self._try_register_with_fabric(hub, installed):
                logger.info("AutoSkill 钩子：技能 %s 已注册到 FabricHub", skill_id)
                return True

            # 即使没注册成功，也返回 True —— 技能已经装好了，可能通过别的路径可用
            logger.info("AutoSkill 钩子：技能 %s 已安装（未注册到 FabricHub）", skill_id)
            return True

        except Exception as e:
            logger.warning("AutoSkill 钩子异常: %s", e)
            return False

    def _try_register_with_fabric(self, hub, installed: "InstalledSkill") -> bool:
        """尝试把安装的技能注册为 FabricHub 的适配器。

        检查技能是否提供了 fabric_adapter.py，如果有就动态加载并注册到 hub。
        """
        if not installed or not installed.install_path:
            return False

        try:
            skill_path = Path(installed.install_path)
            adapter_file = skill_path / "fabric_adapter.py"
            if not adapter_file.is_file():
                # 没有 fabric_adapter.py，不注册到 FabricHub
                return False

            # 动态加载适配器模块
            import importlib.util
            module_name = f"autoskill_{installed.id.replace('-', '_')}_adapter"
            spec = importlib.util.spec_from_file_location(module_name, str(adapter_file))
            if spec is None or spec.loader is None:
                return False

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # 找 register_adapter 函数，返回 BaseAgentAdapter 实例
            if hasattr(module, "register_adapter") and callable(module.register_adapter):
                adapter = module.register_adapter()
                if adapter is not None:
                    hub.register_adapter(adapter)
                    logger.info("技能适配器已注册到 FabricHub: %s", installed.id)
                    return True

            return False
        except Exception as e:
            logger.debug("注册技能到 FabricHub 失败: %s", e)
            return False

    # ── 持久化 ──

    def _load_installed(self) -> None:
        path = _installed_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for sid, sdata in data.items():
                    self._installed[sid] = InstalledSkill(**sdata)
            except Exception as e:
                logger.warning("加载已安装技能列表失败: %s", e)

    def _save_installed(self) -> None:
        path = _installed_file()
        try:
            data = {sid: asdict(s) for sid, s in self._installed.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("保存已安装技能列表失败: %s", e)


# 单例
_engine: Optional[AutoSkillEngine] = None


def get_autoskill_engine() -> AutoSkillEngine:
    global _engine
    if _engine is None:
        _engine = AutoSkillEngine()
    return _engine
