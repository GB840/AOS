"""OpenMAIC HTTP 桥接（单创OS 可插拔教育能力芯粒）。

OpenMAIC = 清华大学 THU-MAIC 开源「多智能体互动课堂」生成引擎（MIT 许可，
2026-06-28 v0.3.0 从 AGPL-3.0 重新授权为 MIT；clone 实物 LICENSE 已核实为 MIT）。
它把行业知识/需求自动转化为「能讲、能练、能互动」的 AI 课堂。

本项目以**独立 HTTP 服务**形式接入（宪法 §3 芯粒隔离、§4 不绑定厂商）：
OpenMAIC 自管 LLM provider（.env.local / server-providers.yml），AOS 只经
REST 调用，绝不耦合其 Node 运行时，也不绑架主系统（未配置静默跳过）。

真实契约（已读 external/openmaic 源码核实，非臆测）：
- GET  {base}/api/health                       -> {success,status:'ok',version,capabilities}
- POST {base}/api/generate-classroom            body{requirement,...}
        -> 202 {success,jobId,status,step,message,pollUrl,pollIntervalMs:5000}
- GET  {base}/api/generate-classroom/{jobId}    -> {success,status,step,progress,message,
                                                    scenesGenerated,totalScenes,result,done,error}

result 结构：{id, url, stage:{name,languageDirective,...}, scenes:[...], scenesCount, createdAt}

本模块零额外依赖，仅用标准库 urllib（与 core fabric 其它适配器一致）。
诚实纪律（宪法 §6/§9）：所有调用附真实 HTTP 状态码 / 异常 / 原始响应，绝不伪造成功。
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from core.fabric.adapter import InvokeResult


DEFAULT_TIMEOUT = 30          # 单次 HTTP 超时（秒）
DEFAULT_POLL_INTERVAL = 5     # 与 OpenMAIC 返回的 pollIntervalMs 一致
DEFAULT_POLL_TIMEOUT = 600    # 课程生成长任务，最长轮询 10 分钟


class OpenMAICBridge:
    """对真实 OpenMAIC 服务的 HTTP 封装。构造不触网，可达性由 health() 判定。"""

    def __init__(self, base_url: str, timeout: int = DEFAULT_TIMEOUT):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> Dict[str, Any]:
        """一次真实 HTTP 调用；统一返回 {ok,status,data,raw,error}。

        异常与 HTTP 错误码都如实带出，不吞、不伪造。
        """
        url = f"{self.base_url}{path}"
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                status = resp.getcode()
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace") if e.fp else ""
            status = e.code
        except Exception as e:  # 网络不可达 / 超时 / DNS 等
            return {"ok": False, "status": None,
                    "error": f"{type(e).__name__}: {e}", "raw": ""}
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {}
        return {"ok": 200 <= status < 300, "status": status, "data": parsed, "raw": raw}

    def health(self) -> Dict[str, Any]:
        """真实健康探测：打 /api/health，返回 {ok,version,capabilities}。"""
        r = self._request("GET", "/api/health")
        if not r["ok"]:
            return {"ok": False,
                    "error": r.get("error") or f"HTTP {r.get('status')}",
                    "version": None, "capabilities": None}
        d = r.get("data", {})
        return {
            "ok": bool(d.get("success") and d.get("status") == "ok"),
            "version": d.get("version"),
            "capabilities": d.get("capabilities"),
            "raw": d,
        }

    def generate_course(
        self,
        requirement: str,
        *,
        enable_web_search: bool = False,
        enable_image: bool = False,
        enable_video: bool = False,
        enable_tts: bool = False,
        agent_mode: str = "default",
        pdf_text: Optional[str] = None,
        poll_timeout: int = DEFAULT_POLL_TIMEOUT,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> Dict[str, Any]:
        """提交课程生成任务并轮询至终态，返回结构化结果。

        输入即 OpenMAIC 的真实字段（camelCase）。返回 {ok, job_id, url,
        course_id, scenes_count, title, result, raw} 或失败 {ok:False, error, raw}。
        """
        if not requirement or not requirement.strip():
            return {"ok": False, "error": "requirement 为空（OpenMAIC 必填字段）", "raw": None}

        body: Dict[str, Any] = {
            "requirement": requirement,
            "enableWebSearch": enable_web_search,
            "enableImageGeneration": enable_image,
            "enableVideoGeneration": enable_video,
            "enableTTS": enable_tts,
            "agentMode": agent_mode,
        }
        if pdf_text:
            body["pdfContent"] = {"text": pdf_text, "images": []}

        # 1) 提交异步 job
        r = self._request("POST", "/api/generate-classroom", body)
        if not r["ok"]:
            return {"ok": False,
                    "error": f"提交课程生成任务失败：HTTP {r.get('status')} {r.get('error') or ''}",
                    "raw": r.get("raw")}
        d = r.get("data", {})
        if not d.get("success"):
            return {"ok": False,
                    "error": f"OpenMAIC 拒绝：{d.get('error')}（{d.get('errorCode')}）",
                    "raw": r.get("raw")}

        job_id = d.get("jobId")
        if not job_id:
            return {"ok": False, "error": "OpenMAIC 未返回 jobId", "raw": r.get("raw")}

        # 2) 轮询至 done（OpenMAIC 自管 LLM，可能数分钟）
        deadline = time.time() + max(poll_timeout, poll_interval)
        last: Optional[Dict[str, Any]] = None
        while time.time() < deadline:
            time.sleep(poll_interval)
            pr = self._request("GET", f"/api/generate-classroom/{job_id}")
            if not pr["ok"]:
                last = {"ok": False,
                        "error": f"轮询失败 HTTP {pr.get('status')} {pr.get('error')}",
                        "raw": pr.get("raw")}
                continue
            last = pr.get("data", {})
            if last.get("done"):
                break

        if last is None:
            return {"ok": False, "error": "轮询超时未拿到结果", "job_id": job_id}
        if not last.get("ok", True) and last.get("status") == "failed":
            last = last  # 保持
        status = last.get("status")
        if status != "succeeded":
            return {
                "ok": False,
                "error": (f"课程生成未成功（status={status}）："
                          f"{last.get('error') or last.get('message')}"),
                "job_id": job_id,
                "step": last.get("step"),
                "raw": last,
            }

        result = last.get("result") or {}
        return {
            "ok": True,
            "job_id": job_id,
            "url": result.get("url"),
            "course_id": result.get("id"),
            "scenes_count": result.get("scenesCount"),
            "title": (result.get("stage") or {}).get("name"),
            "result": result,
            "raw": last,
        }


def generate_course(payload: Dict[str, Any]) -> InvokeResult:
    """autopilot / API 统一派发入口：edu.course_gen -> OpenMAICBridge.generate_course。

    经 extension 取桥接实例；未启用（无 AOS_OPENMAIC_URL 或不可达）返回
    ok=False 且明确 error，绝不谎报成功（宪法 §6 诚实）。
    """
    from .extension import get_extension

    bridge = get_extension("openmaic")
    if bridge is None:
        return InvokeResult(
            ok=False,
            error=("edu.course_gen 未启用：未配置 AOS_OPENMAIC_URL 或 OpenMAIC 不可达"
                   "（opt-in，MIT 开源，需独立启动服务）"),
        )
    requirement = (
        payload.get("requirement") or payload.get("task")
        or payload.get("goal") or ""
    )
    out = bridge.generate_course(
        requirement,
        enable_web_search=bool(payload.get("enable_web_search", False)),
        enable_image=bool(payload.get("enable_image", False)),
        enable_video=bool(payload.get("enable_video", False)),
        enable_tts=bool(payload.get("enable_tts", False)),
        agent_mode=payload.get("agent_mode", "default"),
        pdf_text=payload.get("pdf_text"),
    )
    if not out.get("ok"):
        return InvokeResult(ok=False, error=out.get("error", "课程生成失败"), data=out)
    return InvokeResult(ok=True, data=out)
