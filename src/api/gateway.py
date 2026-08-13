"""AOS 统一网关 (Unified Gateway)
================================
让 AOS(:8000) 成为**唯一对外端口**，内置反向代理把其余三块收编到子路径下，
实现"圆润如一体"：

    /web/*      -> Streamlit 控制台  (默认 127.0.0.1:8501, 不剥离前缀:
                                     因为 Streamlit 配了 server.baseUrlPath=/web)
    /openclaw/* -> OpenClaw 网关     (默认 127.0.0.1:18789, 剥离前缀)
    /deerflow/* -> DeerFlow 网关     (默认 127.0.0.1:2026,  剥离前缀)

特性：
- HTTP 代理支持 SSE / 任意 streaming（用 StreamingResponse 透传字节流）
- WebSocket 代理（Streamlit 的 /web/_stcore/stream 等必须走 WS）
- 上游不可达返回 502 + 清晰错误信息，不会拖垮 AOS 主进程
- 上游 3xx 的 Location 自动重写为代理侧地址
- 各上游地址可用环境变量覆盖：AOS_GW_WEB / AOS_GW_OPENCLAW / AOS_GW_DEERFLOW

这是 AOS "集成层" 的合法职责（胶水/提升层），不是重造四个核心能力本身。
"""
import os
import time
import asyncio
import logging
import threading
from urllib.parse import urlparse, urlunparse

from fastapi import Request, WebSocket
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse

import aiohttp

logger = logging.getLogger("aos.gateway")

# 不应被转发的逐跳 (hop-by-hop) 头
_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}

# 路由表：前缀 -> {目标地址, 是否剥离前缀}
_DEFAULTS = {
    "/web":      {"target": os.getenv("AOS_GW_WEB", "http://127.0.0.1:8501"), "strip": False},
    "/openclaw": {"target": os.getenv("AOS_GW_OPENCLAW", "http://127.0.0.1:18789"), "strip": True},
    "/deerflow": {"target": os.getenv("AOS_GW_DEERFLOW", "http://127.0.0.1:2026"), "strip": True},
}

_session: aiohttp.ClientSession | None = None
# P2 并发修复：get_session 可能在 liveness_loop 和请求处理中并发调用，
# 无锁 check-then-act 会导致两个 ClientSession 被创建（句柄泄漏）。
_session_lock = threading.Lock()

# 上游存活缓存：label -> 最近一次成功探测的 monotonic 时间；用于快速 fail-fast / 友好降级，
# 避免上游未启动时请求挂起等待。仅缓存、不泄露内部地址。
_liveness: dict[str, float] = {}


def _upstream_label(target: str) -> str:
    """把内部 target（含 host:port）映射为对外安全的公共标签，避免泄露内部地址。"""
    t = (target or "").lower()
    if "8501" in t or "/web" in t:
        return "web"
    if "18789" in t or "openclaw" in t:
        return "openclaw"
    if "2026" in t or "deerflow" in t:
        return "deerflow"
    return "upstream"


def _upstream_down(target: str) -> bool:
    """该上游近期从未探活成功 -> 判定为未启动。"""
    last = _liveness.get(_upstream_label(target))
    return last is None or (time.monotonic() - last) > 60


def _friendly_down_msg(label: str) -> str:
    return {
        "web": "Web 控制台未运行，请先启动 web 服务（如 aos_supervisor --only web）。",
        "openclaw": "OpenClaw 网关未运行。",
        "deerflow": "DeerFlow 网关未运行。",
    }.get(label, "上游服务未启动。")


async def _liveness_loop(interval: float = 15.0) -> None:
    """周期性探活三个上游，更新 _liveness 缓存；异常静默，不拖累主进程。"""
    while True:
        try:
            session = get_session()
            for name, cfg in _DEFAULTS.items():
                try:
                    async with session.get(
                        cfg["target"].rstrip("/") + "/",
                        timeout=aiohttp.ClientTimeout(total=3),
                    ) as r:
                        if r.status < 500:
                            _liveness[name] = time.monotonic()
                except Exception as e:
                    logger.warning("上游探活请求失败: %s", e)
        except Exception as e:
            logger.warning("探活会话创建失败: %s", e)
        await asyncio.sleep(interval)


def get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        with _session_lock:
            # DCL：持锁后二次检查，防并发首调各自创建 ClientSession（句柄泄漏）
            if _session is None or _session.closed:
                # trust_env=False: 反向代理到 127.0.0.1 上游时绝不经 HTTP(S)_PROXY 转发，
                # 否则环境中若设了代理（含 localhost 拦截）会导致 "Connection closed"。
                _session = aiohttp.ClientSession(trust_env=False)
    return _session


async def close_gateway_session() -> None:
    global _session
    if _session is not None and not _session.closed:
        await _session.close()
    _session = None


def _match(path: str, routes):
    best = None
    for prefix, cfg in routes.items():
        if path == prefix or path.startswith(prefix + "/"):
            if best is None or len(prefix) > len(best[0]):
                best = (prefix, cfg)
    return best


def _fwd_headers(incoming) -> dict:
    h = {}
    for k, v in incoming.items():
        if k.lower() in _HOP or k.lower() == "host":
            continue
        h[k] = v
    return h


def _rewrite_location(loc: str, request: Request, cfg: dict) -> str:
    """把上游绝对 Location 改写为代理侧地址（保持代理前缀一致）。"""
    try:
        p = urlparse(loc)
        if not p.netloc:
            return loc  # 相对路径：浏览器会基于当前代理前缀解析，无需改写
        new = p._replace(scheme=request.url.scheme, netloc=request.url.netloc)
        if cfg.get("strip"):
            # 上游不含代理前缀，需要补回
            prefix = _prefix_of(request.url.path)
            if prefix and not new.path.startswith(prefix + "/"):
                new = new._replace(path=prefix + (new.path if new.path.startswith("/") else "/" + new.path))
        return urlunparse(new)
    except Exception:
        return loc


def _prefix_of(path: str) -> str:
    for prefix in _DEFAULTS:
        if path == prefix or path.startswith(prefix + "/"):
            return prefix
    return ""


async def _proxy_http(request: Request, prefix: str, cfg: dict):
    path = request.url.path
    if cfg.get("strip"):
        rest = path[len(prefix):]
        if not rest:
            rest = "/"
    else:
        rest = path  # /web 不剥离：Streamlit 自身已带 /web 前缀
    target = cfg["target"].rstrip("/") + rest
    if request.url.query:
        target += "?" + request.url.query

    headers = _fwd_headers(request.headers)
    if prefix == "/openclaw":
        tok = os.getenv("OPENCLAW_GATEWAY_TOKEN")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

    body = None
    if request.method in ("POST", "PUT", "PATCH"):
        body = await request.body()

    session = get_session()
    last_err: Exception | None = None
    # 瞬时抖动重试一次（短超时即退），避免一抖即 502。
    for attempt in range(2):
        try:
            # 注意：不能在 `async with session.request(...) as resp:` 内部 return StreamingResponse——
            # 那样 with 块退出会先关闭上游连接, 导致下游还没开始读就 "Connection closed"。
            # 正确做法：保持 resp 打开, 在 stream 生成器的 finally 中释放连接。
            resp = await session.request(
                method=request.method,
                url=target,
                headers=headers,
                data=body,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=600),
            )
            break
        except aiohttp.ClientError as e:
            last_err = e
            if attempt == 0:
                logger.warning("[gateway] upstream %s 第1次失败，重试: %s", target, e)
                continue
    else:
        # 两次均失败：返回 sanitized 502——内部 host:port/异常细节仅入日志，不泄露给客户端。
        logger.error("[gateway] upstream %s 不可用: %s", target, last_err)
        label = _upstream_label(target)
        detail = "上游服务不可用" if not _upstream_down(target) else _friendly_down_msg(label)
        return JSONResponse(
            {"error": "bad_gateway", "detail": detail, "upstream": label},
            status_code=502,
        )

    async def stream():
        try:
            async for chunk in resp.content.iter_chunked(16384):
                yield chunk
        finally:
            try:
                resp.release()
            except Exception as e:
                logger.warning("释放上游响应连接失败: %s", e)

    resp_headers = {}
    for k, v in resp.headers.items():
        if k.lower() in _HOP or k.lower() in ("content-length", "content-encoding"):
            continue
        resp_headers[k] = v
    if resp.status in (301, 302, 303, 307, 308) and "location" in resp_headers:
        resp_headers["location"] = _rewrite_location(resp_headers["location"], request, cfg)

    return StreamingResponse(
        stream(),
        status_code=resp.status,
        headers=resp_headers,
        media_type=resp.content_type,
    )


async def _proxy_ws(websocket: WebSocket, prefix: str, cfg: dict):
    await websocket.accept()
    path = websocket.url.path
    if cfg.get("strip"):
        rest = path[len(prefix):]
        if not rest:
            rest = "/"
    else:
        rest = path
    ws_url = cfg["target"].replace("http", "ws", 1).rstrip("/") + rest
    if websocket.url.query:
        ws_url += "?" + websocket.url.query

    headers = _fwd_headers(websocket.headers)
    if prefix == "/openclaw":
        tok = os.getenv("OPENCLAW_GATEWAY_TOKEN")
        if tok:
            headers["Authorization"] = f"Bearer {tok}"

    session = get_session()
    try:
        async with session.ws_connect(
            ws_url, headers=headers, timeout=aiohttp.ClientTimeout(total=600)
        ) as up:
            async def client_to_up():
                try:
                    while True:
                        msg = await websocket.receive()
                        t = msg.get("type")
                        if t == "websocket.disconnect":
                            break
                        if t == "websocket.receive":
                            d = msg.get("text")
                            if d is not None:
                                await up.send_str(d)
                            else:
                                b = msg.get("bytes")
                                if b is not None:
                                    await up.send_bytes(b)
                except Exception as e:
                    logger.warning("WebSocket 客户端到上游转发异常: %s", e)

            async def up_to_client():
                try:
                    async for m in up:
                        if m.type == aiohttp.WSMsgType.TEXT:
                            await websocket.send_text(m.data)
                        elif m.type == aiohttp.WSMsgType.BINARY:
                            await websocket.send_bytes(m.data)
                        elif m.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.ERROR,
                        ):
                            break
                except Exception as e:
                    logger.warning("WebSocket 上游到客户端转发异常: %s", e)

            await asyncio.gather(
                asyncio.create_task(client_to_up()),
                asyncio.create_task(up_to_client()),
                return_exceptions=True,
            )
    except Exception as e:
        logger.error("[gateway] ws upstream %s error: %s", ws_url, e)
    finally:
        try:
            await websocket.close()
        except Exception as e:
            logger.warning("关闭 WebSocket 连接失败: %s", e)


async def probe_upstreams() -> dict:
    """启动时对三个上游做可达性探测，结果写入日志，便于从日志侧确认网关贯通。

    仅做只读 GET 探测；上游未就绪不影响 AOS 主进程。
    """
    session = get_session()
    probes = {
        "web":      (_DEFAULTS["/web"]["target"].rstrip("/") + "/web/",),
        "openclaw": (_DEFAULTS["/openclaw"]["target"].rstrip("/") + "/",),
        "deerflow": (_DEFAULTS["/deerflow"]["target"].rstrip("/") + "/health",
                     _DEFAULTS["/deerflow"]["target"].rstrip("/") + "/"),
    }
    results = {}
    for name, urls in probes.items():
        ok = False
        last = None
        for u in urls:
            try:
                async with session.get(u, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    last = r.status
                    if r.status < 500:
                        ok = True
                        break
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {e}"
        results[name] = {"reachable": ok, "status": last}
        logger.info("[gateway] upstream probe %-9s -> %s", name, results[name])
    return results


def mount_gateway(app) -> None:
    """把三个子路径的反向代理挂到 FastAPI app 上。"""
    routes = _DEFAULTS
    for prefix, cfg in routes.items():
        # HTTP catch-all（含 SSE / 大文件 streaming）
        def make_http(p, c):
            async def handler(request: Request, path: str = ""):
                return await _proxy_http(request, p, c)
            return handler
        app.add_route(
            prefix + "/{path:path}", make_http(prefix, cfg),
            methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH", "HEAD"],
        )

        # 精确前缀 -> 307 到 prefix/
        def make_root(p):
            async def handler(request: Request):
                return RedirectResponse(p + "/", status_code=307)
            return handler
        app.add_route(prefix, make_root(prefix), methods=["GET", "HEAD"])

        # WebSocket 代理（Streamlit 必须；OpenClaw/DeerFlow 若上游用 WS 同样受益）
        def make_ws(p, c):
            async def handler(websocket: WebSocket, path: str = ""):
                await _proxy_ws(websocket, p, c)
            return handler
        app.add_api_websocket_route(prefix + "/{path:path}", make_ws(prefix, cfg))

    logger.info("[gateway] mounted routes: %s", ", ".join(routes.keys()))
