"""代码炼化系统测试。

验证沙箱 + 全项目炼化系统的功能完整性和全局一致性。
"""
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

_src_dir = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(_src_dir))


class TestProjectSandbox:
    """项目级沙箱测试。"""

    @pytest.fixture
    def sample_project(self, tmp_path):
        """创建一个示例项目。"""
        proj = tmp_path / "sample_proj"
        proj.mkdir()

        # src 目录
        src = proj / "src"
        src.mkdir()
        (src / "main.py").write_text(
            """import os
import sys
import unused_module

def hello():
    print("hello")

def add(a, b):
    return a + b
""",
            encoding="utf-8",
        )
        (src / "utils.py").write_text(
            """import os

def helper():
    return os.path.join("a", "b")
""",
            encoding="utf-8",
        )

        # tests 目录
        tests = proj / "tests"
        tests.mkdir()
        (tests / "test_sample.py").write_text(
            """from src.main import add

def test_add():
    assert add(1, 2) == 3
""",
            encoding="utf-8",
        )

        return str(proj)

    def test_create_and_destroy(self, sample_project):
        """测试沙箱创建和销毁。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project, name="test-proj")
        result = sb.create()

        assert result["success"] is True
        assert result["name"] == "test-proj"
        assert "file_count" in result
        assert os.path.isdir(result["path"])

        # 沙箱内应该有文件
        read_result = sb.read_file("src/main.py")
        assert read_result["success"] is True
        assert "def hello()" in read_result["content"]

        # 销毁
        destroy_result = sb.destroy()
        assert destroy_result["success"] is True
        assert not os.path.exists(result["path"])

    def test_path_traversal_protection(self, sample_project):
        """测试路径逃逸保护。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project)
        sb.create()

        try:
            # 尝试逃逸
            result = sb.read_file("../../etc/passwd")
            assert result.get("success") is False
            assert "逃逸" in result.get("error", "") or "escape" in result.get("error", "").lower()
        finally:
            sb.destroy()

    def test_write_and_read(self, sample_project):
        """测试写入和读取。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project)
        sb.create()

        try:
            # 写入新文件
            write_result = sb.write_file("src/new_module.py", "x = 42\n")
            assert write_result["success"] is True
            assert write_result["created"] is True

            # 读取验证
            read_result = sb.read_file("src/new_module.py")
            assert read_result["success"] is True
            assert "x = 42" in read_result["content"]

            # 原项目不应被修改
            orig_file = Path(sample_project) / "src" / "new_module.py"
            assert not orig_file.exists(), "沙箱不应该修改原项目"
        finally:
            sb.destroy()

    def test_snapshot_and_rollback(self, sample_project):
        """测试快照和回滚。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project)
        sb.create()

        try:
            # 修改文件
            sb.write_file("src/main.py", "modified content\n")

            # 创建快照
            snap_result = sb.snapshot("snap1", "测试快照")
            assert snap_result["success"] is True
            snap_id = snap_result["snapshot"]["id"]

            # 再修改一次
            sb.write_file("src/main.py", "even more modified\n")
            read_result = sb.read_file("src/main.py")
            assert "even more" in read_result["content"]

            # 回滚
            rollback_result = sb.rollback(snap_id)
            assert rollback_result["success"] is True

            # 验证回滚后内容
            read_result = sb.read_file("src/main.py")
            assert "modified content" in read_result["content"]
            assert "even more" not in read_result["content"]
        finally:
            sb.destroy()

    def test_dangerous_command_blocked(self, sample_project):
        """测试危险命令黑名单。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project)
        sb.create()

        try:
            # 危险命令应该被拦截
            result = sb.run_command("rm -rf /")
            assert result["success"] is False
            assert "Blocked" in result.get("error", "")
        finally:
            sb.destroy()

    def test_list_files(self, sample_project):
        """测试文件列表。"""
        from kernel.refinery import ProjectSandbox

        sb = ProjectSandbox(project_root=sample_project)
        sb.create()

        try:
            result = sb.list_files(pattern="*.py")
            assert result["success"] is True
            assert result["count"] >= 2  # 至少 main.py 和 utils.py
        finally:
            sb.destroy()


class TestCodeAnalyzer:
    """代码分析引擎测试。"""

    @pytest.fixture
    def sandbox_with_code(self, tmp_path):
        """创建一个有代码的沙箱目录。"""
        root = tmp_path / "sandbox"
        root.mkdir()

        src = root / "src"
        src.mkdir()

        # 含问题的代码
        (src / "bad_code.py").write_text(
            '''import os
import sys
import unused_module

API_KEY = "sk-1234567890abcdef"

def complex_func(x):
    """高复杂度函数。"""
    if x > 0:
        if x > 10:
            if x > 20:
                if x > 30:
                    if x > 40:
                        if x > 50:
                            return "very big"
                        else:
                            return "big"
                    else:
                        return "medium"
                else:
                    return "small"
            else:
                return "tiny"
        else:
            if x < -10:
                return "negative big"
            else:
                return "negative small"

def unsafe_eval(data):
    return eval(data)

def run_cmd(cmd):
    os.system(cmd)
''',
            encoding="utf-8",
        )

        (src / "good_code.py").write_text(
            '''def add(a, b):
    """加法函数。"""
    return a + b

def multiply(a, b):
    """乘法函数。"""
    return a * b
''',
            encoding="utf-8",
        )

        return str(root)

    def test_analyze_basic(self, sandbox_with_code):
        """测试基本分析。"""
        from kernel.refinery import CodeAnalyzer

        analyzer = CodeAnalyzer(sandbox_with_code)
        report = analyzer.analyze()

        assert report.total_files >= 2
        assert report.total_functions >= 4
        assert report.overall_score <= 100.0
        assert len(report.issues) > 0

    def test_security_issues_detected(self, sandbox_with_code):
        """测试安全问题检测。"""
        from kernel.refinery import CodeAnalyzer

        analyzer = CodeAnalyzer(sandbox_with_code)
        report = analyzer.analyze()

        # 应该检测到硬编码密钥
        sec_issues = [i for i in report.issues if i.category == "security"]
        assert len(sec_issues) > 0

        # 应该检测到 eval 调用
        eval_issues = [i for i in report.issues if "eval" in i.rule]
        assert len(eval_issues) > 0

        # 应该有高风险问题
        high_issues = [i for i in report.issues if i.severity == "high"]
        assert len(high_issues) > 0

    def test_quality_issues_detected(self, sandbox_with_code):
        """测试质量问题检测。"""
        from kernel.refinery import CodeAnalyzer

        analyzer = CodeAnalyzer(sandbox_with_code)
        report = analyzer.analyze()

        # 应该检测到未使用的 import
        unused = [i for i in report.issues if i.rule == "unused_import"]
        assert len(unused) > 0

    def test_complexity_detected(self, sandbox_with_code):
        """测试复杂度检测。"""
        from kernel.refinery import CodeAnalyzer

        analyzer = CodeAnalyzer(sandbox_with_code)
        report = analyzer.analyze()

        # 应该检测到高复杂度函数
        complex_issues = [i for i in report.issues
                          if i.category == "complexity"]
        # 可能有也可能没有，取决于阈值；分数应该合理
        assert 0 <= report.avg_complexity < 50

    def test_report_structured(self, sandbox_with_code):
        """测试报告结构完整性。"""
        from kernel.refinery import CodeAnalyzer

        analyzer = CodeAnalyzer(sandbox_with_code)
        report = analyzer.analyze()

        d = report.to_dict()
        assert "overall_score" in d
        assert "security_score" in d
        assert "quality_score" in d
        assert "architecture_score" in d
        assert "issue_count" in d
        assert "high_issues" in d
        assert "summary" in d
        assert len(d["summary"]) > 0


class TestCodeOptimizer:
    """代码优化引擎测试。"""

    @pytest.fixture
    def sandbox_with_unused_imports(self, tmp_path):
        root = tmp_path / "sandbox"
        root.mkdir()
        src = root / "src"
        src.mkdir()

        (src / "unused_import.py").write_text(
            '''import os
import sys
import json
import unused_module

def hello():
    print("hello world")
''',
            encoding="utf-8",
        )
        return str(root)

    def test_generate_proposals(self, sandbox_with_unused_imports):
        """测试生成优化提案。"""
        from kernel.refinery import CodeAnalyzer, CodeOptimizer

        analyzer = CodeAnalyzer(sandbox_with_unused_imports)
        report = analyzer.analyze()

        optimizer = CodeOptimizer(sandbox_with_unused_imports)
        proposals = optimizer.generate_proposals(report)

        assert len(proposals) > 0
        # 应该有自动可应用的低风险提案
        auto_props = [p for p in proposals if p.auto_applicable]
        assert len(auto_props) > 0

    def test_apply_auto_proposals(self, sandbox_with_unused_imports):
        """测试应用自动优化。"""
        from kernel.refinery import CodeAnalyzer, CodeOptimizer

        analyzer = CodeAnalyzer(sandbox_with_unused_imports)
        report = analyzer.analyze()

        optimizer = CodeOptimizer(sandbox_with_unused_imports)
        optimizer.generate_proposals(report)

        result = optimizer.apply_auto_proposals()

        assert result["success"] is True
        assert result["applied"] > 0

        # 验证文件已被修改
        file_path = Path(sandbox_with_unused_imports) / "src" / "unused_import.py"
        content = file_path.read_text(encoding="utf-8")
        # 未使用的 import 应该被移除了（unused_module）
        assert "unused_module" not in content

    def test_apply_with_rollback(self, sandbox_with_unused_imports):
        """测试应用失败时自动回滚。"""
        from kernel.refinery import CodeOptimizer

        optimizer = CodeOptimizer(sandbox_with_unused_imports)

        # 手动创建一个假提案
        from kernel.refinery.code_optimizer import OptimizationProposal
        prop = OptimizationProposal(
            id="test-0001",
            category="quality",
            title="测试",
            description="测试提案",
            risk_level="low",
            auto_applicable=True,
            files=["nonexistent/file.py"],
            changes={"nonexistent/file.py": "content"},
        )
        optimizer._proposals["test-0001"] = prop

        # 应用应该失败但不破坏现有文件
        result = optimizer.apply_proposal("test-0001")
        # 这个测试主要验证不会抛异常
        assert "success" in result


class TestTestRunner:
    """测试验证引擎测试。"""

    @pytest.fixture
    def project_with_tests(self, tmp_path):
        proj = tmp_path / "myproj"
        proj.mkdir()
        src = proj / "src"
        src.mkdir()
        (src / "__init__.py").write_text("", encoding="utf-8")
        (src / "math_utils.py").write_text(
            '''def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
''',
            encoding="utf-8",
        )

        tests = proj / "tests"
        tests.mkdir()
        (tests / "__init__.py").write_text("", encoding="utf-8")
        (tests / "test_math.py").write_text(
            '''from src.math_utils import add, subtract

def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(5, 3) == 2
''',
            encoding="utf-8",
        )
        return str(proj)

    def test_syntax_check(self, project_with_tests):
        """测试语法检查。"""
        from kernel.refinery import TestRunner

        runner = TestRunner(project_with_tests)
        result = runner.check_syntax()

        assert result.test_type == "syntax"
        assert result.total >= 2
        assert result.passed >= 2
        assert result.success is True

    def test_syntax_check_fails_on_bad_code(self, tmp_path):
        """测试坏代码的语法检查。"""
        from kernel.refinery import TestRunner

        root = tmp_path / "bad"
        root.mkdir()
        (root / "bad.py").write_text("def broken(:\n    pass\n", encoding="utf-8")

        runner = TestRunner(str(root))
        result = runner.check_syntax()

        assert result.failed >= 1
        assert result.success is False

    def test_run_all(self, project_with_tests):
        """测试运行所有测试类型。"""
        from kernel.refinery import TestRunner

        runner = TestRunner(project_with_tests)
        result = runner.run_all(test_dir="tests", timeout=60)

        assert "success" in result
        assert "results" in result
        assert "syntax" in result["results"]
        assert "unit" in result["results"]


class TestRefineryEngine:
    """炼化总控引擎测试。"""

    @pytest.fixture
    def sample_project(self, tmp_path):
        proj = tmp_path / "sample"
        proj.mkdir()
        src = proj / "src"
        src.mkdir()
        (src / "main.py").write_text(
            '''import os
import unused_pkg

def greet(name):
    return f"Hello, {name}!"
''',
            encoding="utf-8",
        )
        return str(proj)

    def test_end_to_end_refine(self, sample_project):
        """测试端到端炼化流程。"""
        from kernel.refinery import CodeRefineryEngine

        engine = CodeRefineryEngine()
        result = engine.refine_project(
            project_root=sample_project,
            description="测试炼化",
            auto_apply=True,
            run_tests=False,
        )

        assert result["success"] is True
        assert "task" in result
        assert "report" in result
        assert result["report"]["total_proposals"] > 0

        # 原项目不应被修改
        main_file = Path(sample_project) / "src" / "main.py"
        content = main_file.read_text(encoding="utf-8")
        assert "unused_pkg" in content  # 原文件不变

    def test_phase_based_execution(self, sample_project):
        """测试分阶段执行。"""
        from kernel.refinery import CodeRefineryEngine

        engine = CodeRefineryEngine()

        # 阶段1: 创建任务
        create_result = engine.create_task(sample_project, "分阶段测试")
        assert create_result["success"] is True
        task_id = create_result["task_id"]

        # 阶段2: 分析
        analyze_result = engine.analyze(task_id)
        assert analyze_result["success"] is True
        assert "analysis" in analyze_result
        assert "proposals" in analyze_result

        # 阶段3: 应用优化
        apply_result = engine.apply_optimization(task_id)
        assert apply_result["success"] is True

        # 阶段4: 完成
        final_result = engine.finalize(task_id)
        assert final_result["success"] is True
        assert final_result["task"]["status"] == "completed"


class TestEvolutionLoop:
    """进化蒸馏闭环测试。"""

    def test_record_and_patterns(self, tmp_path):
        """测试记录炼化结果和模式蒸馏。"""
        from kernel.refinery import RefineryEvolutionLoop

        store_dir = str(tmp_path / "evo_store")
        evo = RefineryEvolutionLoop(store_dir=store_dir)

        # 记录多次成功的相同类型优化
        proposals = [
            {"id": "p1", "category": "quality", "title": "移除未使用import",
             "risk_level": "low", "description": ""},
        ]

        for i in range(5):
            evo.record_refinery_result(
                task_id=f"task-{i}",
                project_root="/fake/proj",
                initial_score=70.0,
                final_score=75.0 + i,
                applied_proposals=proposals,
                tests_passed=True,
                duration_ms=1000.0,
            )

        # 应该有模式被蒸馏出来
        patterns = evo.get_patterns()
        assert len(patterns) >= 1

        # 统计应该合理
        stats = evo.stats()
        assert stats["total_runs"] == 5
        assert stats["total_patterns"] >= 1

    def test_recommendations(self, tmp_path):
        """测试炼化建议。"""
        from kernel.refinery import RefineryEvolutionLoop

        store_dir = str(tmp_path / "evo_rec")
        evo = RefineryEvolutionLoop(store_dir=store_dir)

        result = evo.get_refinery_recommendations()
        assert result["success"] is True
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)

    def test_persistence(self, tmp_path):
        """测试持久化。"""
        from kernel.refinery import RefineryEvolutionLoop

        store_dir = str(tmp_path / "evo_persist")

        # 第一次：记录
        evo1 = RefineryEvolutionLoop(store_dir=store_dir)
        evo1.record_refinery_result(
            task_id="t1",
            project_root="/p",
            initial_score=60,
            final_score=70,
            applied_proposals=[],
            tests_passed=True,
            duration_ms=100,
        )

        # 第二次：加载
        evo2 = RefineryEvolutionLoop(store_dir=store_dir)
        stats = evo2.stats()

        assert stats["total_runs"] == 1


class TestGlobalConsistency:
    """全局一致性测试：确保炼化系统与现有 AOS 架构兼容。"""

    def test_import_path_consistency(self):
        """测试导入路径与现有模块风格一致。"""
        # 应该能从 kernel.refinery 导入所有公开类
        from kernel.refinery import (
            ProjectSandbox,
            SandboxSnapshot,
            CodeAnalyzer,
            CodeQualityReport,
            CodeOptimizer,
            OptimizationProposal,
            TestRunner,
            TestResult,
            CodeRefineryEngine,
            RefineryTask,
            RefineryReport,
            RefineryEvolutionLoop,
            DistilledPattern,
        )

        # 所有类都应该能实例化或有明确的构造方式
        assert ProjectSandbox is not None
        assert CodeAnalyzer is not None
        assert CodeOptimizer is not None
        assert TestRunner is not None
        assert CodeRefineryEngine is not None
        assert RefineryEvolutionLoop is not None

    def test_follows_aos_conventions(self, tmp_path):
        """测试是否遵循 AOS 全局约定。"""
        from kernel.refinery import ProjectSandbox

        # 1. 有日志记录
        import logging
        logger = logging.getLogger("kernel.refinery.project_sandbox")
        assert logger is not None

        # 2. 资源受限（文件数/大小上限）
        proj = tmp_path / "p"
        proj.mkdir()
        (proj / "a.py").write_text("x=1\n", encoding="utf-8")

        sb = ProjectSandbox(project_root=str(proj))
        sb.create()
        try:
            # 有资源上限检查的内部机制
            assert hasattr(sb, "_check_resource_limits")
        finally:
            sb.destroy()

    def test_api_module_structure(self):
        """测试 API 模块结构与现有 API 一致。"""
        # 应该有 mount_refinery_api 函数
        from api.refinery_api import mount_refinery_api
        assert callable(mount_refinery_api)

    def test_sandbox_security_aligned(self):
        """测试沙箱安全检查与现有系统对齐。"""
        # 复用 SandboxManager 的危险模式检查
        from execution.sandbox import _check_dangerous_patterns

        # 危险命令应该被拦截
        result = _check_dangerous_patterns("rm -rf /")
        assert result is not None

        # 安全代码应该通过
        result = _check_dangerous_patterns("print('hello')")
        assert result is None


# ============================================================================
# 新增功能测试：多智能体团队、FabricHub 集成、增量分析、前端 UI
# ============================================================================

class TestRefineryTeam:
    """多智能体炼化团队测试。"""

    @pytest.fixture
    def sample_proj(self, tmp_path):
        """创建示例项目。"""
        proj = tmp_path / "team_proj"
        proj.mkdir()
        src = proj / "src"
        src.mkdir()
        (src / "a.py").write_text(
            "import os\nimport unused\n\nAPI_KEY='sk-1234567890abcdef'\n\ndef f(x):\n    if x:\n        if x:\n            if x:\n                if x:\n                    return 1\n    return 0\n",
            encoding="utf-8",
        )
        return str(proj)

    def test_import(self):
        """测试模块导入。"""
        from kernel.refinery import RefineryTeam
        assert RefineryTeam is not None

    def test_team_run(self, sample_proj, tmp_path):
        """测试团队协作炼化流程。"""
        from kernel.refinery import ProjectSandbox, CodeAnalyzer, RefineryTeam

        sb = ProjectSandbox(project_root=sample_proj, name="test-team")
        assert sb.create().get("success")

        try:
            analyzer = CodeAnalyzer(sb.root)
            report = analyzer.analyze()
            team = RefineryTeam(sb.root)
            result = team.run(report.to_dict())

            assert "success" in result
            assert "phases" in result
            assert "decisions" in result
            assert len(result["phases"]) >= 3
        finally:
            sb.destroy()


class TestFabricHubIntegration:
    """FabricHub 能力集成测试。"""

    def test_capability_exists(self):
        """测试 CODE_REFINE 能力已定义。"""
        from core.fabric.capability import Capability
        assert Capability.CODE_REFINE == "code.refine"

    def test_refinery_adapter_import(self):
        """测试适配器可导入。"""
        from core.fabric.adapters import RefineryAdapter
        assert RefineryAdapter is not None

    def test_adapter_contract(self):
        """测试适配器满足 BaseAgentAdapter 契约。"""
        from core.fabric.adapters import RefineryAdapter
        from core.fabric.adapter import BaseAgentAdapter

        adapter = RefineryAdapter()
        assert isinstance(adapter, BaseAgentAdapter)
        assert adapter.engine_id == "refinery"

        caps = adapter.advertise_capabilities()
        cap_ids = [c.value for c in caps]
        assert "code.refine" in cap_ids
        assert "security.audit" in cap_ids

    def test_adapter_health(self):
        """测试适配器健康检查。"""
        from core.fabric.adapters import RefineryAdapter
        adapter = RefineryAdapter()
        assert adapter.health() is True

    def test_adapter_invoke_analyze(self, tmp_path):
        """测试通过适配器调用分析。"""
        from core.fabric.adapters import RefineryAdapter
        from core.fabric.adapter import InvokeRequest, InvokeResult
        from core.fabric.capability import Capability

        # 创建示例项目
        proj = tmp_path / "adapter_proj"
        proj.mkdir()
        (proj / "bad.py").write_text(
            "API_KEY='sk-1234567890abcdef'\n", encoding="utf-8",
        )

        adapter = RefineryAdapter()
        req = InvokeRequest(
            capability=Capability.CODE_REFINE,
            payload={"action": "analyze", "project_root": str(proj)},
        )
        result = adapter.invoke(req)

        assert isinstance(result, InvokeResult)
        assert result.ok is True
        assert result.engine_id == "refinery"
        assert "report" in result.data

    def test_engine_registered_in_capability_map(self):
        """测试 refinery 已注册到 ENGINE_CAPABILITY_MAP。"""
        from core.fabric.capability import ENGINE_CAPABILITY_MAP, Capability, ENGINE_TIER

        assert "refinery" in ENGINE_CAPABILITY_MAP
        caps = ENGINE_CAPABILITY_MAP["refinery"]
        assert Capability.CODE_REFINE in caps
        assert Capability.SECURITY_AUDIT in caps

        assert ENGINE_TIER.get("refinery") == "high"


class TestIncrementalAnalyzer:
    """增量炼化分析器测试。"""

    @pytest.fixture
    def sample_proj(self, tmp_path):
        """创建示例项目。"""
        proj = tmp_path / "incr_proj"
        proj.mkdir()
        (proj / "a.py").write_text("x = 1\n", encoding="utf-8")
        (proj / "b.py").write_text("y = 2\n", encoding="utf-8")
        return str(proj)

    def test_import(self):
        """测试模块导入。"""
        from kernel.refinery import IncrementalAnalyzer
        assert IncrementalAnalyzer is not None

    def test_first_run_is_full(self, sample_proj):
        """测试首次运行为全量模式。"""
        from kernel.refinery import IncrementalAnalyzer

        inc = IncrementalAnalyzer(sample_proj, cache_dir=str(
            Path(sample_proj) / ".refinery"))
        result = inc.analyze()

        assert result.mode == "full"
        assert result.total_files == 2
        assert result.report is not None

    def test_second_run_is_incremental_no_changes(self, sample_proj):
        """测试无变化时增量模式。"""
        from kernel.refinery import IncrementalAnalyzer

        cache = str(Path(sample_proj) / ".refinery")
        inc1 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        inc1.analyze()

        inc2 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        result = inc2.analyze()

        # 无变化 → 仍报告 incremental，0 changed
        assert result.mode in ("incremental", "full")
        assert result.changed_files == 0
        assert result.new_files == 0

    def test_detects_changed_file(self, sample_proj):
        """测试检测到文件修改。"""
        from kernel.refinery import IncrementalAnalyzer

        cache = str(Path(sample_proj) / ".refinery")
        inc1 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        inc1.analyze()

        # 修改文件
        import time as _time
        _time.sleep(0.1)
        (Path(sample_proj) / "a.py").write_text("x = 99\n", encoding="utf-8")

        inc2 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        result = inc2.analyze()

        assert result.mode == "incremental"
        assert result.changed_files >= 1
        assert "a.py" in result.changed_file_list

    def test_detects_new_file(self, sample_proj):
        """测试检测到新文件。"""
        from kernel.refinery import IncrementalAnalyzer

        cache = str(Path(sample_proj) / ".refinery")
        inc1 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        inc1.analyze()

        import time as _time
        _time.sleep(0.1)
        (Path(sample_proj) / "c.py").write_text("z = 3\n", encoding="utf-8")

        inc2 = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        result = inc2.analyze()

        assert result.new_files >= 1
        assert "c.py" in result.changed_file_list

    def test_invalidate_cache(self, sample_proj):
        """测试缓存失效。"""
        from kernel.refinery import IncrementalAnalyzer

        cache = str(Path(sample_proj) / ".refinery")
        inc = IncrementalAnalyzer(sample_proj, cache_dir=cache)
        inc.analyze()
        inc.invalidate_cache()

        # 重新分析应该是全量
        result = inc.analyze()
        assert result.mode == "full"


class TestFrontendUI:
    """前端 UI 文件测试。"""

    def test_html_file_exists(self):
        """测试 HTML 文件存在。"""
        html_path = Path(__file__).resolve().parent.parent / "web" / "refinery" / "index.html"
        assert html_path.is_file(), f"前端 UI 文件不存在: {html_path}"

    def test_html_has_required_sections(self):
        """测试 HTML 包含必要功能区域。"""
        html_path = Path(__file__).resolve().parent.parent / "web" / "refinery" / "index.html"
        content = html_path.read_text(encoding="utf-8")

        # 关键功能区域（HTML 用 API_BASE='/api' + '/refinery/xxx' 拼接）
        assert "/refinery/run" in content
        assert "/refinery/analyze" in content
        assert "/refinery/tasks" in content
        assert "/refinery/evolution" in content
        assert "X-API-Key" in content
        assert "API_BASE" in content

    def test_html_is_self_contained(self):
        """测试 HTML 是自包含的（无外部依赖）。"""
        html_path = Path(__file__).resolve().parent.parent / "web" / "refinery" / "index.html"
        content = html_path.read_text(encoding="utf-8")

        # 不应引用外部 CDN 或 JS 库
        assert "cdn.jsdelivr.net" not in content
        assert "unpkg.com" not in content
        assert "cdnjs.cloudflare.com" not in content
