'''pytest conftest — ensures v5.0 Config won't crash during collection.

Stability hook (L3 of the AOS stability system): a few test modules depend on
the native memory stack (zvec / cognee / rocksdb) which is known to CRASH the
process (0xC0000005) under load in this sandbox -- and a crash during import
kills the whole pytest run before any skip can take effect. We therefore
IGNORE those modules at collection time by default, so the suite always
finishes. Set AOS_RUN_NATIVE_TESTS=1 to opt back in (real hosts / deep runs).

The unified native probe (tests/_env_probe.py) still exposes PYTEST_SKIP_NATIVE
for finer-grained skips inside modules that merely *use* the native stack.
'''
import atexit
import os
import shutil
import sys
import tempfile
import pytest
from pathlib import Path

# 将 src/ 与 tests/ 加入 sys.path, 使模块的非前缀 import 在测试环境中可用.
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)
_tests_dir = str(Path(__file__).resolve().parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

# Must run before ANY import touches utils/config.py
_fields = ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]
for f in _fields:
    os.environ.setdefault(f, "conftest-placeholder")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass

# .env 加载后，强制关闭所有会拉起真实子进程的 MCP / 引擎门控。
# 这些 env=1 时 FabricHub.__init__ 会 npx/subprocess 拉起 stdio MCP，
# Windows 上 t.join(timeout) 对 C 层 subprocess 阻塞无效 → 整个 pytest HANG。
# 测试环境统一关掉，让 FabricHub() 构造安全（生产启动时 .env 仍生效）。
for _spawn_env in (
    "VIDEO_USE_MCP_ENABLED",     # npx video-use stdio MCP
    "OMNI_VIDEO_MCP_ENABLED",    # Python stdio MCP（需 ffmpeg/ELEVENLABS/Playwright）
    "DESKTOP_TOUCH_MCP_ENABLED", # Desktop-Touch-MCP stdio
):
    os.environ.pop(_spawn_env, None)

# --- 灵魂文件隔离（母纲原则 10）---------------------------------------------
# 真实缺陷修复：constitution_gaps.get_or_create_soul_id() 默认写
# <repo>/data/soul/soul_id.txt。测试直接调它会**覆盖用户真实灵魂 ID**，
# 等于跑一次测试把人家的「灵魂」换了。这违反「主权归你」。
# 统一把测试期的灵魂文件与同步目录指到临时目录，收集阶段就生效。
_soul_tmp = tempfile.mkdtemp(prefix="aos_soul_test_")
os.environ.setdefault("AOS_SOUL_ID_PATH", os.path.join(_soul_tmp, "soul_id.txt"))
os.environ.setdefault("AOS_SOUL_SYNC_DIR", os.path.join(_soul_tmp, "sync"))
atexit.register(lambda: shutil.rmtree(_soul_tmp, ignore_errors=True))

# --- L3 stability: ignore native-stack modules that crash the runner by default ---
RUN_NATIVE = os.environ.get("AOS_RUN_NATIVE_TESTS") == "1"

collect_ignore = []
if not RUN_NATIVE:
    # 这些模块在 import 阶段就会触发 zvec/cognee 原生崩溃 (0xC0000005)，
    # 必须跳过收集，否则会杀死整个 pytest 进程。
    collect_ignore += [
        "test_memory.py",
        "test_memory_root.py",
        "test_agency_roles_consolidation.py",
    ]

# --- 需要真实外部服务（LLM API / Ollama）的测试，无 Key 无网络时 HANG ---
RUN_REAL = os.environ.get("AOS_RUN_REAL_TESTS") == "1"
if not RUN_REAL:
    collect_ignore += [
        "test_integration.py",       # 真实 LLM 调用（无 module-level skip 守护）
        "test_architecture.py",      # 连本地 Ollama（未启动时 HANG）
        "test_autopilot_causal_reflection.py",  # 真连 DuckDuckGo 搜索
        "test_autopilot_causal_reflection_e2e.py",  # 同上 E2E 版本
        "test_self_evolution_real.py",           # ③级真机自进化闭环（真实本地 ollama LLM）
        "test_content_pipeline_real.py",  # 真实 HTTPS 调用 ima API（urlopen HANG）

        # subprocess 真实子进程执行（无 mock 保护，pytest-timeout 在 Windows 上
        # 对 C 层 subprocess.communicate 阻塞无效 → 整个套件挂死）
        "test_database.py",              # subprocess.run 跑 AST 脚本
        "test_opc_cli.py",               # subprocess.run 跑 OPC CLI 子进程
        "test_code_team.py",             # run_code_team 真实执行生成的代码
        "test_code_team_multilang.py",   # run_code_team 多语言真实执行
        "test_code_team_llm.py",         # CodeTeamOrchestrator 真实跑 pytest
        "test_code_exec_nl_fallback.py", # NL fallback 真实跑代码 + 端到端 FabricHub
        "test_code_team_fabric_route.py",# 真实跑代码 + FabricHub.route
        "test_api_render_endpoints.py",  # code_team_run 真实跑 subprocess
        "test_subprocess_iso.py",        # 真实拉起/杀死子进程
        "test_fabric_isolation_wiring.py",  # 真实子进程隔离 + hub.route
        "test_mcp_stdio_adapter.py",    # 真实 MCP stdio 子进程（mock_stdio_mcp_server）

        # FabricHub() 全量构造（~2min，注册所有真实适配器）+ hub.route 真实调用
        "test_fabric_hub.py",            # 全量构造无 skip
        "test_isolated_agnes_engine.py", # 真实 AgnesAdapter 子进程
        "test_failure_monitor.py",       # 构造完整 FabricHub
        "test_comfyui_real.py",          # 构造完整 FabricHub
        "test_full_integration_real.py", # 构造完整 FabricHub
        # FabricHub() 构造会触发 register_video_use_mcp → mcp_stdio_adapter
        # 子进程 + t.join(timeout) 在 Windows 上对 C 层 subprocess 阻塞无效 → HANG
        "test_orchestrator_end_to_end.py",  # _build_hub_or_skip 裸造 FabricHub()
        "test_mem0_config.py",              # test_fabric_hub_autoloads_env_resolves_agnes 裸造
        "test_openclaw_selfcheck.py",       # test_health_report_includes_health_detail 裸造

        # network 真实网络（模块收集时顶层执行连 Qdrant）
        "test_graphrag_full.py",

        # 真实外部 API 调用（IMA 被限流 403 / 真实 HTTPS）
        "test_ima_handoff_registry.py",
    ]
