"""多智能体代码团队 —— 借鉴华为云码道(CodeArts) Agent Team 的协作生成思路。

把「自然语言需求 → 可运行代码」拆成四个角色协作（对应 CodeArts 的代码智能体团队）：

  - architect（架构师）：把需求拆成文件级任务（plan）
  - coder（工程师）：  为每个文件生成代码（code）
  - reviewer（审查员）：对每个文件跑三分质量门（gate）
  - executor（执行器）：在隔离临时目录里真实跑 pytest / py_compile 验证（execute）

设计原则（与 AOS 现有「ag2→ollama→heuristic 降级」一致）：
  - LLM 生成是可注入的（llm_generate(prompt, role)）；未注入时走 heuristic 生成器，
    保证无 GPU / 无 key 的沙箱环境仍能产出**可运行、过质量门**的代码，真跑验证不编。
  - 质量门复用 kernel.compliance.QualityGate（安全/质量/合规 × ERROR/WARN/INFO）。
  - 执行验证默认用隔离临时目录 + 真实 subprocess（与 code_execution_adapter 的沙箱
    隔离理念一致，但适配多文件测试场景）。

这不是把 CodeArts 整体搬进来（那违反「零付费 / 主权在己」），而是借其「多角色协作写代码」
的编排形态，落到 AOS 已有的 SubAgentRegistry / OrchestrationChiplet / compliance 之上。
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional

from kernel.compliance import QualityGate

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Heuristic 代码生成器（无 LLM 时的降级，保证可运行、过质量门）
# ═══════════════════════════════════════════════════════════════════

def _mod_calculator(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 四则运算。

由 AOS 多智能体代码团队（heuristic 模式）生成的安全脚手架。
"""


def add(left: float, right: float) -> float:
    """返回两数之和。"""
    return left + right


def subtract(left: float, right: float) -> float:
    """返回两数之差。"""
    return left - right


def multiply(left: float, right: float) -> float:
    """返回两数之积。"""
    return left * right


def divide(left: float, right: float) -> float:
    """返回两数之商；除零安全返回 0.0。"""
    if right == 0:
        return 0.0
    return left / right
'''


def _test_calculator(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import add, subtract, multiply, divide


def test_add():
    assert add(1, 2) == 3


def test_subtract():
    assert subtract(5, 3) == 2


def test_multiply():
    assert multiply(2, 4) == 8


def test_divide():
    assert divide(8, 2) == 4


def test_divide_zero():
    assert divide(1, 0) == 0.0
'''


def _mod_sort(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 排序工具。"""
from typing import List


def bubble_sort(items: List[float]) -> List[float]:
    """返回升序排列的新列表（不修改入参）。"""
    result = list(items)
    for i in range(len(result)):
        for j in range(len(result) - i - 1):
            if result[j] > result[j + 1]:
                result[j], result[j + 1] = result[j + 1], result[j]
    return result
'''


def _test_sort(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import bubble_sort


def test_sort_basic():
    assert bubble_sort([3, 1, 2]) == [1, 2, 3]


def test_sort_empty():
    assert bubble_sort([]) == []
'''


def _mod_fib(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 斐波那契。"""
def fibonacci(n: int) -> int:
    """返回第 n 项斐波那契数（n 从 0 开始）。"""
    if n < 0:
        return 0
    if n < 2:
        return n
    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr
'''


def _test_fib(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import fibonacci


def test_fib():
    assert [fibonacci(i) for i in range(7)] == [0, 1, 1, 2, 3, 5, 8]
'''


def _mod_greet(base: str, requirement: str = "") -> str:
    return f'''"""{base} 模块 —— 问候。"""
def greet(name: str) -> str:
    """返回对 name 的问候语。"""
    return f"Hello, {{name}}!"
'''


def _test_greet(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import greet


def test_greet():
    assert greet("AOS") == "Hello, AOS!"
'''


def _mod_default(base: str, requirement: str = "") -> str:
    summary = requirement.strip().replace('"', "'")[:80] or "未提供需求描述"
    return f'''"""{base} 模块。

需求：{summary}

由 AOS 多智能体代码团队（heuristic 模式）生成的通用脚手架。
"""


def main() -> str:
    """返回模块标识。"""
    return "{base}"


if __name__ == "__main__":
    print(main())
'''


def _test_default(base: str, requirement: str = "") -> str:
    return f'''"""{base} 的测试。"""
from {base} import main


def test_main():
    assert main() == "{base}"
'''


def _resolve_kind(requirement: str) -> Optional[str]:
    """从需求识别「模板种类」（语言无关）：calculator/sort/fibonacci/greet 或 None。"""
    r = requirement.lower()
    if any(k in r for k in ("calculator", "计算器", "加减乘除", "四则")):
        return "calculator"
    if any(k in r for k in ("sort", "排序", "冒泡")):
        return "sort"
    if any(k in r for k in ("fib", "斐波那契", "fibonacci")):
        return "fibonacci"
    if any(k in r for k in ("hello", "greet", "问候", "打招呼")):
        return "greet"
    return None


# 种类 → 基名（跨语言一致的文件基名）。
_KIND_BASE = {
    "calculator": "calculator",
    "sort": "sorter",
    "fibonacci": "fibonacci",
    "greet": "greeter",
}


# ═══════════════════════════════════════════════════════════════════
# Heuristic 代码生成器（JavaScript / Node，CommonJS + node:test）
# ═══════════════════════════════════════════════════════════════════

def _mod_js_calculator(base: str, requirement: str = "") -> str:
    return '''"use strict";
// SPDX-License-Identifier: MIT
// AOS 多智能体代码团队（heuristic 模式）生成的安全脚手架 —— 四则运算。
function add(a, b) { return a + b; }
function subtract(a, b) { return a - b; }
function multiply(a, b) { return a * b; }
function divide(a, b) { return b === 0 ? 0 : a / b; }
module.exports = { add, subtract, multiply, divide };
'''


def _test_js_calculator(base: str, requirement: str = "") -> str:
    return f'''"use strict";
const test = require("node:test");
const assert = require("node:assert");
const {{ add, subtract, multiply, divide }} = require("./{base}.js");

test("add", () => assert.strictEqual(add(1, 2), 3));
test("subtract", () => assert.strictEqual(subtract(5, 3), 2));
test("multiply", () => assert.strictEqual(multiply(2, 4), 8));
test("divide", () => assert.strictEqual(divide(8, 2), 4));
test("divide_zero", () => assert.strictEqual(divide(1, 0), 0));
'''


def _mod_js_sort(base: str, requirement: str = "") -> str:
    return '''"use strict";
// SPDX-License-Identifier: MIT
function bubbleSort(items) {
  const result = items.slice();
  for (let i = 0; i < result.length; i++) {
    for (let j = 0; j < result.length - i - 1; j++) {
      if (result[j] > result[j + 1]) {
        const tmp = result[j];
        result[j] = result[j + 1];
        result[j + 1] = tmp;
      }
    }
  }
  return result;
}
module.exports = { bubbleSort };
'''


def _test_js_sort(base: str, requirement: str = "") -> str:
    return f'''"use strict";
const test = require("node:test");
const assert = require("node:assert");
const {{ bubbleSort }} = require("./{base}.js");

test("sort_basic", () => assert.deepStrictEqual(bubbleSort([3, 1, 2]), [1, 2, 3]));
test("sort_empty", () => assert.deepStrictEqual(bubbleSort([]), []));
'''


def _mod_js_fib(base: str, requirement: str = "") -> str:
    return '''"use strict";
// SPDX-License-Identifier: MIT
function fibonacci(n) {
  if (n < 0) return 0;
  if (n < 2) return n;
  let prev = 0, curr = 1;
  for (let i = 2; i <= n; i++) {
    const next = prev + curr;
    prev = curr;
    curr = next;
  }
  return curr;
}
module.exports = { fibonacci };
'''


def _test_js_fib(base: str, requirement: str = "") -> str:
    return f'''"use strict";
const test = require("node:test");
const assert = require("node:assert");
const {{ fibonacci }} = require("./{base}.js");

test("fibonacci", () => {{
  const got = [0, 1, 2, 3, 4, 5, 6].map(fibonacci);
  assert.deepStrictEqual(got, [0, 1, 1, 2, 3, 5, 8]);
}});
'''


def _mod_js_greet(base: str, requirement: str = "") -> str:
    return '''"use strict";
// SPDX-License-Identifier: MIT
function greet(name) { return `Hello, ${name}!`; }
module.exports = { greet };
'''


def _test_js_greet(base: str, requirement: str = "") -> str:
    return f'''"use strict";
const test = require("node:test");
const assert = require("node:assert");
const {{ greet }} = require("./{base}.js");

test("greet", () => assert.strictEqual(greet("AOS"), "Hello, AOS!"));
'''


def _mod_js_default(base: str, requirement: str = "") -> str:
    summary = " ".join((requirement or "").split()).replace("`", "'")[:80] or "未提供需求描述"
    return f'''"use strict";
// SPDX-License-Identifier: MIT
// 需求：{summary}
function main() {{ return "{base}"; }}
module.exports = {{ main }};
if (require.main === module) {{ console.log(main()); }}
'''


def _test_js_default(base: str, requirement: str = "") -> str:
    return f'''"use strict";
const test = require("node:test");
const assert = require("node:assert");
const {{ main }} = require("./{base}.js");

test("main", () => assert.strictEqual(main(), "{base}"));
'''


# ═══════════════════════════════════════════════════════════════════
# 真实 LLM 桥接器（复用 AOS 已有的 LiteLLMAdapter，即推理平面）
# ═══════════════════════════════════════════════════════════════════

def _strip_code_fence(text: str) -> str:
    """清洗 LLM 常返回的 ```python ... ``` 围栏，只留纯代码。"""
    s = (text or "").strip()
    if s.startswith("```"):
        lines = s.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)
    return s


def make_llm_generate(model: Optional[str] = None) -> Optional[Callable[[str, str], str]]:
    """构建真实 LLM 桥接器，复用 AOS 推理平面 LiteLLMAdapter（不造新组件）。

    返回 None = 通道不可用 → 调用方（CodeTeamOrchestrator）自动回落 heuristic，
    行为与未接电时完全一致（零破坏）。仅当显式开启 AOS_CODETEAM_LLM=1 且
    LiteLLMAdapter 可导入时，才注入真实 LLM。

    真实调用失败（无 key / 网络错 / 模型不可用）时，LiteLLMAdapter 优雅返回
    ok=False；此处回落为空字符串，code_team 的 executor 会真实跑失败 →
    result.ok=False（诚实暴露，不编「成功」）。
    """
    if os.getenv("AOS_CODETEAM_LLM") != "1":
        return None
    try:
        from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
        from core.fabric.adapter import InvokeRequest
        from core.fabric.capability import Capability
    except Exception:  # 模块不可导入（极少见）→ 不接电
        logger.warning("code_team: LiteLLMAdapter 不可导入，回落 heuristic")
        return None
    model_id = model or os.getenv("LITELLM_DEFAULT_MODEL", "zhipu/glm-4-flash")
    adapter = LiteLLMAdapter()

    def _gen(prompt: str, role: str) -> str:
        try:
            res = adapter.invoke(InvokeRequest(
                capability=Capability.LLM_GATEWAY,
                payload={"model": model_id,
                         "messages": [{"role": "user", "content": prompt}]},
            ))
            content = (res.data or {}).get("content", "") if res.ok else ""
            return _strip_code_fence(content or "")
        except Exception as e:  # 真实调用崩 → 诚实回落空（executor 会真跑失败）
            logger.warning("code_team: 真实 LLM 调用失败，回落空: %s", e)
            return ""

    return _gen


# ═══════════════════════════════════════════════════════════════════
# 默认执行器 —— 隔离临时目录 + 真实 pytest / py_compile
# ═══════════════════════════════════════════════════════════════════

def _default_executor(files: Dict[str, str]) -> Dict[str, Any]:
    """把 {文件名: 代码} 写到隔离临时目录，真实跑编译 + 测试。

    返回 {ok, stage, output, error}。优先跑 test_* 文件（pytest），
    否则跑主模块的 __main__。
    """
    import os
    d = tempfile.mkdtemp(prefix="aos_codeteam_")
    try:
        for name, code in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(code)

        # 1) 语法/编译校验
        for name in files:
            r = subprocess.run(
                [sys.executable, "-m", "py_compile", os.path.join(d, name)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return {"ok": False, "stage": "compile",
                        "error": f"{name} 编译失败", "detail": r.stderr}

        # 2) 测试 / 运行
        test_files = [n for n in files if n.startswith("test_")]
        if test_files:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", d],
                capture_output=True, text=True, timeout=60,
            )
            return {
                "ok": r.returncode == 0, "stage": "test",
                "output": r.stdout[-1600:], "error": r.stderr[-1600:],
            }
        mains = [n for n in files if not n.startswith("test_")]
        if mains:
            r = subprocess.run(
                [sys.executable, mains[0]], cwd=d,
                capture_output=True, text=True, timeout=30,
            )
            return {"ok": r.returncode == 0, "stage": "run",
                    "output": r.stdout, "error": r.stderr}
        return {"ok": True, "stage": "none", "output": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "exception", "error": str(e)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


def _js_executor(files: Dict[str, str]) -> Dict[str, Any]:
    """把 {文件名: 代码} 写到隔离临时目录，真实跑 node --check + node --test。

    诚实回落：node 运行时不可用时返回 ok=False / stage=runtime_unavailable，
    绝不伪造「通过」。测试用 `node --test <文件名...>` 且 cwd=临时目录（按文件名跑，
    避免目录模式下子进程 cwd 错位导致 require('./x.js') 找不到模块）。
    """
    if shutil.which("node") is None:
        return {"ok": False, "stage": "runtime_unavailable",
                "error": "node 运行时不可用，无法执行 JavaScript（诚实回落，不伪造通过）"}
    d = tempfile.mkdtemp(prefix="aos_codeteam_js_")
    try:
        for name, code in files.items():
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.write(code)

        # 1) 语法校验：node --check
        for name in files:
            if not name.endswith(".js"):
                continue
            r = subprocess.run(
                ["node", "--check", os.path.join(d, name)],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                return {"ok": False, "stage": "compile",
                        "error": f"{name} 语法检查失败", "detail": r.stderr[-1600:]}

        # 2) 测试 / 运行
        test_files = [n for n in files if n.endswith(".test.js")]
        if test_files:
            r = subprocess.run(
                ["node", "--test", *test_files], cwd=d,
                capture_output=True, text=True, timeout=60,
            )
            return {
                "ok": r.returncode == 0, "stage": "test",
                "output": r.stdout[-1600:], "error": r.stderr[-1600:],
            }
        mains = [n for n in files if not n.endswith(".test.js")]
        if mains:
            r = subprocess.run(
                ["node", mains[0]], cwd=d,
                capture_output=True, text=True, timeout=30,
            )
            return {"ok": r.returncode == 0, "stage": "run",
                    "output": r.stdout, "error": r.stderr}
        return {"ok": True, "stage": "none", "output": ""}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "stage": "exception", "error": str(e)}
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# 语言注册表 —— 多语言支持的单一事实源（新增语言只在此加一项）
# ═══════════════════════════════════════════════════════════════════

_LANGS: Dict[str, Dict[str, Any]] = {
    "python": {
        "mod": lambda base: f"{base}.py",
        "test": lambda base: f"test_{base}.py",
        "gens": {
            "calculator": (_mod_calculator, _test_calculator),
            "sort": (_mod_sort, _test_sort),
            "fibonacci": (_mod_fib, _test_fib),
            "greet": (_mod_greet, _test_greet),
        },
        "default": (_mod_default, _test_default),
        "executor": _default_executor,
        "llm_hint": "Python，含 docstring",
    },
    "javascript": {
        "mod": lambda base: f"{base}.js",
        "test": lambda base: f"{base}.test.js",
        "gens": {
            "calculator": (_mod_js_calculator, _test_js_calculator),
            "sort": (_mod_js_sort, _test_js_sort),
            "fibonacci": (_mod_js_fib, _test_js_fib),
            "greet": (_mod_js_greet, _test_js_greet),
        },
        "default": (_mod_js_default, _test_js_default),
        "executor": _js_executor,
        "llm_hint": "JavaScript（CommonJS，用 module.exports 导出；测试用 node:test + node:assert）",
    },
}

_LANG_ALIASES = {
    "py": "python", "python": "python", "python3": "python",
    "js": "javascript", "javascript": "javascript",
    "node": "javascript", "nodejs": "javascript",
}


def _norm_lang(lang: str) -> str:
    """把语言名归一化（别名 → 规范名）。未知语言原样返回（由 run() 诚实处理）。"""
    key = (lang or "python").strip().lower()
    return _LANG_ALIASES.get(key, key)


def supported_languages() -> List[str]:
    """当前 code_team 支持的语言（规范名）。"""
    return sorted(_LANGS)


# ═══════════════════════════════════════════════════════════════════
# 编排器
# ═══════════════════════════════════════════════════════════════════

class CodeTeamOrchestrator:
    """多智能体代码团队编排器。

    四角色：architect（plan）/ coder（code）/ reviewer（gate）/ executor（execute）。
    llm_generate 可注入：(prompt: str, role: str) -> str；未注入走 heuristic。
    """

    ROLES = ["architect", "coder", "reviewer", "executor"]

    def __init__(self,
                 llm_generate: Optional[Callable[[str, str], str]] = None,
                 quality_gate: Optional[QualityGate] = None,
                 executor: Optional[Callable[[Dict[str, str]], Dict[str, Any]]] = None):
        self._llm = llm_generate
        self._gate = quality_gate or QualityGate()
        # 显式注入的执行器优先；否则按语言从 _LANGS 选（见 run）。None = 未注入。
        self._exec_override = executor

    # ── architect ──
    def _base_name(self, requirement: str) -> str:
        kind = _resolve_kind(requirement)
        if kind:
            return _KIND_BASE[kind]
        m = re.search(r"[a-zA-Z][a-zA-Z0-9_]+", requirement)
        base = (m.group(0) if m else "module").lower()
        return re.sub(r"[^a-z0-9_]", "_", base)[:20] or "module"

    def _plan(self, requirement: str, lang: str) -> List[str]:
        spec = _LANGS[lang]
        base = self._base_name(requirement)
        return [spec["mod"](base), spec["test"](base)]

    # ── coder ──
    def _generate(self, fname: str, requirement: str, lang: str) -> str:
        spec = _LANGS[lang]
        if self._llm is not None:
            prompt = (
                f"你是一个资深软件工程师（coder 角色）。\n"
                f"需求：{requirement}\n目标语言：{lang}（{spec['llm_hint']}）。\n"
                f"请生成文件 `{fname}` 的完整代码"
                f"（不要使用 eval/exec/os.system/child_process 等危险调用，"
                f"不要裸 except）。只返回代码本身。"
            )
            return self._llm(prompt, "coder")
        base = self._base_name(requirement)
        kind = _resolve_kind(requirement)
        mod_fn, test_fn = spec["gens"].get(kind, spec["default"])
        is_test = fname == spec["test"](base)
        return (test_fn(base, requirement) if is_test
                else mod_fn(base, requirement))

    # ── 主流程 ──
    def run(self, requirement: str, lang: str = "python") -> Dict[str, Any]:
        norm = _norm_lang(lang)
        if norm not in _LANGS:
            # 诚实回落：不支持的语言不伪造产物/通过。
            return {
                "requirement": requirement,
                "lang": norm,
                "roles": self.ROLES,
                "plan": [],
                "files": {},
                "quality": {"passed": False,
                            "note": f"不支持的语言: {lang}"},
                "execution": {"ok": False, "stage": "lang_unsupported",
                              "error": f"暂不支持语言 '{lang}'，当前支持: "
                                       f"{supported_languages()}"},
                "ok": False,
            }
        plan = self._plan(requirement, norm)
        files: Dict[str, str] = {}
        for fname in plan:
            files[fname] = self._generate(fname, requirement, norm)

        # reviewer：三分质量门
        report = self._gate.run(files)
        # executor：真实跑测试（注入的执行器优先，否则按语言选）
        exec_fn = self._exec_override or _LANGS[norm]["executor"]
        exec_res = exec_fn(files)

        return {
            "requirement": requirement,
            "lang": norm,
            "roles": self.ROLES,
            "plan": plan,
            "files": files,
            "quality": report.to_dict(),
            "execution": exec_res,
            "ok": report.passed and bool(exec_res.get("ok", False)),
        }


def run_code_team(requirement: str, lang: str = "python", **kw) -> Dict[str, Any]:
    """模块级便捷函数。"""
    return CodeTeamOrchestrator(**kw).run(requirement, lang=lang)


def to_a2ui_surface(result: Dict[str, Any]) -> Dict[str, Any]:
    """把 code_team 的 run() 结果渲染为 A2UI v0.9 surface（声明式、不执行代码）。

    返回合并 surface 字典，可直接交给 a2ui.render_html 显示。沿用 AOS 既有
    A2UIBuilder（白名单组件 + 转义渲染，跨信任边界安全）。
    """
    from core.fabric.a2ui import (A2UIBuilder, text, card, column,
                                  divider, lit, tabs)
    b = A2UIBuilder(surface_id="code-team", theme={"primaryColor": "#2a8c6a"})
    req = result.get("requirement", "")
    lang = result.get("lang", "python")
    ok = bool(result.get("ok", False))
    llm_used = bool(result.get("llm_used", False))
    b.add("title", text(lit(f"代码团队 · {lang}"), variant="h2"))
    b.add("meta", text(lit(
        f"需求：{req}  |  状态：{'✓ 通过' if ok else '✗ 失败'}  |  "
        f"生成：{'真实 LLM' if llm_used else 'heuristic 脚手架'}"),
        variant="caption"))
    b.add("rule", divider())

    # 文件：每个文件一个 Tab（卡片内含代码）
    file_tabs = []
    for fname, code in (result.get("files") or {}).items():
        cid = "file-" + fname
        b.add(cid, card(cid + "-inner"))
        b.add(cid + "-inner", text(lit(f"# {fname}\n{code}"), variant="body"))
        file_tabs.append({"title": lit(fname), "child": cid})
    if file_tabs:
        b.add("files", tabs(file_tabs))
    else:
        b.add("files", text(lit("（无生成文件）")))

    # 质量门
    quality = result.get("quality") or {}
    qparts = []
    if isinstance(quality, dict):
        qparts.append(f"passed={quality.get('passed', '?')}")
        issues = quality.get("issues") or quality.get("errors") or []
        if isinstance(issues, list):
            qparts.extend(str(i)[:120] for i in issues[:5])
    b.add("quality", text(lit("质量门：" + ("；".join(qparts) if qparts else "无报告"))))

    # 执行结果
    exec_res = result.get("execution") or {}
    ext = f"ok={exec_res.get('ok')} stage={exec_res.get('stage')}"
    if exec_res.get("error"):
        ext += f" error={exec_res.get('error')}"
    b.add("exec", text(lit("执行：" + ext)))
    if exec_res.get("output"):
        b.add("exec-out", text(lit(str(exec_res.get("output"))[:800])))

    b.add("root", column(["title", "meta", "rule", "files", "quality", "exec", "exec-out"]))
    b.root("root")
    return b.surface()


def render_code_team(result: Dict[str, Any], standalone: bool = True) -> str:
    """把 code_team 结果渲染为 A2UI 安全 HTML（结构化交付物）。"""
    from core.fabric.a2ui import render_html
    return render_html(to_a2ui_surface(result), standalone=standalone)


__all__ = [
    "CodeTeamOrchestrator",
    "run_code_team",
    "to_a2ui_surface",
    "render_code_team",
    "supported_languages",
    "make_llm_generate",
    "QualityGate",
]
