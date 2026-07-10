"""内核 SkillBus 桥接：把现有 Skills (43+) 注册进 MCP 技能总线。

所有 AOS skills 位于 src/skills/，继承 Skill 基类（skills/base.py）。
本模块把它们扫描、包装为 SkillSpec，批量注册进内核的 SkillBus。

设计约束（物种思维）：
- 零依赖：本模块只依赖 kernel ABCs，import skills 是延迟的（只在 register_all 时）
- 向后兼容：skill 内部 import get_brain 等不受影响，本桥接只是多一条注册通道
- 可替换：换技能总线协议（MCP→新协议），本桥接的 register_all 签名不变
"""

from __future__ import annotations

from typing import Any, Dict, List

from kernel.interfaces import SkillBus
from kernel.types import SkillResult, SkillSpec


class SkillsBridge:
    """把 AOS skills 注册进内核 SkillBus 的桥接层。

    用法：
        from kernel.wiring import build_default_kernel
        from kernel.skills_bridge import SkillsBridge
        kernel = build_default_kernel()
        bridge = SkillsBridge(kernel._skill_bus)
        bridge.register_all()  # 批量注册 43+ skills
    """

    def __init__(self, bus: SkillBus) -> None:
        self._bus = bus
        self._skill_modules: Dict[str, str] = {}  # skill_id -> module_name

    def scan(self) -> List[SkillSpec]:
        """扫描 src/skills/ 目录，返回所有可注册 SkillSpec（不注册，仅扫描）。

        只读取模块的类级属性（NAME/DESCRIPTION/TAGS/CATEGORY），不实例化。
        """
        specs: List[SkillSpec] = []
        try:
            import importlib
            import pkgutil
            import skills as skills_pkg  # 延迟导入
        except ImportError:
            return specs

        # 遍历 skills 包下所有模块
        for _, module_name, is_pkg in pkgutil.iter_modules(
            skills_pkg.__path__, skills_pkg.__name__ + "."
        ):
            if is_pkg:
                continue
            # 跳过内部模块
            if module_name.endswith((".base", ".cli_helpers", ".adapter")):
                continue

            try:
                mod = importlib.import_module(module_name)
            except Exception:
                continue

            # 查找继承 Skill 的类
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if not isinstance(obj, type):
                    continue
                name = getattr(obj, "NAME", None)
                desc = getattr(obj, "DESCRIPTION", None)
                if name is None or desc is None:
                    continue
                if name in ("base_skill", "Skill"):
                    continue

                specs.append(SkillSpec(
                    skill_id=name,
                    description=desc,
                    arguments={
                        "context": {
                            "type": "object",
                            "description": f"context dict passed to {name}.execute()",
                        }
                    },
                ))
                self._skill_modules[name] = module_name

        # 去重：同名 skill 只保留第一次发现
        seen: set = set()
        deduped: List[SkillSpec] = []
        for s in specs:
            if s.skill_id not in seen:
                seen.add(s.skill_id)
                deduped.append(s)
        return sorted(deduped, key=lambda s: s.skill_id)

    def register_all(self) -> int:
        """扫描并注册所有 AOS skills 进 SkillBus。返回注册数。"""
        specs = self.scan()
        count = 0
        for spec in specs:
            try:
                self._bus.register_skill(spec)
                count += 1
            except Exception:
                pass
        return count

    def call_skill(self, skill_id: str, params: Dict[str, Any]) -> SkillResult:
        """通过 SkillBus 调用一个已注册的 skill。

        底层：懒加载 skill 类 → 实例化 → 调用 execute(context)。
        """
        module_name = self._skill_modules.get(skill_id)
        if module_name is None:
            return SkillResult(ok=False, error=f"unknown skill: {skill_id}")

        try:
            import importlib
            mod = importlib.import_module(module_name)
            cls = _find_skill_class(mod, skill_id)
            if cls is None:
                return SkillResult(ok=False,
                                   error=f"skill class not found in {module_name}")
            instance = cls()
            context = params.get("context", {}) if params else {}
            result = instance.execute(context)
            return SkillResult(ok=True, data={"result": result})
        except Exception as exc:
            return SkillResult(ok=False, error=str(exc))

    def list_skills(self) -> List[SkillSpec]:
        """列出当前已注册的 skills summary。"""
        results: List[SkillSpec] = []
        for info in self._bus.discover_skills():
            results.append(SkillSpec(
                skill_id=info.skill_id,
                description=info.description,
                arguments=info.arguments,
            ))
        return results

    @property
    def bus(self) -> SkillBus:
        return self._bus


def _find_skill_class(module, skill_name: str) -> type | None:
    """在模块中查找 NAME == skill_name 的 Skill 子类。"""
    for attr in dir(module):
        obj = getattr(module, attr)
        if isinstance(obj, type) and getattr(obj, "NAME", None) == skill_name:
            return obj
    return None


def register_skills_to_system(system) -> int:
    """便捷函数：把 skills 注册进已构建的 AOSSystem。

    用于 build_default_system() 的扩展点。
    """
    bridge = SkillsBridge(system.mcp_bus)
    return bridge.register_all()


__all__ = ["SkillsBridge", "register_skills_to_system"]
