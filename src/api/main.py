import sys
import os
import time
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response
import base64
from pydantic import BaseModel, Field
from datetime import datetime

from utils.config import config
from core import get_brain
from core.fabric import a2ui as a2ui_mod
from api.chat_routing import (
    select_chat_backends,
    BACKEND_FABRIC,
    BACKEND_KERNEL,
    BACKEND_BRAIN,
    BRAIN_DEPRECATION_MSG,
)
from kernel.plugins.code_team import (
    CodeTeamOrchestrator,
    make_llm_generate,
    render_code_team,
    supported_languages,
)
from kernel.compliance import QualityGate
from aos_mcp import MCPMessage
from core.pool import initialize_pools, close_pools
from api.security import (
    APISecurityMiddleware,
    RateLimitMiddleware,
    HTTPSRedirectMiddleware,
    SecurityHeadersMiddleware,
    create_access_token,
    authenticate_user,
)
from utils.exceptions import setup_exception_handlers
from api.gateway import mount_gateway, close_gateway_session, probe_upstreams

logging.basicConfig(
    level=logging.INFO if config.DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def _safe_detail(e: Exception) -> str:
    """G7: 生产环境不向客户端泄露内部异常细节 (防信息泄漏/指纹搜集)。

    仅当 APP_ENV == "production" 时返回通用文案, 真实异常始终服务端记录 (exc_info);
    开发/调试环境保留原文便于排错。
    """
    from utils.sanitize import safe_error_detail
    msg = safe_error_detail(e, config.APP_ENV)
    if config.APP_ENV == "production":
        logger.error("Unhandled server error: %s", e, exc_info=True)
    return msg

app = FastAPI(
    title=config.APP_NAME,
    version=config.APP_VERSION,
    description="AOS v5.0 -- Hermes v0.15.2 + DeerFlow 2.0 -- 26-method full scheduler",
    docs_url="/docs" if config.DEBUG else None,
    redoc_url="/redoc" if config.DEBUG else None,
)

# CORS配置 - 安全改进
allowed_origins = [origin.strip() for origin in config.ALLOWED_ORIGINS.split(",") if origin.strip()]

# 验证CORS配置
if config.APP_ENV == "production":
    # 生产环境必须明确指定域名，不允许通配符
    if not allowed_origins or "*" in allowed_origins or "" in allowed_origins:
        logger.error("生产环境必须明确配置ALLOWED_ORIGINS，不允许使用通配符")
        raise ValueError("生产环境CORS配置不安全：请设置具体的ALLOWED_ORIGINS")
    
    # 验证域名格式
    import re
    for origin in allowed_origins:
        if not re.match(r'^https?://[\w\-\.]+(:\d+)?$', origin):
            logger.warning(f"可能不安全的CORS源: {origin}")
    
    logger.info(f"生产环境CORS配置: {allowed_origins}")
else:
    # 开发环境允许本地地址
    if not allowed_origins:
        allowed_origins = [
            "http://localhost:8501",
            "http://localhost:8000", 
            "http://127.0.0.1:8501",
            "http://127.0.0.1:8000"
        ]
        logger.info("开发环境使用默认CORS配置")
    
    # 开发环境可以包含通配符，但记录警告
    if "*" in allowed_origins:
        logger.warning("开发环境使用了CORS通配符，生产环境请明确指定域名")

# O10: 带凭据的跨域禁止通配符（避免"带凭据的通配符跨域" -> 凭据泄露）。
# 生产环境已在上方 fail-fast 拒绝 '*'；此处对开发环境做降级：出现 '*' 则关闭凭据。
allow_credentials = True
if "*" in allowed_origins:
    if config.APP_ENV == "production":
        raise ValueError("生产环境CORS配置不安全：不允许通配符 + 凭据（ALLOWED_ORIGINS 请勿含 *）")
    allow_credentials = False
    logger.warning("CORS 含通配符且 allow_credentials=True，已强制关闭凭据以避免跨站凭据泄露")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    max_age=600,  # 预检请求缓存10分钟
)

@app.middleware("http")
async def add_request_time(request: Request, call_next):
    from datetime import datetime
    request.state.request_time = datetime.now()
    response = await call_next(request)
    return response

# 安全中间件配置
# 添加HTTPS强制重定向（仅生产环境）
if config.APP_ENV == "production":
    app.add_middleware(HTTPSRedirectMiddleware, https_port=443)
    logger.info("生产环境：启用HTTPS强制重定向")

# 添加安全HTTP头
app.add_middleware(SecurityHeadersMiddleware)
logger.info("启用安全HTTP头中间件")

# API安全认证
app.add_middleware(APISecurityMiddleware)

# 速率限制
app.add_middleware(RateLimitMiddleware, max_requests=config.MAX_REQUESTS_PER_MINUTE)

# 设置统一异常处理
setup_exception_handlers(app)
logger.info("统一异常处理器已注册")

# 产品飞轮 API（Studio / Hub / Pulse / Evolve）
try:
    from api.product_flywheel_api import mount_product_flywheel
    mount_product_flywheel(app)
except Exception as e:  # noqa: BLE001
    logger.warning("产品飞轮 API 挂载失败: %s", e)

# AutoSkill 全自动技能 API
try:
    from api.autoskill_api import router as autoskill_router
    app.include_router(autoskill_router)
    logger.info("AutoSkill API 已挂载: /api/autoskill")
except Exception as e:  # noqa: BLE001
    logger.warning("AutoSkill API 挂载失败: %s", e)

# Context Engineering API（Task 2）
try:
    from api.context_api import mount_context_api
    mount_context_api(app)
    logger.info("Context Engineering API 已挂载: /api/context")
except Exception as e:  # noqa: BLE001
    logger.warning("Context Engineering API 挂载失败: %s", e)

# Eval Framework API（Task 3: P0-b）
try:
    from api.eval_api import mount_eval_api
    mount_eval_api(app)
    logger.info("Eval Framework API 已挂载: /api/eval")
except Exception as e:  # noqa: BLE001
    logger.warning("Eval Framework API 挂载失败: %s", e)

# Human-in-the-Loop 审批 API（Task 4）
try:
    from api.approval_api import mount_approval_api
    mount_approval_api(app)
    logger.info("Approval API 已挂载: /api/approvals")
except Exception as e:  # noqa: BLE001
    logger.warning("Approval API 挂载失败: %s", e)

# Replay & Debug API（Task 5: 失败回放、单步调试、trace 对比）
try:
    from api.replay_api import mount_replay_api
    mount_replay_api(app)
    logger.info("Replay & Debug API 已挂载: /api/replay")
except Exception as e:  # noqa: BLE001
    logger.warning("Replay & Debug API 挂载失败: %s", e)

# Self-Harness API（自测闭环：/api/self-harness/run）
try:
    from api.self_harness_api import mount_self_harness_api
    mount_self_harness_api(app)
    logger.info("Self-Harness API 已挂载: /api/self-harness")
except Exception as e:  # noqa: BLE001
    logger.warning("Self-Harness API 挂载失败: %s", e)

# 多模态（视觉理解）API（/api/multimodal/*，底层 VLMAdapter 诚实降级）
try:
    from api.vlm_api import mount_vlm_api
    mount_vlm_api(app)
    logger.info("多模态 API 已挂载: /api/multimodal")
except Exception as e:  # noqa: BLE001
    logger.warning("多模态 API 挂载失败: %s", e)

# 编排运行可视化看板 API（/api/kanban/*，只读 trace 落盘，理念8 白盒可视化）
try:
    from api.kanban_api import mount_kanban_api
    mount_kanban_api(app)
    logger.info("编排看板 API 已挂载: /api/kanban")
except Exception as e:  # noqa: BLE001
    logger.warning("编排看板 API 挂载失败: %s", e)

# 可干预记忆控制面 API（/api/memory/control/*，补全理念8 最后一公里）
try:
    from api.memory_control_api import mount_memory_control_api
    mount_memory_control_api(app)
    logger.info("记忆控制面 API 已挂载: /api/memory/control")
except Exception as e:  # noqa: BLE001
    logger.warning("记忆控制面 API 挂载失败: %s", e)

# 步骤级审核控制面（三省六部制式封驳闭环：/api/review/*）
try:
    from api.review_api import mount_review_api
    mount_review_api(app)
    logger.info("审核控制面 API 已挂载: /api/review")
except Exception as e:  # noqa: BLE001
    logger.warning("审核控制面 API 挂载失败: %s", e)

# Remotion 质量视频渲染 API（/api/video/remotion/*，Tier1 缺口③）
try:
    from api.video_api import mount_video_api
    mount_video_api(app)
    logger.info("Remotion 视频 API 已挂载: /api/video/remotion")
except Exception as e:  # noqa: BLE001
    logger.warning("Remotion 视频 API 挂载失败: %s", e)

# 产品飞轮前端页面（/studio/）
try:
    from fastapi.staticfiles import StaticFiles
    import os
    studio_web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "web", "studio")
    if os.path.exists(studio_web_dir):
        app.mount("/studio", StaticFiles(directory=studio_web_dir, html=True), name="studio")
        logger.info("产品飞轮前端已挂载: /studio/")
except Exception as e:  # noqa: BLE001
    logger.warning("产品飞轮前端挂载失败: %s", e)

# 投标分析前端页面（/bidding/）
try:
    from fastapi.staticfiles import StaticFiles as _SF2
    bidding_web_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "web", "bidding")
    if os.path.exists(bidding_web_dir):
        app.mount("/bidding", _SF2(directory=bidding_web_dir, html=True), name="bidding")
        logger.info("投标分析前端已挂载: /bidding/")
except Exception as e:  # noqa: BLE001
    logger.warning("投标分析前端挂载失败: %s", e)

# ---- Unified Brain (singleton: Hermes + DeerFlow + Memory + Skills + SubAgents) ----
# 延迟代理：UnifiedBrain() 构造极重（~2min，加载 mem0/ChromaDB/Hermes/AG2 等），
# 用代理把构造推迟到首次真实访问，避免 import/启动期阻塞事件循环导致 /health 超时误杀。
# 启动期依赖（health_check / handlers 注册）改由 startup_event 内的后台任务完成（见 _deferred_brain_init）。
class _BrainProxy:
    _obj = None

    def _resolve(self):
        if self._obj is None:
            self._obj = get_brain()
        return self._obj

    def __getattr__(self, name):
        return getattr(self._resolve(), name)

    def shutdown(self):
        if self._obj is not None:
            self._obj.shutdown()


brain = _BrainProxy()


# ---- Pydantic Models ----

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID")
    task_type: Optional[str] = Field(None, description="Task type")
    stream: bool = Field(False, description="Streaming mode")

class KnowledgeRequest(BaseModel):
    title: str = Field(..., description="Knowledge title")
    content: str = Field(..., description="Knowledge content")
    source: str = Field("", description="Source")
    tags: List[str] = Field(default_factory=list, description="Tags")

class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    search_type: str = Field("hybrid", description="hybrid/semantic/fulltext")

class TaskRequest(BaseModel):
    task_type: str = Field(..., description="Task type")
    input_data: Dict[str, Any] = Field(default_factory=dict)

class MetaRouteRequest(BaseModel):
    intent: str = Field(..., description="用户/系统意图文本")
    user_id: Optional[str] = Field(None, description="用户 ID")
    project_id: Optional[str] = Field(None, description="项目 ID")
    trace_id: Optional[str] = Field(None, description="追踪 ID")

class MetaProposeRequest(BaseModel):
    intent: str = Field(..., description="进化/自修改意图")
    proposer: Optional[str] = Field(None, description="提案方")

class SemanticMemoryRequest(BaseModel):
    content: str = Field(..., description="要记住的语义内容")
    user_id: Optional[str] = Field("aos", description="用户/项目 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="附加元数据")

class MCPRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[str] = None
    method: str
    params: Optional[Dict[str, Any]] = None

class SubAgentInvokeRequest(BaseModel):
    message: Optional[str] = Field(None)
    task: Optional[str] = Field(None)
    timeout: int = Field(600)
    extra: Dict[str, Any] = Field(default_factory=dict)


# ---- Startup / Shutdown ----

# 专用隔离线程池：brain 重型 health_check 走这里，避免占用默认事件循环线程池
# （默认池被其余端点共享；health_check 卡住会拖垮整池 → 拒绝服务）。
# lambda 形式确保 brain 代理的懒构造发生在隔离线程内，而非事件循环线程。
_BRAIN_HEALTH_TIMEOUT = 60
_BRAIN_INIT_TIMEOUT = 180
_BRAIN_HEALTH_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="aos-brain-health"
)


async def _brain_health_check(timeout: float = _BRAIN_HEALTH_TIMEOUT):
    """带超时护栏的 brain.health_check（隔离线程池执行）。

    health_check 内部可能触发 brain 首次构造（~2min）及若干组件同步自检；
    用专用单线程池 + asyncio.wait_for 限定最长时间，既不在默认池中占坑，
    也不会因某组件卡死而无限挂起调用方。
    """
    loop = asyncio.get_event_loop()
    return await asyncio.wait_for(
        loop.run_in_executor(_BRAIN_HEALTH_EXECUTOR, lambda: brain.health_check()),
        timeout=timeout,
    )


async def _deferred_brain_init(app):
    """后台初始化 brain（重型，~2min）：不阻塞启动事件，避免 /health 超时误杀。

    把原先在 startup_event 里同步触发的 brain.health_check() 与 deerflow handlers 注册
    移到后台任务；期间 /health 立即可用，首个真实 chat 请求才触发构造。降级运行亦可。
    """
    try:
        # 后台任务内同步调重型 health_check 仍会阻塞事件循环（包含 brain 首次构造 ~2min），
        # 故移入线程池，避免 /health 在启动期被拖垮。
        h = await _brain_health_check(timeout=_BRAIN_INIT_TIMEOUT)
        logger.info("Health: %s", h["status"])
        for name, info in h["components"].items():
            logger.info("  %s: %s", name, info.get("status") or info.get("type", "?"))

        # Register chat/skill handlers on the deerflow engine. Guarded: in a degraded
        # start the engine may be the inert stub, in which case we skip silently rather
        # than crash startup (brain._init_real_deerflow now always assigns .deerflow).
        df_engine = getattr(brain, "deerflow", None)
        if df_engine is not None and hasattr(df_engine, "register_handler"):
            df_engine.register_handler("chat",
                lambda d: brain.hermes.chat(message=d.get("message", ""), session_id=d.get("session_id")))

            # Register skill handlers
            for sn in ["skill-creator","find-skills","superpowers","j-stack","frontend-design","ui-ux-pro-max","duckduckgo-search"]:
                df_engine.register_handler("skill:"+sn, (lambda n: lambda d: brain.hermes.execute_skill(n, d))(sn))
        else:
            logger.warning("deerflow engine unavailable; chat/skill handlers not registered")

        # ---- v1.0 内核引擎回调注册 ----
        # brain 初始化完成后，把 hermes/deerflow 注册为内核的 AgentRuntime 插件。
        # 这样 kernel.send_message() 可以路由到真实的 Hermes/DeerFlow 引擎，
        # 而不是仅依赖 wiring.py 的 LiteLLMAdapter 静态插件。
        bridge = getattr(app.state, "bridge", None)
        if bridge is not None:
            hermes = getattr(brain, "hermes", None)
            if hermes is not None and hasattr(hermes, "chat"):
                try:
                    bridge.register_engine_callback(
                        "hermes",
                        lambda prompt, **kw: hermes.chat(
                            message=prompt,
                            session_id=kw.get("session_id", ""),
                        ),
                    )
                    logger.info("v1.0 kernel: hermes engine registered")
                except Exception as exc:
                    logger.warning("hermes engine callback registration failed: %s", exc)

            df = getattr(brain, "deerflow", None)
            if df is not None and hasattr(df, "execute"):
                try:
                    bridge.register_engine_callback(
                        "deerflow",
                        lambda prompt, **kw: df.execute(
                            message=prompt,
                            session_id=kw.get("session_id", ""),
                        ),
                    )
                    logger.info("v1.0 kernel: deerflow engine registered")
                except Exception as exc:
                    logger.warning("deerflow engine callback registration failed: %s", exc)
        else:
            logger.debug("kernel bridge not mounted; engine callbacks skipped")
    except Exception as e:  # noqa: BLE001
        logger.warning("brain 后台初始化未完成（降级运行）: %s", e)


@app.on_event("startup")
async def startup_event():
    logger.info("=== %s v%s ===", config.APP_NAME, config.APP_VERSION)

    # 初始化连接池
    try:
        await initialize_pools()
        logger.info("数据库连接池初始化完成")
    except Exception as e:
        logger.error(f"连接池初始化失败: {e}")
        # 不阻断启动，降级运行

    logger.info("=== AOS v5.0 ready ===")

    # ---- v1.0 内核接管（双轨并存）----
    # 把极简内核挂到 app.state，供 /api/v1/* 使用。brain.py 已非默认
    # chat 运行时（/api/chat 现默认走 FabricHub，brain.py 仅 opt-in 兜底）；
    # 新 /api/v1/chat 走内核 → mistralrs。
    # 铁律：内核挂载失败绝不阻断启动（try/except 包裹，降级为无内核）。
    try:
        from kernel.v5_bridge import V5Bridge
        bridge = await asyncio.to_thread(lambda: V5Bridge().mount(app))
        logger.info("v1.0 kernel mounted: skills=%s, gateway ready",
                    getattr(app.state, "skills_registered", 0))
    except Exception as e:  # noqa: BLE001
        app.state.kernel = None
        app.state.bridge = None
        logger.warning("v1.0 kernel mount skipped: %s", e)

    # AutoSkill 注册为 FabricHub 能力缺失钩子——缺什么技能自动去 SkillHub 找并安装
    # best-effort，失败不阻断启动；AutoSkill 不可用时 FabricHub 照常工作
    try:
        hub = await _get_fabric_hub()
        from skills.autoskill_engine import get_autoskill_engine
        autoskill = get_autoskill_engine()
        autoskill.register_with_fabric_hub(hub)
        logger.info("AutoSkill 已注册为 FabricHub 能力缺失钩子")
    except Exception as e:  # noqa: BLE001
        logger.warning("AutoSkill-FabricHub 注册跳过: %s", e)

    # Echo 适配器注入 Pulse——内容飞轮采集的数据自动进 Pulse
    # 这样 Evolve 就能直接从 Pulse 读内容反馈做分析和优化提案
    try:
        hub = await _get_fabric_hub()
        echo_adapter = hub._registry._adapters.get("echo")
        if echo_adapter is not None and hasattr(echo_adapter, "set_pulse"):
            from kernel.pulse.pulse_collector import get_pulse_collector
            pulse = get_pulse_collector()
            echo_adapter.set_pulse(pulse)
            logger.info("Echo 适配器已注入 Pulse（内容飞轮数据闭环）")
    except Exception as e:  # noqa: BLE001
        logger.warning("Echo Pulse 注入跳过: %s", e)

    # 统一网关上游可达性探测（仅日志，不阻断启动）
    try:
        await probe_upstreams()
    except Exception as e:  # noqa: BLE001
        logger.warning("gateway probe skipped: %s", e)

    # 网关上游周期探活（更新存活缓存，用于友好 502 降级），后台运行不阻塞启动。
    try:
        from api.gateway import _liveness_loop
        asyncio.create_task(_liveness_loop())
    except Exception as e:  # noqa: BLE001
        logger.warning("gateway liveness loop skipped: %s", e)

    # brain 重型初始化移到后台任务（见 _deferred_brain_init），不阻塞 /health。
    asyncio.create_task(_deferred_brain_init(app))

    # 常驻记忆提炼 Agent（借鉴 Jcode）：周期扫描 trace → 提炼事实 → 写记忆。
    # best-effort，失败不阻断启动；增强通道 mem0 不可用时自动降级为仅 jsonl 落盘。
    try:
        from kernel.memory_distiller import get_distiller
        _distiller = get_distiller()
        asyncio.create_task(_distiller.run_loop())
    except Exception as e:  # noqa: BLE001
        logger.warning("memory distiller start skipped: %s", e)

    # 海马卷轴可信长期记忆（Hippo-Scroll）：纯内存、零外部依赖，启动即构造并
    # 挂 app.state.hippo_scroll，供 /api/memory/hippo/* 真实触达其检索/仲裁/巡检。
    # best-effort，失败不阻断启动（铁律：内核/增强挂载失败绝不阻断启动）。
    try:
        from kernel.hippo_scroll import get_hippo_scroll
        app.state.hippo_scroll = get_hippo_scroll()
        logger.info("hippo-scroll memory engine mounted")
    except Exception as e:  # noqa: BLE001
        app.state.hippo_scroll = None
        logger.warning("hippo-scroll memory engine skipped: %s", e)

    # 内容生产导演（ContentDirector）：一句话目标 → 自主跑完整条内容生产链路。
    # route_fn 用 lambda 延迟到首次 produce 才构造 hub（避免 startup 阻塞）；
    # best-effort，失败不阻断启动。
    try:
        from kernel.plugins.content_director import get_content_director
        from aos_mcp.protocol import _get_hub
        app.state.content_director = get_content_director(
            route_fn=lambda cap, payload: _get_hub().route(cap, payload))
        logger.info("content director mounted")
    except Exception as e:  # noqa: BLE001
        app.state.content_director = None
        logger.warning("content director skipped: %s", e)

    # 活体进化闭环（LiveEvolutionEngine）：默认构造会 build_default_system() 接真实内核
    # （生产：真 LLM 进化）。该构造较重（可能联网），故放后台任务，不阻塞 /health；
    # 沙箱无内核/网络时 best-effort 跳过，绝不阻断启动，也不伪造成功。
    asyncio.create_task(_deferred_live_init(app))


async def _deferred_live_init(app):
    """后台挂载活体进化引擎单例（构造较重，放后台不阻塞 /health）。"""
    try:
        from kernel.live import get_live_engine
        engine = get_live_engine()
        app.state.live_engine = engine
        logger.info("live evolution engine mounted")
    except Exception as e:  # noqa: BLE001
        app.state.live_engine = None
        logger.warning("live evolution engine skipped: %s", e)


@app.on_event("shutdown")
async def shutdown_event():
    # 关闭连接池
    try:
        await close_pools()
        logger.info("数据库连接池已关闭")
    except Exception as e:
        logger.error(f"关闭连接池时出错: {e}")
    
    brain.shutdown()
    try:
        await close_gateway_session()
    except Exception as e:
        logger.warning("关闭网关会话失败: %s", e)
    logger.info("=== AOS shutdown complete ===")


# ---- Root & Health ----

@app.get("/")
async def root():
    # 统一前门：直接返回 AOS 统一门户 SPA，打开即完整系统
    from fastapi.responses import HTMLResponse
    portal_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "web", "portal.html")
    try:
        with open(portal_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/web/", status_code=307)


@app.get("/info")
async def info():
    return {
        "name": config.APP_NAME,
        "version": config.APP_VERSION,
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "chat": "/api/chat",
            "stream_chat": "/api/chat/stream",
            "knowledge": "/api/knowledge",
            "search": "/api/search",
            "sessions": "/api/sessions",
            "tasks": "/api/tasks",
            "providers": "/api/providers",
            "mcp": "/api/mcp",
            "skills": "/api/skills",
            "subagents": "/api/subagents",
            "memory": "/api/memory",
            "deerflow": "/api/deerflow",
            "stats": "/api/stats",
            "health": "/health",
            "docs": "/docs",
            "compliance": {
                "audit": "/api/compliance/audit",
                "identity": "/api/compliance/identity",
                "trace": "/api/compliance/trace",
            },
            "sandbox": "/api/sandbox",
            "subagents_deep": "/api/subagents/deep",
            "meta_route": "/api/meta/route",
            "meta_classify": "/api/meta/classify",
            "meta_priority": "/api/meta/priority",
            "meta_propose": "/api/meta/propose",
            "semantic_memory_add": "/api/memory/semantic/add",
            "semantic_memory_search": "/api/memory/semantic/search",
        },
    }

# 深检结果缓存 (避免 /health/deep 每次都对 fabric 各引擎做网络探测)
_HEALTH_CACHE: dict = {"ts": 0.0, "data": None}
_HEALTH_TTL = 5.0


@app.get("/health")
async def health_check():
    """轻量存活探针 (liveness).

    生产铁律: 此端点必须秒回, 绝不做组件深检 / 网络探测 / 同步阻塞调用。
    supervisor 只凭本端点判断进程存活, 因此即便聊天占满 worker,
    事件循环仍能瞬间应答, 不会被误杀。深度组件状态见 /health/deep。
    """
    return {"status": "alive", "service": "aos", "ts": time.time()}


@app.get("/health/deep")
async def health_check_deep():
    """完整 9 组件健康 (readiness). 在线程池执行 + 短缓存, 不阻塞事件循环。"""
    now = time.time()
    if _HEALTH_CACHE["data"] is not None and (now - _HEALTH_CACHE["ts"]) < _HEALTH_TTL:
        return _HEALTH_CACHE["data"]
    data = await _brain_health_check()
    _HEALTH_CACHE["data"] = data
    _HEALTH_CACHE["ts"] = now
    return data


# ---- 团队级认证 (OAuth2/JWT, 与 API-Key 并存) ----

class TokenRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/token")
async def issue_token(req: TokenRequest):
    """用账号密码换取 JWT (Bearer). 团队级可替换为 OIDC/LDAP, 接口不变."""
    if not authenticate_user(req.username, req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = create_access_token(req.username)
    return {"access_token": token, "token_type": "bearer"}


@app.get("/api/fabric")
async def fabric_status():
    """查看 fabric 当前 live 引擎与能力。

    双轨融合：优先内核层 FabricHub（唯一运行时，真实连通性探测、全部适配器），
    内核不可用时回退 brain.fabric（legacy）。避免 brain.fabric 优雅降级为 None 时
    仪表盘引擎列表全空、而内核实际 22+ 引擎在线的双轨不一致。
    """
    def _status():
        # 1) 优先内核层 FabricHub（与 /api/chat 等走同一实例，状态全链路一致）
        try:
            from kernel.plugins.fabric_hub import get_fabric_hub
            report = get_fabric_hub().health_report()
            engines = []
            for eid, info in report.get("adapters", {}).items():
                item = {
                    "engine_id": eid,
                    "live": bool(info.get("live")),
                    "capabilities": info.get("capabilities", []),
                    "protocols": [],
                }
                if info.get("error"):
                    item["error"] = info["error"]
                engines.append(item)
            live = [e["engine_id"] for e in engines if e["live"]]
            return {"fabric": "ok", "source": "kernel", "live_count": len(live),
                    "live": live, "engines": engines}
        except Exception as e:  # noqa: BLE001
            logger.warning("kernel FabricHub 状态获取失败，回退 brain.fabric: %s", e)
        # 2) 回退：brain 层 fabric（legacy 双轨）
        if not getattr(brain, "fabric", None):
            return {"fabric": "unavailable", "engines": []}
        engines = []
        for eid, ad in brain.fabric._adapters.items():
            try:
                engines.append({
                    "engine_id": eid,
                    "live": ad.health(),
                    "capabilities": [c.value for c in ad.advertise_capabilities()],
                    "protocols": ad.supported_protocols(),
                })
            except Exception as e:
                engines.append({"engine_id": eid, "live": False, "error": str(e)})
        live = [e["engine_id"] for e in engines if e.get("live")]
        return {"fabric": "ok", "source": "brain", "live_count": len(live), "live": live, "engines": engines}
    return await asyncio.to_thread(_status)


# ---- Chat ----

# 单基座第一性：/api/chat 默认经 FabricHub 单一运行时（目标「唯一运行时」），
# brain.py（legacy UnifiedBrain）已废弃，仅作 opt-in 兜底（AOS_BRAIN_FALLBACK=1）。
# 后端链由 api.chat_routing.select_chat_backends() 依据 env 决策，每个后端失败
# 诚实回退到下一后端（理念6/9），绝不伪造响应。改 env 无需重启即生效。
# 旧灰度旋钮 AOS_KERNEL_TRAFFIC_PCT / AOS_FABRIC_CHAT 已被 AOS_CHAT_BACKEND 取代。


@app.post("/api/chat")
async def chat(request: ChatRequest):
    # 单基座第一性：默认经 FabricHub 单一运行时；brain.py 已废弃为 opt-in 兜底。
    # 后端链由 select_chat_backends() 依据 env 决策（默认 [fabric, kernel]），
    # 每个后端失败诚实回退到下一后端（理念6/9），绝不伪造响应。
    bridge = getattr(app.state, "bridge", None)
    try:
        if bridge is not None:
            bridge.record_chat_request()

        chain = select_chat_backends()
        last_exc = None
        for backend in chain:
            if backend == BACKEND_FABRIC:
                try:
                    if bridge is not None:
                        bridge.record_chat_route("fabric")
                    hub = await _get_fabric_hub()
                    result = await asyncio.to_thread(
                        hub.chat,
                        message=request.message,
                        session_id=request.session_id or "",
                    )
                    engine = result.get("engine") or "fabric"
                    logger.info("chat routed to FabricHub (%s)", engine)
                    return {"response": result["response"],
                            "route": f"fabric/{engine}", "ok": result.get("ok")}
                except Exception as exc:
                    last_exc = exc
                    logger.warning("FabricHub chat failed, rolling back: %s", exc)
                    continue

            elif backend == BACKEND_KERNEL:
                try:
                    if bridge is not None:
                        bridge.record_chat_route("kernel")
                    resp = await asyncio.to_thread(
                        bridge.chat,
                        prompt=request.message,
                        session_id=request.session_id or "",
                    )
                    content = resp.data.get("content", "") if resp.data else ""
                    logger.info("chat routed to kernel (v1.0)")
                    return {"response": content, "route": "kernel/v1", "ok": resp.ok}
                except Exception as exc:
                    last_exc = exc
                    logger.warning("kernel chat failed, rolling back: %s", exc)
                    continue

            elif backend == BACKEND_BRAIN:
                # legacy 路径（已废弃）：仅当 AOS_CHAT_BACKEND=brain 或
                # AOS_BRAIN_FALLBACK=1 时到达。打废弃标记以驱动迁移。
                logger.warning(BRAIN_DEPRECATION_MSG)
                if bridge is not None:
                    bridge.record_chat_route("brain")
                # 进化治理钩子：每次对话经 L3.5 元调度引擎做意图分层决策。
                # 关键：只算一次, 结果传给 brain.chat() 复用 —— 避免重复调用 route_intent
                # 导致 evolution_log 双写 (此前 /api/chat 与 brain.chat() 各调一次)。
                meta_decision = None
                try:
                    # Run the (synchronous, potentially long) governance + chat in a
                    # worker thread so the event loop stays free to serve /health.
                    # Without this, a single blocking chat would stall the only uvicorn
                    # worker, /health would time out, and the supervisor would kill AOS
                    # mid-request (taking the whole API down on one chat).
                    meta_decision = await asyncio.to_thread(
                        brain.meta_orchestrator.route_intent,
                        intent=request.message, user_id="chat",
                        trace_id=request.session_id or "")
                except Exception as e:  # pragma: no cover - 治理钩子绝不阻断主流程
                    logger.debug("meta governance hook skipped: %s", e)
                result = await asyncio.to_thread(
                    brain.chat, message=request.message, session_id=request.session_id,
                    meta_decision=meta_decision)
                if isinstance(result, dict) and meta_decision:
                    result["meta"] = {
                        "layer": meta_decision.get("layer"),
                        "complexity": meta_decision.get("complexity"),
                        "workflow_id": meta_decision.get("workflow_id"),
                        "priority": meta_decision.get("priority"),
                    }
                # 可观测钩子: 发 Langfuse trace (input/output/metadata 含 meta 分层)
                try:
                    tracer = getattr(brain, "langfuse_tracer", None)
                    if tracer is not None and tracer.enabled:
                        tracer.trace(
                            name="chat",
                            input=request.message,
                            output=result if isinstance(result, (str, dict)) else None,
                            metadata={"layer": (result.get("meta", {}) if isinstance(result, dict) else {}).get("layer")},
                        )
                except Exception as e:  # pragma: no cover - 可观测绝不阻断主流程
                    logger.debug("langfuse trace skipped: %s", e)
                return result

        # 所有后端耗尽 —— 诚实返回 503（不伪造响应），附最后一跳错误（理念6/9）。
        detail = "chat backend unavailable: all backends failed"
        if last_exc is not None:
            detail += f" (last: {_safe_detail(last_exc)})"
        logger.error("Chat error: all backends exhausted: %s", last_exc)
        raise HTTPException(status_code=503, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))

# ---- v1.0 内核路由（双轨并存，走 mistralrs 本地推理）----

class KernelChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID")
    engine: str = Field("litellm", description="AgentRuntime 引擎")
    model: str = Field("mistralrs_general",
                       description="内核 ModelGateway 模型 id")
    mode: str = Field("auto", description="auto=自动检测, chat=纯LLM对话, task=think→do闭环")


class RunTaskRequest(BaseModel):
    task: str = Field(..., description="自然语言任务，如 搜索Python最新版本并写代码打印结果")
    planner: str = Field("heuristic", description="规划器: heuristic=本地关键词切分, ag2=LLM规划")
    session_id: Optional[str] = Field(None, description="会话ID，传入则记住之前对话，支持多轮连续交互")


def _looks_like_task(message: str) -> bool:
    """自动检测用户消息是否需要 think→do 闭环执行。

    判断依据：消息中是否包含工具触发词或多步连接词。
    命中任一即走 task 模式——宁可多走一次 run_task（LLM 会兜底），
    也不漏掉需要执行的真实任务。
    """
    msg_lower = message.lower()
    # 工具触发词：搜索/执行代码/写代码/读文件/写文件
    tool_keywords = [
        "搜索", "搜一下", "查一下", "查找", "search",
        "执行代码", "运行代码", "跑代码", "run code", "exec",
        "写代码", "写一段", "write code", "generate code",
        "读文件", "写文件", "打开文件", "read file", "write file",
        "帮我查", "帮我写", "帮我搜索",
    ]
    # 多步连接词：出现这些通常意味着需要编排多步
    multi_step_keywords = [
        "然后", "接着", "之后再", "随后", "and then", "after that",
    ]
    for kw in tool_keywords:
        if kw in msg_lower:
            return True
    for kw in multi_step_keywords:
        if kw in msg_lower:
            return True
    return False


@app.post("/api/v1/chat")
async def kernel_chat(request: KernelChatRequest):
    """v1.0 内核路由：/api/v1/chat → bridge.chat() → AOSKernel.send_message。

    mode="chat": 纯 LLM 对话，文本进文本出。
    mode="task": think→do 闭环 — 规划→步骤→逐跳执行真实工具（搜索/代码/浏览器）。
    mode="auto"（默认）: 自动检测——含工具触发词或多步连接词时走 task，否则走 chat。
    """
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="kernel not mounted")

    # 自动路由：mode 未指定或为 "auto" 时，自动检测
    effective_mode = request.mode
    if effective_mode in ("auto", "chat") and _looks_like_task(request.message):
        effective_mode = "task"

    # ---- think→do 闭环：任务执行模式 ----
    if effective_mode == "task":
        result = await asyncio.to_thread(
            bridge.run_task, task=request.message, planner="heuristic",
            session_id=request.session_id,
        )
        return result

    # ---- 默认：纯 LLM 对话 ----
    try:
        resp = await asyncio.to_thread(
            bridge.chat,
            prompt=request.message,
            session_id=request.session_id or "",
            engine=request.engine,
        )
        content = resp.data.get("content", "") if resp.data else ""
        return {
            "ok": resp.ok,
            "content": content,
            "model": resp.data.get("model", "") if resp.data else "",
            "backend": resp.data.get("backend", "") if resp.data else "",
            "route": "kernel/v1",
            "error": resp.error,
        }
    except Exception as e:
        logger.error("Kernel chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/v1/run_task")
async def kernel_run_task(request: RunTaskRequest):
    """v1.0 think→do 闭环：规划 → steps[] → OrchestrationChiplet 逐跳执行。

    与 /api/v1/chat 的区别：chat 只调一次 LLM；run_task 把任务拆成多步，
    每步路由到真实工具（搜索/代码执行/浏览器…），上一步产出喂下一步。
    """
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="kernel not mounted")
    result = await asyncio.to_thread(
        bridge.run_task, task=request.task, planner=request.planner,
        session_id=request.session_id,
    )
    return result


@app.get("/api/v1/health")
async def kernel_health():
    """v1.0 内核健康报告（轻量，不阻塞）。"""
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        return {"status": "not_mounted"}
    health = await asyncio.to_thread(bridge.health)
    try:
        health["telemetry"] = bridge.telemetry()
    except Exception as e:
        logger.warning("获取内核遥测数据失败: %s", e)
    return health


@app.post("/api/v1/chat/stream")
async def kernel_stream_chat(request: KernelChatRequest):
    """v1.0 内核 SSE streaming — 通过 ModelGateway.stream_chat 逐块返回。

    注意：streaming 路径直接经 ModelGateway（不经过 send_message 同步链路），
    因为内核 send_message() 当前为同步阻塞。后续 AgentRuntime.stream_run()
    实现后可迁移至完整内核链路。
    """
    bridge = getattr(app.state, "bridge", None)
    if bridge is None:
        raise HTTPException(status_code=503, detail="kernel not mounted")

    async def generate():
        try:
            gw = bridge.kernel._model_gateway
            if not hasattr(gw, "stream_chat"):
                # 降级：不支持 streaming 的 gateway 走单次调用
                resp = await asyncio.to_thread(
                    bridge.chat,
                    prompt=request.message,
                    session_id=request.session_id or "",
                    engine=request.engine,
                )
                content = resp.data.get("content", "") if resp.data else ""
                yield f"data: {json.dumps({'content': content, 'done': True})}\n\n"
                yield "data: [DONE]\n\n"
                return

            messages = [{"role": "user", "content": request.message}]
            async for chunk in gw.stream_chat(request.model, messages):
                payload = chunk if isinstance(chunk, dict) else {"content": str(chunk)}
                yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Kernel stream error: %s", e, exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/api/chat/stream")
async def stream_chat(request: ChatRequest):
    async def generate():
        async for chunk in brain.hermes.stream_chat(message=request.message, session_id=request.session_id):
            yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")


# ---- Knowledge & Memory ----

@app.post("/api/knowledge")
async def add_knowledge(request: KnowledgeRequest):
    try:
        # 同步写库（SQLite I/O）移出事件循环，避免阻塞 /health 与并发请求。
        return await asyncio.to_thread(brain.add_memory, content=request.content, category="user")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.get("/api/knowledge")
async def list_knowledge(limit: int = Query(50, ge=1, le=200)):
    try:
        # SQLite 查询整体移入线程池（cursor 不可跨线程复用，故查询+fetch 一并包住）。
        def _q():
            cur = brain.memory.sqlite_conn.execute(
                "SELECT * FROM knowledge ORDER BY created_at DESC LIMIT ?", (limit,))
            return cur.fetchall()
        rows = await asyncio.to_thread(_q)
        import json
        def _safe_tags(tags_str):
            try:
                return json.loads(tags_str or "[]")
            except (json.JSONDecodeError, TypeError):
                return []
        return {"items": [{"id": r["id"],"title": r["title"],"content": r["content"],
                "source": r["source"],"tags": _safe_tags(r["tags"]),
                "created_at": r["created_at"]} for r in rows],
                "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.post("/api/search")
async def search_memory(request: SearchRequest):
    return await asyncio.to_thread(brain.search_memory, query=request.query, search_type=request.search_type)


@app.get("/api/web-search")
async def web_search(q: str, max_results: int = Query(8, ge=1, le=20)):
    """六级源网络搜索（AnySearch→百度→Bing→DDG→Jina→智谱，全部免 key）。

    经内核 FabricHub 统一路由 web.search 能力，自动故障转移。
    返回 {ok, data:{results:[{title,url,body}], count, engine, confidence}, error}。
    """
    def _do():
        from kernel.plugins.fabric_hub import get_fabric_hub
        res = get_fabric_hub().route("web.search", {"query": q, "max_results": max_results})
        return {"ok": bool(res.ok), "data": res.data, "error": res.error}
    return await asyncio.to_thread(_do)


@app.get("/api/memory")
async def memory_overview():
    return await asyncio.to_thread(brain.export_memory)


# ---- Mem0 语义记忆 (真实接入) ----

@app.post("/api/memory/semantic/add")
async def semantic_memory_add(request: SemanticMemoryRequest):
    return await asyncio.to_thread(
        brain.semantic_memory_add,
        content=request.content, user_id=request.user_id or "aos",
        metadata=request.metadata)


@app.get("/api/memory/semantic/search")
async def semantic_memory_search(query: str, user_id: str = "aos", limit: int = 5):
    return await asyncio.to_thread(
        brain.semantic_memory_search, query=query, user_id=user_id, limit=limit)


# ---- Sessions ----

@app.get("/api/sessions")
async def list_sessions():
    sessions = await asyncio.to_thread(brain.list_sessions)
    return {"sessions": sessions, "count": len(sessions)}

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    info = await asyncio.to_thread(brain.get_session, session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    return info

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    # 首触可能触发 brain 重型构造；整体移入线程池，避免阻塞事件循环。
    def _del():
        if session_id in brain.hermes.sessions:
            del brain.hermes.sessions[session_id]
        return {"success": True, "session_id": session_id}
    return await asyncio.to_thread(_del)


# ---- Tasks ----

@app.post("/api/tasks")
async def submit_task(request: TaskRequest):
    task_id = await asyncio.to_thread(brain.deerflow.submit_task, task_type=request.task_type, input_data=request.input_data)
    return {"task_id": task_id, "status": "submitted"}

@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    return {"tasks": await asyncio.to_thread(brain.deerflow.list_tasks, status=status, limit=limit)}

@app.get("/api/tasks/running")
async def get_running_tasks():
    return {"tasks": await asyncio.to_thread(brain.deerflow.get_running_tasks)}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = await asyncio.to_thread(brain.deerflow.get_task_status, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if not await asyncio.to_thread(brain.deerflow.cancel_task, task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    return {"success": True, "task_id": task_id}


# ---- DeerFlow Native API ----

@app.get("/api/deerflow/models")
async def deerflow_models():
    return await asyncio.to_thread(brain.deerflow.list_models)

@app.get("/api/deerflow/skills")
async def deerflow_skills():
    return await asyncio.to_thread(brain.deerflow.list_skills)

@app.get("/api/deerflow/threads")
async def deerflow_threads(limit: int = 10):
    return await asyncio.to_thread(brain.deerflow.list_threads, limit)

@app.get("/api/deerflow/threads/{thread_id}")
async def deerflow_thread(thread_id: str):
    return await asyncio.to_thread(brain.deerflow.get_thread, thread_id)

@app.get("/api/deerflow/memory")
async def deerflow_memory():
    return await asyncio.to_thread(brain.deerflow.get_memory)

@app.get("/api/deerflow/mcp")
async def deerflow_mcp_config():
    return await asyncio.to_thread(brain.deerflow.get_mcp_config)


# ---- Meta Orchestrator (L3.5 进化治理) ----

@app.post("/api/meta/route")
async def meta_route(request: MetaRouteRequest):
    """意图分层路由：返回 layer / workflow_id / priority / persona_config。"""
    try:
        # route_intent 可能触发 LLM 分层决策，移出事件循环。
        return await asyncio.to_thread(
            brain.meta_orchestrator.route_intent,
            intent=request.intent,
            user_id=request.user_id or "system",
            project_id=request.project_id or "",
            trace_id=request.trace_id or "",
        )
    except Exception as e:
        logger.error("meta route error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/meta/classify")
async def meta_classify(intent: str):
    """纯函数意图分类（L1/L2/L3/L3.5）。"""
    try:
        from meta_orchestrator.engine import classify_intent
        layer, complexity, wf = await asyncio.to_thread(classify_intent, intent)
        return {"layer": layer, "complexity": complexity, "workflow_id": wf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/meta/priority")
async def meta_priority(task_id: str):
    """查询任务优先级（结合进化层与历史指纹）。"""
    return {"task_id": task_id, "priority": await asyncio.to_thread(brain.meta_orchestrator.query_priority, task_id)}


@app.post("/api/meta/propose")
async def meta_propose(request: MetaProposeRequest):
    """捕获 L3.5 自修改意图，生成受人工门控的提案（绝不自动改代码）。"""
    return await asyncio.to_thread(
        brain.meta_orchestrator.propose_self_modification,
        request.intent, proposer=request.proposer or "aos")


# ---- MCP ----

@app.post("/api/mcp")
async def mcp_endpoint(request: MCPRequest):
    try:
        msg = MCPMessage(id=request.id, method=request.method, params=request.params or {})
        resp = await asyncio.to_thread(brain.mcp.handle_message, msg)
        return resp.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.get("/api/mcp/info")
async def mcp_info():
    return await asyncio.to_thread(brain.mcp.get_server_info)


# ---- SubAgents ----

@app.get("/api/subagents")
async def list_subagents():
    def _g():
        return {"subagents": brain.subagents.list_agents(), "stats": brain.subagents.get_stats()}
    return await asyncio.to_thread(_g)

@app.get("/api/subagents/{name}/status")
async def get_subagent_status(name: str):
    info = await asyncio.to_thread(brain.subagents.get, name)
    if not info:
        raise HTTPException(status_code=404, detail=f"SubAgent {name} not found")
    return info.to_dict()

@app.post("/api/subagents/{name}/invoke")
async def invoke_subagent(name: str, request: SubAgentInvokeRequest):
    if not await asyncio.to_thread(brain.subagents.has, name):
        raise HTTPException(status_code=404, detail=f"SubAgent {name} not found")
    input_data = {}
    if request.message: input_data["message"] = request.message
    if request.task: input_data["task"] = request.task
    input_data["timeout"] = request.timeout
    input_data.update(request.extra)
    result = await asyncio.to_thread(brain.subagents.invoke, name, input_data)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Invocation failed"))
    return result


# ---- Skills ----

class SkillExecuteRequest(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)

@app.get("/api/skills/search")
async def search_skills(q: str):
    return await asyncio.to_thread(brain.hermes.search_skills, query=q)

@app.post("/api/skills/{name}/execute")
async def execute_skill_endpoint(name: str, request: SkillExecuteRequest):
    result = await asyncio.to_thread(brain.hermes.execute_skill, name, request.context)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Skill execution failed"))
    return result

# ---- DeerFlow 2.0 实时技能目录 (thin-seam) ----
@app.get("/api/skills/deerflow")
async def list_deerflow_skills():
    """列出 DeerFlow 网关实时技能目录 (skills/public + 用户 custom)。"""
    try:
        return await asyncio.to_thread(brain.deerflow_skill_provider.as_dict)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"DeerFlow skill catalog unavailable: {e}")

@app.post("/api/skills/refresh")
async def refresh_deerflow_skills():
    """强制重拉 DeerFlow 实时技能目录 (热加载往 skills/custom 丢的自定义技能)。"""
    n = await asyncio.to_thread(brain.refresh_deerflow_skills)
    return {"refreshed": n, "status": "ok"}


# ---- Providers & Stats ----

@app.get("/api/providers")
async def get_providers():
    return await asyncio.to_thread(brain.hermes.get_providers_status)

@app.get("/api/stats")
async def get_stats():
    return await asyncio.to_thread(brain.get_full_stats)


# ---- Compliance: Audit ----

@app.get("/api/compliance/audit")
async def compliance_audit(event_type: str = "", limit: int = 100):
    return {"entries": await asyncio.to_thread(brain.audit.query, event_type=event_type or None, limit=limit)}

@app.get("/api/compliance/audit/stats")
async def compliance_audit_stats():
    return await asyncio.to_thread(brain.audit.get_stats)

# ---- Compliance: Identity ----

@app.get("/api/compliance/identity")
async def compliance_identity():
    def _ident():
        return {
            "root_identity": brain.identity.to_dict(),
            "stats": brain.aid_gen.get_stats(),
            "all": [i.to_dict() for i in brain.aid_gen.list_identities()],
        }
    return await asyncio.to_thread(_ident)

@app.get("/api/compliance/identity/{aid}")
async def compliance_get_identity(aid: str):
    ident = await asyncio.to_thread(brain.aid_gen.get_identity, aid)
    if not ident:
        raise HTTPException(status_code=404, detail="Identity not found")
    return ident.to_dict()

@app.post("/api/compliance/identity")
async def compliance_create_identity(name: str, capabilities: str = ""):
    caps = [c.strip() for c in capabilities.split(",")] if capabilities else None
    ident = await asyncio.to_thread(brain.aid_gen.create_identity, name=name, capabilities=caps)
    return ident.to_dict()

# ---- Compliance: Trace ----

@app.get("/api/compliance/trace")
async def compliance_traces(limit: int = 50):
    return {"traces": await asyncio.to_thread(brain.tracer.list_traces, limit=limit)}

@app.get("/api/compliance/trace/{trace_id}")
async def compliance_get_trace(trace_id: str):
    trace = await asyncio.to_thread(brain.tracer.get_trace, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace.to_dict()

@app.get("/api/compliance/trace/stats")
async def compliance_trace_stats():
    return await asyncio.to_thread(brain.tracer.get_stats)

# ---- Sandbox Operations ----
# ⚠️ 安全：/api/sandbox/* 属高危 RCE 面（经 DeerFlow 本地 provider 在宿主机执行任意命令）。
# 默认关闭（config.SANDBOX_API_ENABLED=False），仅受信任环境显式开启。开启前请确保
# 已配置真正的隔离 provider（容器/WASM），而非在宿主机直接执行。

class SandboxExecRequest(BaseModel):
    command: str
    thread_id: str = ""
    confirm: bool = False  # 安全边界：SANDBOX_REQUIRE_CONFIRM=True 时必须为 True


# ── 安全边界：sandbox exec 命令白名单校验 ──────────────────────────────────
# 只有以 SANDBOX_ALLOWED_COMMANDS 中某个前缀开头的命令才被放行。
# 这是 defense-in-depth 的一层；真正的隔离应由底层 sandbox provider 保证。
def _is_command_allowed(command: str) -> bool:
    """检查命令是否匹配白名单中的某个前缀，并检测命令拼接攻击。"""
    stripped = command.strip()
    
    # 1. 检测命令拼接操作符
    dangerous_operators = [";", "|", "&", "&&", "||", ">", ">>", "<", "`", "$(", "$("]
    for op in dangerous_operators:
        if op in stripped:
            logger.warning(
                "sandbox_exec 拒绝：检测到命令拼接操作符 (operator=%s, command=%.120s)", op, stripped,
            )
            return False
    
    # 2. 精确匹配：命令第一个token必须在白名单中
    tokens = stripped.split()
    if not tokens:
        return False
    
    first_token = tokens[0]
    for prefix in config.SANDBOX_ALLOWED_COMMANDS:
        if first_token == prefix or first_token.startswith(prefix + " ") or first_token.startswith(prefix + "\t"):
            return True
    
    return False


@app.post("/api/sandbox/acquire")
async def sandbox_acquire(thread_id: str = ""):
    if not config.SANDBOX_API_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Sandbox API disabled (AOS_SANDBOX_API_ENABLED=false). "
                   "It executes commands on the host via the local provider; enable only in trusted environments.",
        )
    # 首触/获取沙箱可能触发 brain 构造或宿主调用，整体移入线程池。
    def _acq():
        sb = brain.deerflow.sandbox
        return {"sandbox_id": sb.acquire(), "provider": type(sb._provider).__name__}
    return await asyncio.to_thread(_acq)

@app.post("/api/sandbox/exec")
async def sandbox_exec(req: SandboxExecRequest, request: Request):
    # ── 安全边界：此端点为高危 RCE 面，多层防护 ──
    # 认证已在 APISecurityMiddleware 中间件处理（Bearer JWT / API Key / 上游令牌）
    # 无需再次调用 authenticate_user

    if not config.SANDBOX_API_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Sandbox exec API disabled (AOS_SANDBOX_API_ENABLED=false). "
                   "It executes commands on the host via the local provider; enable only in trusted environments.",
        )

    command = req.command
    if not command or not command.strip():
        raise HTTPException(status_code=400, detail="command must be a non-empty string")

    # 层1：确认机制 — 防止误触或自动化滥用
    if config.SANDBOX_REQUIRE_CONFIRM and not req.confirm:
        logger.warning(
            "sandbox_exec 拒绝：缺少 confirm=true (command=%.120s)", command,
        )
        return {
            "success": False,
            "error": "Confirmation required. Set confirm=true in request body to execute. "
                     "Disable with AOS_SANDBOX_REQUIRE_CONFIRM=false (not recommended).",
        }

    # 层2：命令白名单 — 只允许安全只读操作
    if not _is_command_allowed(command):
        logger.warning(
            "sandbox_exec 拒绝：命令不在白名单中 (command=%.120s)", command,
        )
        return {
            "success": False,
            "error": f"Command not in allowlist. Allowed prefixes: {config.SANDBOX_ALLOWED_COMMANDS}",
        }

    # 层3：执行 — 结构化响应，永不向客户端泄露未处理异常
    sb = None
    try:
        logger.info("sandbox_exec 执行: command=%.120s", command)
        # 创建即执行即释放，避免每次请求泄漏一个未释放的沙箱。
        # 沙箱在宿主执行命令是重阻塞操作，整体移入线程池，避免拖垮事件循环。
        sb = await asyncio.to_thread(brain.deerflow.create_sandbox, thread_id=req.thread_id or None)
        result = await asyncio.to_thread(sb.execute_command, command)
        return {"success": True, "output": result}
    except Exception as e:
        logger.error("sandbox_exec 执行失败: %s", e, exc_info=True)
        return {"success": False, "error": _safe_detail(e)}
    finally:
        if sb is not None:
            try:
                await asyncio.to_thread(sb.release)
            except Exception as e:
                logger.warning("释放沙箱失败: %s", e)

@app.post("/api/sandbox/release")
async def sandbox_release():
    if not config.SANDBOX_API_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Sandbox API disabled (AOS_SANDBOX_API_ENABLED=false).",
        )
    # 释放是宿主调用，移出事件循环。
    def _rel():
        brain.deerflow.sandbox.release()
        return {"success": True}
    return await asyncio.to_thread(_rel)

# ---- Deep Subagent Operations ----

class SubAgentConfigRequest(BaseModel):
    name: str
    description: str
    system_prompt: str = ""
    tools: List[str] = None
    skills: List[str] = None
    model: str = "inherit"
    max_turns: int = 50
    timeout_seconds: int = 900

class SubAgentExecuteRequest(BaseModel):
    name: str
    task: str
    async_mode: bool = False

@app.post("/api/subagents/deep/register")
async def deep_subagent_register(req: SubAgentConfigRequest):
    # 防御式: REAL DeerFlow 网关模式下, 子智能体后端依赖 harness deerflow 包;
    # 若该运行时未导入/缺依赖, 返回干净的 success:false 而非 AttributeError->HTTP 500。
    try:
        def _reg():
            return brain.deerflow.register_subagent(
                name=req.name, description=req.description,
                system_prompt=req.system_prompt or None,
                tools=req.tools, skills=req.skills,
                model=req.model, max_turns=req.max_turns,
                timeout_seconds=req.timeout_seconds,
            )
        cfg = await asyncio.to_thread(_reg)
        return {"success": True, "config": {"name": cfg["name"], "description": cfg["description"]}}
    except Exception as e:
        logger.warning("deep subagent register failed: %s", e)
        return {"success": False, "error": str(e), "available": False}


@app.get("/api/subagents/deep")
async def deep_subagent_list():
    try:
        return {"subagents": await asyncio.to_thread(brain.deerflow.list_subagents)}
    except Exception as e:
        logger.warning("deep subagent list failed: %s", e)
        return {"subagents": [], "success": False, "error": str(e), "available": False}


@app.post("/api/subagents/deep/execute")
async def deep_subagent_execute(req: SubAgentExecuteRequest):
    try:
        thread_id = f"aos-api-{req.name}-{int(time.time())}"
        if req.async_mode:
            task_id = await asyncio.to_thread(
                brain.deerflow.execute_subagent_async, req.name, req.task, thread_id=thread_id)
            return {"task_id": task_id, "mode": "async"}
        result = await asyncio.to_thread(
            brain.deerflow.execute_subagent, req.name, req.task, thread_id=thread_id)
        return result
    except Exception as e:
        logger.warning("deep subagent execute failed: %s", e)
        return {"success": False, "error": str(e), "available": False}


@app.get("/api/subagents/deep/task/{task_id}")
async def deep_subagent_task(task_id: str):
    try:
        result = await asyncio.to_thread(brain.deerflow.get_subagent_result, task_id)
        if not result:
            raise HTTPException(status_code=404, detail="Task not found")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("deep subagent task query failed: %s", e)
        return {"success": False, "error": str(e), "available": False}


@app.post("/api/subagents/deep/task/{task_id}/cancel")
async def deep_subagent_cancel(task_id: str):
    try:
        await asyncio.to_thread(brain.deerflow.cancel_subagent, task_id)
        return {"success": True}
    except Exception as e:
        logger.warning("deep subagent cancel failed: %s", e)
        return {"success": False, "error": str(e), "available": False}


# ---- ViMax Video API ----

class ViMaxRequest(BaseModel):
    workflow: str = Field(..., description="工作流类型: idea2video/novel2video/script2video/autocameo")
    input: str = Field(..., description="输入内容")
    params: Optional[Dict[str, Any]] = Field(default={}, description="可选参数")


@app.get("/api/vimax/workflows")
async def vimax_workflows():
    """列出所有 ViMax 工作流"""
    try:
        from skills.vimax import VIMAX_WORKFLOWS
        return {"workflows": VIMAX_WORKFLOWS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/vimax/generate")
async def vimax_generate(req: ViMaxRequest):
    """生成视频"""
    try:
        result = await asyncio.to_thread(brain.subagents.invoke, "vimax", {
            "workflow": req.workflow,
            "input": req.input,
            "params": req.params
        })
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/vimax/task/{task_id}")
async def vimax_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.vimax import get_vimax_skill
        def _st():
            skill = get_vimax_skill()
            return skill.get_status(task_id)
        status = await asyncio.to_thread(_st)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/vimax/configure")
async def vimax_configure(api_keys: Dict[str, str]):
    """配置 ViMax API 密钥"""
    try:
        from subagents.vimax_agent import get_vimax_subagent
        agent = get_vimax_subagent()
        await asyncio.to_thread(agent.configure, api_keys)
        return {"success": True, "configured_keys": list(api_keys.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- IMA (Tencent Knowledge Base) API ----

class IMARequest(BaseModel):
    operation: str = Field(..., description="操作类型: search_knowledge/search_knowledge_base/get_knowledge_base/list_knowledge/create_note/store_handoff/get_handoff/search_handoffs")
    input: str = Field(default="", description="检索关键词 / 笔记内容（视 operation 而定）")
    params: Optional[Dict[str, Any]] = Field(default={}, description="操作专属参数（knowledge_base_id/title/content/...）")


@app.get("/api/ima/operations")
async def ima_operations():
    """列出所有 IMA 操作"""
    try:
        from skills.ima import IMA_OPERATIONS
        return {"operations": IMA_OPERATIONS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ima/execute")
async def ima_execute(req: IMARequest):
    """执行 IMA 操作（知识检索 / 笔记读写）"""
    try:
        params = dict(req.params or {})
        payload = {"operation": req.operation, "input": req.input, **params}
        result = await asyncio.to_thread(brain.subagents.invoke, "ima", payload)
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "IMA 执行失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/ima/task/{task_id}")
async def ima_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.ima import get_ima_skill
        def _st():
            skill = get_ima_skill()
            return skill.get_status(task_id)
        status = await asyncio.to_thread(_st)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ima/configure")
async def ima_configure(api_keys: Dict[str, str]):
    """配置 IMA API 密钥"""
    try:
        from subagents.ima_agent import get_ima_subagent
        agent = get_ima_subagent()
        await asyncio.to_thread(agent.configure, api_keys)
        return {"success": True, "configured_keys": list(api_keys.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Meeting Agent API ----
class MeetingRequest(BaseModel):
    transcript: Optional[str] = Field(default=None, description="会议转录文本（无音频时必填）")
    audio_path: Optional[str] = Field(default=None, description="音频文件路径（服务端 STT）")
    audio_b64: Optional[str] = Field(default=None, description="音频 base64（前端直传）")
    audio_suffix: str = Field(default="wav", description="音频后缀（audio_b64 时，默认 wav）")
    task_id: Optional[str] = Field(default=None, description="任务 ID（缺省自动生成）")
    title: Optional[str] = Field(default=None, description="会议标题（缺省自动生成）")
    attendees: Optional[str] = Field(default=None, description="参会人（可选，写入交接信封）")
    auto_handoff: bool = Field(default=True, description="是否把结构化会议交接信封存 IMA 知识库")


@app.post("/api/meeting/run")
async def meeting_run(req: MeetingRequest):
    """运行会议自动化流水线：转录 → 摘要/行动项 → 结构化交接存 IMA"""
    try:
        from subagents.meeting_agent import get_meeting_subagent
        payload = req.model_dump(exclude_none=True)
        agent = get_meeting_subagent()
        result = await asyncio.to_thread(agent.handle, payload)
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "会议流水线执行失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/meeting/operations")
async def meeting_operations():
    """列出会议子智能体支持的操作"""
    try:
        from subagents.meeting_agent import MeetingAgent
        return {"operations": MeetingAgent.OPERATIONS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Orchestrator API ----
class OrchestratorRunRequest(BaseModel):
    task_id: Optional[str] = Field(None, description="任务 ID（缺省自动生成）")
    steps: List[Dict[str, Any]] = Field(..., description="流水线步骤定义（每步: capability + in/in_from）")
    initial: Optional[Dict[str, Any]] = Field(default={}, description="初始上下文（首步输入）")
    auto_handoff: bool = Field(False, description="收尾自动存结构化交接信封存 IMA 知识库")
    parallel_groups: Optional[List[Any]] = Field(None, description="并行分组（可选，进阶用法）")
    review_mode: str = Field("", description="审核模式：'gate' 开启步骤级审核封驳（敏感步执行前需人工准/驳）")


@app.post("/api/orchestrator/run")
async def orchestrator_run(req: OrchestratorRunRequest):
    """运行多芯粒编排流水线（system.workflow）。

    把 steps 按序/并行串联，每步经 fabric 能力路由委派给 live 引擎；
    设 auto_handoff=true 时，收尾自动把结构化交接信封存 IMA 知识库。
    流水线逻辑在 OrchestrationChiplet，路由复用 FabricHub（单一可信源）。
    """
    try:
        from aos_mcp.protocol import _get_hub
        from core.fabric.capability import Capability
        hub = _get_hub()
        # 编排芯粒已在 build_fabric_hub 注册；此处幂等确保存在
        try:
            if hub.resolve_engine(Capability.WORKFLOW_EXECUTE.value) is None:
                hub.add_orchestrator()
        except Exception:
            pass
        spec: Dict[str, Any] = {
            "steps": req.steps,
            "initial": req.initial or {},
            "auto_handoff": req.auto_handoff,
        }
        if req.task_id:
            spec["task_id"] = req.task_id
        if req.parallel_groups:
            spec["parallel_groups"] = req.parallel_groups
        if req.review_mode:
            spec["review_mode"] = req.review_mode
        res = await asyncio.to_thread(hub.route, Capability.WORKFLOW_EXECUTE.value, spec)
        return {
            "success": getattr(res, "ok", False),
            "data": getattr(res, "data", None),
            "error": getattr(res, "error", None),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/orchestrator/render")
async def orchestrator_render(req: OrchestratorRunRequest):
    """运行多芯粒编排流水线并渲染为 A2UI 可视化 HTML（可直接浏览器查看）。

    复用 OrchestrationChiplet.render_orchestration_result 把 trace 转成 A2UI
    surface 并安全渲染（声明式、不执行代码、不注入 HTML）；编排失败时诚实
    降级为错误 surface，不伪造成功报告。流水线逻辑同 /api/orchestrator/run。
    """
    try:
        from aos_mcp.protocol import _get_hub
        from core.fabric.capability import Capability
        from kernel.plugins.orchestration_chiplet import render_orchestration_result
        hub = _get_hub()
        # 编排芯粒已在 build_fabric_hub 注册；此处幂等确保存在
        try:
            if hub.resolve_engine(Capability.WORKFLOW_EXECUTE.value) is None:
                hub.add_orchestrator()
        except Exception:
            pass
        spec: Dict[str, Any] = {
            "steps": req.steps,
            "initial": req.initial or {},
            "auto_handoff": req.auto_handoff,
        }
        if req.task_id:
            spec["task_id"] = req.task_id
        if req.parallel_groups:
            spec["parallel_groups"] = req.parallel_groups
        if req.review_mode:
            spec["review_mode"] = req.review_mode
        res = await asyncio.to_thread(hub.route, Capability.WORKFLOW_EXECUTE.value, spec)
        html = render_orchestration_result(res, standalone=True)
        return Response(content=html, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/route/predictor")
async def route_predictor_diagnostics():
    """路由预测器状态快照（只读可观测端点）。

    返回当前 FabricHub 注册表里的 learned 策略诊断：是否已注入 predictor /
    是否已训练 / 落盘样本数 / 最小训练阈值 / 词汇表规模 / 对各已注册能力×引擎
    的预测成功概率。无 predictor（默认 preference 策略）时诚实返回「未启用」。

    对应 AOS 第 9 条「可验证即真理」——路由学了什么必须可查、不黑盒。
    """
    try:
        from aos_mcp.protocol import _get_hub
        hub = _get_hub()
        return hub._registry.predictor_diagnostics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- RuFlo API ----

class RuFloRequest(BaseModel):
    task: str = Field(..., description="任务类型: code_gen/code_review/test_gen/security_audit/architect_design/full_stack/data_pipeline/deploy")
    input: str = Field(..., description="任务描述")
    agents: Optional[List[str]] = Field(default=[], description="指定智能体列表")
    params: Optional[Dict[str, Any]] = Field(default={}, description="额外参数")


@app.get("/api/ruflo/agents")
async def ruflo_agents():
    """列出所有 RuFlo 智能体"""
    try:
        from skills.ruflo import RUFLO_AGENTS
        return {"agents": RUFLO_AGENTS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/ruflo/tasks")
async def ruflo_tasks():
    """列出所有 RuFlo 任务类型"""
    try:
        from skills.ruflo import RUFLO_TASKS
        return {"tasks": RUFLO_TASKS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ruflo/execute")
async def ruflo_execute(req: RuFloRequest):
    """执行 RuFlo 开发任务"""
    try:
        result = await asyncio.to_thread(brain.subagents.invoke, "ruflo", {
            "task": req.task,
            "input": req.input,
            "agents": req.agents,
            "params": req.params
        })
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/ruflo/task/{task_id}")
async def ruflo_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.ruflo import get_ruflo_skill
        def _st():
            skill = get_ruflo_skill()
            return skill.get_task_status(task_id)
        status = await asyncio.to_thread(_st)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ruflo/configure")
async def ruflo_configure(api_key: str):
    """配置 RuFlo API 密钥"""
    try:
        from subagents.ruflo_agent import get_ruflo_subagent
        agent = get_ruflo_subagent()
        await asyncio.to_thread(agent.configure, api_key)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Ollama API ----

class OllamaRequest(BaseModel):
    action: str = Field("chat", description="操作类型: chat/generate/list_models/pull_model/delete_model/embeddings/show_model")
    model: Optional[str] = Field("qwen2.5:7b", description="模型名称")
    message: Optional[str] = Field(None, description="聊天消息")
    prompt: Optional[str] = Field(None, description="生成提示词")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外参数")


@app.get("/api/ollama/models")
async def ollama_models():
    """列出 Ollama 可用模型"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "ollama", {"action": "list_models"})
        if result.get("success"):
            return result
        else:
            return {"models": [], "count": 0, "ollama_available": result.get("ollama_available", False)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ollama/chat")
async def ollama_chat(req: OllamaRequest):
    """Ollama 聊天"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "ollama", {
            "action": "chat",
            "model": req.model,
            "message": req.message or req.prompt or "",
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ollama/generate")
async def ollama_generate(req: OllamaRequest):
    """Ollama 文本生成"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "ollama", {
            "action": "generate",
            "model": req.model,
            "prompt": req.prompt or req.message or "",
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ollama/embeddings")
async def ollama_embeddings(req: OllamaRequest):
    """Ollama 生成嵌入向量"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "ollama", {
            "action": "embeddings",
            "model": req.model,
            "prompt": req.prompt or req.message or "",
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/ollama/pull")
async def ollama_pull(model: str):
    """拉取 Ollama 模型"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "ollama", {
            "action": "pull_model",
            "model": model,
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "拉取失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/ollama/status")
async def ollama_status():
    """检查 Ollama 服务状态"""
    try:
        # requests.get 是同步阻塞网络调用，整体移入线程池，避免阻塞事件循环。
        def _status():
            import requests
            resp = requests.get("http://localhost:11434/api/tags", timeout=3)
            running = resp.status_code == 200
            models = resp.json().get("models", []) if running else []
            return {
                "running": running,
                "url": "http://localhost:11434",
                "model_count": len(models),
                "models": [m["name"] for m in models],
            }
        return await asyncio.to_thread(_status)
    except Exception as e:
        return {"running": False, "url": "http://localhost:11434", "error": str(e)}


# ---- UI-TARS API ----

class UITARSRequest(BaseModel):
    action: str = Field("task_execution", description="操作类型: desktop_automation/browser_automation/screen_capture/visual_qa/task_execution")
    task: str = Field(..., description="任务描述")
    max_steps: Optional[int] = Field(20, description="最大步骤数")
    timeout: Optional[int] = Field(300, description="超时时间(秒)")
    params: Optional[Dict[str, Any]] = Field(default_factory=dict, description="额外参数")


@app.get("/api/uitars/features")
async def uitars_features():
    """列出 UI-TARS 功能"""
    try:
        from skills.uitars import UITARS_FEATURES, UITARS_PRESETS
        return {
            "features": UITARS_FEATURES,
            "presets": UITARS_PRESETS,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/uitars/execute")
async def uitars_execute(req: UITARSRequest):
    """执行 UI-TARS 自动化任务"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "uitars", {
            "action": req.action,
            "task": req.task,
            "max_steps": req.max_steps,
            "timeout": req.timeout,
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/uitars/status")
async def uitars_status():
    """检查 UI-TARS 状态"""
    try:
        from deerflow.path_detect import detect_uitars_path
        uitars_path = await asyncio.to_thread(detect_uitars_path)
        return {
            "source_available": uitars_path is not None,
            "source_path": uitars_path or "未检测到",
            "cli_command": "npx @agent-tars/cli@latest",
            "capabilities": [
                "desktop_automation",
                "browser_automation",
                "screen_capture",
                "mouse_keyboard_control",
                "visual_qa",
                "task_execution",
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Pixelle-Video API ----

class PixelleRequest(BaseModel):
    topic: str = Field(..., description="视频主题")
    style: Optional[str] = Field(default="douyin", description="视频风格")
    duration: Optional[int] = Field(default=60, description="视频时长(秒)")
    voice: Optional[str] = Field(default="female", description="配音类型")


@app.get("/api/pixelle/styles")
async def pixelle_styles():
    """列出所有 Pixelle-Video 风格"""
    try:
        from skills.pixelle_video import PIXELLE_STYLES
        return {"styles": PIXELLE_STYLES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/pixelle/voices")
async def pixelle_voices():
    """列出所有 Pixelle-Video 配音"""
    try:
        from skills.pixelle_video import PIXELLE_VOICES
        return {"voices": PIXELLE_VOICES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/pixelle/generate")
async def pixelle_generate(req: PixelleRequest):
    """生成短视频"""
    try:
        result = await asyncio.to_thread(brain.subagents.invoke, "pixelle_video", {
            "topic": req.topic,
            "style": req.style,
            "duration": req.duration,
            "voice": req.voice,
        })
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/pixelle/task/{task_id}")
async def pixelle_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.pixelle_video import get_pixelle_skill
        def _st():
            skill = get_pixelle_skill()
            return skill.get_task_status(task_id)
        status = await asyncio.to_thread(_st)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Loop Engineering API ----

class LoopRequest(BaseModel):
    action: Optional[str] = Field(default="run", description="操作类型")
    template: Optional[str] = Field(default="code_gen", description="循环模板")
    goal: Optional[str] = Field(default="", description="目标描述")
    criteria: Optional[List[str]] = Field(default=[], description="验收标准")
    input: str = Field(..., description="输入数据")
    max_iterations: Optional[int] = Field(default=5, description="最大迭代次数")


@app.get("/api/loop/templates")
async def loop_templates():
    """列出所有循环模板"""
    try:
        from skills.loop_engineering import LOOP_TEMPLATES
        return {"templates": LOOP_TEMPLATES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/loop/components")
async def loop_components():
    """列出所有核心组件"""
    try:
        from skills.loop_engineering import LOOP_COMPONENTS
        return {"components": LOOP_COMPONENTS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/loop/execute")
async def loop_execute(req: LoopRequest):
    """执行循环"""
    try:
        result = await asyncio.to_thread(brain.subagents.invoke, "loop_engineering", {
            "action": req.action,
            "template": req.template,
            "goal": req.goal,
            "criteria": req.criteria,
            "input": req.input,
            "max_iterations": req.max_iterations,
        })
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "执行失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/loop/status/{loop_id}")
async def loop_status(loop_id: str):
    """查询循环状态"""
    try:
        from skills.loop_engineering import get_loop_skill
        def _st():
            skill = get_loop_skill()
            return skill._get_loop_status({"loop_id": loop_id})
        return await asyncio.to_thread(_st)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/loop/list")
async def loop_list():
    """列出所有循环"""
    try:
        from skills.loop_engineering import get_loop_skill
        def _lst():
            skill = get_loop_skill()
            return skill._list_loops({})
        return await asyncio.to_thread(_lst)
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


class AutopilotRequest(BaseModel):
    task: str = Field(..., description="一句话自然语言任务")
    planner: str = Field(default="ag2", description="ag2 / zhipu / heuristic（ag2 不可用自动降级智谱）")
    run_id: Optional[str] = Field(default=None)


@app.post("/api/autopilot/run")
async def autopilot_run(req: AutopilotRequest):
    """一句话触发 AOS 自主闭环（规划/反思走智谱直连，无需 ag2/ollama）。

    服务器常驻即可调用，无需单独启任何组件——发一句任务，自主环自己规划、
    执行、反思、落盘 Trace。
    """
    try:
        from kernel.autopilot import run as _ap_run
        result = await asyncio.to_thread(_ap_run, req.task, req.planner, req.run_id)
        return {"ok": True, "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Manage Provider (for failover) ----

@app.post("/api/providers/switch")
async def switch_provider(provider: str):
    try:
        await asyncio.to_thread(brain.hermes.set_provider, provider)
        brain.audit.log("system.config_change", agent_id=brain.identity.aid,
                        details={"provider": provider})
        return {"success": True, "provider": provider}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ---- Dynamic Routing API ----

class RouteChatRequest(BaseModel):
    message: str = Field(..., description="用户消息")
    task_type: str = Field("general", description="任务类型: coding/high_concurrency/long_context/voice/experiment/general")
    temperature: float = Field(0.7, description="温度参数")
    max_tokens: int = Field(2048, description="最大token数")

@app.post("/api/chat/route")
async def route_chat(req: RouteChatRequest):
    """动态路由聊天 - 根据任务类型自动选择最优模型"""
    try:
        # route_chat 触发 LLM 调用，移出事件循环。
        result = await asyncio.to_thread(
            brain.hermes.route_chat,
            message=req.message,
            task_type=req.task_type,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return result
    except Exception as e:
        logger.error(f"Route chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.get("/api/router/providers")
async def router_providers():
    """获取路由管理器中所有可用提供商"""
    try:
        from router import LLMRouter
        # LLMRouter() 构造 + 探测可用提供商可能做网络探测，移入线程池。
        def _rp():
            r = LLMRouter()
            return {"providers": r.get_available_providers()}
        return await asyncio.to_thread(_rp)
    except Exception as e:
        logger.error(f"Router providers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.get("/api/router/config")
async def router_config():
    """获取路由配置"""
    try:
        return {
            "coding_primary": config.ROUTER_CODING_PRIMARY,
            "high_concurrency_primary": config.ROUTER_HIGH_CONCURRENCY_PRIMARY,
            "long_context_primary": config.ROUTER_LONG_CONTEXT_PRIMARY,
            "voice_primary": config.ROUTER_VOICE_PRIMARY,
            "experiment_primary": config.ROUTER_EXPERIMENT_PRIMARY,
            "fallback": config.ROUTER_FALLBACK,
        }
    except Exception as e:
        logger.error(f"Router config error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=_safe_detail(e))

# ---- Voice API ----

from voice import ASREngine, TTSEngine

asr_engine = ASREngine()
tts_engine = TTSEngine()

@app.post("/api/voice/asr")
async def voice_recognition(audio: bytes = File(...), format: str = "wav"):
    try:
        # ASR 模型推理是 CPU 重阻塞，移入线程池避免拖垮事件循环。
        result = await asyncio.to_thread(asr_engine.recognize, audio, format=format)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"ASR error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.post("/api/voice/tts")
async def voice_synthesis(text: str, voice: str = "zh", speed: float = 1.0, pitch: float = 0.0):
    try:
        # TTS 合成是模型推理重阻塞，移入线程池。
        result = await asyncio.to_thread(tts_engine.synthesize, text, voice=voice, speed=speed, pitch=pitch)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return Response(content=result["audio"], media_type=result["content_type"])
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))

@app.post("/api/voice/chat")
async def voice_chat(audio: bytes = File(...), format: str = "wav", session_id: str = None):
    try:
        # ASR + LLM chat + TTS 三段都是重阻塞（模型推理），逐段移入线程池，
        # 任一段都不应阻塞事件循环（否则一个语音对话卡住所有并发请求）。
        asr_result = await asyncio.to_thread(asr_engine.recognize, audio, format=format)
        if not asr_result["success"]:
            raise HTTPException(status_code=400, detail=asr_result["error"])

        text = asr_result["text"]
        chat_result = await asyncio.to_thread(brain.chat, message=text, session_id=session_id)

        tts_result = await asyncio.to_thread(tts_engine.synthesize, chat_result.get("response", ""))
        if not tts_result["success"]:
            return {
                "recognized_text": text,
                "response": chat_result.get("response", ""),
                "audio": None,
                "error": tts_result["error"],
            }
        
        return {
            "recognized_text": text,
            "response": chat_result.get("response", ""),
            "audio": base64.b64encode(tts_result["audio"]).decode(),
            "provider": tts_result.get("provider", ""),
        }
    except Exception as e:
        logger.error(f"Voice chat error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))

# ---- Multimodal API ----

@app.post("/api/groupchat")
async def api_groupchat(message: str, agents: Optional[List[str]] = None):
    """真实 AG2 群聊编排入口 (满足铁律: 群聊/多智能体由真实开源 AG2 驱动)。

    经 fabric 薄缝统一入口 route_capability 路由到 live 的 AG2 适配器 (真实 GroupChat)。
    若 AG2 不可用 (未装 ag2 / 无 LLM key), 返回 503 而非假装成功。
    """
    try:
        # route_capability 可能触发 AG2 群聊编排（LLM 推理），移出事件循环。
        res = await asyncio.to_thread(brain.route_capability, "group.orchestration", {"text": message})
        if res is None or not res.ok:
            raise HTTPException(
                status_code=503,
                detail="AG2 group orchestration unavailable (ag2 not live / no LLM key)",
            )
        return {
            "engine": "ag2",
            "group_chat": True,
            "reply": (res.data or {}).get("reply", ""),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Group chat error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/capability/{capability}")
async def api_resolve_engine(capability: str):
    """能力→引擎 单一可信源 introspection (fabric 真实调用面, 非死设计)。"""
    engine = await asyncio.to_thread(brain.resolve_engine, capability)
    return {"capability": capability, "engine": engine, "live": engine is not None}


_fabric_hub_cache = None


async def _get_fabric_hub():
    """懒加载并缓存 FabricHub 单例——全局唯一实例，由 fabric_hub.get_fabric_hub() 管理。

    所有模块（API / Studio / Hub / Evolve / AutoSkill / MCP）共享同一个实例，
    确保能力路由、健康状态、记忆门面全链路一致。
    """
    global _fabric_hub_cache
    if _fabric_hub_cache is None:
        from kernel.plugins.fabric_hub import get_fabric_hub
        _fabric_hub_cache = await asyncio.to_thread(get_fabric_hub)
    return _fabric_hub_cache


@app.get("/api/fabric/health")
async def api_fabric_health():
    """fabric 薄适配层通电自检：诚实报告每个真实 OSS 引擎 live/dead。

    返回 {total, live, adapters:{engine:{live,capabilities,error}}, registration_errors}。
    这是「知道自己现在到底行不行」的对外落地（MASTER_PLAN 阶段 1.2）。
    """
    global _fabric_hub_cache
    try:
        hub = await _get_fabric_hub()
        return await asyncio.to_thread(_fabric_hub_cache.health_report)
    except Exception as e:  # noqa: BLE001
        return {"error": _safe_detail(e)}


@app.get("/api/skills")
async def api_skills(capability: str = "", category: str = ""):
    """Skill 生态化对外接口：查询 AOS 所有技能或按能力发现技能。

    - GET /api/skills → 全部技能的摘要（id/name/category/capabilities/status）
    - GET /api/skills?capability=web.search → 只返回声明 web.search 的能力技能
    - GET /api/skills?category=xxx → capability 的兼容别名（旧客户端）

    数据源为 skills/manifest.json（单一真相），零导入开销（纯 json 读），
    不触发 skills/__init__.py 的急加载链。

    注：旧版走 brain.hermes.list_skills 的实现已被本路由替代（修复 P0-3 重复注册），
    旧 ?category= 参数作为 capability 的别名保留，行为等价。
    """
    try:
        from kernel.skill_registry import get_skill_registry
        reg = get_skill_registry()
        # 兼容旧 ?category= 参数：作为 capability 的别名（修复 P0-3）
        cap = capability or category
        if cap:
            skills = reg.discover(cap)
            return {"capability": cap, "skills": skills, "total": len(skills)}
        return {"skills": [{"id": s["id"], "name": s["name"], "category": s["category"],
                             "capabilities": s["capabilities"], "status": s["status"]}
                           for s in reg.list_all()],
                "total": len(reg.list_all()),
                "summary": reg.summary()}
    except Exception as e:  # noqa: BLE001
        return {"error": _safe_detail(e)}


@app.get("/api/failure_monitor")
async def failure_monitor_api():
    """MAST 式多智能体失败监控快照（只读）：失败率/按模式计数/告警/最近失败。

    failure_monitor.py 此前是死模块（全仓无任何调用）；本次通电——它已被
    FabricHub.route() 的真实失败流量埋点，并经此端点对外可观测。零重型依赖、
    纯内存，瞬时返回。route() 成功/失败均会喂数据，故 stats 反映真实路由健康。
    """
    try:
        from kernel.plugins.failure_monitor import get_failure_monitor
        mon = get_failure_monitor()
        stats = mon.get_stats()
        return {
            "status": "ok",
            "stats": stats,
            "recent_failures": mon.get_recent_failures(20),
            "alerts": stats.get("alerts", []),
            "uptime_seconds": stats.get("uptime_seconds"),
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/memory/hippo/status")
async def hippo_scroll_status():
    """Hippo-Scroll 可信记忆引擎状态（只读）：真实调用其检索，非假数据。

    返回：总物证锚点数、总认知节点数、认知轨冲突发现数、一次真实 retrieve 示例。
    引擎未挂载（startup 失败）时返回 503，不伪造成功。
    """
    engine = getattr(app.state, "hippo_scroll", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="hippo-scroll engine not mounted")
    try:
        conflicts = engine.cognition.find_conflicts()
        sample_retrieve = engine.retrieve("猫", top_k=3)
        return {
            "status": "ok",
            "total_anchors": engine.evidence.total_anchors,
            "total_nodes": engine.cognition.total_nodes,
            "conflicts_found": len(conflicts),
            "sample_query": "猫",
        "sample_retrieve": sample_retrieve,
    }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/content/produce")
async def content_produce(request: Request):
    """一句话目标 → 自主内容生产（检索→分析→剧本→导演→工具→审核包）。

    默认停在审核（human-in-the-loop），不自动发布；auto_publish=true 仅用于
    无人值守流水线。导演未挂载返回 503，缺 goal 返回 400。
    """
    director = getattr(app.state, "content_director", None)
    if director is None:
        raise HTTPException(status_code=503, detail="content director not mounted")
    try:
        body = await request.json()
        goal = (body.get("goal") or "").strip()
        if not goal:
            raise HTTPException(status_code=400, detail="缺少 goal")
        auto_publish = bool(body.get("auto_publish", False))
        reference_image = (body.get("reference_image") or None)
        # 重活丢线程池，避免阻塞事件循环
        result = await asyncio.to_thread(
            director.produce, goal, auto_publish=auto_publish,
            reference_image=reference_image)
        return {
            "status": "ok",
            "task_id": result.task_id,
            "goal": result.goal,
            "stages": result.stages,
            "materials": result.materials,
            "analysis": result.analysis,
            "script_path": result.script_path,
            "shots": result.shots,
            "review_id": result.review_id,
            "review_path": result.review_path,
            "published": result.published,
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/content/review/{review_id}")
async def content_review(review_id: str):
    """读取审核包（reviews/{id}.md），真实返回内容，非假数据。不存在返回 404。"""
    director = getattr(app.state, "content_director", None)
    if director is None:
        raise HTTPException(status_code=503, detail="content director not mounted")
    try:
        import os
        review_path = os.path.join(director._work_root, "reviews", f"{review_id}.md")
        if not os.path.isfile(review_path):
            raise HTTPException(status_code=404, detail="审核包不存在")
        with open(review_path, "r", encoding="utf-8") as f:
            return {"status": "ok", "review_id": review_id, "content": f.read()}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/content/approve/{review_id}")
async def content_approve(review_id: str, request: Request = None):
    """审核通过 → 自动发布（落 published/ + 记 IMA 发布）。human-in-the-loop 解锁。"""
    director = getattr(app.state, "content_director", None)
    if director is None:
        raise HTTPException(status_code=503, detail="content director not mounted")
    try:
        notes = ""
        if request is not None:
            try:
                body = await request.json()
                notes = body.get("notes", "") or ""
            except Exception:  # noqa: BLE001
                notes = ""
        pub = director.approve(review_id, notes=notes)
        return {
            "status": "ok" if pub.ok else "error",
            "task_id": pub.task_id,
            "review_id": pub.review_id,
            "published_path": pub.published_path,
            "ima_stored": pub.ima_stored,
            "error": pub.error,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/live/status")
async def live_evolution_status():
    """活体进化闭环状态（只读）：真实调用 engine.status()，非假数据。

    返回：当前代、种群规模、完成任务数、淘汰数、孵化数、Top Agent 与适应度。
    引擎未挂载（startup 失败/沙箱无内核）时返回 503，不伪造成功。
    """
    engine = getattr(app.state, "live_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="live evolution engine not mounted")
    try:
        s = engine.status()
        return {
            "status": "ok",
            "generation": s.generation,
            "population": s.population,
            "tasks_completed": s.tasks_completed,
            "eliminations": s.eliminations,
            "spawns": s.spawns,
            "heal_events": s.heal_events,
            "anomaly_alerts": s.anomaly_alerts,
            "total_tokens": s.total_tokens,
            "top_agent": s.top_agent,
            "top_fitness": round(s.top_fitness, 4),
            "uptime_seconds": s.uptime_seconds,
        }
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_safe_detail(e))



@app.post("/api/multimodal/chat")
async def multimodal_chat(
    message: str,
    image: Optional[UploadFile] = None,
    session_id: Optional[str] = None,
):
    try:
        image_data = None
        if image:
            image_bytes = await image.read()
            image_data = {
                "name": image.filename,
                "size": len(image_bytes),
                "content_type": image.content_type,
            }
        
        result = await asyncio.to_thread(brain.chat, message=message, session_id=session_id)
        
        return {
            "success": True,
            "response": result.get("response", ""),
            "session_id": result.get("session_id", ""),
            "image_processed": image_data is not None,
            "image_info": image_data,
        }
    except Exception as e:
        logger.error(f"Multimodal chat error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))

# ---- ComfyUI Visual Generation API ----

class ComfyUIRequest(BaseModel):
    action: str = Field("txt2img", description="操作类型: txt2img/img2vid/style_transfer/vid2vid/generate/list_workflows/status")
    prompt: Optional[str] = Field(None, description="提示词")
    negative_prompt: Optional[str] = Field("", description="负向提示词")
    width: Optional[int] = Field(1024, description="图像宽度")
    height: Optional[int] = Field(768, description="图像高度")
    image_path: Optional[str] = Field(None, description="输入图像路径")
    video_path: Optional[str] = Field(None, description="输入视频路径")
    reference_image: Optional[str] = Field(None, description="参考图像路径")
    duration: Optional[int] = Field(5, description="视频时长")
    style: Optional[str] = Field(None, description="风格类型")
    workflow: Optional[str] = Field("txt2img", description="工作流名称")


@app.get("/api/comfyui/status")
async def comfyui_status():
    """检查 ComfyUI 服务状态"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {"action": "status"})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/comfyui/workflows")
async def comfyui_workflows():
    """列出所有可用工作流"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {"action": "list_workflows"})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/comfyui/txt2img")
async def comfyui_txt2img(req: ComfyUIRequest):
    """文生图"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {
            "action": "txt2img",
            "prompt": req.prompt or "",
            "negative_prompt": req.negative_prompt or "",
            "width": req.width or 1024,
            "height": req.height or 768,
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/comfyui/img2vid")
async def comfyui_img2vid(req: ComfyUIRequest):
    """图生视频"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {
            "action": "img2vid",
            "image_path": req.image_path or "",
            "prompt": req.prompt or "",
            "duration": req.duration or 5,
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/comfyui/style_transfer")
async def comfyui_style_transfer(req: ComfyUIRequest):
    """风格迁移"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {
            "action": "style_transfer",
            "image_path": req.image_path or "",
            "reference_image": req.reference_image or "",
            "style_prompt": req.prompt or "",
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/comfyui/vid2vid")
async def comfyui_vid2vid(req: ComfyUIRequest):
    """视频生视频"""
    try:
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", {
            "action": "vid2vid",
            "video_path": req.video_path or "",
            "prompt": req.prompt or "",
            "style": req.style or "",
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/comfyui/generate")
async def comfyui_generate(req: ComfyUIRequest):
    """通用生成"""
    try:
        params = {"action": "generate", "workflow": req.workflow or "txt2img"}
        if req.prompt:
            params["prompt"] = req.prompt
        if req.negative_prompt:
            params["negative_prompt"] = req.negative_prompt
        if req.width:
            params["width"] = req.width
        if req.height:
            params["height"] = req.height
        if req.image_path:
            params["image_path"] = req.image_path
        if req.video_path:
            params["video_path"] = req.video_path
        
        result = await asyncio.to_thread(brain.skill_registry.execute, "comfyui", params)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- A2UI（Agent-to-UI，v0.9）----

class A2UIRenderRequest(BaseModel):
    surface: Optional[Dict[str, Any]] = None
    messages: Optional[List[Dict[str, Any]]] = None


@app.post("/api/a2ui/render")
async def a2ui_render(request: A2UIRenderRequest):
    """把 A2UI surface / 消息列表渲染为安全 HTML（声明式、不执行代码）。

    输入：{"surface": <合并 surface>} 或 {"messages": [<v0.9 信封>]}。
    输出：{"html": "<div class='a2ui-surface'>...</div>"}。
    """
    try:
        if request.surface is not None:
            html = a2ui_mod.render_html(request.surface, standalone=False)
        elif request.messages is not None:
            html = a2ui_mod.render_a2ui({"messages": request.messages}, standalone=False)
        else:
            raise ValueError("须提供 surface 或 messages")
        return {"html": html}
    except Exception as e:
        raise HTTPException(status_code=400, detail=_safe_detail(e))


@app.get("/api/a2ui/demo")
async def a2ui_demo():
    """返回自包含 A2UI 演示 HTML（AOS 用 A2UI 协议生成的界面）。"""
    try:
        html = a2ui_mod.render_html(a2ui_mod._demo_surface(), standalone=True)
        return Response(content=html, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.get("/api/a2ui/hub")
async def a2ui_hub():
    """AOS 可视化交付物目录：一页列出所有 A2UI 可视化端点（浏览器可看）。

    用 A2UI 协议自身渲染（声明式、安全），把散落的可视化端点收敛成一个
    可发现入口。目录内容为静态说明，仍经 lit() 转义。
    """
    try:
        entries = [
            {"title": "编排流水线可视化", "method": "POST",
             "path": "/api/orchestrator/render",
             "desc": "运行编排芯粒流水线，把端到端 trace（每步能力/成功失败/"
                     "最终结果）渲染成 A2UI 报告；失败诚实降级为错误 surface。"},
            {"title": "代码团队可视化", "method": "POST",
             "path": "/api/code_team/render",
             "desc": "多智能体代码团队：自然语言需求 → 生成代码 + 质量门 + "
                     "真实测试验证，结果渲染成 A2UI 结构化交付物。"},
            {"title": "A2UI 通用渲染", "method": "POST",
             "path": "/api/a2ui/render",
             "desc": "把任意 A2UI surface / v0.9 消息列表渲染为安全 HTML 片段。"},
            {"title": "A2UI 演示", "method": "GET",
             "path": "/api/a2ui/demo",
             "desc": "自包含 A2UI 协议演示界面（声明式、安全渲染）。"},
            {"title": "路由预测器可观测", "method": "GET",
             "path": "/api/route/predictor",
             "desc": "learned 策略下路由预测器的只读快照：是否已训练、样本数、"
                     "各能力×引擎的预测成功概率；无 predictor（preference 策略）时诚实返回未启用。"},
        ]
        surface = a2ui_mod.build_index_surface(
            "AOS 可视化交付物目录",
            entries,
            subtitle="所有面板由 A2UI 协议声明式渲染 · 不执行代码 · 跨信任边界安全",
        )
        html = a2ui_mod.render_html(surface, standalone=True)
        return Response(content=html, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


class CodeTeamRequest(BaseModel):
    requirement: str
    lang: str = "python"


class ComplianceGateRequest(BaseModel):
    files: dict[str, str]


@app.get("/api/code_team/languages")
async def code_team_languages():
    """代码团队当前支持的编程语言（可发现性）。

    多语言由 code_team._LANGS 单一事实源驱动；此端点只读暴露，
    方便前端/调用方在提交需求前选择 lang（如 python / javascript）。
    """
    return {"languages": supported_languages(), "default": "python"}


@app.post("/api/code_team/run")
async def code_team_run(req: CodeTeamRequest):
    """多智能体代码团队：自然语言需求 → 协作生成 + 质量门 + 真实测试验证。

    借鉴华为云码道(CodeArts) Agent Team 的协作生成形态，落到 AOS 已有的
    compliance 质量门 + 隔离执行之上。默认 heuristic 生成（无 GPU/key 可跑），
    真实 LLM 由调用方在 CodeTeamOrchestrator 注入。

    通电：若 FabricHub 已热身（/_fabric_hub_cache 非空，通常由 /api/fabric/health
    或 /api/orchestrator/run 拉起），则经统一能力路由 hub.route("code.generate",...)
    派发——享受引擎透明化（响应带 engine_id="code-team"）且真实流量喂路由预测器。
    否则回落直连编排器（零依赖、行为不变），避免在该端点首次拉起重型 hub。
    """
    try:
        global _fabric_hub_cache
        hub = _fabric_hub_cache
        if hub is not None:
            res = await asyncio.to_thread(
                hub.route, "code.generate",
                {"requirement": req.requirement, "lang": req.lang})
            from core.fabric.adapter import InvokeResult
            if isinstance(res, InvokeResult) and res.data is not None:
                out = dict(res.data)
                out["engine_id"] = res.engine_id  # 诚实标注执行引擎
                return out
        # 兜底：直连编排器（与历史行为一致）
        llm = make_llm_generate()
        result = CodeTeamOrchestrator(llm_generate=llm).run(req.requirement, lang=req.lang)
        result["llm_used"] = llm is not None  # 诚实标注：是否走了真实 LLM
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/code_team/render")
async def code_team_render(req: CodeTeamRequest):
    """把代码团队结果渲染为 A2UI 可视化 HTML（结构化交付物，可直接浏览器查看）。

    复用 code_team.to_a2ui_surface 把 run() 结果转成 A2UI v0.9 surface，
    再经 a2ui 安全渲染器输出 HTML（声明式、不执行代码、不注入 HTML）。
    默认走 heuristic 生成；设 AOS_CODETEAM_LLM=1 则走真实 LLM。

    通电：hub 已热身时同样经 hub.route("code.generate",...) 派发（透明化+预测器），
    否则回落直连编排器。
    """
    try:
        global _fabric_hub_cache
        hub = _fabric_hub_cache
        if hub is not None:
            res = await asyncio.to_thread(
                hub.route, "code.generate",
                {"requirement": req.requirement, "lang": req.lang})
            from core.fabric.adapter import InvokeResult
            if isinstance(res, InvokeResult) and res.data is not None:
                html = render_code_team(res.data, standalone=True)
                return Response(content=html, media_type="text/html")
        # 兜底：直连编排器（与历史行为一致）
        llm = make_llm_generate()
        result = CodeTeamOrchestrator(llm_generate=llm).run(req.requirement, lang=req.lang)
        result["llm_used"] = llm is not None
        html = render_code_team(result, standalone=True)
        return Response(content=html, media_type="text/html")
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


@app.post("/api/compliance/gate")
async def compliance_gate(req: ComplianceGateRequest):
    """三分质量门：{文件名: 代码} → 安全/质量/合规 × ERROR/WARN/INFO 报告。"""
    try:
        report = QualityGate().run(req.files)
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=_safe_detail(e))


# ---- Bidding Analysis API ----


@app.post("/api/bidding/analyze")
async def bidding_analyze(
    file: UploadFile = File(...),
    company_name: Optional[str] = None,
    qualifications: Optional[str] = None,
    focus_areas: Optional[str] = None,
):
    """投标分析：上传招标 PDF → 结构化报告（需求提取 + 合规检查 + 策略建议）。

    - file: 招标文件 PDF（必须）
    - company_name: 企业名称（可选，用于资质匹配）
    - qualifications: 企业资质列表，逗号分隔（可选）
    - focus_areas: 重点关注领域，逗号分隔（可选）
    """
    import tempfile
    import shutil

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件")

    # 保存上传文件到临时路径（BiddingAgent 需要文件路径）
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "_traces", "uploads")
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_path = os.path.join(tmp_dir, f"bidding_{int(time.time()*1000)}_{file.filename}")

    try:
        with open(tmp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 构建 BiddingAgent 上下文
        context: Dict[str, Any] = {"pdf_path": tmp_path}
        if company_name or qualifications:
            context["company_profile"] = {
                "name": company_name or "",
                "qualifications": [q.strip() for q in (qualifications or "").split(",") if q.strip()],
            }
        if focus_areas:
            context["focus_areas"] = [a.strip() for a in focus_areas.split(",") if a.strip()]

        # PDF 解析 + 规则引擎是 CPU 重阻塞，移入线程池
        from skills.bidding_agent import BiddingAgent
        agent = BiddingAgent()
        result = await asyncio.to_thread(agent.execute, context)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bidding analyze error: {e}")
        raise HTTPException(status_code=500, detail=_safe_detail(e))
    finally:
        # 清理临时文件
        try:
            if os.path.isfile(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


# ---- Main ----


# 统一网关：把 /web、/openclaw、/deerflow 反向代理收编到 AOS 单端口下
# （必须在所有 /api 路由注册之后挂载，避免被 catch-all 抢路径）
mount_gateway(app)
logger.info("=== AOS unified gateway mounted (single-port front door) ===")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=config.HOST, port=config.PORT,
                reload=config.DEBUG, log_level="info" if config.DEBUG else "warning")
