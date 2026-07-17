"""Tool-Call Repair 层（借鉴 DeepSeek Reasonix 的 Tool-Call Repair 思路）。

问题背景：LLM 返回的工具调用（OpenAI Function Calling 风格）经常「能用但脏」——
参数 JSON 不合法（单引号/尾逗号/缺引号）、类型错位（数字给成字符串）、
必填缺失、枚举越界、夹带未知字段。这些不该直接判失败，应当就地诊断并修复后重试。

设计原则（对齐 AOS 理念）：
- 诚实+量化（理念6）：每次修复都留下 RepairReport（修了什么、哪类错误），不偷偷改。
- best-effort、零副作用：只做「安全修复」；激进修复（如推断补必填）默认第二轮才
  启用，且明确标注为推断填充，绝不伪造工具意图。
- 不引外部依赖：纯标准库（json/ast/re）。
- 复用现有栈：接入 ToolExecutor（工具执行中枢），对所有经执行器的工具调用生效。

主入口：
- ToolCallRepair.repair(raw_args, schema, aggressiveness=0) -> RepairResult
- execute_with_repair(executor, tool_name, raw_args, schema=None, max_rounds=3) -> dict
"""
from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# 错误分类（量化可观测，可映射进 failure_monitor）
CLASS_OK = "ok"
CLASS_JSON_DECODE = "json_decode"
CLASS_TYPE = "type_mismatch"
CLASS_MISSING_REQUIRED = "missing_required"
CLASS_ENUM = "enum_out_of_range"
CLASS_UNKNOWN = "unknown_field"
CLASS_RUNTIME = "runtime_error"


@dataclass
class RepairStep:
    action: str          # 修复动作类别
    field: str           # 涉及字段（全局级用 "__root__"）
    before: Any
    after: Any
    note: str = ""


@dataclass
class RepairReport:
    ok: bool = False
    rounds: int = 0
    classification: str = CLASS_OK
    steps: List[RepairStep] = field(default_factory=list)
    final_error: Optional[str] = None

    def add(self, action: str, field: str, before: Any, after: Any, note: str = "") -> None:
        self.steps.append(RepairStep(action, field, before, after, note))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "rounds": self.rounds,
            "classification": self.classification,
            "steps": [
                {"action": s.action, "field": s.field,
                 "before": s.before, "after": s.after, "note": s.note}
                for s in self.steps
            ],
            "final_error": self.final_error,
        }


class UnrepairableToolCall(Exception):
    """修复层已尽力但仍无法让工具调用可执行。"""

    def __init__(self, message: str, report: Optional[RepairReport] = None):
        super().__init__(message)
        self.report = report


def _json_type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _coerce_scalar(value: Any, target: str) -> Any:
    """把标量值强制转为目标 JSON 类型；无法转则抛 ValueError。"""
    if target == "string":
        if isinstance(value, (dict, list)):
            raise ValueError("cannot coerce container to string")
        return str(value)
    if target == "integer":
        if isinstance(value, bool):
            raise ValueError("bool is not int")
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            s = value.strip()
            if re.fullmatch(r"[+-]?\d+", s):
                return int(s)
            if re.fullmatch(r"[+-]?\d+\.0+", s):
                return int(float(s))
            raise ValueError(f"not an integer: {value!r}")
        raise ValueError(f"cannot coerce {type(value).__name__} to integer")
    if target == "number":
        if isinstance(value, bool):
            raise ValueError("bool is not number")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            return float(value.strip())
        raise ValueError(f"cannot coerce {type(value).__name__} to number")
    if target == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "y"):
                return True
            if s in ("false", "0", "no", "n", ""):
                return False
            raise ValueError(f"not a boolean: {value!r}")
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise ValueError(f"cannot coerce {type(value).__name__} to boolean")
    raise ValueError(f"unsupported target type {target}")


def _parse_args(raw: Union[str, dict, Any], *, aggressive: bool,
                report: Optional[RepairReport] = None) -> dict:
    """把 LLM 返回的原始参数解析成 dict。aggressive=True 时启用更激进的
    容错修复（单引号/尾逗号/抽取最外层花括号/Python 字面量）。修复动作记进 report。"""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        try:
            return dict(raw)
        except Exception:
            raise UnrepairableToolCall(
                f"参数既不是 dict 也不是 str: {type(raw).__name__}")

    text = raw.strip()
    if not text:
        return {}

    # 1) 严格 JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    if not aggressive:
        raise UnrepairableToolCall(f"JSON 解析失败（非激进模式）: {text[:120]}")

    # 2) 激进修复
    fixed = text
    m = re.search(r"\{.*\}", fixed, re.DOTALL)
    if m:
        fixed = m.group(0)
    fixed = _smart_quote(fixed)
    fixed = re.sub(r",\s*([}\]])", r"\1", fixed)
    fixed = re.sub(r"([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:", r'\1"\2":', fixed)
    try:
        parsed = json.loads(fixed)
        if report is not None:
            report.add(CLASS_JSON_DECODE, "__root__", text, parsed,
                       "激进容错修复JSON（单引号/尾逗号/缺引号）")
        return parsed
    except json.JSONDecodeError:
        pass
    try:
        val = ast.literal_eval(text)
        if isinstance(val, dict):
            if report is not None:
                report.add(CLASS_JSON_DECODE, "__root__", text, val,
                           "Python字面量兜底解析")
            return val
    except Exception:
        pass
    raise UnrepairableToolCall(f"JSON 解析失败（激进模式仍失败）: {text[:120]}")


def _smart_quote(s: str) -> str:
    """把单引号风格的 JSON 转成双引号。仅在整体不含双引号时安全替换。"""
    if '"' in s:
        return s
    out = []
    in_str = False
    quote = None
    for c in s:
        if not in_str:
            if c in ("'", '"'):
                in_str = True
                quote = c
                out.append('"')
            else:
                out.append(c)
        else:
            if c == quote:
                in_str = False
                quote = None
                out.append('"')
            else:
                out.append(c)
    return "".join(out)


def _edit_distance(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            cur = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = cur
    return dp[n]


def _nearest_enum(value: Any, enum: List[Any]) -> Any:
    """枚举越界时选最近似的合法值：字符串 → 编辑距离最小；否则取第一个。"""
    for e in enum:
        if e == value:
            return e
    if isinstance(value, str) and any(isinstance(e, str) for e in enum):
        best, best_d = None, None
        for e in enum:
            if not isinstance(e, str):
                continue
            d = _edit_distance(value, e)
            if best_d is None or d < best_d:
                best_d, best = d, e
        if best is not None:
            return best
    return enum[0]


def _default_for_type(t: str) -> Any:
    return {"string": "", "integer": 0, "number": 0.0,
            "boolean": False, "array": [], "object": {}}.get(t, None)


@dataclass
class RepairResult:
    fixed: Optional[dict]
    report: "RepairReport"


class ToolCallRepair:
    """工具调用修复器：诊断 + 就地修复 LLM 返回的工具参数。"""

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds

    def repair(self, raw_args: Union[str, dict], schema: Optional[dict],
               *, aggressiveness: int = 0) -> RepairResult:
        """解析并修复参数。返回 RepairResult（含 fixed dict 与 report）。

        aggressiveness:
          0 = 仅安全修复（JSON 严格解析、类型强制、枚举裁剪、未知字段剔除、
              必填用 schema default）
          1 = 额外启用激进 JSON 容错 + 推断补必填（无 default 时用类型零值，
              明确标注为推断填充）
        """
        report = RepairReport()
        aggressive_json = aggressiveness >= 1
        try:
            args = _parse_args(raw_args, aggressive=aggressive_json, report=report)
        except UnrepairableToolCall as e:
            report.classification = CLASS_JSON_DECODE
            report.final_error = str(e)
            return RepairResult(None, report)

        if not isinstance(args, dict):
            report.classification = CLASS_JSON_DECODE
            report.final_error = f"解析结果不是 dict: {type(args).__name__}"
            return RepairResult(None, report)

        schema = schema or {}
        props = schema.get("properties", {}) or {}
        required = schema.get("required", []) or []

        fixed = dict(args)
        # 1) 未知字段剔除
        if props:
            for k in list(fixed.keys()):
                if k not in props:
                    report.add(CLASS_UNKNOWN, k, fixed[k], None, "剔除未知字段")
                    del fixed[k]

        # 2) 按 schema 修复每个已知字段
        for name, spec in props.items():
            if not isinstance(spec, dict):
                continue
            target_type = spec.get("type")
            if name in fixed:
                val = fixed[name]
                if target_type and target_type in _TYPE_MAP:
                    cur_type = _json_type_of(val)
                    if cur_type != target_type and not (
                            target_type == "number" and cur_type == "integer"):
                        try:
                            new_val = _coerce_scalar(val, target_type)
                            if new_val != val:
                                report.add(CLASS_TYPE, name, val, new_val,
                                           f"{cur_type}→{target_type}")
                                fixed[name] = new_val
                        except ValueError:
                            pass
                enum = spec.get("enum")
                if enum and fixed[name] not in enum:
                    new_val = _nearest_enum(fixed[name], enum)
                    report.add(CLASS_ENUM, name, fixed[name], new_val,
                               "枚举越界→最近合法值")
                    fixed[name] = new_val
            else:
                if name in required:
                    if "default" in spec:
                        new_val = spec["default"]
                        report.add(CLASS_MISSING_REQUIRED, name, None, new_val,
                                   "必填缺失→用 schema default")
                        fixed[name] = new_val
                    elif aggressiveness >= 1:
                        t = target_type or "string"
                        new_val = _default_for_type(t)
                        report.add(CLASS_MISSING_REQUIRED, name, None, new_val,
                                   "必填缺失→推断填充(类型零值)")
                        fixed[name] = new_val

        if not report.steps and required:
            missing = [r for r in required if r not in fixed]
            if missing:
                report.classification = CLASS_MISSING_REQUIRED
                report.final_error = f"必填缺失且无 default: {missing}"

        return RepairResult(fixed, report)

    def execute_with_repair(self, executor, tool_name: str,
                            raw_args: Union[str, dict],
                            schema: Optional[dict] = None,
                            *, max_rounds: Optional[int] = None) -> Dict[str, Any]:
        return execute_with_repair(executor, tool_name, raw_args, schema=schema,
                                   max_rounds=max_rounds or self.max_rounds)


def execute_with_repair(executor, tool_name: str, raw_args: Union[str, dict],
                        schema: Optional[dict] = None,
                        *, max_rounds: int = 3) -> Dict[str, Any]:
    """用修复层包裹一次工具执行：解析→修复→执行，失败则逐步升级 aggressiveness 重试。

    返回 dict：
      success=True  → {success, result, repair(RepairReport.to_dict())}
      success=False → {success, error, repair(RepairReport.to_dict())}
    """
    repairer = ToolCallRepair(max_rounds=max_rounds)
    last_report: Optional[RepairReport] = None
    for rnd in range(max_rounds):
        aggressiveness = 1 if rnd >= 1 else 0
        result = repairer.repair(raw_args, schema, aggressiveness=aggressiveness)
        last_report = result.report
        if result.fixed is None:
            if rnd == max_rounds - 1:
                return {"success": False,
                        "error": result.report.final_error or "参数不可解析",
                        "repair": result.report.to_dict()}
            continue
        # 用不带修复的底层执行，避免 execute_tool→execute_with_repair→execute_tool 递归
        if hasattr(executor, "_execute_raw"):
            res = executor._execute_raw(tool_name, result.fixed)
        else:
            res = executor.execute_tool(tool_name, result.fixed)
        if res.get("success"):
            result.report.ok = True
            result.report.rounds = rnd + 1
            result.report.classification = CLASS_OK
            return {"success": True, "result": res.get("result"),
                    "repair": result.report.to_dict()}
        last_err = res.get("error", "未知错误")
        # 解析+修复已尽力（无可修复步骤）仍运行时失败 → 非参数问题，停止
        if not result.report.steps and rnd >= 1:
            result.report.final_error = last_err
            result.report.classification = CLASS_RUNTIME
            return {"success": False, "error": last_err,
                    "repair": result.report.to_dict()}
        result.report.final_error = last_err
    if last_report is not None:
        last_report.final_error = last_report.final_error or "修复轮次耗尽"
        return {"success": False,
                "error": last_report.final_error,
                "repair": last_report.to_dict()}
    return {"success": False, "error": "修复轮次耗尽",
            "repair": RepairReport().to_dict()}
