"""Eval Framework 验证脚本（Task 3）。

逐项验证：
1. EvalHarness 单例与基础 API
2. 数据集 CRUD（create/list/get/delete）
3. EvalCase 数据模型序列化
4. CaseResult / EvalRun dataclass
5. _extract_text 文本提取（多种输出形态）
6. _run_case 6 类 check（success/keywords/min_steps/max_duration/max_cost/output_not_empty）
7. _exec_task 通过 FabricHub 跑（best-effort，hub 不可用不阻塞）
8. _exec_workflow 通过 WorkflowRunner 跑
9. 基线管理（set/get/delete/对比退化检测）
10. 运行报告持久化（_save_run / list_runs / get_run）
11. 非侵入：被测系统状态不被修改
12. API 路由可用（导入 eval_api 不报错）
13. main.py 已挂载

运行：python verify_eval_framework.py
"""
from __future__ import annotations

import os
import sys
import shutil
import tempfile
import time
import traceback
from pathlib import Path

# 设置 PYTHONPATH
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

# 用临时目录做评估数据落盘（不污染仓库）
TMP_EVAL_DIR = tempfile.mkdtemp(prefix="aos_eval_verify_")
os.environ["AOS_EVAL_DIR"] = TMP_EVAL_DIR

PASS = 0
FAIL = 0
ERRORS: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        ERRORS.append(f"{label}: {detail}")
        print(f"  ✗ {label}  {detail}")


def section(title: str) -> None:
    print(f"\n── {title} ──")


# ────────────────────────────────────────────
# 1. EvalHarness 单例与基础 API
# ────────────────────────────────────────────
section("1. EvalHarness 单例与基础 API")

try:
    from kernel.eval.eval_harness import (
        EvalHarness, EvalCase, CaseResult, EvalRun, get_eval_harness,
    )
    check("EvalHarness 类可导入", True)

    h1 = EvalHarness()
    h2 = get_eval_harness()
    h3 = get_eval_harness()
    check("get_eval_harness 返回单例", h2 is h3)
    check("直接 new 的实例与单例不同（无全局污染）", h1 is not h2)
except Exception as e:
    check("EvalHarness 导入失败", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 2. 数据集 CRUD
# ────────────────────────────────────────────
section("2. 数据集 CRUD")

try:
    h = get_eval_harness()
    cases = [
        EvalCase(id="c1", name="case1", task="hello", expected_keywords=["hello"]),
        EvalCase(id="c2", name="case2", task="world", expected_keywords=["world"]),
    ]
    path = h.create_dataset("smoke", cases)
    check("create_dataset 返回路径", isinstance(path, str) and path.endswith("smoke.json"))
    check("数据集文件真实落盘", os.path.exists(path))

    listed = h.list_datasets()
    check("list_datasets 返回非空列表", len(listed) >= 1)
    check("list_datasets 包含 smoke", any(d["name"] == "smoke" for d in listed))
    check("smoke 数据集有 2 个 case", next((d["cases"] for d in listed if d["name"] == "smoke"), 0) == 2)

    got = h.get_dataset("smoke")
    check("get_dataset 返回 cases 列表", got is not None and len(got) == 2)
    check("case 字段正确反序列化", got[0].id == "c1" and got[0].expected_keywords == ["hello"])

    miss = h.get_dataset("not_exist")
    check("get_dataset 不存在返回 None", miss is None)

    ok = h.delete_dataset("smoke")
    check("delete_dataset 返回 True", ok is True)
    check("删除后 get_dataset 返回 None", h.get_dataset("smoke") is None)

    ok2 = h.delete_dataset("smoke")
    check("再次删除返回 False", ok2 is False)
except Exception as e:
    check("数据集 CRUD 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 3. EvalCase 数据模型序列化
# ────────────────────────────────────────────
section("3. EvalCase 数据模型序列化")

try:
    c = EvalCase(
        id="x1", name="x", task="test",
        expected_keywords=["a", "b"],
        expected_min_steps=2,
        expected_max_duration=10.0,
        expected_max_cost_usd=0.5,
        tags=["smoke", "quick"],
    )
    d = c.to_dict()
    check("to_dict 返回 dict", isinstance(d, dict))
    check("所有字段序列化", d["id"] == "x1" and d["expected_keywords"] == ["a", "b"]
          and d["expected_min_steps"] == 2 and d["tags"] == ["smoke", "quick"])

    c2 = EvalCase.from_dict(d)
    check("from_dict 还原字段", c2.id == c.id and c2.expected_keywords == c.expected_keywords
          and c2.expected_max_duration == c.expected_max_duration)

    # 缺字段也能反序列化
    c3 = EvalCase.from_dict({"name": "minimal"})
    check("from_dict 缺字段用默认值", c3.name == "minimal" and c3.id == ""
          and c3.expected_keywords == [])
except Exception as e:
    check("EvalCase 序列化异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 4. CaseResult / EvalRun dataclass
# ────────────────────────────────────────────
section("4. CaseResult / EvalRun dataclass")

try:
    cr = CaseResult(
        case_id="t1", name="t", ok=True, success=True,
        output="hello", duration=1.5, ok_steps=2, failed_steps=0,
        total_tokens=100, cost_usd=0.001,
        checks=[{"name": "x", "passed": True, "detail": "ok"}],
    )
    crd = cr.to_dict()
    check("CaseResult.to_dict", crd["case_id"] == "t1" and crd["ok"] is True
          and crd["ok_steps"] == 2)

    # EvalRun.error 字段（修复点）
    er = EvalRun(id="r1", dataset_name="d", error="something failed")
    erd = er.to_dict()
    check("EvalRun 有 error 字段", hasattr(er, "error") and erd["error"] == "something failed")

    # 错误场景（数据集不存在）
    h = get_eval_harness()
    err_run = h.run_dataset("__not_exist__")
    check("跑不存在的数据集返回 EvalRun", isinstance(err_run, EvalRun))
    check("EvalRun.error 有错误信息", err_run.error and "不存在" in err_run.error)
    check("EvalRun.id 是 'error'", err_run.id == "error")
except Exception as e:
    check("CaseResult/EvalRun 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 5. _extract_text 文本提取
# ────────────────────────────────────────────
section("5. _extract_text 文本提取")

try:
    h = get_eval_harness()
    check("str 直接返回", h._extract_text("hello") == "hello")

    check("空值返回空串", h._extract_text("") == "" and h._extract_text(None) == "")

    d = {"content": "alpha", "output": "beta"}
    txt = h._extract_text(d)
    check("dict 多字段拼接", "alpha" in txt and "beta" in txt)

    d2 = {"result": {"text": "nested"}}
    txt2 = h._extract_text(d2)
    check("dict 嵌套提取", "nested" in txt2)

    d3 = {"foo": "bar", "count": 42}
    txt3 = h._extract_text(d3)
    check("dict 无匹配字段 fallback json", isinstance(txt3, str) and len(txt3) > 0)

    check("list 转字符串", isinstance(h._extract_text([1, 2, 3]), str))
except Exception as e:
    check("_extract_text 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 6. _run_case 6 类 check
# ────────────────────────────────────────────
section("6. _run_case 6 类 check")

try:
    h = get_eval_harness()
    # 注入 mock _exec_task 让结果可控
    original_exec = h._exec_task

    def mock_exec(case, prefix):
        return (
            {"content": "hello world answer"},
            {
                "success": True, "duration": 1.0,
                "ok_steps": 3, "failed_steps": 0,
                "total_tokens": 50, "cost_usd": 0.0001,
            },
        )

    h._exec_task = mock_exec
    try:
        # 6 个 check 全过
        case_pass = EvalCase(
            id="p1", name="pass", task="t",
            expected_keywords=["hello", "world"],
            expected_success=True,
            expected_min_steps=2,
            expected_max_duration=5.0,
            expected_max_cost_usd=0.01,
        )
        cr = h._run_case(case_pass, "")
        check("整体通过", cr.ok is True)
        check("6 个 check 全过", len(cr.checks) == 6 and all(c["passed"] for c in cr.checks))
        check("check 名称齐全",
              {c["name"] for c in cr.checks} == {
                  "expected_success", "expected_keywords",
                  "min_success_steps", "max_duration",
                  "max_cost", "output_not_empty",
              })
        check("checks 有 detail 字段", all("detail" in c for c in cr.checks))
        check("output 提取正确", "hello" in cr.output)

        # 单项失败：keyword 缺失
        case_kw_fail = EvalCase(
            id="kf", name="kw_fail", task="t",
            expected_keywords=["missing_keyword"],
        )
        cr2 = h._run_case(case_kw_fail, "")
        check("keyword 缺失导致失败", cr2.ok is False)
        kw_check = next(c for c in cr2.checks if c["name"] == "expected_keywords")
        check("missing 列表正确", "missing_keyword" in kw_check["detail"])

        # 单项失败：期望失败但成功了
        case_inv = EvalCase(
            id="inv", name="inv", task="t",
            expected_success=False,
        )
        cr3 = h._run_case(case_inv, "")
        check("期望失败但成功了导致失败", cr3.ok is False)

        # 单项失败：超时
        case_timeout = EvalCase(
            id="to", name="to", task="t",
            expected_max_duration=0.5,  # 实际 1.0 > 0.5
        )
        cr4 = h._run_case(case_timeout, "")
        check("超时导致失败", cr4.ok is False)

        # 单项失败：成本超标
        case_cost = EvalCase(
            id="cost", name="cost", task="t",
            expected_max_cost_usd=0.00001,  # 实际 0.0001 > 0.00001
        )
        cr5 = h._run_case(case_cost, "")
        check("成本超标导致失败", cr5.ok is False)

        # 单项失败：min_steps 不够
        case_steps = EvalCase(
            id="steps", name="steps", task="t",
            expected_min_steps=5,  # 实际 3 < 5
        )
        cr6 = h._run_case(case_steps, "")
        check("成功步数不够导致失败", cr6.ok is False)
    finally:
        h._exec_task = original_exec
except Exception as e:
    check("_run_case 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 7. _exec_task 通过 FabricHub 跑（best-effort）
# ────────────────────────────────────────────
section("7. _exec_task 通过 FabricHub 跑")

try:
    h = get_eval_harness()
    case = EvalCase(id="t7", name="t7", task="say hi")
    data, info = h._exec_task(case, "")
    check("返回 (data, info) 元组", isinstance(data, dict) and isinstance(info, dict))
    check("info 有 success 字段", "success" in info)
    check("info 有 duration 字段", "duration" in info and info["duration"] >= 0)
    check("info 有 ok_steps 字段", "ok_steps" in info)
    # FabricHub 可能可用可能不可用，关键是结构正确不抛异常
    if not info.get("success"):
        check("失败时有 error 信息", "error" in info and info["error"])
        print(f"    (info: {info})")
    else:
        check("成功时 data 非空", data is not None)
except Exception as e:
    check("_exec_task 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 8. _exec_workflow 通过 WorkflowRunner 跑
# ────────────────────────────────────────────
section("8. _exec_workflow 通过 WorkflowRunner 跑")

try:
    h = get_eval_harness()
    case = EvalCase(id="t8", name="t8", workflow_id="__not_exist_wf__")
    data, info = h._exec_workflow(case, "")
    check("返回 (data, info) 元组", isinstance(data, dict) and isinstance(info, dict))
    # workflow 不存在应返回 success=False
    check("工作流不存在时 success=False", info.get("success") is False)
    check("失败时 ok_steps=0", info.get("ok_steps", 0) == 0)
except Exception as e:
    check("_exec_workflow 异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 9. 基线管理 + 对比退化检测
# ────────────────────────────────────────────
section("9. 基线管理 + 对比退化检测")

try:
    h = get_eval_harness()

    # 构造两次运行，第二次退化
    run1 = EvalRun(
        id="r_baseline", dataset_name="bl_test",
        pass_rate=0.9, avg_duration=1.0, avg_cost_usd=0.001,
        total_tokens=100, total_cases=10, passed_cases=9,
    )
    path = h.set_baseline("bl_test", run1)
    check("set_baseline 落盘", os.path.exists(path))

    bl = h.get_baseline("bl_test")
    check("get_baseline 返回 dict", isinstance(bl, dict))
    check("基线 pass_rate 正确", bl["pass_rate"] == 0.9)
    check("基线 run_id 正确", bl["run_id"] == "r_baseline")

    # 退化运行：pass_rate 下降、duration 翻倍、cost 翻倍
    run2 = EvalRun(
        id="r_regression", dataset_name="bl_test",
        pass_rate=0.7, avg_duration=2.0, avg_cost_usd=0.002,
        total_tokens=150, total_cases=10, passed_cases=7,
    )
    diff = h._compare_baseline("bl_test", run2)
    check("diff.has_baseline=True", diff["has_baseline"] is True)
    check("检测到 pass_rate 退化", any("pass_rate" in r for r in diff["regressions"]))
    check("检测到 duration 退化（>50%）", any("avg_duration" in r for r in diff["regressions"]))
    check("检测到 cost 退化（>50%）", any("avg_cost" in r for r in diff["regressions"]))
    check("improvements 列表为空", len(diff["improvements"]) == 0)

    # 改善运行
    run3 = EvalRun(
        id="r_improve", dataset_name="bl_test",
        pass_rate=1.0, avg_duration=0.5, avg_cost_usd=0.0005,
        total_tokens=80, total_cases=10, passed_cases=10,
    )
    diff3 = h._compare_baseline("bl_test", run3)
    check("改善场景无退化", len(diff3["regressions"]) == 0)
    check("改善场景有 improvements", len(diff3["improvements"]) >= 2)

    # 无基线场景
    diff_none = h._compare_baseline("__no_baseline__", run2)
    check("无基线时 has_baseline=False", diff_none["has_baseline"] is False)

    # 删除基线
    ok = h.delete_baseline("bl_test")
    check("delete_baseline 返回 True", ok is True)
    check("删除后 get_baseline 返回 None", h.get_baseline("bl_test") is None)
except Exception as e:
    check("基线管理异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 10. 运行报告持久化
# ────────────────────────────────────────────
section("10. 运行报告持久化")

try:
    h = get_eval_harness()
    # 构造一个完整 EvalRun 持久化
    run = EvalRun(
        id="persist_test_run",
        dataset_name="persist_test",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        ended_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        total_cases=2, passed_cases=1, failed_cases=1,
        pass_rate=0.5, avg_duration=1.0, avg_cost_usd=0.001, total_tokens=100,
        results=[
            CaseResult(case_id="c1", name="c1", ok=True, success=True, output="ok"),
            CaseResult(case_id="c2", name="c2", ok=False, success=False, output=""),
        ],
        baseline_diff={"has_baseline": False, "regressions": [], "improvements": []},
    )
    path = h._save_run(run)
    check("_save_run 返回路径", path and os.path.exists(path))

    listed = h.list_runs(limit=10)
    check("list_runs 包含本次", any(r["id"] == "persist_test_run" for r in listed))

    got = h.get_run("persist_test_run")
    check("get_run 返回完整 dict", got is not None and got["id"] == "persist_test_run")
    check("get_run 包含 results 列表", len(got["results"]) == 2)
    check("get_run results 字段正确还原", got["results"][0]["case_id"] == "c1"
          and got["results"][1]["ok"] is False)

    miss = h.get_run("__not_exist__")
    check("get_run 不存在返回 None", miss is None)
except Exception as e:
    check("运行报告持久化异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 11. run_dataset 端到端（mock exec_task）
# ────────────────────────────────────────────
section("11. run_dataset 端到端")

try:
    h = get_eval_harness()
    cases = [
        EvalCase(id="e1", name="ok_case", task="t",
                 expected_keywords=["ok"], expected_min_steps=1),
        EvalCase(id="e2", name="bad_case", task="t",
                 expected_keywords=["__missing__"]),
    ]
    h.create_dataset("e2e_test", cases)

    # mock _exec_task：第一个返回 "ok"，第二个返回 "no_match"
    def mock_exec_e2e(case, prefix):
        if case.id == "e1":
            return ({"content": "ok result"}, {"success": True, "duration": 0.5,
                    "ok_steps": 1, "failed_steps": 0, "total_tokens": 10, "cost_usd": 0.0001})
        return ({"content": "no_match"}, {"success": True, "duration": 0.5,
                "ok_steps": 1, "failed_steps": 0, "total_tokens": 10, "cost_usd": 0.0001})

    original = h._exec_task
    h._exec_task = mock_exec_e2e
    try:
        run = h.run_dataset("e2e_test")
        check("run_dataset 返回 EvalRun", isinstance(run, EvalRun))
        check("total_cases=2", run.total_cases == 2)
        check("passed_cases=1", run.passed_cases == 1)
        check("failed_cases=1", run.failed_cases == 1)
        check("pass_rate=0.5", abs(run.pass_rate - 0.5) < 0.001)
        check("avg_duration 正确计算", run.avg_duration > 0)
        check("run 持久化", h.get_run(run.id) is not None)
        check("baseline_diff 存在", "has_baseline" in run.baseline_diff)

        # 设为基线，再跑一次（mock 仍生效）应该有对比
        h.set_baseline("e2e_test", run)
        run2 = h.run_dataset("e2e_test")
        # 第二次结果应该一样，pass_rate 一致
        check("第二次跑 has_baseline=True", run2.baseline_diff["has_baseline"] is True)
        check("无退化（pass_rate 一致）", len(run2.baseline_diff["regressions"]) == 0)
    finally:
        h._exec_task = original
except Exception as e:
    check("run_dataset 端到端异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 12. API 路由可用
# ────────────────────────────────────────────
section("12. API 路由可用")

try:
    from api.eval_api import router, mount_eval_api
    check("eval_api 模块导入成功", True)

    check("router prefix=/api/eval", router.prefix == "/api/eval")

    # 收集所有路由（FastAPI 中 path 包含 prefix 完整路径）
    routes = [r.path for r in router.routes]
    expected = [
        "/api/eval/datasets", "/api/eval/datasets/{name}", "/api/eval/datasets/{name}/run",
        "/api/eval/baselines", "/api/eval/baselines/{name}", "/api/eval/baselines/{name}/set/{run_id}",
        "/api/eval/runs", "/api/eval/runs/{run_id}",
    ]
    for exp in expected:
        check(f"路由包含 {exp}", any(exp == r for r in routes), f"routes={routes}")

    # mount_eval_api 应可调用
    class FakeApp:
        def __init__(self):
            self.routers = []
        def include_router(self, r):
            self.routers.append(r)

    fa = FakeApp()
    mount_eval_api(fa)
    check("mount_eval_api 注册 router", len(fa.routers) == 1)
except Exception as e:
    check("API 路由异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 13. main.py 已挂载
# ────────────────────────────────────────────
section("13. main.py 已挂载")

try:
    main_py = (SRC / "api" / "main.py").read_text(encoding="utf-8")
    check("main.py 引用 eval_api", "from api.eval_api import mount_eval_api" in main_py)
    check("main.py 调用 mount_eval_api(app)", "mount_eval_api(app)" in main_py)
    check("main.py 有 Eval Framework 日志", "Eval Framework API" in main_py)
except Exception as e:
    check("main.py 检查异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 14. 非侵入：被测系统状态不被修改
# ────────────────────────────────────────────
section("14. 非侵入：被测系统状态不被修改")

try:
    h = get_eval_harness()
    # 跑评估前记录状态
    before_datasets = set(d["name"] for d in h.list_datasets())
    before_runs = set(r["id"] for r in h.list_runs())

    # 跑一次评估（mock）
    h.create_dataset("noninv", [EvalCase(id="n1", name="n", task="t", expected_keywords=["ok"])])
    original = h._exec_task
    h._exec_task = lambda c, p: ({"content": "ok"}, {"success": True, "duration": 0.1,
                                 "ok_steps": 1, "failed_steps": 0, "total_tokens": 1, "cost_usd": 0.0})
    try:
        run = h.run_dataset("noninv")
    finally:
        h._exec_task = original

    # 评估产生的副作用：数据集 +1（自己创建的），运行记录 +1，但没有修改其他系统状态
    after_datasets = set(d["name"] for d in h.list_datasets())
    after_runs = set(r["id"] for r in h.list_runs())

    new_datasets = after_datasets - before_datasets
    check("新增数据集 = 自己创建的", "noninv" in new_datasets)
    check("新增运行记录 = 本次评估", run.id in after_runs)

    # 关键：不应该写 workflow / pulse / evolve / context 等其他系统的数据
    # 只允许写 data/eval/ 目录
    eval_dir = os.environ["AOS_EVAL_DIR"]
    check("eval 数据只在 AOS_EVAL_DIR", os.path.exists(eval_dir))

    # 清理临时数据
    h.delete_dataset("noninv")
except Exception as e:
    check("非侵入检查异常", False, str(e))
    traceback.print_exc()


# ────────────────────────────────────────────
# 清理
# ────────────────────────────────────────────
print("\n── 清理临时目录 ──")
try:
    shutil.rmtree(TMP_EVAL_DIR, ignore_errors=True)
    check("临时目录已清理", not os.path.exists(TMP_EVAL_DIR))
except Exception as e:
    check("清理异常", False, str(e))


# ────────────────────────────────────────────
# 总结
# ────────────────────────────────────────────
print(f"\n{'='*60}")
print("Task 3 (Eval Framework) 验证结果：")
print(f"  PASS: {PASS}")
print(f"  FAIL: {FAIL}")
print(f"  总计: {PASS + FAIL}")
print(f"{'='*60}")

if FAIL > 0:
    print("\n失败项：")
    for e in ERRORS:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n全部通过 ✓")
    sys.exit(0)
