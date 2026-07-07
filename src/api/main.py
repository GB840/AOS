import sys
import os

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import logging
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Query, Request, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response
import base64
from pydantic import BaseModel, Field
from datetime import datetime

from utils.config import config
from core import get_brain
from mcp import MCPMessage
from router import TaskType
from api.security import (
    APISecurityMiddleware, 
    RateLimitMiddleware,
    HTTPSRedirectMiddleware,
    SecurityHeadersMiddleware
)
from utils.exceptions import setup_exception_handlers

logging.basicConfig(
    level=logging.INFO if config.DEBUG else logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
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

# ---- Unified Brain (singleton: Hermes + DeerFlow + Memory + Skills + SubAgents) ----
brain = get_brain()


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

@app.on_event("startup")
async def startup_event():
    logger.info("=== %s v%s ===", config.APP_NAME, config.APP_VERSION)
    h = brain.health_check()
    logger.info("Health: %s", h["status"])
    for name, info in h["components"].items():
        logger.info("  %s: %s", name, info.get("status") or info.get("type", "?"))

    # Register chat handler
    brain.deerflow.register_handler("chat",
        lambda d: brain.hermes.chat(message=d.get("message", ""), session_id=d.get("session_id")))

    # Register skill handlers
    for sn in ["skill-creator","find-skills","superpowers","j-stack","frontend-design","ui-ux-pro-max","duckduckgo-search"]:
        brain.deerflow.register_handler("skill:"+sn, (lambda n: lambda d: brain.hermes.execute_skill(n, d))(sn))

    logger.info("=== AOS v5.0 ready ===")


@app.on_event("shutdown")
async def shutdown_event():
    brain.shutdown()
    logger.info("=== AOS shutdown complete ===")


# ---- Root & Health ----

@app.get("/")
async def root():
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
        },
    }

@app.get("/health")
async def health_check():
    return brain.health_check()


# ---- Chat ----

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        result = brain.chat(message=request.message, session_id=request.session_id)
        return result
    except Exception as e:
        logger.error("Chat error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
        return brain.add_memory(content=request.content, category="user")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/knowledge")
async def list_knowledge(limit: int = Query(50, ge=1, le=200)):
    try:
        cursor = brain.memory.sqlite_conn.execute(
            "SELECT * FROM knowledge ORDER BY created_at DESC LIMIT ?", (limit,))
        import json
        return {"items": [{"id": r["id"],"title": r["title"],"content": r["content"],
                "source": r["source"],"tags": json.loads(r["tags"] or "[]"),
                "created_at": r["created_at"]} for r in cursor.fetchall()],
                "count": cursor.rowcount}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
async def search_memory(request: SearchRequest):
    return brain.search_memory(query=request.query, search_type=request.search_type)

@app.get("/api/memory")
async def memory_overview():
    return brain.export_memory()


# ---- Sessions ----

@app.get("/api/sessions")
async def list_sessions():
    sessions = brain.list_sessions()
    return {"sessions": sessions, "count": len(sessions)}

@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    info = brain.get_session(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    return info

@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    if session_id in brain.hermes.sessions:
        del brain.hermes.sessions[session_id]
    return {"success": True, "session_id": session_id}


# ---- Tasks ----

@app.post("/api/tasks")
async def submit_task(request: TaskRequest):
    task_id = brain.deerflow.submit_task(task_type=request.task_type, input_data=request.input_data)
    return {"task_id": task_id, "status": "submitted"}

@app.get("/api/tasks")
async def list_tasks(status: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    return {"tasks": brain.deerflow.list_tasks(status=status, limit=limit)}

@app.get("/api/tasks/running")
async def get_running_tasks():
    return {"tasks": brain.deerflow.get_running_tasks()}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = brain.deerflow.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    if not brain.deerflow.cancel_task(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")
    return {"success": True, "task_id": task_id}


# ---- DeerFlow Native API ----

@app.get("/api/deerflow/models")
async def deerflow_models():
    return brain.deerflow.list_models()

@app.get("/api/deerflow/skills")
async def deerflow_skills():
    return brain.deerflow.list_skills()

@app.get("/api/deerflow/threads")
async def deerflow_threads(limit: int = 10):
    return brain.deerflow.list_threads(limit=limit)

@app.get("/api/deerflow/threads/{thread_id}")
async def deerflow_thread(thread_id: str):
    return brain.deerflow.get_thread(thread_id)

@app.get("/api/deerflow/memory")
async def deerflow_memory():
    return brain.deerflow.get_memory()

@app.get("/api/deerflow/mcp")
async def deerflow_mcp_config():
    return brain.deerflow.get_mcp_config()


# ---- MCP ----

@app.post("/api/mcp")
async def mcp_endpoint(request: MCPRequest):
    try:
        msg = MCPMessage(id=request.id, method=request.method, params=request.params or {})
        return brain.mcp.handle_message(msg).to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/mcp/info")
async def mcp_info():
    return brain.mcp.get_server_info()


# ---- SubAgents ----

@app.get("/api/subagents")
async def list_subagents():
    return {"subagents": brain.subagents.list_agents(), "stats": brain.subagents.get_stats()}

@app.get("/api/subagents/{name}/status")
async def get_subagent_status(name: str):
    info = brain.subagents.get(name)
    if not info:
        raise HTTPException(status_code=404, detail=f"SubAgent {name} not found")
    return info.to_dict()

@app.post("/api/subagents/{name}/invoke")
async def invoke_subagent(name: str, request: SubAgentInvokeRequest):
    if not brain.subagents.has(name):
        raise HTTPException(status_code=404, detail=f"SubAgent {name} not found")
    input_data = {}
    if request.message: input_data["message"] = request.message
    if request.task: input_data["task"] = request.task
    input_data["timeout"] = request.timeout
    input_data.update(request.extra)
    result = brain.subagents.invoke(name, input_data)
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Invocation failed"))
    return result


# ---- Skills ----

class SkillExecuteRequest(BaseModel):
    context: Dict[str, Any] = Field(default_factory=dict)

@app.get("/api/skills")
async def list_skills(category: str = ""):
    return brain.hermes.list_skills(category=category)

@app.get("/api/skills/search")
async def search_skills(q: str):
    return brain.hermes.search_skills(query=q)

@app.post("/api/skills/{name}/execute")
async def execute_skill_endpoint(name: str, request: SkillExecuteRequest):
    result = brain.hermes.execute_skill(name, request.context)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Skill execution failed"))
    return result


# ---- Providers & Stats ----

@app.get("/api/providers")
async def get_providers():
    return brain.hermes.get_providers_status()

@app.get("/api/stats")
async def get_stats():
    return brain.get_full_stats()


# ---- Compliance: Audit ----

@app.get("/api/compliance/audit")
async def compliance_audit(event_type: str = "", limit: int = 100):
    return {"entries": brain.audit.query(event_type=event_type or None, limit=limit)}

@app.get("/api/compliance/audit/stats")
async def compliance_audit_stats():
    return brain.audit.get_stats()

# ---- Compliance: Identity ----

@app.get("/api/compliance/identity")
async def compliance_identity():
    return {
        "root_identity": brain.identity.to_dict(),
        "stats": brain.aid_gen.get_stats(),
        "all": [i.to_dict() for i in brain.aid_gen.list_identities()],
    }

@app.get("/api/compliance/identity/{aid}")
async def compliance_get_identity(aid: str):
    ident = brain.aid_gen.get_identity(aid)
    if not ident:
        raise HTTPException(status_code=404, detail="Identity not found")
    return ident.to_dict()

@app.post("/api/compliance/identity")
async def compliance_create_identity(name: str, capabilities: str = ""):
    caps = [c.strip() for c in capabilities.split(",")] if capabilities else None
    ident = brain.aid_gen.create_identity(name=name, capabilities=caps)
    return ident.to_dict()

# ---- Compliance: Trace ----

@app.get("/api/compliance/trace")
async def compliance_traces(limit: int = 50):
    return {"traces": brain.tracer.list_traces(limit=limit)}

@app.get("/api/compliance/trace/{trace_id}")
async def compliance_get_trace(trace_id: str):
    trace = brain.tracer.get_trace(trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace.to_dict()

@app.get("/api/compliance/trace/stats")
async def compliance_trace_stats():
    return brain.tracer.get_stats()

# ---- Sandbox Operations ----

@app.post("/api/sandbox/acquire")
async def sandbox_acquire(thread_id: str = ""):
    sb = brain.deerflow.sandbox
    sid = sb.acquire()
    return {"sandbox_id": sid, "provider": type(sb._provider).__name__}

@app.post("/api/sandbox/exec")
async def sandbox_exec(command: str, thread_id: str = ""):
    try:
        result = brain.deerflow.create_sandbox(thread_id=thread_id or None).execute_command(command)
        return {"success": True, "output": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sandbox/release")
async def sandbox_release():
    brain.deerflow.sandbox.release()
    return {"success": True}

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
    cfg = brain.deerflow.register_subagent(
        name=req.name, description=req.description,
        system_prompt=req.system_prompt or None,
        tools=req.tools, skills=req.skills,
        model=req.model, max_turns=req.max_turns,
        timeout_seconds=req.timeout_seconds,
    )
    return {"success": True, "config": {"name": cfg.name, "description": cfg.description}}

@app.get("/api/subagents/deep")
async def deep_subagent_list():
    return {"subagents": brain.deerflow.list_subagents()}

@app.post("/api/subagents/deep/execute")
async def deep_subagent_execute(req: SubAgentExecuteRequest):
    thread_id = f"aos-api-{req.name}-{int(time.time())}"
    if req.async_mode:
        task_id = brain.deerflow.execute_subagent_async(req.name, req.task, thread_id=thread_id)
        return {"task_id": task_id, "mode": "async"}
    result = brain.deerflow.execute_subagent(req.name, req.task, thread_id=thread_id)
    return result

@app.get("/api/subagents/deep/task/{task_id}")
async def deep_subagent_task(task_id: str):
    result = brain.deerflow.get_subagent_result(task_id)
    if not result:
        raise HTTPException(status_code=404, detail="Task not found")
    return result

@app.post("/api/subagents/deep/task/{task_id}/cancel")
async def deep_subagent_cancel(task_id: str):
    brain.deerflow.cancel_subagent(task_id)
    return {"success": True}


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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vimax/generate")
async def vimax_generate(req: ViMaxRequest):
    """生成视频"""
    try:
        result = brain.subagents.invoke("vimax", {
            "workflow": req.workflow,
            "input": req.input,
            "params": req.params
        })
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vimax/task/{task_id}")
async def vimax_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.vimax import get_vimax_skill
        skill = get_vimax_skill()
        status = skill.get_status(task_id)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/vimax/configure")
async def vimax_configure(api_keys: Dict[str, str]):
    """配置 ViMax API 密钥"""
    try:
        from subagents.vimax_agent import get_vimax_subagent
        agent = get_vimax_subagent()
        agent.configure(api_keys)
        return {"success": True, "configured_keys": list(api_keys.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ruflo/tasks")
async def ruflo_tasks():
    """列出所有 RuFlo 任务类型"""
    try:
        from skills.ruflo import RUFLO_TASKS
        return {"tasks": RUFLO_TASKS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ruflo/execute")
async def ruflo_execute(req: RuFloRequest):
    """执行 RuFlo 开发任务"""
    try:
        result = brain.subagents.invoke("ruflo", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ruflo/task/{task_id}")
async def ruflo_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.ruflo import get_ruflo_skill
        skill = get_ruflo_skill()
        status = skill.get_task_status(task_id)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ruflo/configure")
async def ruflo_configure(api_key: str):
    """配置 RuFlo API 密钥"""
    try:
        from subagents.ruflo_agent import get_ruflo_subagent
        agent = get_ruflo_subagent()
        agent.configure(api_key)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        result = brain.skill_registry.execute("ollama", {"action": "list_models"})
        if result.get("success"):
            return result
        else:
            return {"models": [], "count": 0, "ollama_available": result.get("ollama_available", False)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ollama/chat")
async def ollama_chat(req: OllamaRequest):
    """Ollama 聊天"""
    try:
        result = brain.skill_registry.execute("ollama", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ollama/generate")
async def ollama_generate(req: OllamaRequest):
    """Ollama 文本生成"""
    try:
        result = brain.skill_registry.execute("ollama", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ollama/embeddings")
async def ollama_embeddings(req: OllamaRequest):
    """Ollama 生成嵌入向量"""
    try:
        result = brain.skill_registry.execute("ollama", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ollama/pull")
async def ollama_pull(model: str):
    """拉取 Ollama 模型"""
    try:
        result = brain.skill_registry.execute("ollama", {
            "action": "pull_model",
            "model": model,
        })
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "拉取失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ollama/status")
async def ollama_status():
    """检查 Ollama 服务状态"""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/uitars/execute")
async def uitars_execute(req: UITARSRequest):
    """执行 UI-TARS 自动化任务"""
    try:
        result = brain.skill_registry.execute("uitars", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/uitars/status")
async def uitars_status():
    """检查 UI-TARS 状态"""
    try:
        from deerflow.path_detect import detect_uitars_path
        uitars_path = detect_uitars_path()
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
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pixelle/voices")
async def pixelle_voices():
    """列出所有 Pixelle-Video 配音"""
    try:
        from skills.pixelle_video import PIXELLE_VOICES
        return {"voices": PIXELLE_VOICES}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/pixelle/generate")
async def pixelle_generate(req: PixelleRequest):
    """生成短视频"""
    try:
        result = brain.subagents.invoke("pixelle_video", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pixelle/task/{task_id}")
async def pixelle_task(task_id: str):
    """查询任务状态"""
    try:
        from skills.pixelle_video import get_pixelle_skill
        skill = get_pixelle_skill()
        status = skill.get_task_status(task_id)
        return {"task_id": task_id, **status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/loop/components")
async def loop_components():
    """列出所有核心组件"""
    try:
        from skills.loop_engineering import LOOP_COMPONENTS
        return {"components": LOOP_COMPONENTS}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/loop/execute")
async def loop_execute(req: LoopRequest):
    """执行循环"""
    try:
        result = brain.subagents.invoke("loop_engineering", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/loop/status/{loop_id}")
async def loop_status(loop_id: str):
    """查询循环状态"""
    try:
        from skills.loop_engineering import get_loop_skill
        skill = get_loop_skill()
        status = skill._get_loop_status({"loop_id": loop_id})
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/loop/list")
async def loop_list():
    """列出所有循环"""
    try:
        from skills.loop_engineering import get_loop_skill
        skill = get_loop_skill()
        loops = skill._list_loops({})
        return loops
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Manage Provider (for failover) ----

@app.post("/api/providers/switch")
async def switch_provider(provider: str):
    try:
        brain.hermes.set_provider(provider)
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
        result = brain.hermes.route_chat(
            message=req.message,
            task_type=req.task_type,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )
        return result
    except Exception as e:
        logger.error(f"Route chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/router/providers")
async def router_providers():
    """获取路由管理器中所有可用提供商"""
    try:
        from router import LLMRouter
        router = LLMRouter()
        return {"providers": router.get_available_providers()}
    except Exception as e:
        logger.error(f"Router providers error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

# ---- Voice API ----

from voice import ASREngine, TTSEngine

asr_engine = ASREngine()
tts_engine = TTSEngine()

@app.post("/api/voice/asr")
async def voice_recognition(audio: bytes = File(...), format: str = "wav"):
    try:
        result = asr_engine.recognize(audio, format=format)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except Exception as e:
        logger.error(f"ASR error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/tts")
async def voice_synthesis(text: str, voice: str = "zh", speed: float = 1.0, pitch: float = 0.0):
    try:
        result = tts_engine.synthesize(text, voice=voice, speed=speed, pitch=pitch)
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        return Response(content=result["audio"], media_type=result["content_type"])
    except Exception as e:
        logger.error(f"TTS error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/voice/chat")
async def voice_chat(audio: bytes = File(...), format: str = "wav", session_id: str = None):
    try:
        asr_result = asr_engine.recognize(audio, format=format)
        if not asr_result["success"]:
            raise HTTPException(status_code=400, detail=asr_result["error"])
        
        text = asr_result["text"]
        chat_result = brain.chat(message=text, session_id=session_id)
        
        tts_result = tts_engine.synthesize(chat_result.get("response", ""))
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
        raise HTTPException(status_code=500, detail=str(e))

# ---- Multimodal API ----

@app.post("/api/multimodal/analyze")
async def analyze_image(image: UploadFile = File(...), prompt: str = "分析这张图片"):
    try:
        image_bytes = await image.read()
        return {
            "success": True,
            "image_name": image.filename,
            "image_size": len(image_bytes),
            "prompt": prompt,
            "analysis": "图片分析功能需要配置支持视觉的LLM模型",
        }
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        
        result = brain.chat(message=message, session_id=session_id)
        
        return {
            "success": True,
            "response": result.get("response", ""),
            "session_id": result.get("session_id", ""),
            "image_processed": image_data is not None,
            "image_info": image_data,
        }
    except Exception as e:
        logger.error(f"Multimodal chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        result = brain.skill_registry.execute("comfyui", {"action": "status"})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/comfyui/workflows")
async def comfyui_workflows():
    """列出所有可用工作流"""
    try:
        result = brain.skill_registry.execute("comfyui", {"action": "list_workflows"})
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/comfyui/txt2img")
async def comfyui_txt2img(req: ComfyUIRequest):
    """文生图"""
    try:
        result = brain.skill_registry.execute("comfyui", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/comfyui/img2vid")
async def comfyui_img2vid(req: ComfyUIRequest):
    """图生视频"""
    try:
        result = brain.skill_registry.execute("comfyui", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/comfyui/style_transfer")
async def comfyui_style_transfer(req: ComfyUIRequest):
    """风格迁移"""
    try:
        result = brain.skill_registry.execute("comfyui", {
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
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/comfyui/vid2vid")
async def comfyui_vid2vid(req: ComfyUIRequest):
    """视频生视频"""
    try:
        result = brain.skill_registry.execute("comfyui", {
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
        raise HTTPException(status_code=500, detail=str(e))


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
        
        result = brain.skill_registry.execute("comfyui", params)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Main ----

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.api.main:app", host=config.HOST, port=config.PORT,
                reload=config.DEBUG, log_level="info" if config.DEBUG else "warning")
