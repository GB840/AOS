"""AOS 个人级 Web 控制台（最小化可用版，双前端之一）。

⚠ 双前端定位（防混淆）：
  · 本文件（web/console.py，~109 行）= **最小化个人控制台**：仅健康/供应商状态条
    + 一个 /api/chat 对话框 + 侧栏技能/资产概览。适合「只想快速连上 AOS 聊两句、
    看下状态」的轻量个人场景。
  · src/web/app.py（~4769 行）= **完整控制台**：BYOK 设置页、autopilot 自主执行页、
    32+ 功能页。适合需要全套能力的场景。
  二者都是「连已通电 AOS API 的前端」，互不冲突、都不废弃，按需要选。后端
  /api/chat 默认走 FabricHub；brain.py 仅作 opt-in 兜底（见 src/core/brain.py docstring）。

连到已通电的 AOS API（默认 http://127.0.0.1:8000），提供：
  · 顶部健康/供应商状态条
  · 底部对话输入框，调用 /api/chat（带 X-API-Key 鉴权）
  · 侧栏技能/资产概览

启动：
  streamlit run web/console.py --server.port 8501
依赖：streamlit（已装）
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

import streamlit as st

# ---------- 配置 ----------
DEFAULT_API = os.getenv("AOS_API_BASE", "http://127.0.0.1:8000")
ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def _load_api_key() -> str:
    try:
        with open(ENV_PATH, encoding="utf-8") as f:
            for line in f:
                if line.startswith("API_KEY="):
                    return line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


# ---------- API 封装 ----------
def api_get(path: str, api_key: str):
    url = DEFAULT_API + path
    req = urllib.request.Request(url, headers={"X-API-Key": api_key}, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def api_chat(message: str, api_key: str) -> dict:
    url = DEFAULT_API + "/api/chat"
    body = json.dumps({"message": message, "session_id": st.session_state.get("sid")}).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json", "X-API-Key": api_key}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"response": f"[HTTP {e.code}] {e.read().decode()[:200]}"}
    except Exception as e:  # noqa: BLE001
        return {"response": f"[连接错误] {e}"}


# ---------- 页面 ----------
st.set_page_config(page_title="AOS 控制台", page_icon="🤖", layout="wide")
st.title("🤖 AOS · 个人级控制台")

api_key = st.sidebar.text_input("API Key", value=_load_api_key(), type="password")
st.sidebar.caption(f"API 地址：{DEFAULT_API}")

# 健康条
try:
    health = api_get("/health", api_key)
    healthy = health.get("status") == "healthy"
    comp = health.get("init_summary", {}).get("successful_components", 0)
    total = health.get("init_summary", {}).get("total_components", 0)
    st.sidebar.success(f"● 服务健康：{health.get('status')}（{comp}/{total} 组件）")
except Exception as e:  # noqa: BLE001
    st.sidebar.error(f"● 无法连接 API：{e}")
    healthy = False

try:
    prov = api_get("/api/providers", api_key).get("providers", [])
    st.sidebar.write("**可用 LLM 供应商：**")
    for p in prov:
        st.sidebar.write(f"· {p['name']}（`{p['model']}`）{'🟢' if p.get('available') else '🔴'}")
except Exception:
    pass

# 会话状态
if "messages" not in st.session_state:
    st.session_state.messages = []
if "sid" not in st.session_state:
    st.session_state.sid = None

# 聊天历史
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# 输入
if prompt := st.chat_input("和 AOS 对话…（例如：用一句话解释什么是人工智能）"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("AOS 思考中…"):
            resp = api_chat(prompt, api_key)
        text = resp.get("response") or resp.get("result") or str(resp)
        if not st.session_state.sid and resp.get("session_id"):
            st.session_state.sid = resp.get("session_id")
        st.markdown(text)
    st.session_state.messages.append({"role": "assistant", "content": text})
