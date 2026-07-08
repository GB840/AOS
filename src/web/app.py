import sys
import os
import json
import base64
import time
import io
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import requests

from compliance.audit import AuditEvent
from utils.config import config

st.set_page_config(
    page_title="AOS v5.0 - 能体操作系统",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

API_BASE_URL = config.API_BASE_URL or "http://localhost:8000"
OUTPUTS_DIR = config.OUTPUTS_DIR or str(Path(config.BASE_DIR) / "outputs")

if "api_key" not in st.session_state:
    st.session_state.api_key = ""

if "api_key" not in st.query_params:
    st.query_params["api_key"] = st.session_state.api_key

if "pyaudio_available" not in st.session_state:
    try:
        import pyaudio
        st.session_state.pyaudio_available = True
    except ImportError:
        st.session_state.pyaudio_available = False


def make_api_request(endpoint, method="GET", **kwargs):
    headers = {"Content-Type": "application/json"}
    if st.session_state.api_key:
        headers["X-API-Key"] = st.session_state.api_key
    
    url = f"{API_BASE_URL}{endpoint}"
    
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, params=kwargs.get("params"))
        elif method == "POST":
            if kwargs.get("files"):
                response = requests.post(url, headers={k: v for k, v in headers.items() if k != "Content-Type"}, **kwargs)
            else:
                response = requests.post(url, headers=headers, json=kwargs.get("json"))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        try:
            return {"error": response.json() if response else str(e)}
        except Exception:
            return {"error": str(e)}


def make_audio_request(endpoint, audio_bytes, **kwargs):
    headers = {}
    if st.session_state.api_key:
        headers["X-API-Key"] = st.session_state.api_key
    
    url = f"{API_BASE_URL}{endpoint}"
    try:
        files = {"audio": ("audio.wav", audio_bytes, "audio/wav")}
        data = {k: v for k, v in kwargs.items() if v is not None}
        response = requests.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        try:
            return {"error": response.json() if response else str(e)}
        except Exception:
            return {"error": str(e)}


@st.cache_resource
def get_brain():
    from core import get_brain
    return get_brain()


brain = get_brain()

PARTICLE_CLOUD_CSS = """
<style>
.particle-cloud {
    position: relative;
    width: 100%;
    height: 300px;
    background: linear-gradient(135deg, #0c0c1e 0%, #1a1a3e 50%, #0c0c1e 100%);
    border-radius: 12px;
    overflow: hidden;
}

.particle {
    position: absolute;
    width: 4px;
    height: 4px;
    background: #00ffff;
    border-radius: 50%;
    opacity: 0.6;
    animation: float 3s ease-in-out infinite;
    box-shadow: 0 0 10px #00ffff, 0 0 20px #00ffff;
}

@keyframes float {
    0%, 100% { transform: translateY(0) translateX(0); opacity: 0.3; }
    50% { transform: translateY(-20px) translateX(10px); opacity: 0.8; }
}

.speaking-wave {
    position: absolute;
    bottom: 20px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: flex-end;
    gap: 4px;
    height: 40px;
}

.wave-bar {
    width: 4px;
    background: #00ffff;
    border-radius: 2px;
    animation: wave 0.5s ease-in-out infinite;
    box-shadow: 0 0 8px #00ffff;
}

@keyframes wave {
    0%, 100% { height: 10px; }
    50% { height: 35px; }
}

.wave-bar:nth-child(1) { animation-delay: 0s; }
.wave-bar:nth-child(2) { animation-delay: 0.1s; }
.wave-bar:nth-child(3) { animation-delay: 0.2s; }
.wave-bar:nth-child(4) { animation-delay: 0.3s; }
.wave-bar:nth-child(5) { animation-delay: 0.4s; }

.glass-card {
    background: rgba(10, 10, 30, 0.7);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(0, 255, 255, 0.2);
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 4px 30px rgba(0, 255, 255, 0.1);
}

.tech-input {
    background: rgba(0, 0, 0, 0.5);
    border: 1px solid rgba(0, 255, 255, 0.3);
    border-radius: 8px;
    color: #00ffff;
    padding: 10px 15px;
    font-family: 'Courier New', monospace;
}

.tech-button {
    background: linear-gradient(135deg, #0066cc 0%, #00aaff 100%);
    border: none;
    border-radius: 8px;
    color: white;
    font-weight: bold;
    transition: all 0.3s ease;
}

.tech-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0, 170, 255, 0.4);
}
</style>
"""


def render_particle_cloud(speaking=False):
    particles = "\n".join([
        f'<div class="particle" style="top: {i*10+5}%; left: {i*8+5}%; animation-delay: {i*0.2}s;"></div>'
        for i in range(12)
    ])
    
    wave_html = ""
    if speaking:
        wave_html = """
        <div class="speaking-wave">
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
            <div class="wave-bar"></div>
        </div>
        """
    
    html_content = f"""
    {PARTICLE_CLOUD_CSS}
    <div class="particle-cloud">
        {particles}
        {wave_html}
    </div>
    """
    
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False)
    temp_file.write(html_content)
    temp_file.close()
    
    try:
        st.iframe(f"file:///{temp_file.name.replace(os.sep, '/')}", height=320)
    finally:
        os.unlink(temp_file.name)


def render_chat_message(msg, show_audio=True):
    with st.chat_message(msg["role"], avatar="👤" if msg["role"] == "user" else "🤖"):
        if msg.get("image"):
            st.image(msg["image"], caption="上传的图片", width=300)
        st.markdown(msg["content"])
        if msg.get("timestamp"):
            st.caption(msg["timestamp"])
        if msg.get("audio") and show_audio:
            st.audio(base64.b64decode(msg["audio"]), format="audio/wav")


with st.sidebar:
    st.title("🧠 AOS v5.0")
    st.caption(f"AID: `{brain.identity.aid[:24]}...`")
    
    st.divider()
    
    st.subheader("🔐 API 设置")
    api_key_input = st.text_input("API Key", type="password", value=st.session_state.api_key)
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        st.rerun()
    
    st.divider()
    
    page = st.radio(
        "导航",
        ["💬 智能对话", "🧠 代码库记忆", "🤝 专家智能体", "🌐 搜索中心", "📚 知识库", "🔄 Loop循环", "👨‍💻 RuFlo开发", "🎬 ViMax视频", "🎨 ComfyUI视觉", "🎥 Pixelle短视频", "🎬 OpenMontage", "✂️ 视频剪辑", "🎛️ 模型网关", "🧠 知识图谱", "👥 Agent管理", "🎨 设计规范", "✅ 代码质检", "🗺️ 3D重建", "🌐 网页提取", "🤖 本地模型", "🖱️ UI-TARS自动化", "🎤 语音编辑", "🖼️ 多模态", "🛠️ 技能中心", "🤖 子智能体", "🗂️ 沙盒终端", "📁 项目导入", "📊 审计日志", "📝 实时日志", "📈 系统状态"],
        label_visibility="collapsed",
    )
    
    st.divider()
    
    if st.button("🔍 健康检查"):
        with st.spinner("检查中..."):
            health = brain.health_check()
            for name, info in health["components"].items():
                status = info.get("status", "?")
                icon = "✅" if status == "ok" else "❌"
                st.text(f"{icon} {name}: {status}")
    
    st.divider()
    st.caption(f"v5.0 | {datetime.now().strftime('%H:%M')}")


# ---- Chat Page ----
if page == "💬 智能对话":
    st.title("💬 AOS 智能对话")
    st.caption("Hermes v0.15.2 + DeerFlow 2.0 — Unified Brain")
    
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = None
    
    for msg in st.session_state.chat_messages:
        render_chat_message(msg)
    
    col1, col2 = st.columns([4, 1])
    with col1:
        prompt = st.chat_input("问 AOS 任何问题...")
    with col2:
        use_deerflow = st.checkbox("使用 DeerFlow", value=False)
    
    if prompt:
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.chat_messages.append({"role": "user", "content": prompt, "timestamp": timestamp})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
            st.caption(timestamp)
        
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("思考中..."):
                try:
                    result = brain.chat(
                        message=prompt,
                        session_id=st.session_state.chat_session_id,
                        use_deerflow=use_deerflow,
                    )
                    response = result.get("response", str(result))
                    st.session_state.chat_session_id = result.get("session_id")
                    response_timestamp = datetime.now().strftime("%H:%M:%S")
                    st.markdown(response)
                    st.caption(response_timestamp)
                    st.session_state.chat_messages.append(
                        {"role": "assistant", "content": response, "timestamp": response_timestamp}
                    )
                except Exception as e:
                    st.error(f"错误: {e}")
    
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🧹 清空聊天"):
            st.session_state.chat_messages = []
            st.session_state.chat_session_id = None
            st.rerun()


# ---- Voice Page ----
elif page == "🎤 语音交互":
    st.title("🎤 语音交互")
    st.caption("粒子云语音识别 → AI 对话 → 语音合成")
    
    if "voice_messages" not in st.session_state:
        st.session_state.voice_messages = []
    if "voice_session_id" not in st.session_state:
        st.session_state.voice_session_id = None
    if "is_speaking" not in st.session_state:
        st.session_state.is_speaking = False
    
    st.markdown(PARTICLE_CLOUD_CSS, unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("🎛️ 语音设置")
        voice_speed = st.slider("语速", 0.5, 2.0, 1.0, step=0.1)
        auto_speak = st.checkbox("自动播放回复", value=True)
        recording_duration = st.slider("录音时长(秒)", 5, 30, 10, step=5)
    
    with col2:
        st.subheader("☁️ 粒子云")
        render_particle_cloud(st.session_state.is_speaking)
    
    st.subheader("📜 对话历史")
    for msg in st.session_state.voice_messages:
        render_chat_message(msg, show_audio=True)
    
    st.divider()
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if not st.session_state.pyaudio_available:
            st.warning("⚠️ 未安装 pyaudio，请运行: pip install pyaudio")
            recording = st.button("🎙️ 开始录音", type="primary", use_container_width=True, disabled=True)
        else:
            recording = st.button("🎙️ 开始录音", type="primary", use_container_width=True)
    with col2:
        status_text = st.empty()
    
    if recording and st.session_state.pyaudio_available:
        import pyaudio
        import wave
        
        chunk = 1024
        sample_format = pyaudio.paInt16
        channels = 1
        fs = 16000
        seconds = recording_duration
        
        p = pyaudio.PyAudio()
        
        status_text.info(f"🎙️ 正在录音... ({seconds}秒)")
        
        try:
            stream = p.open(format=sample_format,
                            channels=channels,
                            rate=fs,
                            frames_per_buffer=chunk,
                            input=True)
            
            frames = []
            for i in range(0, int(fs / chunk * seconds)):
                data = stream.read(chunk)
                frames.append(data)
                progress = int((i / int(fs / chunk * seconds)) * 100)
                status_text.info(f"🎙️ 录音中... {progress}%")
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            
            audio_bytes = b''.join(frames)
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.session_state.voice_messages.append(
                {"role": "user", "content": "🎙️ [语音输入]", "timestamp": timestamp}
            )
            
            status_text.info("🔊 正在识别...")
            
            result = make_audio_request("/api/voice/asr", audio_bytes)
            
            if result.get("success"):
                text = result["text"]
                provider = result.get("provider", "")
                st.session_state.voice_messages.append(
                    {"role": "user", "content": text, "timestamp": timestamp}
                )
                
                status_text.info("🧠 正在思考...")
                
                chat_result = brain.chat(
                    message=text,
                    session_id=st.session_state.voice_session_id,
                )
                response = chat_result.get("response", "")
                st.session_state.voice_session_id = chat_result.get("session_id")
                
                response_timestamp = datetime.now().strftime("%H:%M:%S")
                
                audio_b64 = None
                if auto_speak and response:
                    status_text.info("🔉 正在合成语音...")
                    st.session_state.is_speaking = True
                    st.rerun()
                    
                    tts_response = requests.post(
                        f"{API_BASE_URL}/api/voice/tts",
                        params={"text": response, "speed": voice_speed},
                        headers={"X-API-Key": st.session_state.api_key} if st.session_state.api_key else {}
                    )
                    if tts_response.status_code == 200:
                        audio_b64 = base64.b64encode(tts_response.content).decode()
                
                st.session_state.is_speaking = False
                st.session_state.voice_messages.append({
                    "role": "assistant",
                    "content": response,
                    "timestamp": response_timestamp,
                    "audio": audio_b64
                })
                
                status_text.success("✅ 完成!")
                st.rerun()
            else:
                st.session_state.is_speaking = False
                status_text.error(f"❌ 识别失败: {result.get('error', '未知错误')}")
        except Exception as e:
            st.session_state.is_speaking = False
            status_text.error(f"❌ 录音失败: {e}")
            try:
                p.terminate()
            except Exception:
                pass


# ---- Loop Engineering Page ----
elif page == "🔄 Loop循环":
    st.title("🔄 Loop Engineering 循环工程")
    st.caption("Agent = Model + Harness + Loop — 让AI自主完成任务迭代")
    
    if "loop_results" not in st.session_state:
        st.session_state.loop_results = []
    
    templates = {
        "code_gen": {"name": "代码生成循环", "emoji": "💻", "desc": "从需求到可运行代码", "goal": "生成完整、可运行的代码"},
        "content_gen": {"name": "内容生成循环", "emoji": "📝", "desc": "从创意到成品内容", "goal": "生成高质量内容"},
        "problem_solving": {"name": "问题解决循环", "emoji": "🔧", "desc": "从问题到解决方案", "goal": "提供可行的解决方案"},
        "research": {"name": "研究循环", "emoji": "🔍", "desc": "从问题到深度分析", "goal": "提供深度分析报告"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🎯 五大核心组件")
        components = {
            "scheduler": {"name": "定时任务", "emoji": "⏰", "desc": "自动启动循环"},
            "worktree": {"name": "工作树隔离", "emoji": "🌲", "desc": "多Agent并行执行"},
            "knowledge": {"name": "项目知识", "emoji": "💾", "desc": "持久化记忆"},
            "connector": {"name": "连接器", "emoji": "🔗", "desc": "对接外部工具"},
            "subagent": {"name": "子Agent", "emoji": "👥", "desc": "任务拆分与验收分离"},
        }
        for key, comp in components.items():
            st.markdown(f"**{comp['emoji']} {comp['name']}**")
            st.caption(comp['desc'])
            st.markdown("---")
    
    with col2:
        with st.form("loop_form"):
            selected_template = st.selectbox(
                "选择循环模板",
                list(templates.keys()),
                format_func=lambda x: f"{templates[x]['emoji']} {templates[x]['name']}"
            )
            
            input_data = st.text_area(
                "输入数据",
                "创建一个简单的待办事项应用，包含增删改查功能",
                height=100,
            )
            
            max_iterations = st.slider("最大迭代次数", 1, 10, 5)
            
            submitted = st.form_submit_button("🚀 启动循环", type="primary")
            
            if submitted:
                with st.spinner("🔄 循环执行中..."):
                    result = brain.subagents.invoke("loop_engineering", {
                        "action": "run",
                        "template": selected_template,
                        "input": input_data,
                        "max_iterations": max_iterations,
                    })
                    
                    st.session_state.loop_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "template": selected_template,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 循环完成！状态: {result.get('status')}")
                        
                        st.subheader("📊 循环统计")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("总迭代次数", result.get("total_iterations", 0))
                        with col2:
                            st.metric("最大迭代次数", result.get("max_iterations", 0))
                        with col3:
                            st.metric("耗时(秒)", f"{result.get('duration', 0):.2f}")
                        
                        if result.get("iterations"):
                            st.subheader("📋 迭代详情")
                            for iteration in result["iterations"]:
                                with st.expander(f"🔄 迭代 #{iteration['iteration']}"):
                                    st.markdown(f"**执行结果:**")
                                    st.markdown(iteration.get('result', ''))
                                    
                                    st.markdown(f"**验收结果:** {'✅ 通过' if iteration.get('verified') else '❌ 未通过'}")
                                    st.markdown(f"**验收详情:**")
                                    st.markdown(iteration.get('verification', {}).get('verification', ''))
                                    
                                    if not iteration.get('verified'):
                                        st.markdown(f"**复盘建议:**")
                                        st.markdown(iteration.get('review', {}).get('review', ''))
                        
                        if result.get("final_result"):
                            st.subheader("🎯 最终结果")
                            st.markdown(result["final_result"])
                    else:
                        st.error(f"❌ 执行失败: {result.get('error')}")
    
    if st.session_state.loop_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.loop_results[:3]:
            with st.expander(f"⏰ {entry['timestamp']} - {templates[entry['template']]['name']}"):
                st.json(entry["result"])
    
    st.divider()
    st.subheader("📚 行业演进")
    st.markdown("""
    **Prompt Engineering** → **Context Engineering** → **Harness Engineering** → **Loop Engineering**
    
    - 📝 Prompt Engineering: 比拼"谁会提问"
    - 📋 Context Engineering: 比拼"谁会给AI提供有效信息"
    - 🛠️ Harness Engineering: 比拼"谁能搭建高效的工具链"
    - 🔄 Loop Engineering: 比拼"谁能设计出高质量的闭环机制"
    """)


# ---- ViMax Video Page ----
elif page == "🎬 ViMax视频":
    st.title("🎬 ViMax 多智能体视频生成")
    st.caption("ViMax by HKUDS — 从创意到成片的端到端自动化")
    
    if "vimax_workflow" not in st.session_state:
        st.session_state.vimax_workflow = "idea2video"
    if "vimax_results" not in st.session_state:
        st.session_state.vimax_results = []
    
    workflows = {
        "idea2video": {"name": "Idea2Video", "icon": "💡", "desc": "一句话创意 → 完整视频", 
                      "example": "一个勇敢的宇航员在火星上发现古老文明的遗迹"},
        "novel2video": {"name": "Novel2Video", "icon": "📖", "desc": "小说文本 → 分集视频",
                       "example": "《三体》第一章内容..."},
        "script2video": {"name": "Script2Video", "icon": "📝", "desc": "标准剧本 → 视频",
                        "example": "场景1：办公室\\n人物：张三、李四\\n张三：你好，李四..."},
        "autocameo": {"name": "AutoCameo", "icon": "🎭", "desc": "照片客串 → 视频",
                     "example": "上传照片，成为视频主角"},
    }
    
    selected_workflow = st.selectbox(
        "选择工作流",
        list(workflows.keys()),
        format_func=lambda x: f"{workflows[x]['icon']} {workflows[x]['name']} - {workflows[x]['desc']}"
    )
    
    st.divider()
    
    st.subheader(f"{workflows[selected_workflow]['icon']} {workflows[selected_workflow]['name']}")
    
    with st.form("vimax_form"):
        input_content = st.text_area(
            "输入内容",
            workflows[selected_workflow]["example"],
            height=150,
            help="根据选择的工作流，输入创意、小说、剧本或照片路径"
        )
        
        col1, col2 = st.columns(2)
        
        with col1:
            resolution = st.selectbox("分辨率", ["720p", "1080p", "4K"], index=1)
            if selected_workflow == "idea2video":
                duration = st.slider("视频时长(秒)", 10, 120, 30, step=10)
                style = st.selectbox("风格", ["cinematic", "cartoon", "realistic", "abstract"], index=0)
            elif selected_workflow == "novel2video":
                chapters = st.slider("分集数", 2, 10, 5)
                chapter_duration = st.slider("每集时长(秒)", 30, 180, 60, step=30)
            elif selected_workflow == "script2video":
                script_style = st.selectbox("风格", ["cinematic", "documentary", "commercial"], index=0)
            elif selected_workflow == "autocameo":
                photo_path = st.text_input("照片路径", "")
        
        with col2:
            st.subheader("🎬 工作流介绍")
            st.markdown(f"**{workflows[selected_workflow]['name']}**")
            st.markdown(f"描述: {workflows[selected_workflow]['desc']}")
            st.markdown("---")
            st.markdown("**技术亮点:**")
            st.markdown("- 🧠 多智能体协作 (编剧、分镜、角色设计)")
            st.markdown("- 🔗 RAG 技术维持叙事连贯性")
            st.markdown("- 👁️ 跨镜头视觉一致性监控")
            st.markdown("- 🎯 端到端自动化流程")
        
        submitted = st.form_submit_button("🚀 生成视频", type="primary")
        
        if submitted:
            with st.spinner("🎬 ViMax 正在生成视频..."):
                params = {"resolution": resolution}
                if selected_workflow == "idea2video":
                    params.update({"duration": duration, "style": style})
                elif selected_workflow == "novel2video":
                    params.update({"chapters": chapters, "duration_per_chapter": chapter_duration})
                elif selected_workflow == "script2video":
                    params.update({"style": script_style})
                elif selected_workflow == "autocameo":
                    params.update({"photo_path": photo_path})
                
                result = brain.subagents.invoke("vimax", {
                    "workflow": selected_workflow,
                    "input": input_content,
                    "params": params
                })
                
                st.session_state.vimax_results.insert(0, {
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "workflow": selected_workflow,
                    "workflow_name": workflows[selected_workflow]["name"],
                    "result": result,
                })
                
                if result.get("success"):
                    st.success(f"✅ 视频生成成功！任务ID: {result.get('task_id')}")
                    st.json(result)
                    
                    video_url = result.get("video_url")
                    if video_url:
                        st.video(video_url)
                else:
                    st.error(f"❌ 生成失败: {result.get('error', '未知错误')}")
    
    if st.session_state.vimax_results:
        st.divider()
        st.subheader("📜 历史记录")
        
        for entry in st.session_state.vimax_results[:5]:
            with st.expander(f"⏰ {entry['timestamp']} - {entry['workflow_name']}"):
                result = entry["result"]
                if result.get("success"):
                    st.success(f"任务ID: {result.get('task_id')}")
                    if result.get("video_url"):
                        st.video(result["video_url"])
                    st.json(result)
                else:
                    st.error(result.get("error"))
    
    st.divider()
    st.subheader("⚙️ API 配置")
    
    col1, col2 = st.columns(2)
    with col1:
        google_key = st.text_input("Google API Key", type="password", 
                                  help="用于 Gemini 2.5 和 Veo 视频生成")
        if st.button("保存 Google Key"):
            os.environ["GOOGLE_API_KEY"] = google_key
            st.success("已保存")
    with col2:
        seedance_key = st.text_input("豆包 Seedance API Key", type="password",
                                     help="可选，用于额外视频生成能力")
        if st.button("保存 Seedance Key"):
            os.environ["SEEDANCE_API_KEY"] = seedance_key
            st.success("已保存")
    
    st.info("💡 **提示**: 未安装 ViMax SDK 时将使用模拟模式。实际使用请运行: `pip install vimax`")


# ---- ComfyUI Visual Generation Page ----
elif page == "🎨 ComfyUI视觉":
    st.title("🎨 ComfyUI 视觉内容生产引擎")
    st.caption("VisualWorker — 文生图、图生视频、风格迁移、视频生视频")

    comfyui_features = {
        "txt2img": {"name": "文生图", "emoji": "🖼️", "desc": "根据提示词生成高质量图像", "input": ["prompt", "negative_prompt", "width", "height"]},
        "img2vid": {"name": "图生视频", "emoji": "🎬", "desc": "将静态图片转换为动态视频", "input": ["image_path", "prompt", "duration"]},
        "style_transfer": {"name": "风格迁移", "emoji": "🎭", "desc": "将图片转换为指定风格", "input": ["image_path", "reference_image", "style_prompt"]},
        "vid2vid": {"name": "视频生视频", "emoji": "🎮", "desc": "对视频进行风格化处理", "input": ["video_path", "prompt", "style"]},
    }

    if "comfyui_results" not in st.session_state:
        st.session_state.comfyui_results = []

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("🔧 工作流模板")
        for key, info in comfyui_features.items():
            st.markdown(f"**{info['emoji']} {info['name']}**")
            st.caption(info['desc'])
            st.markdown("---")

        st.subheader("📊 系统状态")
        try:
            status_result = brain.skill_registry.execute("comfyui", {"action": "status"})
            if status_result.get("success") and status_result.get("result", {}).get("running"):
                st.success("✅ ComfyUI 服务运行中")
                st.caption(f"地址: {status_result['result']['url']}")
            else:
                st.warning("⚠️ ComfyUI 未运行")
                st.caption("将使用降级模式")
        except Exception as e:
            st.warning(f"⚠️ 状态检查失败: {e}")

    with col2:
        tab1, tab2, tab3, tab4 = st.tabs(["🖼️ 文生图", "🎬 图生视频", "🎭 风格迁移", "🎮 视频生视频"])

        with tab1:
            with st.form("comfyui_txt2img"):
                prompt = st.text_area("提示词", "一只可爱的小猫在草地上玩耍，阳光明媚，水彩风格", height=80)
                negative_prompt = st.text_input("负向提示词", "low quality, blurry, distorted, bad anatomy")
                
                col1, col2 = st.columns(2)
                with col1:
                    width = st.slider("宽度", 512, 1536, 1024, step=128)
                with col2:
                    height = st.slider("高度", 512, 1536, 768, step=128)
                
                col1, col2 = st.columns(2)
                with col1:
                    steps = st.slider("步数", 10, 50, 20, step=5)
                with col2:
                    cfg_scale = st.slider("CFG Scale", 1, 15, 7, step=0.5)

                submitted = st.form_submit_button("🎨 生成图像", type="primary")

                if submitted:
                    with st.spinner("生成中..."):
                        result = brain.skill_registry.execute("comfyui", {
                            "action": "txt2img",
                            "prompt": prompt,
                            "negative_prompt": negative_prompt,
                            "width": width,
                            "height": height,
                            "steps": steps,
                            "cfg_scale": cfg_scale,
                        })

                        st.session_state.comfyui_results.insert(0, {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "action": "txt2img",
                            "action_name": "文生图",
                            "result": result,
                        })

                        if result.get("success"):
                            st.success(f"✅ 生成成功！任务ID: {result.get('task_id')}")
                            result_data = result.get("result", {})
                            output_path = result_data.get("output_path")
                            if output_path and os.path.exists(output_path):
                                st.image(output_path, caption="生成的图像", use_column_width=True)
                            else:
                                st.json(result)
                        else:
                            st.error(f"❌ 生成失败: {result.get('error', '未知错误')}")

        with tab2:
            with st.form("comfyui_img2vid"):
                image_path = st.text_input("输入图像路径", os.path.join(OUTPUTS_DIR, "comfyui", "example.jpg"))
                prompt = st.text_area("视频描述", "让图片中的风景动起来，流水潺潺，树叶飘动", height=60)
                duration = st.slider("视频时长(秒)", 3, 15, 5, step=1)

                submitted = st.form_submit_button("🎬 生成视频", type="primary")

                if submitted:
                    with st.spinner("生成中..."):
                        result = brain.skill_registry.execute("comfyui", {
                            "action": "img2vid",
                            "image_path": image_path,
                            "prompt": prompt,
                            "duration": duration,
                        })

                        st.session_state.comfyui_results.insert(0, {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "action": "img2vid",
                            "action_name": "图生视频",
                            "result": result,
                        })

                        if result.get("success"):
                            st.success(f"✅ 生成成功！任务ID: {result.get('task_id')}")
                            result_data = result.get("result", {})
                            output_path = result_data.get("output_path")
                            if output_path and os.path.exists(output_path):
                                st.video(output_path)
                            else:
                                st.json(result)
                        else:
                            st.error(f"❌ 生成失败: {result.get('error', '未知错误')}")

        with tab3:
            with st.form("comfyui_style_transfer"):
                image_path = st.text_input("源图像路径", os.path.join(OUTPUTS_DIR, "comfyui", "source.jpg"))
                reference_image = st.text_input("参考风格图像路径", os.path.join(OUTPUTS_DIR, "comfyui", "style.jpg"))
                style_prompt = st.text_area("风格描述", "梵高星空风格，印象派，色彩鲜艳", height=60)

                submitted = st.form_submit_button("🎭 风格迁移", type="primary")

                if submitted:
                    with st.spinner("生成中..."):
                        result = brain.skill_registry.execute("comfyui", {
                            "action": "style_transfer",
                            "image_path": image_path,
                            "reference_image": reference_image,
                            "style_prompt": style_prompt,
                        })

                        st.session_state.comfyui_results.insert(0, {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "action": "style_transfer",
                            "action_name": "风格迁移",
                            "result": result,
                        })

                        if result.get("success"):
                            st.success(f"✅ 生成成功！任务ID: {result.get('task_id')}")
                            result_data = result.get("result", {})
                            output_path = result_data.get("output_path")
                            if output_path and os.path.exists(output_path):
                                st.image(output_path, caption="风格迁移结果", use_column_width=True)
                            else:
                                st.json(result)
                        else:
                            st.error(f"❌ 生成失败: {result.get('error', '未知错误')}")

        with tab4:
            with st.form("comfyui_vid2vid"):
                video_path = st.text_input("输入视频路径", os.path.join(OUTPUTS_DIR, "comfyui", "input.mp4"))
                prompt = st.text_area("风格描述", "赛博朋克风格，霓虹灯光，未来感", height=60)
                style = st.selectbox("风格类型", ["cyberpunk", "anime", "watercolor", "oil_painting", "sketch"])

                submitted = st.form_submit_button("🎮 视频转换", type="primary")

                if submitted:
                    with st.spinner("生成中..."):
                        result = brain.skill_registry.execute("comfyui", {
                            "action": "vid2vid",
                            "video_path": video_path,
                            "prompt": prompt,
                            "style": style,
                        })

                        st.session_state.comfyui_results.insert(0, {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "action": "vid2vid",
                            "action_name": "视频生视频",
                            "result": result,
                        })

                        if result.get("success"):
                            st.success(f"✅ 生成成功！任务ID: {result.get('task_id')}")
                            result_data = result.get("result", {})
                            output_path = result_data.get("output_path")
                            if output_path and os.path.exists(output_path):
                                st.video(output_path)
                            else:
                                st.json(result)
                        else:
                            st.error(f"❌ 生成失败: {result.get('error', '未知错误')}")

    if st.session_state.comfyui_results:
        st.divider()
        st.subheader("📜 历史记录")

        for entry in st.session_state.comfyui_results[:5]:
            with st.expander(f"⏰ {entry['timestamp']} - {entry['action_name']}"):
                result = entry["result"]
                if result.get("success"):
                    st.success(f"任务ID: {result.get('task_id')}")
                    result_data = result.get("result", {})
                    output_path = result_data.get("output_path")
                    if output_path and os.path.exists(output_path):
                        if output_path.lower().endswith(('.mp4', '.avi', '.mov')):
                            st.video(output_path)
                        else:
                            st.image(output_path)
                    st.json(result)
                else:
                    st.error(result.get("error"))

    st.divider()
    st.subheader("⚙️ 配置")

    col1, col2 = st.columns(2)
    with col1:
        comfyui_url = st.text_input("ComfyUI 服务地址", "http://localhost:8188")
        if st.button("保存地址"):
            os.environ["COMFYUI_BASE_URL"] = comfyui_url
            st.success("已保存")
    with col2:
        workflows_dir = st.text_input("工作流模板目录", "./src/skills/workflows")
        if st.button("保存目录"):
            os.environ["COMFYUI_WORKFLOWS_DIR"] = workflows_dir
            st.success("已保存")

    st.info("💡 **提示**: 需要启动 ComfyUI 服务才能生成真实图像/视频。启动命令: `python main.py --listen --lowvram`")


# ---- Pixelle Video Page ----
elif page == "🎥 Pixelle短视频":
    st.title("🎥 Pixelle-Video 短视频自动化生产线")
    st.caption("阿里短视频引擎 — 文案+配图+配音+合成，一键出片")
    
    if "pixelle_results" not in st.session_state:
        st.session_state.pixelle_results = []
    
    styles = {
        "douyin": {"name": "抖音风格", "emoji": "🎵", "desc": "竖屏9:16，快节奏", "ratio": "9:16"},
        "kuaishou": {"name": "快手风格", "emoji": "📱", "desc": "竖屏9:16，生活化", "ratio": "9:16"},
        "youtube": {"name": "YouTube风格", "emoji": "📺", "desc": "横屏16:9，专业感", "ratio": "16:9"},
        "weibo": {"name": "微博风格", "emoji": "📢", "desc": "方形1:1，社交分享", "ratio": "1:1"},
    }
    
    voices = {
        "female": {"name": "女声", "emoji": "👩", "desc": "温柔甜美"},
        "male": {"name": "男声", "emoji": "👨", "desc": "稳重磁性"},
        "child": {"name": "童声", "emoji": "👧", "desc": "活泼可爱"},
        "robot": {"name": "机器人", "emoji": "🤖", "desc": "科技感"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📋 生产流程")
        steps = [
            {"name": "文案生成", "emoji": "✍️", "desc": "LLM写文案"},
            {"name": "配图生成", "emoji": "🖼️", "desc": "文生图/视频"},
            {"name": "语音合成", "emoji": "🎤", "desc": "TTS配音"},
            {"name": "背景音乐", "emoji": "🎵", "desc": "添加BGM"},
            {"name": "视频合成", "emoji": "🎬", "desc": "一键出片"},
        ]
        for step in steps:
            st.markdown(f"**{step['emoji']} {step['name']}**")
            st.caption(step['desc'])
            st.markdown("---")
    
    with col2:
        with st.form("pixelle_form"):
            topic = st.text_input("视频主题", "如何快速提升工作效率")
            
            col1, col2 = st.columns(2)
            with col1:
                selected_style = st.selectbox(
                    "选择风格",
                    list(styles.keys()),
                    format_func=lambda x: f"{styles[x]['emoji']} {styles[x]['name']}"
                )
            with col2:
                selected_voice = st.selectbox(
                    "选择配音",
                    list(voices.keys()),
                    format_func=lambda x: f"{voices[x]['emoji']} {voices[x]['name']}"
                )
            
            duration = st.slider("视频时长(秒)", 30, 120, 60, step=10)
            
            submitted = st.form_submit_button("🚀 一键生成", type="primary")
            
            if submitted:
                with st.spinner("🎥 短视频生产中..."):
                    result = brain.subagents.invoke("pixelle_video", {
                        "topic": topic,
                        "style": selected_style,
                        "duration": duration,
                        "voice": selected_voice,
                    })
                    
                    st.session_state.pixelle_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "topic": topic,
                        "style": selected_style,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 视频生成完成！任务ID: {result.get('task_id')}")
                        
                        st.subheader("📊 生产详情")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("风格", styles[selected_style]["name"])
                        with col2:
                            st.metric("配音", voices[selected_voice]["name"])
                        with col3:
                            st.metric("时长", f"{duration}秒")
                        
                        if result.get("steps"):
                            st.subheader("📋 步骤进度")
                            for step in result["steps"]:
                                status_icon = "✅" if step.get("status") == "completed" else "🔄"
                                st.markdown(f"{status_icon} **{step.get('name')}**: {step.get('status')}")
                        
                        result_data = result.get("result", {})
                        if result_data.get("script", {}).get("full_text"):
                            st.subheader("✍️ 生成的文案")
                            st.markdown(result_data["script"]["full_text"])
                            
                            if st.button("📋 复制文案"):
                                st.copy_to_clipboard(result_data["script"]["full_text"])
                                st.success("已复制")
                        
                        if result_data.get("images"):
                            st.subheader("🖼️ 生成的配图")
                            for img in result_data["images"][:3]:
                                st.markdown(f"- **场景{img['id']}**: {img['scene']}")
                                st.markdown(f"  提示词: {img['prompt']}")
                        
                        if result_data.get("video_url"):
                            st.subheader("🎬 预览视频")
                            st.video(result_data["video_url"])
                    else:
                        st.error(f"❌ 生成失败: {result.get('error')}")
    
    if st.session_state.pixelle_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.pixelle_results[:5]:
            with st.expander(f"⏰ {entry['timestamp']} - {entry['topic']}"):
                st.json(entry["result"])
    
    st.divider()
    st.subheader("⚙️ 技术特点")
    st.markdown("""
    - 🚀 **ComfyUI 流水线模式**: LLM写文案 → 文生图/视频 → TTS配音 → 合成输出
    - 💾 **支持离线运行**: 可使用Ollama完全离线执行
    - 📦 **Apache-2.0 协议**: 可自由使用、修改和商用
    - 🖥️ **低硬件要求**: 8GB内存可跑CPU模式
    """)


# ---- OpenMontage Page ----
elif page == "🎬 OpenMontage":
    st.title("🎬 OpenMontage 视频生产流水线")
    st.caption("12条专业视频生产流水线 — 从创意到视频的端到端自动化")
    
    if "openmontage_results" not in st.session_state:
        st.session_state.openmontage_results = []
    
    pipeline_result = brain.subagents.invoke("open_montage", {"action": "list_pipelines"})
    pipelines = {}
    if pipeline_result.get("success"):
        pipelines = pipeline_result.get("result", {}).get("pipelines", {})
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🎛️ 流水线列表")
        pipeline_emojis = {"idea2video": "💡", "novel2video": "📖", "script2video": "📝", 
                          "autocameo": "🎭", "short_video": "📱", "tutorial_video": "🎓",
                          "product_showcase": "📦", "vlog_video": "🎥", "animation_video": "🎨",
                          "live_stream": "🔴", "documentary": "📽️", "ad_commercial": "📺"}
        
        for pipe_key, pipe_info in pipelines.items():
            emoji = pipeline_emojis.get(pipe_key, "🎬")
            with st.expander(f"{emoji} {pipe_info.get('name', pipe_key)}"):
                st.write(pipe_info.get('description', ''))
                st.write(f"**时长**: {pipe_info.get('duration', '')}")
                st.write(f"**质量**: {pipe_info.get('quality', '')}")
                st.write("**步骤**:")
                for step in pipe_info.get('steps', []):
                    st.markdown(f"- {step}")
    
    with col2:
        with st.form("openmontage_form"):
            selected_pipeline = st.selectbox(
                "选择流水线",
                list(pipelines.keys()),
                format_func=lambda x: f"{pipeline_emojis.get(x, '🎬')} {pipelines[x].get('name', x)}"
            )
            
            input_content = st.text_area(
                "输入内容",
                "一个未来城市的概念视频，展示自动驾驶汽车和智能建筑",
                height=100
            )
            
            col1_opt, col2_opt = st.columns(2)
            with col1_opt:
                duration = st.slider("视频时长(秒)", 10, 120, 30, step=10)
            with col2_opt:
                quality = st.selectbox("质量", ["low", "medium", "high", "professional"])
            
            submitted = st.form_submit_button("🚀 生成视频", type="primary")
            
            if submitted:
                with st.spinner("🎬 视频生产中..."):
                    result = brain.subagents.invoke("open_montage", {
                        "action": "create_video",
                        "pipeline": selected_pipeline,
                        "content": input_content,
                        "duration": duration,
                        "quality": quality,
                    })
                    
                    brain.audit.log(AuditEvent.AGENT_TOOL_CALL,
                                   details={"action": "create_video", "pipeline": selected_pipeline})
                    
                    st.session_state.openmontage_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "pipeline": selected_pipeline,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 视频生成成功！任务ID: {result.get('task_id')}")
                        
                        result_data = result.get("result", {})
                        
                        if result_data.get("steps"):
                            st.subheader("📋 生产进度")
                            progress_bar = st.progress(0)
                            total_steps = len(result_data["steps"])
                            for i, step in enumerate(result_data["steps"]):
                                icon = "✅" if step.get("status") == "completed" else "🔄"
                                st.markdown(f"{icon} **{step.get('step', '')}**: {step.get('message', '')}")
                                progress_bar.progress((i + 1) / total_steps)
                        
                        if result_data.get("video_url"):
                            st.subheader("🎬 预览视频")
                            st.video(result_data["video_url"])
                        elif result_data.get("preview_url"):
                            st.subheader("🖼️ 预览图")
                            st.image(result_data["preview_url"])
                    else:
                        st.error(f"❌ 生成失败: {result.get('error')}")
    
    st.divider()
    st.subheader("🛠️ 工具统计")
    tools_result = brain.subagents.invoke("open_montage", {"action": "list_tools"})
    if tools_result.get("success"):
        tool_count = tools_result.get("result", {}).get("count", 0)
        st.metric("工具总数", tool_count)
    
    if st.session_state.openmontage_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.openmontage_results[:3]:
            pipe_info = pipelines.get(entry['pipeline'], {'name': entry['pipeline']})
            with st.expander(f"⏰ {entry['timestamp']} - {pipe_info.get('name')}"):
                st.json(entry["result"])
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 🎬 **12条流水线**: 覆盖多种视频生产场景
    - 🛠️ **52种工具**: 丰富的视频处理能力
    - 🧠 **500+技能**: Agent技能库
    - 🔄 **自动化流程**: 一键生成视频
    - 📱 **多平台适配**: 抖音、快手、B站等
    """)


# ---- Video-Use Page ----
elif page == "✂️ 视频剪辑":
    st.title("✂️ Video-Use 对话式视频剪辑")
    st.caption("AI通过自然语言指令自动完成视频剪辑")
    
    if "videouse_results" not in st.session_state:
        st.session_state.videouse_results = []
    
    operations = {
        "clip_video": {"name": "对话式剪辑", "emoji": "✂️", "desc": "用自然语言描述剪辑需求"},
        "trim_video": {"name": "裁剪视频", "emoji": "📐", "desc": "裁剪视频到指定时间段"},
        "merge_clips": {"name": "合并片段", "emoji": "🔗", "desc": "合并多个视频片段"},
        "add_subtitles": {"name": "添加字幕", "emoji": "📝", "desc": "为视频添加字幕"},
        "apply_filter": {"name": "应用滤镜", "emoji": "🎨", "desc": "应用视觉滤镜效果"},
        "add_music": {"name": "添加音乐", "emoji": "🎵", "desc": "添加背景音乐"},
        "speed_up": {"name": "加速视频", "emoji": "⚡", "desc": "加快播放速度"},
        "slow_down": {"name": "减速视频", "emoji": "🐢", "desc": "减慢播放速度"},
        "extract_audio": {"name": "提取音频", "emoji": "🔊", "desc": "从视频中提取音频"},
        "reverse_video": {"name": "反转视频", "emoji": "🔄", "desc": "反转播放顺序"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🔧 剪辑操作")
        for op_key, op_info in operations.items():
            if st.button(f"{op_info['emoji']} {op_info['name']}", key=f"videouse_op_{op_key}"):
                st.session_state['videouse_op'] = op_key
                st.rerun()
    
    with col2:
        selected_op = st.session_state.get('videouse_op', 'clip_video')
        
        with st.form("videouse_form"):
            st.subheader(f"{operations[selected_op]['emoji']} {operations[selected_op]['name']}")
            
            video_url = st.text_input("视频URL/路径", "https://example.com/video.mp4")
            
            params = {"action": selected_op, "video_url": video_url}
            
            if selected_op == "clip_video":
                instruction = st.text_area(
                    "自然语言指令",
                    "把视频前30秒剪掉，添加中文字幕，加速到1.5倍，添加背景音乐",
                    height=100,
                    help="用自然语言描述你想对视频做什么"
                )
                params["instruction"] = instruction
            
            elif selected_op == "trim_video":
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    start_time = st.number_input("开始时间(秒)", min_value=0, value=0)
                with col_t2:
                    end_time = st.number_input("结束时间(秒)", min_value=1, value=60)
                params["start_time"] = start_time
                params["end_time"] = end_time
            
            elif selected_op == "add_subtitles":
                subtitle_text = st.text_area("字幕内容", "这是第一行字幕\n这是第二行字幕", height=80)
                params["text"] = subtitle_text
            
            elif selected_op == "apply_filter":
                filter_list = ["brightness", "contrast", "saturation", "grayscale", "sepia", "vintage", "cool", "warm", "blur", "sharpen"]
                selected_filter = st.selectbox("选择滤镜", filter_list, format_func=lambda x: {"brightness": "亮度", "contrast": "对比度", "saturation": "饱和度", "grayscale": "灰度", "sepia": "复古", "vintage": "怀旧", "cool": "冷色调", "warm": "暖色调", "blur": "模糊", "sharpen": "锐化"}[x])
                intensity = st.slider("强度", 0.1, 2.0, 1.0, step=0.1)
                params["filter"] = selected_filter
                params["intensity"] = intensity
            
            elif selected_op == "add_music":
                music_genre = st.selectbox("音乐风格", ["background", "upbeat", "dramatic", "romantic", "epic", "chill", "electronic", "classical"], format_func=lambda x: {"background": "背景音乐", "upbeat": "欢快", "dramatic": "戏剧性", "romantic": "浪漫", "epic": "史诗", "chill": "放松", "electronic": "电子", "classical": "古典"}[x])
                volume = st.slider("音量", 0.0, 1.0, 0.5, step=0.1)
                params["music_url"] = f"music://{music_genre}"
                params["volume"] = volume
            
            elif selected_op in ["speed_up", "slow_down"]:
                speed = st.slider("速度倍数", 0.1, 3.0, 1.5 if selected_op == "speed_up" else 0.5, step=0.1)
                params["speed"] = speed
            
            submitted = st.form_submit_button("✂️ 执行剪辑", type="primary")
            
            if submitted:
                with st.spinner("✂️ 视频剪辑中..."):
                    result = brain.subagents.invoke("video_use", params)
                    
                    brain.audit.log(AuditEvent.AGENT_TOOL_CALL,
                                   details={"action": selected_op, "video_url": video_url})
                    
                    st.session_state.videouse_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "instruction": instruction if "instruction" in params else selected_op,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 剪辑完成！")
                        
                        result_data = result.get("result", {})
                        
                        if result_data.get("operations"):
                            st.subheader("📋 执行的操作")
                            for op in result_data["operations"]:
                                icon = "✅" if op.get("status") == "completed" else "🔄"
                                st.markdown(f"{icon} **{op.get('command', '')}**: {op.get('description', '')}")
                        
                        if result_data.get("edited_url"):
                            st.subheader("🎬 剪辑结果")
                            st.video(result_data["edited_url"])
                        elif result_data.get("audio_url"):
                            st.subheader("🔊 提取的音频")
                            st.audio(result_data["audio_url"])
                    else:
                        st.error(f"❌ 剪辑失败: {result.get('error')}")
    
    if st.session_state.videouse_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.videouse_results[:3]:
            with st.expander(f"⏰ {entry['timestamp']}"):
                st.caption(f"指令: {entry['instruction']}")
                st.json(entry["result"])
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 🗣️ **自然语言**: 用中文描述剪辑需求
    - ✂️ **智能解析**: AI自动理解剪辑指令
    - 🎯 **精准操作**: 精确控制剪辑效果
    - ⚡ **快速处理**: 高效视频处理
    - 🎨 **10种滤镜**: 亮度、对比度、复古等
    - 🎵 **8种音乐**: 背景音乐、欢快、史诗等
    """)


# ---- OmniRoute Page ----
elif page == "🎛️ 模型网关":
    st.title("🎛️ OmniRoute 智能模型网关")
    st.caption("统一接口连接231家AI提供商 — 4级智能降级，自动故障转移")
    
    if "omniroute_stats" not in st.session_state:
        st.session_state.omniroute_stats = {}
    
    strategies = {
        "cost": {"name": "成本优先", "emoji": "💰", "desc": "选择最便宜的提供商"},
        "performance": {"name": "性能优先", "emoji": "⚡", "desc": "选择响应最快的提供商"},
        "reliability": {"name": "可靠性优先", "emoji": "🔒", "desc": "选择最稳定的提供商"},
        "balanced": {"name": "平衡模式", "emoji": "⚖️", "desc": "综合平衡成本和性能"},
        "auto": {"name": "自动选择", "emoji": "🤖", "desc": "根据任务复杂度自动选择"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📊 提供商状态")
        provider_result = brain.subagents.invoke("omni_route", {"action": "list_providers"})
        if provider_result.get("success"):
            providers = provider_result.get("result", {}).get("providers", [])
            for provider in providers:
                status_icon = "🟢" if provider["status"] == "available" else "🔴"
                st.markdown(f"**{status_icon} {provider['name']}**")
                st.caption(f"模型: {provider['model']}")
                st.caption(f"延迟: {provider['latency']}ms | 成本: ${provider['cost_per_token']:.6f}/token")
                if provider["quota_remaining"] != float("inf"):
                    quota_percent = (provider["quota_remaining"] / provider["quota_total"]) * 100
                    st.progress(quota_percent)
                    st.caption(f"配额剩余: {int(provider['quota_remaining']):,}")
                st.markdown("---")
        else:
            st.error(f"❌ 获取提供商列表失败: {provider_result.get('error')}")
    
    with col2:
        with st.form("omniroute_form"):
            selected_strategy = st.selectbox(
                "路由策略",
                list(strategies.keys()),
                format_func=lambda x: f"{strategies[x]['emoji']} {strategies[x]['name']}"
            )
            
            message = st.text_area("测试消息", "你好，请介绍一下你自己", height=80)
            
            col1_btn, col2_btn = st.columns(2)
            with col1_btn:
                auto_failover = st.checkbox("自动故障转移", value=True)
            with col2_btn:
                quota_tracking = st.checkbox("配额追踪", value=True)
            
            submitted = st.form_submit_button("🚀 发送请求", type="primary")
            
            if submitted:
                with st.spinner("🔄 智能路由中..."):
                    result = brain.subagents.invoke("omni_route", {
                        "action": "route_request",
                        "message": message,
                        "strategy": selected_strategy,
                        "auto_failover": auto_failover,
                        "quota_tracking": quota_tracking,
                    })
                    
                    brain.audit.log(AuditEvent.MODEL_REQUEST, 
                                   details={"strategy": selected_strategy, "message_length": len(message)})
                    
                    if result.get("success"):
                        st.success(f"✅ 请求成功！")
                        
                        result_data = result.get("result", {})
                        provider_info = result_data.get("provider", {})
                        
                        st.subheader("🔌 路由信息")
                        st.markdown(f"**选择的提供商**: {provider_info.get('name', 'N/A')}")
                        st.markdown(f"**使用模型**: {provider_info.get('model', 'N/A')}")
                        st.markdown(f"**路由原因**: {result_data.get('routing_reason', 'N/A')}")
                        st.markdown(f"**延迟**: {result_data.get('latency', 0)}ms")
                        st.markdown(f"**Token消耗**: {int(result_data.get('tokens_used', 0)):,}")
                        st.markdown(f"**成本**: ${result_data.get('cost', 0):.6f}")
                        
                        if result_data.get("response"):
                            st.subheader("🤖 模型回复")
                            st.markdown(result_data["response"])
                            
                            brain.audit.log(AuditEvent.MODEL_RESPONSE, 
                                           details={"provider": provider_info.get('name'), "tokens": int(result_data.get('tokens_used', 0))})
                    else:
                        st.error(f"❌ 请求失败: {result.get('error')}")
                        brain.audit.log(AuditEvent.SYSTEM_ERROR, 
                                       details={"error": result.get('error'), "action": "route_request"})
    
    st.divider()
    st.subheader("📈 配额统计")
    quota_result = brain.subagents.invoke("omni_route", {"action": "get_quota_stats"})
    if quota_result.get("success"):
        quota_data = quota_result.get("result", {})
        col_q1, col_q2 = st.columns(2)
        with col_q1:
            st.metric("总Token消耗", f"{int(quota_data.get('total_tokens', 0)):,}")
        with col_q2:
            st.metric("总成本", f"${quota_data.get('total_cost', 0):.6f}")
    
    st.divider()
    st.subheader("🎯 4级智能降级")
    st.markdown("""
    1. **订阅级** 🥇: OpenAI、Anthropic等付费API - 最高优先级
    2. **API Key级** 🥈: 智谱AI、通义千问等按调用计费 - 标准优先级
    3. **低价级** 🥉: Ollama本地等低成本选项 - 低优先级
    4. **免费级** 🤝: 本地免费模型 - 最低优先级
    
    自动故障转移：当高级别提供商不可用时，自动降级到低级别
    """)


# ---- Cognee Page ----
elif page == "🧠 知识图谱":
    st.title("🧠 Cognee 知识图谱记忆层")
    st.caption("将对话、文档转化为长期记忆 — 知识图谱推理能力")
    
    if "cognee_results" not in st.session_state:
        st.session_state.cognee_results = []
    
    actions = {
        "add_knowledge": {"name": "添加知识", "emoji": "📥", "desc": "添加新的知识实体"},
        "search_knowledge": {"name": "搜索知识", "emoji": "🔍", "desc": "搜索知识图谱"},
        "query_graph": {"name": "查询图谱", "emoji": "📊", "desc": "查询知识图谱结构"},
        "discover_relations": {"name": "发现关系", "emoji": "🔗", "desc": "发现实体间的关系"},
        "list_entities": {"name": "列出实体", "emoji": "📋", "desc": "列出所有知识实体"},
        "export_graph": {"name": "导出图谱", "emoji": "📤", "desc": "导出知识图谱"},
        "get_stats": {"name": "统计信息", "emoji": "📈", "desc": "图谱统计信息"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🔧 知识操作")
        for action_key, action_info in actions.items():
            if st.button(f"{action_info['emoji']} {action_info['name']}", key=f"action_{action_key}"):
                st.session_state['cognee_action'] = action_key
                st.rerun()
    
    with col2:
        selected_action = st.session_state.get('cognee_action', 'add_knowledge')
        
        with st.form("cognee_form"):
            st.subheader(f"{actions[selected_action]['emoji']} {actions[selected_action]['name']}")
            
            if selected_action == "add_knowledge":
                content = st.text_area("知识内容", "人工智能是计算机科学的一个分支，致力于研究、开发用于模拟、延伸和扩展人的智能的理论、方法、技术及应用系统", height=100)
                entity_type = st.selectbox("实体类型", ["concept", "person", "organization", "technology", "project", "document", "location", "event"])
            
            elif selected_action == "search_knowledge":
                query = st.text_input("搜索关键词", "人工智能")
                entity_type_filter = st.selectbox("实体类型过滤", ["", "concept", "person", "organization", "technology", "project"])
            
            elif selected_action == "query_graph":
                query = st.text_input("查询内容", "")
                entity_id = st.text_input("实体ID（可选）", "")
            
            elif selected_action == "discover_relations":
                entity_id = st.text_input("实体ID", "")
            
            elif selected_action == "list_entities":
                entity_type_filter = st.selectbox("实体类型", ["", "concept", "person", "organization", "technology", "project"])
            
            elif selected_action == "export_graph":
                export_format = st.selectbox("导出格式", ["json"])
            
            submitted = st.form_submit_button("🚀 执行", type="primary")
            
            if submitted:
                with st.spinner("🧠 处理中..."):
                    params = {"action": selected_action}
                    if selected_action == "add_knowledge":
                        params["content"] = content
                        params["entity_type"] = entity_type
                    elif selected_action == "search_knowledge":
                        params["query"] = query
                        if entity_type_filter:
                            params["entity_type"] = entity_type_filter
                    elif selected_action == "query_graph":
                        if query:
                            params["query"] = query
                        if entity_id:
                            params["entity_id"] = entity_id
                    elif selected_action == "discover_relations":
                        params["entity_id"] = entity_id
                    elif selected_action == "list_entities":
                        if entity_type_filter:
                            params["entity_type"] = entity_type_filter
                    elif selected_action == "export_graph":
                        params["format"] = export_format
                    
                    result = brain.subagents.invoke("cognee", params)
                    
                    brain.audit.log(AuditEvent.DATA_WRITE if selected_action == "add_knowledge" else AuditEvent.DATA_READ,
                                   details={"action": selected_action, "query": query if "query" in params else ""})
                    
                    st.session_state.cognee_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "action": selected_action,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 操作完成！")
                        
                        result_data = result.get("result", {})
                        
                        if selected_action == "add_knowledge":
                            st.markdown(f"**实体ID**: {result_data.get('entity_id')}")
                            st.markdown(f"**提取的关联实体**: {result_data.get('extracted_entities', 0)} 个")
                            st.info(result_data.get("message", ""))
                        
                        elif selected_action == "search_knowledge":
                            if result_data.get("results"):
                                st.subheader("🔍 搜索结果")
                                st.write(f"找到 {result_data.get('count', 0)} 条匹配结果")
                                for res in result_data["results"]:
                                    with st.expander(f"📄 {res.get('type_name', '')}: {res.get('content', '')[:60]}..."):
                                        st.markdown(res.get("content", ""))
                                        st.caption(f"ID: {res.get('id')} | 标签: {res.get('tags', [])}")
                        
                        elif selected_action == "query_graph":
                            if result_data.get("entities"):
                                st.subheader("📊 实体")
                                for entity in result_data["entities"]:
                                    st.markdown(f"- **{entity.get('type_name', '')}**: {entity.get('content', '')[:80]}...")
                            if result_data.get("relations"):
                                st.subheader("🔗 关系")
                                for rel in result_data["relations"]:
                                    source_name = result_data.get("entities", [])[0].get("content", "") if result_data.get("entities") else ""
                                    st.markdown(f"- {rel.get('type_name', '')}: {rel.get('source')} → {rel.get('target')}")
                        
                        elif selected_action == "discover_relations":
                            if result_data.get("relations"):
                                st.subheader("🔗 发现的关系")
                                for rel in result_data["relations"]:
                                    st.markdown(f"- {rel.get('type_name', '')} (置信度: {rel.get('confidence', 0)})")
                        
                        elif selected_action == "list_entities":
                            if result_data.get("entities"):
                                st.subheader("📋 知识实体")
                                for entity in result_data["entities"]:
                                    st.markdown(f"- **{entity.get('id')}** [{entity.get('type_name', '')}]: {entity.get('content', '')[:100]}...")
                        
                        elif selected_action == "export_graph":
                            if result_data.get("graph"):
                                st.subheader("📤 图谱数据")
                                st.json(result_data["graph"])
                                st.write(f"节点数: {result_data.get('node_count')}, 边数: {result_data.get('edge_count')}")
                        
                        elif selected_action == "get_stats":
                            st.subheader("📈 统计信息")
                            col_s1, col_s2 = st.columns(2)
                            with col_s1:
                                st.metric("实体总数", result_data.get("entity_count", 0))
                            with col_s2:
                                st.metric("关系总数", result_data.get("relation_count", 0))
                            if result_data.get("types"):
                                st.write("实体类型分布:")
                                for type_name, count in result_data["types"].items():
                                    st.markdown(f"- {type_name}: {count}")
                    else:
                        st.error(f"❌ 操作失败: {result.get('error')}")
    
    if st.session_state.cognee_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.cognee_results[:3]:
            with st.expander(f"⏰ {entry['timestamp']} - {actions[entry['action']]['name']}"):
                st.json(entry["result"])
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 🗂️ **知识图谱**: 构建语义关系图
    - 🧠 **长期记忆**: 持久化存储知识
    - 🔗 **关系发现**: 自动发现实体间关系
    - 📝 **智能摘要**: 生成知识摘要
    """)


# ---- Herdr Page ----
elif page == "👥 Agent管理":
    st.title("👥 Herdr 多Agent终端管理")
    st.caption("同时运行并管理多个AI编码Agent")
    
    if "herdr_agents" not in st.session_state:
        st.session_state.herdr_agents = {}
    if "herdr_tasks" not in st.session_state:
        st.session_state.herdr_tasks = []
    
    agent_roles = {
        "code_engineer": {"name": "代码工程师", "emoji": "💻", "desc": "负责代码编写和开发"},
        "code_reviewer": {"name": "代码审查员", "emoji": "🔍", "desc": "负责代码审查和质量检查"},
        "test_engineer": {"name": "测试工程师", "emoji": "🧪", "desc": "负责测试用例编写和测试"},
        "architect": {"name": "架构师", "emoji": "🏗️", "desc": "负责系统架构设计"},
        "devops": {"name": "DevOps工程师", "emoji": "☁️", "desc": "负责部署和运维"},
        "data_scientist": {"name": "数据科学家", "emoji": "📊", "desc": "负责数据分析和建模"},
        "product_manager": {"name": "产品经理", "emoji": "📋", "desc": "负责产品规划和需求分析"},
        "designer": {"name": "设计师", "emoji": "🎨", "desc": "负责UI/UX设计"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🤖 Agent列表")
        list_result = brain.subagents.invoke("herdr", {"action": "list_agents"})
        agents = {}
        if list_result.get("success"):
            agents = list_result.get("result", {}).get("agents", {})
        
        if agents:
            for agent_id, agent_info in agents.items():
                status_icon = "🟢" if agent_info["status"] == "running" else "🔴" if agent_info["status"] == "stopped" else "🟡"
                with st.expander(f"{status_icon} {agent_info.get('name', agent_id)}"):
                    st.write(f"角色: {agent_info.get('role', '')}")
                    st.write(f"状态: {agent_info.get('status', '')}")
                    st.write(f"创建时间: {agent_info.get('created_at', '')}")
                    if st.button(f"停止 Agent", key=f"stop_{agent_id}"):
                        brain.subagents.invoke("herdr", {"action": "stop_agent", "agent_id": agent_id})
                        st.rerun()
                    if st.button(f"查看日志", key=f"logs_{agent_id}"):
                        log_result = brain.subagents.invoke("herdr", {"action": "get_agent_logs", "agent_id": agent_id})
                        if log_result.get("success"):
                            logs = log_result.get("result", {}).get("logs", [])
                            for log in logs:
                                st.write(log)
                        else:
                            st.error(f"获取日志失败: {log_result.get('error')}")
        else:
            st.info("暂无运行中的Agent")
    
    with col2:
        with st.form("herdr_form"):
            selected_role = st.selectbox(
                "选择Agent角色",
                list(agent_roles.keys()),
                format_func=lambda x: f"{agent_roles[x]['emoji']} {agent_roles[x]['name']}"
            )
            
            agent_name = st.text_input("Agent名称", f"{agent_roles[selected_role]['name']}")
            
            task = st.text_area(
                "任务描述",
                "创建一个Python函数，计算斐波那契数列",
                height=80
            )
            
            col1_btn, col2_btn = st.columns(2)
            with col1_btn:
                max_workers = st.slider("并行Agent数", 1, 5, 1)
            with col2_btn:
                priority = st.selectbox("优先级", ["low", "normal", "high", "urgent"])
            
            submitted = st.form_submit_button("🚀 启动Agent", type="primary")
            
            if submitted:
                with st.spinner("🤖 启动Agent..."):
                    agent_ids = []
                    for i in range(max_workers):
                        create_result = brain.subagents.invoke("herdr", {
                            "action": "create_agent",
                            "name": f"{agent_name} #{i+1}",
                            "role": selected_role,
                        })
                        if create_result.get("success"):
                            agent_ids.append(create_result.get("result", {}).get("agent_id"))
                    
                    if agent_ids:
                        brain.audit.log(AuditEvent.SUBAGENT_INVOKE,
                                       details={"agents": agent_ids, "role": selected_role})
                        
                        results = []
                        for agent_id in agent_ids:
                            result = brain.subagents.invoke("herdr", {
                                "action": "assign_task",
                                "agent_id": agent_id,
                                "task": task,
                                "priority": priority,
                            })
                            results.append(result)
                        
                        st.session_state.herdr_tasks.insert(0, {
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "agent_role": selected_role,
                            "task": task[:50],
                            "results": results,
                        })
                        
                        success_count = sum(1 for r in results if r.get("success"))
                        st.success(f"✅ {success_count}/{len(results)} 个Agent执行完成！")
                        
                        for i, result in enumerate(results):
                            if result.get("success"):
                                result_data = result.get("result", {})
                                st.subheader(f"🤖 Agent {agent_ids[i]} 执行结果")
                                st.markdown(f"**任务ID**: {result_data.get('task_id')}")
                                st.markdown(f"**状态**: {result_data.get('status')}")
                                
                                if result_data.get("output"):
                                    st.subheader("📝 输出")
                                    st.code(result_data["output"], language="python")
                            else:
                                st.error(f"❌ Agent {agent_ids[i]} 执行失败: {result.get('error')}")
                    else:
                        st.error("❌ 创建Agent失败")
    
    stats_result = brain.subagents.invoke("herdr", {"action": "get_stats"})
    if stats_result.get("success"):
        stats_data = stats_result.get("result", {})
        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.metric("总Agent数", stats_data.get("total_agents", 0))
        with col_s2:
            st.metric("运行中", stats_data.get("running_agents", 0))
        with col_s3:
            st.metric("任务数", stats_data.get("tasks", 0))
    
    if st.session_state.herdr_tasks:
        st.divider()
        st.subheader("📜 任务历史")
        for entry in st.session_state.herdr_tasks[:3]:
            with st.expander(f"⏰ {entry['timestamp']}"):
                st.caption(f"Agent角色: {agent_roles[entry['agent_role']]['name']}")
                st.json(entry["results"])
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 👥 **多Agent管理**: 同时运行多个Agent
    - 📊 **实时监控**: 监控Agent状态
    - 🎯 **任务分配**: 智能分配任务
    - 🔄 **并行执行**: 多Agent并行处理
    - 📝 **日志查看**: 获取Agent运行日志
    - 📈 **统计信息**: 系统状态统计
    """)


# ---- Design.md Page ----
elif page == "🎨 设计规范":
    st.title("🎨 Design.md UI设计规范知识库")
    st.caption("让AI生成符合设计规范的前端代码 — 移动端/桌面端/深色模式")
    
    if "designmd_results" not in st.session_state:
        st.session_state.designmd_results = []
    
    spec_templates = {
        "mobile": {"name": "移动端设计规范", "emoji": "📱", "desc": "手机端UI设计规范"},
        "desktop": {"name": "桌面端设计规范", "emoji": "🖥️", "desc": "桌面端UI设计规范"},
        "dark": {"name": "深色模式", "emoji": "🌙", "desc": "深色主题设计规范"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📐 设计规范")
        for spec_key, spec_info in spec_templates.items():
            with st.expander(f"{spec_info['emoji']} {spec_info['name']}"):
                st.write(spec_info['desc'])
                get_result = brain.subagents.invoke("design_md", {"action": "get_spec", "spec_name": spec_key})
                if get_result.get("success"):
                    spec_data = get_result.get("result", {})
                    if spec_data.get("colors"):
                        st.write("**颜色**:")
                        for color_name, color_value in spec_data["colors"].items():
                            st.markdown(f"- {color_name}: {color_value}")
    
    with col2:
        with st.form("designmd_form"):
            selected_spec = st.selectbox(
                "选择设计规范",
                list(spec_templates.keys()),
                format_func=lambda x: f"{spec_templates[x]['emoji']} {spec_templates[x]['name']}"
            )
            
            action_options = ["查看规范", "生成主题", "导出规范", "验证设计", "列出组件"]
            action = st.selectbox("操作", action_options)
            
            params = {"action": "get_spec" if action == "查看规范" else action}
            params["spec_name"] = selected_spec
            
            if action == "生成主题":
                primary_color = st.color_picker("主色调", "#6366f1")
                accent_color = st.color_picker("强调色", "#8b5cf6")
                params["primary_color"] = primary_color
                params["accent_color"] = accent_color
            
            elif action == "导出规范":
                export_format = st.selectbox("导出格式", ["json", "css", "tailwind"])
                params["format"] = export_format
            
            elif action == "验证设计":
                design_json = st.text_area("设计数据(JSON)", '{"colors": {"primary": "#6366f1"}}', height=80)
                import json
                try:
                    params["design_data"] = json.loads(design_json)
                except Exception:
                    st.error("无效的JSON格式")
                    st.stop()
            
            submitted = st.form_submit_button("🚀 执行", type="primary")
            
            if submitted:
                with st.spinner("🎨 处理中..."):
                    result = brain.subagents.invoke("design_md", params)
                    
                    brain.audit.log(AuditEvent.DATA_READ,
                                   details={"action": action, "spec": selected_spec})
                    
                    st.session_state.designmd_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "spec": selected_spec,
                        "action": action,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 操作完成！")
                        
                        result_data = result.get("result", {})
                        
                        if action == "查看规范":
                            st.subheader("📐 设计规范详情")
                            if result_data.get("colors"):
                                st.write("**颜色**:")
                                for color_name, color_value in result_data["colors"].items():
                                    st.markdown(f"- {color_name}: {color_value}")
                            if result_data.get("typography"):
                                st.write("**排版**:")
                                for style_name, style_data in result_data["typography"].items():
                                    st.markdown(f"- {style_name}: {style_data}")
                            if result_data.get("spacing"):
                                st.write("**间距**:")
                                for spacing_name, spacing_value in result_data["spacing"].items():
                                    st.markdown(f"- {spacing_name}: {spacing_value}px")
                        
                        elif action == "生成主题":
                            st.subheader("🎨 生成的主题")
                            st.json(result_data)
                        
                        elif action == "导出规范":
                            st.subheader("📥 导出内容")
                            content = result_data.get("content", "")
                            format_type = result_data.get("format", "")
                            st.code(content, language=format_type)
                            
                            col1_cpy, col2_dl = st.columns(2)
                            with col1_cpy:
                                if st.button("📋 复制"):
                                    st.copy_to_clipboard(content)
                                    st.success("已复制")
                            with col2_dl:
                                st.download_button(
                                    "📥 下载",
                                    data=content.encode('utf-8'),
                                    file_name=f"design_spec.{format_type}",
                                    mime=f"text/{format_type}",
                                )
                        
                        elif action == "验证设计":
                            st.subheader("✅ 验证结果")
                            st.markdown(f"**有效**: {'✅' if result_data.get('valid') else '❌'}")
                            if result_data.get("errors"):
                                st.write("**错误**:")
                                for error in result_data["errors"]:
                                    st.error(f"- {error}")
                            if result_data.get("warnings"):
                                st.write("**警告**:")
                                for warning in result_data["warnings"]:
                                    st.warning(f"- {warning}")
                        
                        elif action == "列出组件":
                            st.subheader("🧩 组件模式")
                            if result_data.get("components"):
                                for comp_name, comp_data in result_data["components"].items():
                                    st.markdown(f"**{comp_name}**:")
                                    if comp_data.get("variants"):
                                        st.markdown(f"  变体: {', '.join(comp_data['variants'])}")
                                    if comp_data.get("sizes"):
                                        st.markdown(f"  尺寸: {', '.join(comp_data['sizes'])}")
                    else:
                        st.error(f"❌ 操作失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 📐 **设计规范**: 移动端、桌面端、深色模式
    - 🎨 **主题生成**: 自定义颜色主题
    - 📥 **多格式导出**: JSON、CSS、Tailwind
    - ✅ **设计验证**: 验证设计规范
    """)


# ---- No-Mistakes Page ----
elif page == "✅ 代码质检":
    st.title("✅ No-Mistakes AI代码质量把关")
    st.caption("代码推送前自动运行AI验证流程")
    
    if "nomistakes_results" not in st.session_state:
        st.session_state.nomistakes_results = []
    
    check_types = {
        "syntax": {"name": "语法检查", "emoji": "🔍", "desc": "验证代码语法正确性"},
        "security": {"name": "安全检查", "emoji": "🛡️", "desc": "检测常见安全漏洞"},
        "style": {"name": "代码风格", "emoji": "🎨", "desc": "检查代码风格一致性"},
        "complexity": {"name": "复杂度分析", "emoji": "📊", "desc": "分析代码复杂度"},
        "best_practices": {"name": "最佳实践", "emoji": "⭐", "desc": "检查是否遵循语言最佳实践"},
        "all": {"name": "全面检查", "emoji": "✅", "desc": "运行所有检查"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🔧 检查类型")
        for check_key, check_info in check_types.items():
            with st.expander(f"{check_info['emoji']} {check_info['name']}"):
                st.write(check_info['desc'])
    
    with col2:
        with st.form("nomistakes_form"):
            code_input = st.text_area(
                "输入代码",
                "def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)",
                height=150
            )
            
            language = st.selectbox("编程语言", ["python", "javascript", "typescript", "java", "cpp", "go", "rust"])
            
            selected_checks = st.multiselect(
                "选择检查项",
                list(check_types.keys()),
                default=["all"]
            )
            
            submitted = st.form_submit_button("✅ 开始检查", type="primary")
            
            if submitted:
                with st.spinner("🔍 代码检查中..."):
                    effective_checks = selected_checks if "all" not in selected_checks else ["security", "syntax", "style", "complexity", "best_practices"]
                    result = brain.subagents.invoke("no_mistakes", {
                        "action": "validate",
                        "code": code_input,
                        "language": language,
                        "checks": effective_checks,
                    })
                    
                    brain.audit.log(AuditEvent.AGENT_TOOL_CALL,
                                   details={"action": "code_validation", "language": language, "checks": effective_checks})
                    
                    st.session_state.nomistakes_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "language": language,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        result_data = result.get("result", {})
                        
                        score = result_data.get("score", 0)
                        status = result_data.get("status", "unknown")
                        
                        st.subheader(f"📊 检查结果")
                        col1_score, col2_status = st.columns(2)
                        with col1_score:
                            st.metric("代码质量分数", score)
                        with col2_status:
                            status_color = "green" if status == "pass" else "orange" if status == "warning" else "red"
                            st.markdown(f"<span style='color: {status_color}; font-size: 20px;'>**状态**: {status}</span>", unsafe_allow_html=True)
                        
                        if result_data.get("issues"):
                            st.subheader("⚠️ 发现的问题")
                            for issue in result_data["issues"]:
                                severity_color = {"critical": "red", "high": "orange", "medium": "yellow", "low": "blue"}.get(issue.get("severity", "medium"), "gray")
                                st.markdown(f"<span style='color: {severity_color};'>**{issue.get('type', '')}**: {issue.get('message', '')}</span>", unsafe_allow_html=True)
                        
                        if result_data.get("checks_performed"):
                            st.subheader("✅ 执行的检查")
                            for check in result_data["checks_performed"]:
                                st.markdown(f"- {check}")
                        
                        if result_data.get("complexity"):
                            st.subheader("📈 复杂度分析")
                            comp = result_data["complexity"]
                            col_c1, col_c2, col_c3 = st.columns(3)
                            with col_c1:
                                st.metric("代码行数", comp.get("lines_of_code", 0))
                            with col_c2:
                                st.metric("圈复杂度", comp.get("cyclomatic_complexity", 0))
                            with col_c3:
                                st.metric("最大嵌套深度", comp.get("max_nesting_depth", 0))
                    else:
                        st.error(f"❌ 检查失败: {result.get('error')}")
    
    st.divider()
    st.subheader("📁 文件扫描")
    with st.form("nomistakes_file_form"):
        file_path = st.text_input("文件路径", os.path.join(config.BASE_DIR, "src", "core", "brain.py"))
        if st.form_submit_button("📁 扫描文件"):
            with st.spinner("🔍 扫描文件中..."):
                result = brain.subagents.invoke("no_mistakes", {
                    "action": "scan_file",
                    "file_path": file_path,
                })
                
                brain.audit.log(AuditEvent.DATA_READ,
                               details={"action": "file_scan", "path": file_path})
                
                if result.get("success"):
                    result_data = result.get("result", {})
                    st.success(f"✅ 扫描完成！")
                    st.metric("质量分数", result_data.get("score", 0))
                    st.metric("问题数", result_data.get("total_issues", 0))
                    st.json(result_data)
                else:
                    st.error(f"❌ 扫描失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 🔍 **语法检查**: 验证代码语法
    - 🛡️ **安全扫描**: 检测安全漏洞
    - 📊 **复杂度分析**: 评估代码质量
    - 🎨 **风格检查**: 代码风格一致性
    - 📁 **文件扫描**: 扫描整个文件
    """)


# ---- Lingbot-Map Page ----
elif page == "🗺️ 3D重建":
    st.title("🗺️ Lingbot-Map 实时3D重建")
    st.caption("支持机器人、AR/VR场景的点云处理和场景建模")
    
    if "lingbot_results" not in st.session_state:
        st.session_state.lingbot_results = []
    
    pipelines = {
        "rgbd_reconstruction": {"name": "RGB-D重建", "emoji": "📷", "desc": "使用深度摄像头进行3D重建"},
        "sfm_reconstruction": {"name": "运动恢复结构", "emoji": "🏃", "desc": "从多视角图片重建"},
        "lidar_reconstruction": {"name": "LiDAR重建", "emoji": "📡", "desc": "使用激光雷达重建"},
        "neural_reconstruction": {"name": "神经辐射场", "emoji": "🧠", "desc": "NeRF高质量重建"},
    }
    
    scene_types = {
        "indoor": {"name": "室内场景", "emoji": "🏠", "desc": "房间、办公室"},
        "outdoor": {"name": "室外场景", "emoji": "🌳", "desc": "街道、建筑"},
        "object": {"name": "单个物体", "emoji": "🔧", "desc": "小物体精细重建"},
        "mixed": {"name": "混合场景", "emoji": "🔄", "desc": "室内外混合"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🎛️ 重建流水线")
        for pipe_key, pipe_info in pipelines.items():
            with st.expander(f"{pipe_info['emoji']} {pipe_info['name']}"):
                st.write(pipe_info['desc'])
                pipe_detail = brain.subagents.invoke("lingbot_map", {"action": "get_pipeline_info", "pipeline": pipe_key})
                if pipe_detail.get("success"):
                    detail_data = pipe_detail.get("result", {})
                    if detail_data.get("steps"):
                        st.write("**步骤**:")
                        for step in detail_data["steps"]:
                            st.markdown(f"- {step}")
        
        st.subheader("🗺️ 场景类型")
        for scene_key, scene_info in scene_types.items():
            st.markdown(f"{scene_info['emoji']} **{scene_info['name']}**: {scene_info['desc']}")
    
    with col2:
        with st.form("lingbot_form"):
            selected_pipeline = st.selectbox(
                "选择重建流水线",
                list(pipelines.keys()),
                format_func=lambda x: f"{pipelines[x]['emoji']} {pipelines[x]['name']}"
            )
            
            selected_scene = st.selectbox(
                "场景类型",
                list(scene_types.keys()),
                format_func=lambda x: f"{scene_types[x]['emoji']} {scene_types[x]['name']}"
            )
            
            input_data = st.text_input("输入数据路径", os.path.join(OUTPUTS_DIR, "3d", "input"))
            
            col1_opt, col2_opt = st.columns(2)
            with col1_opt:
                resolution = st.slider("分辨率", 1000, 1000000, 100000, step=10000)
            with col2_opt:
                quality = st.selectbox("质量", ["low", "medium", "high"])
            
            submitted = st.form_submit_button("🚀 开始重建", type="primary")
            
            if submitted:
                with st.spinner("🗺️ 3D重建中..."):
                    result = brain.subagents.invoke("lingbot_map", {
                        "action": "start_reconstruction",
                        "pipeline": selected_pipeline,
                        "input_path": input_data,
                        "scene_type": selected_scene,
                        "resolution": resolution,
                        "quality": quality,
                    })
                    
                    brain.audit.log(AuditEvent.AGENT_TOOL_CALL,
                                   details={"action": "3d_reconstruction", "pipeline": selected_pipeline, "scene": selected_scene})
                    
                    st.session_state.lingbot_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "pipeline": selected_pipeline,
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 重建完成！")
                        
                        result_data = result.get("result", {})
                        
                        st.subheader("📊 重建信息")
                        col_info1, col_info2 = st.columns(2)
                        with col_info1:
                            st.markdown(f"**项目ID**: {result_data.get('project_id')}")
                            st.markdown(f"**状态**: {result_data.get('status')}")
                        with col_info2:
                            st.markdown(f"**进度**: {result_data.get('progress')}%")
                            st.markdown(f"**点云数量**: {result_data.get('point_count', 0):,}")
                        
                        if result_data.get("steps"):
                            st.subheader("🔄 执行步骤")
                            for step_name, step_status in result_data["steps"].items():
                                status_icon = "✅" if step_status else "❌"
                                st.markdown(f"{status_icon} {step_name}")
                        
                        if result_data.get("outputs"):
                            st.subheader("🎯 输出文件")
                            for output_type, output_url in result_data["outputs"].items():
                                st.markdown(f"- **{output_type}**: {output_url}")
                        
                        if result_data.get("metrics"):
                            st.subheader("📈 性能指标")
                            metrics = result_data["metrics"]
                            col_m1, col_m2, col_m3 = st.columns(3)
                            with col_m1:
                                st.metric("重建时间", f"{metrics.get('reconstruction_time', 0):.2f}s")
                            with col_m2:
                                st.metric("精度", f"{metrics.get('accuracy', 0):.2f}%")
                            with col_m3:
                                st.metric("完整性", f"{metrics.get('completeness', 0):.2f}%")
                    else:
                        st.error(f"❌ 重建失败: {result.get('error')}")
    
    st.divider()
    st.subheader("📦 格式转换")
    with st.form("lingbot_format_form"):
        input_format = st.selectbox("输入格式", ["ply", "pcd", "obj", "stl"])
        output_format = st.selectbox("输出格式", ["ply", "obj", "stl", "glb", "gltf"])
        
        if st.form_submit_button("🔄 转换格式"):
            result = brain.subagents.invoke("lingbot_map", {
                "action": "convert_format",
                "input_format": input_format,
                "output_format": output_format,
            })
            
            brain.audit.log(AuditEvent.DATA_WRITE,
                           details={"action": "format_conversion", "from": input_format, "to": output_format})
            
            if result.get("success"):
                st.success(f"✅ 格式转换完成: {input_format} → {output_format}")
            else:
                st.error(f"❌ 转换失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 📷 **RGB-D重建**: 深度摄像头3D重建
    - 🧠 **NeRF**: 神经辐射场高质量重建
    - 📡 **LiDAR**: 激光雷达高精度重建
    - 🔄 **格式转换**: 支持多种3D格式
    """)


# ---- RuFlo Development Page ----
elif page == "👨‍💻 RuFlo开发":
    st.title("👨‍💻 RuFlo 多智能体开发团队")
    st.caption("Agent = Model + Harness — 赋予 AI 工具、记忆、循环和沙箱")
    
    if "ruflo_results" not in st.session_state:
        st.session_state.ruflo_results = []
    
    agents = {
        "architect": {"name": "架构师", "emoji": "🏗️", "role": "架构设计", "desc": "系统架构设计、技术选型"},
        "developer": {"name": "开发者", "emoji": "👨‍💻", "role": "编码实现", "desc": "核心代码编写和实现"},
        "reviewer": {"name": "代码审查员", "emoji": "🔍", "role": "代码审查", "desc": "代码质量审查和优化"},
        "tester": {"name": "测试工程师", "emoji": "🧪", "role": "测试验证", "desc": "单元测试和集成测试"},
        "security": {"name": "安全专家", "emoji": "🛡️", "role": "安全审计", "desc": "安全漏洞扫描和审计"},
        "devops": {"name": "DevOps工程师", "emoji": "🚀", "role": "部署运维", "desc": "CI/CD和部署配置"},
        "frontend": {"name": "前端工程师", "emoji": "🎨", "role": "前端开发", "desc": "UI/UX开发"},
        "backend": {"name": "后端工程师", "emoji": "⚙️", "role": "后端开发", "desc": "API和数据库设计"},
        "data": {"name": "数据工程师", "emoji": "📊", "role": "数据处理", "desc": "数据管道和分析"},
        "qa": {"name": "QA工程师", "emoji": "✅", "role": "质量保证", "desc": "质量保证和验收测试"},
    }
    
    tasks = {
        "code_gen": {"name": "代码生成", "emoji": "💻", "desc": "根据需求生成代码", "default_agents": ["developer"]},
        "code_review": {"name": "代码审查", "emoji": "🔍", "desc": "审查代码质量", "default_agents": ["reviewer", "security"]},
        "test_gen": {"name": "测试生成", "emoji": "🧪", "desc": "生成测试用例", "default_agents": ["tester", "qa"]},
        "security_audit": {"name": "安全审计", "emoji": "🛡️", "desc": "安全漏洞扫描", "default_agents": ["security"]},
        "architect_design": {"name": "架构设计", "emoji": "🏗️", "desc": "系统架构设计", "default_agents": ["architect", "backend"]},
        "full_stack": {"name": "全栈开发", "emoji": "🌐", "desc": "完整项目开发", "default_agents": ["frontend", "backend", "devops"]},
        "data_pipeline": {"name": "数据管道", "emoji": "📊", "desc": "数据处理管道", "default_agents": ["data", "backend"]},
        "deploy": {"name": "部署上线", "emoji": "🚀", "desc": "CI/CD部署", "default_agents": ["devops"]},
    }
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.subheader("🤖 智能体团队")
        for key, agent in agents.items():
            with st.container():
                st.markdown(f"**{agent['emoji']} {agent['name']}**")
                st.caption(f"角色: {agent['role']}")
                st.markdown(f"{agent['desc']}")
                st.markdown("---")
    
    with col2:
        with st.form("ruflo_form"):
            selected_task = st.selectbox(
                "选择任务类型",
                list(tasks.keys()),
                format_func=lambda x: f"{tasks[x]['emoji']} {tasks[x]['name']} - {tasks[x]['desc']}"
            )
            
            input_content = st.text_area(
                "任务描述",
                "创建一个完整的待办事项应用，包含增删改查功能",
                height=100,
            )
            
            selected_agents = st.multiselect(
                "选择智能体",
                list(agents.keys()),
                default=tasks[selected_task]["default_agents"],
                format_func=lambda x: f"{agents[x]['emoji']} {agents[x]['name']}"
            )
            
            col1, col2 = st.columns(2)
            with col1:
                max_iterations = st.slider("最大迭代次数", 1, 20, 10)
            with col2:
                timeout = st.slider("超时时间(秒)", 30, 600, 300, step=30)
            
            submitted = st.form_submit_button("🚀 开始执行", type="primary")
            
            if submitted:
                with st.spinner("🧠 RuFlo 智能体团队正在执行..."):
                    result = brain.subagents.invoke("ruflo", {
                        "task": selected_task,
                        "input": input_content,
                        "agents": selected_agents,
                        "params": {
                            "max_iterations": max_iterations,
                            "timeout": timeout,
                            "memory_enabled": True,
                        }
                    })
                    
                    st.session_state.ruflo_results.insert(0, {
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "task_type": selected_task,
                        "task_name": tasks[selected_task]["name"],
                        "result": result,
                    })
                    
                    if result.get("success"):
                        st.success(f"✅ 任务完成！任务ID: {result.get('task_id')}")
                        
                        result_data = result.get("result", {})
                        
                        if result_data.get("enhanced_mock"):
                            st.info("🚀 AOS 增强模式：真实执行开发任务")
                            
                            st.subheader("🧠 参与智能体")
                            for agent_info in result_data.get("agents", []):
                                st.markdown(f"- {agent_info.get('emoji', '🤖')} {agent_info.get('name')}: {agent_info.get('role')}")
                            
                            st.subheader("📋 执行步骤")
                            for step in result_data.get("execution_steps", []):
                                status_icon = "✅" if step.get("status") == "completed" else "🔄"
                                step_emoji = step.get("emoji", "")
                                st.markdown(f"{status_icon} {step_emoji} **{step.get('agent')}**: {step.get('action')}")
                            
                            if result_data.get("generated_code"):
                                st.subheader("💻 生成的代码")
                                st.code(result_data["generated_code"], language="python")
                                
                                col1, col2 = st.columns(2)
                                with col1:
                                    if st.button("📋 复制代码"):
                                        st.copy_to_clipboard(result_data["generated_code"])
                                        st.success("已复制")
                                with col2:
                                    code_bytes = result_data["generated_code"].encode('utf-8')
                                    st.download_button(
                                        "📥 下载代码",
                                        data=code_bytes,
                                        file_name=f"ruflo_generated_{task_id}.py",
                                        mime="text/python",
                                    )
                            
                            if result_data.get("code_output"):
                                st.subheader("📝 执行输出")
                                st.code(result_data["code_output"], language="text")
                            
                            if result_data.get("review_results"):
                                st.subheader("🔍 审查结果")
                                for i, review in enumerate(result_data["review_results"], 1):
                                    st.markdown(f"**审查 #{i}:**")
                                    st.markdown(review)
                            
                            st.subheader("✨ RuFlo 核心特性")
                            for feature in result_data.get("features", []):
                                st.markdown(f"- {feature}")
                            
                        elif result_data.get("basic_mock"):
                            st.info("📢 基础模拟模式")
                            
                            st.subheader("🧠 参与智能体")
                            for agent_info in result_data.get("agents", []):
                                st.markdown(f"- {agent_info.get('name')}: {agent_info.get('role')}")
                            
                            st.subheader("📋 执行步骤")
                            for step in result_data.get("execution_steps", []):
                                status_icon = "✅" if step.get("status") == "completed" else "🔄"
                                st.markdown(f"{status_icon} **{step.get('agent')}**: {step.get('action')}")
                            
                            st.subheader("✨ RuFlo 核心特性")
                            for feature in result_data.get("features", []):
                                st.markdown(f"- {feature}")
                        else:
                            st.json(result)
                    else:
                        st.error(f"❌ 执行失败: {result.get('error', '未知错误')}")
    
    if st.session_state.ruflo_results:
        st.divider()
        st.subheader("📜 历史记录")
        
        for entry in st.session_state.ruflo_results[:5]:
            with st.expander(f"⏰ {entry['timestamp']} - {entry['task_name']}"):
                result = entry["result"]
                if result.get("success"):
                    st.success(f"任务ID: {result.get('task_id')}")
                    st.json(result)
                else:
                    st.error(result.get("error"))
    
    st.divider()
    st.subheader("⚙️ 配置")
    
    api_key = st.text_input("RuFlo API Key", type="password",
                           help="可选，用于连接远程 RuFlo 服务")
    if st.button("保存 API Key"):
        os.environ["RUFLO_API_KEY"] = api_key
        st.success("已保存")
    
    st.info("💡 **提示**: 未安装 RuFlo CLI 时将使用模拟模式。实际使用请运行: `npm install -g ruflo`")


# ---- Codebase Memory Page ----
elif page == "🧠 代码库记忆":
    st.title("🧠 Codebase Memory MCP")
    st.caption("代码库知识图谱 — 将AI从'逐行读代码'提升到'理解代码结构'")
    
    tools = {
        "search": {"name": "语义搜索", "emoji": "🔍", "desc": "搜索代码中的符号、函数、类"},
        "architecture": {"name": "架构分析", "emoji": "🏗️", "desc": "分析模块结构和依赖关系"},
        "call_graph": {"name": "调用链追踪", "emoji": "🔗", "desc": "追踪函数调用链"},
        "impact": {"name": "变更影响分析", "emoji": "⚠️", "desc": "评估变更对其他模块的影响"},
        "find_definition": {"name": "查找定义", "emoji": "📍", "desc": "查找符号定义位置"},
        "find_references": {"name": "查找引用", "emoji": "🔗", "desc": "查找符号引用位置"},
        "list_symbols": {"name": "列出符号", "emoji": "📋", "desc": "列出项目中的所有符号"},
        "generate_doc": {"name": "生成文档", "emoji": "📝", "desc": "为代码生成文档"},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🔧 工具列表")
        for tool, info in tools.items():
            st.markdown(f"**{info['emoji']} {info['name']}**")
            st.caption(info['desc'])
            st.markdown("---")
    
    with col2:
        with st.form("codebase_form"):
            project_path = st.text_input("项目路径", value=config.BASE_DIR, help="要分析的代码项目路径")
            
            selected_tool = st.selectbox(
                "选择工具",
                list(tools.keys()),
                format_func=lambda x: f"{tools[x]['emoji']} {tools[x]['name']}"
            )
            
            query = st.text_input("查询内容", placeholder="搜索关键词或函数名", 
                                help="搜索时需要填写")
            
            submitted = st.form_submit_button("🚀 执行分析", type="primary")
            
            if submitted:
                with st.spinner("🧠 分析中..."):
                    action_map = {
                        "search": "search_code",
                        "architecture": "analyze_project",
                        "call_graph": "get_file_context",
                        "impact": "analyze_project",
                        "find_definition": "get_symbol",
                        "find_references": "search_code",
                        "list_symbols": "list_symbols",
                        "generate_doc": "get_file_context",
                    }
                    action = action_map.get(selected_tool, selected_tool)
                    params = {"action": action, "path": project_path}
                    if query:
                        params["query"] = query
                        if selected_tool == "find_definition":
                            params["symbol_name"] = query
                        elif selected_tool == "find_references":
                            params["search_type"] = "symbol"
                    
                    result = brain.subagents.invoke("codebase_memory_mcp", params)
                    
                    if result.get("success"):
                        st.success(f"✅ 分析完成！")
                        
                        result_data = result.get("result", {})
                        
                        if selected_tool == "search":
                            st.subheader("🔍 搜索结果")
                            results = result_data.get("results", [])
                            st.metric("搜索结果数", len(results))
                            for item in results:
                                if item.get("type") == "symbol":
                                    st.markdown(f"**🗂️ {item.get('symbol_type')}**: `{item.get('name')}`")
                                    st.markdown(f"  文件: `{item.get('file')}`")
                                    st.markdown(f"  行号: {item.get('line')}")
                                    if item.get("context"):
                                        st.code(item.get("context"), language="python")
                                elif item.get("type") == "file":
                                    st.markdown(f"**📄 文件**: `{item.get('path')}`")
                                    st.markdown(f"  大小: {item.get('size')} bytes, 行数: {item.get('lines')}")
                        
                        elif selected_tool == "architecture":
                            st.subheader("🏗️ 架构分析")
                            proj_info = result_data.get("project_info", {})
                            st.metric("文件数", proj_info.get("file_count", 0))
                            st.metric("符号数", proj_info.get("symbol_count", 0))
                            st.metric("类数", proj_info.get("class_count", 0))
                            st.metric("函数数", proj_info.get("function_count", 0))
                            
                            st.subheader("📁 目录结构")
                            directories = {}
                            for file_path in result_data.get("files", {}):
                                parts = file_path.replace("\\", "/").split("/")
                                dir_name = "/".join(parts[:-1])
                                directories[dir_name] = directories.get(dir_name, 0) + 1
                            
                            for dir_name, count in sorted(directories.items(), key=lambda x: x[1], reverse=True)[:10]:
                                st.markdown(f"- **{dir_name}**: {count}个文件")
                        
                        elif selected_tool == "call_graph":
                            st.subheader("🔗 文件上下文")
                            file_info = result_data.get("file_info", {})
                            st.markdown(f"**文件**: `{file_info.get('path')}`")
                            st.markdown(f"**大小**: {file_info.get('size')} bytes")
                            st.markdown(f"**行数**: {file_info.get('lines')}")
                            
                            if file_info.get("classes"):
                                st.subheader("📚 类")
                                for cls in file_info["classes"]:
                                    st.markdown(f"- `{cls}`")
                            
                            if file_info.get("functions"):
                                st.subheader("🔧 函数")
                                for func in file_info["functions"]:
                                    st.markdown(f"- `{func}`")
                            
                            if file_info.get("imports"):
                                st.subheader("📥 导入")
                                for imp in file_info["imports"][:10]:
                                    st.markdown(f"- `{imp}`")
                        
                        elif selected_tool == "impact":
                            st.subheader("⚠️ 影响分析")
                            proj_info = result_data.get("project_info", {})
                            st.metric("总文件数", proj_info.get("file_count", 0))
                            st.metric("总符号数", proj_info.get("symbol_count", 0))
                            
                            st.subheader("🔗 核心符号")
                            symbols = result_data.get("symbols", {})
                            for symbol_name, symbol in list(symbols.items())[:10]:
                                st.markdown(f"- **{symbol['type']} `{symbol_name}`**: {symbol['file']}")
                        
                        elif selected_tool == "find_definition":
                            st.subheader("📍 符号定义")
                            symbol = result_data.get("symbol", {})
                            if symbol:
                                st.markdown(f"**符号**: `{symbol.get('name')}`")
                                st.markdown(f"**类型**: {symbol.get('type')}")
                                st.markdown(f"**文件**: `{symbol.get('file')}`")
                                st.markdown(f"**行号**: {symbol.get('line')}")
                                if symbol.get("context"):
                                    st.subheader("上下文")
                                    st.code(symbol.get("context"), language="python")
                            
                            refs = result_data.get("references", [])
                            if refs:
                                st.subheader("🔗 引用位置")
                                for ref in refs[:10]:
                                    st.markdown(f"- `{ref}`")
                        
                        elif selected_tool == "find_references":
                            st.subheader("🔗 引用搜索")
                            results = result_data.get("results", [])
                            st.metric("引用结果数", len(results))
                            for item in results:
                                if item.get("type") == "symbol":
                                    st.markdown(f"**{item.get('symbol_type')}**: `{item.get('name')}`")
                                    st.markdown(f"  文件: `{item.get('file')}`")
                        
                        elif selected_tool == "list_symbols":
                            st.subheader("📋 符号列表")
                            symbols = result_data.get("symbols", {})
                            st.metric("符号总数", len(symbols))
                            
                            classes = [s for s in symbols.values() if s["type"] == "class"]
                            functions = [s for s in symbols.values() if s["type"] == "function"]
                            
                            st.subheader("📚 类")
                            for cls in classes[:15]:
                                st.markdown(f"- `{cls['name']}` (`{cls['file']}`)")
                            
                            st.subheader("🔧 函数")
                            for func in functions[:20]:
                                st.markdown(f"- `{func['name']}` (`{func['file']}`)")
                        
                        elif selected_tool == "generate_doc":
                            st.subheader("📝 文档")
                            file_info = result_data.get("file_info", {})
                            if file_info:
                                st.markdown(f"**文件**: `{file_info.get('path')}`")
                                if file_info.get("docstrings"):
                                    st.subheader("文档字符串")
                                    for doc in file_info["docstrings"]:
                                        st.markdown(f"- {doc}")
                        
                        else:
                            st.json(result_data)
                    else:
                        st.error(f"❌ 分析失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚡ 性能数据")
    st.markdown("""
    - 普通项目：毫秒级索引
    - Linux内核（2800万行）：3分钟
    - Token节省：10倍
    - 工具调用减少：2.1倍
    """)


# ---- Agency Agents Page ----
elif page == "🤝 专家智能体":
    st.title("🤝 Agency Agents 专家智能体工厂")
    st.caption("144+专业AI角色 — 组建虚拟团队解决复杂问题")
    
    if "agency_results" not in st.session_state:
        st.session_state.agency_results = []
    
    categories = {
        "engineering": {"name": "工程技术", "emoji": "🔧", "agents": ["software_architect", "full_stack_developer", "backend_developer", "frontend_developer", "devops_engineer", "data_scientist", "machine_learning_engineer"]},
        "design": {"name": "设计创意", "emoji": "🎨", "agents": ["ui_designer", "ux_researcher", "product_manager", "project_manager"]},
        "business": {"name": "商业管理", "emoji": "💼", "agents": ["entrepreneur", "marketing_manager", "financial_analyst", "investment_advisor"]},
        "research": {"name": "研究分析", "emoji": "🔍", "agents": ["ai_researcher", "research_scientist", "mathematician", "physicist"]},
        "creative": {"name": "创意创作", "emoji": "🎭", "agents": ["content_creator", "copywriter", "technical_writer"]},
        "health": {"name": "健康医疗", "emoji": "🏥", "agents": ["doctor", "nutritionist"]},
        "education": {"name": "教育培训", "emoji": "📚", "agents": ["teacher", "career_advisor"]},
        "legal": {"name": "法律合规", "emoji": "⚖️", "agents": ["lawyer", "compliance_officer"]},
    }
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📚 专家分类")
        for cat_key, cat_info in categories.items():
            with st.expander(f"{cat_info['emoji']} {cat_info['name']}"):
                st.write(f"专家数量: {len(cat_info['agents'])}")
                for agent_name in cat_info['agents']:
                    st.markdown(f"- {agent_name.replace('_', ' ').title()}")
    
    with col2:
        with st.form("agency_form"):
            selected_category = st.selectbox(
                "选择专家分类",
                list(categories.keys()),
                format_func=lambda x: f"{categories[x]['emoji']} {categories[x]['name']}"
            )
            
            agent_options = categories[selected_category]["agents"]
            selected_agents = st.multiselect(
                "选择专家（可多选）",
                agent_options,
                format_func=lambda x: x.replace('_', ' ').title()
            )
            
            task = st.text_area(
                "任务描述",
                "设计一个电商平台的系统架构，包含前端、后端、数据库和安全方案",
                height=120
            )
            
            col1_btn, col2_btn = st.columns(2)
            with col1_btn:
                team_mode = st.checkbox("团队协作模式", value=True)
            with col2_btn:
                max_iterations = st.slider("最大迭代", 1, 10, 3)
            
            submitted = st.form_submit_button("🚀 执行任务", type="primary")
            
            if submitted:
                if not selected_agents:
                    st.error("❌ 请至少选择一位专家")
                elif not task:
                    st.error("❌ 请输入任务描述")
                else:
                    with st.spinner("🧠 专家团队正在执行..."):
                        if team_mode and len(selected_agents) > 1:
                            team_name = f"task_team_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                            create_result = brain.subagents.invoke("agency_agents", {
                                "action": "create_team",
                                "team_name": team_name,
                                "agent_ids": selected_agents,
                                "description": f"团队协作任务: {task[:50]}",
                            })
                            
                            if not create_result.get("success"):
                                st.error(f"❌ 创建团队失败: {create_result.get('error')}")
                            else:
                                st.info(f"✅ 团队 '{team_name}' 创建成功，共 {len(selected_agents)} 位专家")
                                
                                responses = []
                                for agent_id in selected_agents:
                                    st.info(f"🔄 正在咨询专家: {agent_id.replace('_', ' ').title()}")
                                    result = brain.subagents.invoke("agency_agents", {
                                        "action": "invoke_agent",
                                        "agent_id": agent_id,
                                        "task": task,
                                    })
                                    if result.get("success"):
                                        responses.append({
                                            "agent": agent_id,
                                            "response": result.get("result", {}).get("response", ""),
                                        })
                                        brain.audit.log(AuditEvent.SUBAGENT_RESULT, 
                                                       agent_id=agent_id, 
                                                       details={"task": task[:50], "result": "success"})
                                    else:
                                        responses.append({
                                            "agent": agent_id,
                                            "response": f"❌ 调用失败: {result.get('error')}",
                                        })
                                        brain.audit.log(AuditEvent.SUBAGENT_ERROR, 
                                                       agent_id=agent_id, 
                                                       details={"task": task[:50], "error": result.get('error')})
                                
                                st.session_state.agency_results.insert(0, {
                                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                                    "agents": selected_agents,
                                    "task": task[:50],
                                    "result": {"success": True, "responses": responses},
                                })
                                
                                st.success("✅ 所有专家咨询完成！")
                                
                                st.subheader("🎯 专家反馈")
                                for resp in responses:
                                    with st.expander(f"👤 {resp['agent'].replace('_', ' ').title()}"):
                                        st.markdown(resp["response"])
                        else:
                            agent_id = selected_agents[0]
                            result = brain.subagents.invoke("agency_agents", {
                                "action": "invoke_agent",
                                "agent_id": agent_id,
                                "task": task,
                            })
                            
                            brain.audit.log(AuditEvent.SUBAGENT_INVOKE, 
                                           agent_id=agent_id, 
                                           details={"task": task[:50]})
                            
                            st.session_state.agency_results.insert(0, {
                                "timestamp": datetime.now().strftime("%H:%M:%S"),
                                "agents": selected_agents,
                                "task": task[:50],
                                "result": result,
                            })
                            
                            if result.get("success"):
                                st.success(f"✅ {agent_id.replace('_', ' ').title()} 执行完成！")
                                
                                result_data = result.get("result", {})
                                
                                st.subheader("🤝 执行专家")
                                st.markdown(f"- {result_data.get('agent', {}).get('name', '')}")
                                
                                if result_data.get("response"):
                                    st.subheader("🎯 专家建议")
                                    st.markdown(result_data["response"])
                                    
                                    col1_cpy, col2_dl = st.columns(2)
                                    with col1_cpy:
                                        if st.button("📋 复制成果"):
                                            st.copy_to_clipboard(result_data["response"])
                                            st.success("已复制")
                                else:
                                    st.json(result_data)
                            else:
                                st.error(f"❌ 执行失败: {result.get('error')}")
    
    if st.session_state.agency_results:
        st.divider()
        st.subheader("📜 历史记录")
        for entry in st.session_state.agency_results[:3]:
            with st.expander(f"⏰ {entry['timestamp']} - {', '.join(entry['agents'])}"):
                st.caption(f"任务: {entry['task']}")
                st.json(entry["result"])
    
    st.divider()
    st.subheader("⚡ 核心特性")
    st.markdown("""
    - 👥 **266+专家角色**: 覆盖工程、设计、商业、研究等领域
    - 🤝 **团队协作**: 多专家协同解决复杂问题
    - 📋 **任务分配**: 智能分配任务给最合适的专家
    - 🔄 **迭代优化**: 多轮迭代直到满意
    - 🇨🇳 **中国市场适配**: 50个中文专属角色
    """)


# ---- SearXNG Page ----
elif page == "🔍 搜索中心":
    st.title("🔍 SearXNG 元搜索引擎")
    st.caption("聚合70+搜索引擎结果 — 无限制、免费、隐私保护")
    
    search_types = {
        "general": {"name": "通用搜索", "emoji": "🔍"},
        "images": {"name": "图片搜索", "emoji": "🖼️"},
        "news": {"name": "新闻搜索", "emoji": "📰"},
    }
    
    with st.form("search_form"):
        query = st.text_input("搜索关键词", "人工智能最新进展")
        
        col1, col2 = st.columns(2)
        with col1:
            search_type = st.selectbox(
                "搜索类型",
                list(search_types.keys()),
                format_func=lambda x: f"{search_types[x]['emoji']} {search_types[x]['name']}"
            )
        with col2:
            count = st.slider("结果数量", 5, 20, 10)
        
        submitted = st.form_submit_button("🔍 搜索", type="primary")
        
        if submitted:
            with st.spinner("搜索中..."):
                result = brain.subagents.invoke("searxng", {
                    "query": query,
                    "search_type": search_type,
                    "count": count,
                })
                
                if result.get("success"):
                    results = result.get("results", [])
                    st.success(f"✅ 搜索完成！找到 {len(results)} 条结果")
                    
                    if search_type == "images":
                        cols = st.columns(3)
                        for i, item in enumerate(results):
                            with cols[i % 3]:
                                st.image(item.get("url", ""), caption=item.get("title", ""), use_column_width=True)
                    else:
                        for i, item in enumerate(results, 1):
                            st.markdown(f"**{i}. [{item.get('title', '')}]({item.get('url', '')})**")
                            st.markdown(item.get("description", ""))
                            st.markdown(f"来源: {item.get('source', '')}")
                            st.markdown("---")
                else:
                    st.error(f"❌ 搜索失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚙️ 技术特点")
    st.markdown("""
    - 🚀 **聚合70+搜索引擎**: Google、Bing、DuckDuckGo等
    - 🔒 **隐私保护**: 无广告、无追踪
    - 📦 **Docker部署**: `docker run -d -p 8080:8080 searxng/searxng`
    - 💾 **免费额度**: 使用DDGS免费搜索
    """)


# ---- LightRAG Page ----
elif page == "📚 知识库":
    st.title("📚 LightRAG 本地知识图谱")
    st.caption("本地知识库（DKG）核心 — 向量检索 + 知识图谱")
    
    features = {
        "vector_search": {"name": "向量搜索", "emoji": "🔍", "desc": "基于语义的向量检索"},
        "add_document": {"name": "添加文档", "emoji": "📤", "desc": "添加新文档到知识库"},
        "list_documents": {"name": "列出文档", "emoji": "📋", "desc": "列出知识库中的所有文档"},
        "create_collection": {"name": "创建集合", "emoji": "📁", "desc": "创建新的文档集合"},
        "summarization": {"name": "摘要生成", "emoji": "📝", "desc": "为检索结果生成摘要"},
    }
    
    with st.form("rag_form"):
        collection = st.text_input("集合名称", "default")
        
        selected_feature = st.selectbox(
            "选择操作",
            list(features.keys()),
            format_func=lambda x: f"{features[x]['emoji']} {features[x]['name']}"
        )
        
        if selected_feature in ["vector_search", "summarization"]:
            query = st.text_input("查询内容", "人工智能")
        elif selected_feature == "add_document":
            document = st.text_area("文档内容", "人工智能是计算机科学的一个分支...", height=100)
        else:
            pass
        
        submitted = st.form_submit_button("🚀 执行", type="primary")
        
        if submitted:
            with st.spinner("处理中..."):
                params = {"action": selected_feature, "collection": collection}
                if selected_feature in ["vector_search", "summarization"]:
                    params["query"] = query
                elif selected_feature == "add_document":
                    params["document"] = document
                
                result = brain.subagents.invoke("lightrag", params)
                
                if result.get("success"):
                    st.success(f"✅ 操作完成！")
                    
                    result_data = result.get("result", {})
                    
                    if selected_feature == "vector_search":
                        st.subheader("🔍 检索结果")
                        for doc in result_data.get("documents", []):
                            st.markdown(doc)
                            st.markdown("---")
                    
                    elif selected_feature == "add_document":
                        st.info(f"文档ID: {result_data.get('document_id')}")
                    
                    elif selected_feature == "list_documents":
                        st.subheader("📋 文档列表")
                        st.metric("文档总数", result_data.get("count", 0))
                        for doc in result_data.get("documents", []):
                            st.markdown(f"- **ID**: {doc.get('id')}")
                            st.markdown(f"  内容: {doc.get('content', '')[:100]}...")
                    
                    elif selected_feature == "summarization":
                        st.subheader("📝 摘要")
                        st.markdown(result_data.get("summary", ""))
                        st.info(f"来源文档数: {result_data.get('source_count', 0)}")
                    
                    else:
                        st.json(result_data)
                else:
                    st.error(f"❌ 操作失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚙️ 技术特点")
    st.markdown("""
    - 🧠 **知识图谱**: 构建语义关系图
    - 💾 **ChromaDB集成**: 轻量级向量数据库
    - 🚀 **完全本地**: 无需云端API
    - 📦 **pip安装**: `pip install lightrag chromadb`
    """)


# ---- Jina Reader Page ----
elif page == "🌐 网页提取":
    st.title("🌐 Jina Reader 网页正文提取")
    st.caption("将任意URL转换为干净的Markdown — 免费额度充足")
    
    features = {
        "extract": {"name": "正文提取", "emoji": "📄", "desc": "提取网页正文内容"},
        "summary": {"name": "摘要生成", "emoji": "📝", "desc": "生成网页摘要"},
        "validate": {"name": "URL验证", "emoji": "✅", "desc": "验证URL是否可访问"},
    }
    
    with st.form("jina_form"):
        url = st.text_input("目标URL", "https://en.wikipedia.org/wiki/Artificial_intelligence")
        
        selected_feature = st.selectbox(
            "选择操作",
            list(features.keys()),
            format_func=lambda x: f"{features[x]['emoji']} {features[x]['name']}"
        )
        
        submitted = st.form_submit_button("🚀 提取", type="primary")
        
        if submitted:
            with st.spinner("提取中..."):
                result = brain.subagents.invoke("jina_reader", {
                    "action": selected_feature,
                    "url": url,
                })
                
                if result.get("success"):
                    st.success(f"✅ 提取完成！")
                    
                    result_data = result.get("result", {})
                    
                    if selected_feature == "extract":
                        st.subheader("📄 提取内容")
                        st.markdown(result_data if isinstance(result_data, str) else result_data.get("content", ""))
                        
                        if st.button("📋 复制内容"):
                            text = result_data if isinstance(result_data, str) else result_data.get("content", "")
                            st.copy_to_clipboard(text)
                            st.success("已复制")
                    
                    elif selected_feature == "summary":
                        st.subheader("📝 摘要")
                        st.markdown(result_data.get("summary", ""))
                        st.info(f"原文长度: {result_data.get('source_length', 0)} 字符")
                    
                    elif selected_feature == "validate":
                        st.subheader("✅ URL验证")
                        if result_data.get("valid"):
                            st.success(f"URL有效！状态码: {result_data.get('status_code')}")
                            if result_data.get("redirect_url"):
                                st.info(f"重定向到: {result_data.get('redirect_url')}")
                        else:
                            st.error(f"URL无效: {result_data.get('error')}")
                else:
                    st.error(f"❌ 提取失败: {result.get('error')}")
    
    st.divider()
    st.subheader("⚙️ 技术特点")
    st.markdown("""
    - 🧹 **自动清理**: 去除广告和无关内容
    - 📋 **多格式输出**: Markdown、JSON、纯文本
    - 🆓 **免费额度**: 无API Key时20次/分钟，注册后1000万Token
    - 🔗 **使用方式**: `https://r.jina.ai/http://目标网址`
    """)


# ---- Ollama Page ----
elif page == "🤖 本地模型":
    st.title("🤖 Ollama 本地大模型")
    st.caption("全程本地、无Token费用 — 架构中'本地推理大脑'的核心")
    
    ollama_status = "🟢 运行中"
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=3)
        ollama_running = resp.status_code == 200
        if ollama_running:
            local_models = resp.json().get("models", [])
            local_model_names = [m["name"] for m in local_models]
        else:
            local_models = []
            local_model_names = []
    except Exception:
        ollama_running = False
        ollama_status = "🔴 未运行"
        local_models = []
        local_model_names = []
    
    st.info(f"Ollama 服务状态: {ollama_status}")
    
    all_models = {
        "qwen2.5:7b": {"name": "Qwen2.5 7B", "emoji": "🧠", "desc": "阿里通义千问，中文能力强", "size": "约4.5GB"},
        "qwen2.5:3b": {"name": "Qwen2.5 3B", "emoji": "⚡", "desc": "轻量级，8GB内存友好", "size": "约2GB"},
        "qwen2.5:14b": {"name": "Qwen2.5 14B", "emoji": "🚀", "desc": "更高性能，16GB显存推荐", "size": "约8GB"},
        "minicpm-v:latest": {"name": "MiniCPM-V", "emoji": "👁️", "desc": "多模态视觉模型，支持图文理解", "size": "约5.5GB"},
        "deepseek-chat:latest": {"name": "DeepSeek Chat", "emoji": "🔍", "desc": "深度求索，代码能力强", "size": "约7GB"},
        "llama3.3:8b": {"name": "Llama 3.3 8B", "emoji": "🦙", "desc": "Meta轻量级模型", "size": "约4.5GB"},
        "llama3.2:1b": {"name": "Llama 3.2 1B", "emoji": "🐑", "desc": "超轻量级，极速响应", "size": "约1.3GB"},
        "qwen2.5:1.5b": {"name": "Qwen2.5 1.5B", "emoji": "💡", "desc": "超轻量中文模型", "size": "约1GB"},
        "qwen2.5:0.5b": {"name": "Qwen2.5 0.5B", "emoji": "⚡", "desc": "极小模型，CPU可跑", "size": "约400MB"},
        "mistral:latest": {"name": "Mistral", "emoji": "🌫️", "desc": "高效开源模型", "size": "约4GB"},
        "phi3:latest": {"name": "Phi-3", "emoji": "🔷", "desc": "微软轻量级模型", "size": "约2GB"},
    }
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["💬 模型对话", "📦 模型管理", "⚙️ 推理参数", "📊 性能监控", "🔢 嵌入生成"])
    
    with tab1:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("📦 可用模型")
            installed_count = 0
            for model, info in all_models.items():
                installed = model in local_model_names
                if installed:
                    installed_count += 1
                badge = "✅ 已安装" if installed else "⬜ 未安装"
                st.markdown(f"**{info['emoji']} {info['name']}** {badge}")
                st.caption(info['desc'])
                st.caption(f"大小: {info['size']}")
                st.markdown("---")
            st.caption(f"已安装: {installed_count}/{len(all_models)}")
        
        with col2:
            with st.form("ollama_chat_form"):
                available_models = [m for m in all_models.keys() if m in local_model_names]
                if not available_models:
                    available_models = list(all_models.keys())[:2]
                
                selected_model = st.selectbox(
                    "选择模型",
                    available_models,
                    format_func=lambda x: f"{all_models[x]['emoji']} {all_models[x]['name']}"
                )
                
                message = st.text_area("消息内容", "你好，请介绍一下你自己", height=120)
                
                col_params1, col_params2 = st.columns(2)
                with col_params1:
                    use_custom_params = st.checkbox("使用自定义参数", value=False)
                with col_params2:
                    stream_mode = st.checkbox("流式输出", value=False)
                
                custom_params = {}
                if use_custom_params:
                    st.subheader("⚙️ 推理参数")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        custom_params["temperature"] = st.slider("温度 (0-2)", 0.0, 2.0, 0.7, 0.1)
                        custom_params["top_p"] = st.slider("Top P (0-1)", 0.0, 1.0, 0.9, 0.05)
                    with col_p2:
                        custom_params["max_tokens"] = st.slider("最大Token", 64, 2048, 512, 64)
                        custom_params["context_window"] = st.slider("上下文长度", 512, 8192, 2048, 512)
                
                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    submitted = st.form_submit_button("🚀 发送", type="primary")
                
                if submitted:
                    with st.spinner("思考中..."):
                        action = "chat_with_params" if use_custom_params else "chat"
                        action_params = {
                            "action": action,
                            "model": selected_model,
                            "message": message,
                        }
                        if use_custom_params:
                            action_params["params"] = custom_params
                        
                        result = brain.skill_registry.execute("ollama", action_params)
                        
                        if result.get("success"):
                            st.success("✅ 回复完成！")
                            st.subheader("🤖 模型回复")
                            response_text = result.get("result", {}).get("response", "")
                            st.markdown(response_text)
                            
                            time_ms = result.get("result", {}).get("time_ms", 0)
                            if time_ms > 0:
                                st.caption(f"⏱️ 耗时: {time_ms}ms")
                            
                            if result.get("result", {}).get("params"):
                                st.caption(f"📊 参数: T={result['result']['params'].get('temperature', 0.7)}")
                            
                            if result.get("ollama_available"):
                                st.info("✅ 使用本地 Ollama 模型")
                            else:
                                st.info("🔄 使用降级模式（外部LLM）")
                        else:
                            st.error(f"❌ 调用失败: {result.get('error')}")
    
    with tab2:
        st.subheader("📦 模型管理")
        
        col_m1, col_m2 = st.columns([2, 1])
        
        with col_m1:
            st.write("#### 已安装模型")
            if local_models:
                for m in local_models:
                    with st.expander(f"📦 {m['name']}"):
                        st.write(f"**大小**: {round(m['size'] / 1024 / 1024 / 1024, 2)} GB")
                        st.write(f"**修改时间**: {m['modified_at'][:19].replace('T', ' ')}")
                        details = m.get("details", {})
                        st.write(f"**参数量**: {details.get('parameter_size', 'N/A')}")
                        st.write(f"**上下文长度**: {details.get('context_length', 'N/A')}")
                        st.write(f"**能力**: {', '.join(m.get('capabilities', []))}")
            else:
                st.info("暂无已安装模型")
        
        with col_m2:
            st.write("#### 拉取新模型")
            pull_model = st.selectbox(
                "选择模型",
                [m for m in all_models.keys() if m not in local_model_names],
                format_func=lambda x: f"{all_models[x]['emoji']} {all_models[x]['name']}"
            )
            if st.button("⬇️ 拉取模型"):
                with st.spinner("拉取中..."):
                    result = brain.skill_registry.execute("ollama", {
                        "action": "pull_model",
                        "model": pull_model,
                    })
                    if result.get("success"):
                        st.success("✅ 拉取成功！")
                        st.rerun()
                    else:
                        st.error(f"❌ 拉取失败: {result.get('error')}")
    
    with tab3:
        st.subheader("⚙️ 推理参数设置")
        
        st.info("根据任务类型自动调整参数，比 LM Studio 手动调更智能！")
        
        col_p1, col_p2 = st.columns(2)
        
        with col_p1:
            st.subheader("🎯 预设参数方案")
            
            preset_options = {
                "code_generation": {"name": "代码生成", "temp": 0.2, "top_p": 0.9, "context": 4096},
                "creative_writing": {"name": "创意写作", "temp": 0.9, "top_p": 0.95, "context": 2048},
                "data_analysis": {"name": "数据分析", "temp": 0.3, "top_p": 0.8, "context": 4096},
                "conversation": {"name": "日常对话", "temp": 0.7, "top_p": 0.9, "context": 2048},
                "summary": {"name": "文本摘要", "temp": 0.5, "top_p": 0.85, "context": 4096},
            }
            
            selected_preset = st.selectbox("选择预设", list(preset_options.keys()), format_func=lambda x: preset_options[x]["name"])
            
            if selected_preset:
                preset = preset_options[selected_preset]
                st.markdown(f"**温度**: {preset['temp']} (越低越确定性)")
                st.markdown(f"**Top P**: {preset['top_p']} (采样概率)")
                st.markdown(f"**上下文**: {preset['context']} tokens")
        
        with col_p2:
            st.subheader("⚡ 自定义默认参数")
            
            temp = st.slider("温度 (Temperature)", 0.0, 2.0, 0.7, 0.1)
            top_p = st.slider("Top P", 0.0, 1.0, 0.9, 0.05)
            top_k = st.slider("Top K", 1, 100, 40, 5)
            max_tokens = st.slider("最大生成Token", 64, 4096, 512, 64)
            context_window = st.slider("上下文窗口", 512, 8192, 2048, 512)
            repeat_penalty = st.slider("重复惩罚", 0.5, 2.0, 1.1, 0.1)
            
            if st.button("💾 保存默认参数", type="primary"):
                result = brain.skill_registry.execute("ollama", {
                    "action": "set_default_params",
                    "params": {
                        "temperature": temp,
                        "top_p": top_p,
                        "top_k": top_k,
                        "max_tokens": max_tokens,
                        "context_window": context_window,
                        "repeat_penalty": repeat_penalty,
                    },
                })
                if result.get("success"):
                    st.success("✅ 默认参数已更新！")
                else:
                    st.error(f"❌ 更新失败: {result.get('error')}")
        
        st.divider()
        
        st.subheader("📚 参数说明")
        params_info = {
            "temperature": "控制生成的随机性。0=完全确定，2=非常随机",
            "top_p": "核采样，控制候选词的概率范围",
            "top_k": "限制每次只从K个最可能的词中选择",
            "max_tokens": "生成的最大Token数",
            "context_window": "上下文窗口大小",
            "repeat_penalty": "惩罚重复内容",
        }
        
        for param, desc in params_info.items():
            st.markdown(f"**{param}**: {desc}")
    
    with tab4:
        st.subheader("📊 性能监控")
        
        if st.button("🔄 刷新性能数据"):
            result = brain.skill_registry.execute("ollama", {"action": "get_performance"})
            if result.get("success"):
                stats = result.get("result", {})
                
                col_p1, col_p2, col_p3, col_p4 = st.columns(4)
                
                with col_p1:
                    st.metric("📝 总请求数", stats.get("total_requests", 0))
                with col_p2:
                    st.metric("🔤 总Token数", stats.get("total_tokens", 0))
                with col_p3:
                    st.metric("⏱️ 总耗时(ms)", round(stats.get("total_time_ms", 0), 2))
                with col_p4:
                    st.metric("⚡ 平均速度(token/s)", stats.get("avg_tokens_per_second", 0))
                
                st.divider()
                
                model_stats = stats.get("model_stats", {})
                if model_stats:
                    st.subheader("📦 各模型性能")
                    for model, m_stats in model_stats.items():
                        with st.expander(f"📊 {model}"):
                            col_m1, col_m2, col_m3 = st.columns(3)
                            with col_m1:
                                st.metric("请求数", m_stats.get("requests", 0))
                            with col_m2:
                                st.metric("总Token", m_stats.get("tokens", 0))
                            with col_m3:
                                st.metric("速度(token/s)", m_stats.get("avg_tokens_per_second", 0))
                else:
                    st.info("暂无性能数据，请先进行对话")
            else:
                st.error(f"❌ 获取失败: {result.get('error')}")
        
        st.divider()
        
        st.subheader("📈 Llama.cpp 服务器状态")
        try:
            resp = requests.get("http://localhost:8080/health", timeout=3)
            if resp.status_code == 200:
                st.success("✅ Llama.cpp 服务器运行中")
                st.info("地址: http://localhost:8080")
            else:
                st.warning("⚠️ Llama.cpp 服务器状态异常")
        except Exception:
            st.info("🔄 Llama.cpp 服务器未运行")
    
    with tab5:
        st.subheader("🔢 文本嵌入生成")
        with st.form("ollama_embed_form"):
            embed_model = st.selectbox(
                "选择嵌入模型",
                [m for m in all_models.keys() if m in local_model_names] or ["qwen2.5:7b"],
                format_func=lambda x: f"{all_models.get(x, {}).get('name', x)}"
            )
            embed_text = st.text_area("输入文本", "你好世界", height=80)
            if st.form_submit_button("🔢 生成嵌入"):
                with st.spinner("生成中..."):
                    result = brain.skill_registry.execute("ollama", {
                        "action": "embeddings",
                        "model": embed_model,
                        "prompt": embed_text,
                    })
                    if result.get("success"):
                        emb = result.get("result", {}).get("embedding", [])
                        dims = result.get("result", {}).get("dimensions", 0)
                        st.success(f"✅ 生成成功！维度: {dims}")
                        st.write(f"前10个值: {emb[:10]}")
                    else:
                        st.error(f"❌ 生成失败: {result.get('error')}")


# ---- UI-TARS Page ----
elif page == "🖱️ UI-TARS自动化":
    st.title("🖱️ UI-TARS 桌面自动化")
    st.caption("字节跳动开源 GUI Agent — 给AI装上眼睛和手，看懂屏幕、操控鼠标键盘")
    
    uitars_available = False
    try:
        from deerflow.path_detect import detect_uitars_path
        uitars_available = detect_uitars_path() is not None
    except Exception:
        pass
    
    status = "🟢 源码可用" if uitars_available else "🔴 未安装"
    st.info(f"UI-TARS 状态: {status}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["🎯 任务执行", "📋 预设任务", "⚙️ 配置", "📖 文档"])
    
    with tab1:
        st.subheader("🎯 自动化任务执行")
        
        col_a, col_b = st.columns([2, 1])
        
        with col_a:
            action_options = {
                "desktop_automation": "🖥️ 桌面自动化",
                "browser_automation": "🌐 浏览器自动化",
                "screen_capture": "📸 截屏识别",
                "visual_qa": "👁️ 视觉问答",
                "task_execution": "🤖 通用任务执行",
            }
            
            selected_action = st.selectbox(
                "选择操作类型",
                list(action_options.keys()),
                format_func=lambda x: action_options[x]
            )
            
            task_desc = st.text_area(
                "任务描述",
                "打开浏览器搜索 AI Agent 最新动态",
                height=100,
                placeholder="用自然语言描述你想让AI做什么..."
            )
            
            col_p1, col_p2, col_p3 = st.columns(3)
            with col_p1:
                max_steps = st.number_input("最大步骤数", min_value=1, max_value=100, value=20)
            with col_p2:
                timeout = st.number_input("超时时间(秒)", min_value=10, max_value=3600, value=300)
            with col_p3:
                use_sim = st.checkbox("模拟模式", value=True)
            
            if st.button("🚀 执行任务", type="primary"):
                if not task_desc:
                    st.error("❌ 请输入任务描述")
                else:
                    with st.spinner("执行中..."):
                        result = brain.skill_registry.execute("uitars", {
                            "action": selected_action,
                            "task": task_desc,
                            "max_steps": max_steps,
                            "timeout": timeout,
                        })
                        
                        if result.get("success"):
                            st.success("✅ 任务执行完成！")
                            res_data = result.get("result", {})
                            
                            if res_data.get("mode") == "simulation":
                                st.info("📋 模拟模式 - 以下是执行计划")
                                
                                steps = res_data.get("steps", [])
                                st.write(f"**总步骤数**: {res_data.get('step_count', 0)}")
                                st.write(f"**预计时间**: {res_data.get('estimated_time', 'N/A')}")
                                
                                st.divider()
                                st.write("#### 📝 执行步骤")
                                for step in steps:
                                    step_icon = "⏳" if step["status"] == "pending" else "✅"
                                    st.markdown(f"{step_icon} **步骤 {step['step']}**: {step['action']}")
                                    st.caption(step["description"])
                                
                                st.divider()
                                st.info(res_data.get("note", ""))
                                
                                with st.expander("📖 启动 UI-TARS 说明"):
                                    for instr in res_data.get("instructions", []):
                                        st.write(instr)
                            else:
                                st.json(res_data)
                        else:
                            st.error(f"❌ 执行失败: {result.get('error')}")
        
        with col_b:
            st.subheader("💡 使用提示")
            st.info("""
            **桌面自动化**
            - 打开应用程序
            - 文件操作管理
            - 表单填写提交
            
            **浏览器自动化**
            - 网页搜索
            - 数据抓取
            - 在线操作
            
            **视觉能力**
            - 屏幕内容识别
            - 图像理解问答
            - 元素定位点击
            """)
            
            st.divider()
            st.subheader("⚡ 快速示例")
            examples = [
                "打开计算器计算 123 * 456",
                "打开浏览器搜索今天天气",
                "截图并告诉我屏幕上有什么",
                "打开记事本写一段Python代码",
            ]
            for ex in examples:
                if st.button(f"📌 {ex}", key=f"ex_{ex[:20]}"):
                    st.session_state['uitars_task'] = ex
                    st.rerun()
    
    with tab2:
        st.subheader("📋 预设任务模板")
        
        presets = {
            "search_web": {
                "name": "🌐 网页搜索",
                "desc": "打开浏览器搜索指定内容",
                "example": "搜索 AI Agent 最新动态",
                "action": "browser_automation",
            },
            "fill_form": {
                "name": "📝 填写表单",
                "desc": "自动填写网页或应用表单",
                "example": "在注册页面填写用户名密码",
                "action": "browser_automation",
            },
            "open_app": {
                "name": "📱 打开应用",
                "desc": "启动指定桌面应用程序",
                "example": "打开计算器应用",
                "action": "desktop_automation",
            },
            "data_extract": {
                "name": "📊 数据提取",
                "desc": "从网页或应用中提取数据",
                "example": "提取商品价格信息到表格",
                "action": "browser_automation",
            },
            "file_operation": {
                "name": "📁 文件操作",
                "desc": "自动化文件管理操作",
                "example": "整理下载文件夹，按类型分类",
                "action": "desktop_automation",
            },
            "screen_analyze": {
                "name": "🔍 屏幕分析",
                "desc": "截取屏幕并分析内容",
                "example": "当前屏幕上显示了什么应用？",
                "action": "visual_qa",
            },
        }
        
        for preset_id, preset in presets.items():
            with st.expander(f"{preset['name']} — {preset['desc']}"):
                st.write(f"**示例**: {preset['example']}")
                st.write(f"**操作类型**: {preset['action']}")
                if st.button(f"🚀 使用此模板", key=f"preset_{preset_id}"):
                    st.success(f"已选择: {preset['name']}")
                    st.info(f"示例任务: {preset['example']}")
    
    with tab3:
        st.subheader("⚙️ UI-TARS 配置")
        
        st.write("#### 📍 路径配置")
        uitars_path_display = detect_uitars_path() or "external/UI-TARS-desktop (需配置)"
        st.code(f"UI-TARS 源码路径: {uitars_path_display}")
        st.code(r"CLI 命令: npx @agent-tars/cli@latest")
        
        st.divider()
        st.write("#### 🔧 系统要求")
        st.markdown("""
        - **Node.js**: >= 18.x
        - **操作系统**: Windows / macOS / Linux
        - **内存**: 建议 8GB+
        - **GPU**: 可选，加速视觉模型
        """)
        
        st.divider()
        st.write("#### 🚀 启动方式")
        st.markdown("""
        **方式一: CLI 模式**
        ```bash
        npx @agent-tars/cli@latest
        ```
        
        **方式二: Desktop 应用**
        ```bash
        cd external/UI-TARS-desktop/apps/ui-tars
        npm install
        npm run dev
        ```
        
        **方式三: Server 模式**
        ```bash
        npx @agent-tars/cli@latest server
        ```
        """)
    
    with tab4:
        st.subheader("📖 UI-TARS 文档")
        
        st.write("#### 🎯 什么是 UI-TARS?")
        st.markdown("""
        UI-TARS (Agent TARS) 是字节跳动开源的多模态 AI Agent Stack，包含：
        
        - **Agent TARS**: 通用多模态 AI Agent，CLI + Web UI
        - **UI-TARS Desktop**: 桌面应用，提供原生 GUI Agent
        
        核心能力：
        - 🖱️ 桌面自动化 - 操控鼠标键盘
        - 🌐 浏览器自动化 - GUI + DOM 混合策略
        - 👁️ 视觉理解 - 截屏识别、视觉问答
        - 🔌 MCP 协议 - 原生支持 MCP 工具集成
        """)
        
        st.divider()
        st.write("#### 🔗 相关链接")
        st.markdown("""
        - **GitHub**: https://github.com/bytedance/UI-TARS-desktop
        - **官方文档**: https://agent-tars.com
        - **NPM 包**: @agent-tars/cli
        """)
        
        st.divider()
        st.write("#### 💡 与 AOS 集成")
        st.markdown("""
        UI-TARS 作为 AOS 的 **执行层** 组件：
        
        | 层级 | 组件 | 职责 |
        |------|------|------|
        | 决策层 | Hermes / OpenClaw | 理解需求、生成计划 |
        | 调度层 | DeerFlow | 任务编排、多 Agent 协作 |
        | 执行层 | UI-TARS | 桌面/浏览器实际操作 |
        """)


# ---- ViiTorVoice Page ----
elif page == "🎤 语音编辑":
    st.title("🎤 ViiTorVoice 中文语音编辑")
    st.caption("片段级局部编辑 — 像改Word一样修语音")
    
    styles = {
        "default": {"name": "默认", "emoji": "🎙️"},
        "female": {"name": "女声", "emoji": "👩"},
        "male": {"name": "男声", "emoji": "👨"},
        "child": {"name": "童声", "emoji": "👧"},
        "robot": {"name": "机器人", "emoji": "🤖"},
    }
    
    emotions = {
        "neutral": {"name": "中性", "emoji": "😐"},
        "happy": {"name": "开心", "emoji": "😊"},
        "sad": {"name": "悲伤", "emoji": "😢"},
        "excited": {"name": "兴奋", "emoji": "🎉"},
    }
    
    with st.form("voice_form"):
        text = st.text_area("输入文本", "你好，这是一段测试语音", height=50)
        
        col1, col2 = st.columns(2)
        with col1:
            selected_style = st.selectbox(
                "语音风格",
                list(styles.keys()),
                format_func=lambda x: f"{styles[x]['emoji']} {styles[x]['name']}"
            )
        with col2:
            selected_emotion = st.selectbox(
                "情绪",
                list(emotions.keys()),
                format_func=lambda x: f"{emotions[x]['emoji']} {emotions[x]['name']}"
            )
        
        submitted = st.form_submit_button("🎤 生成语音", type="primary")
        
        if submitted:
            with st.spinner("生成中..."):
                result = brain.subagents.invoke("viitor_voice", {
                    "action": "tts",
                    "text": text,
                    "style": selected_style,
                    "emotion": selected_emotion,
                })
                
                if result.get("success"):
                    st.success(f"✅ 语音生成完成！")
                    
                    result_data = result.get("result", {})
                    st.info(f"风格: {styles[selected_style]['name']} | 情绪: {emotions[selected_emotion]['name']}")
                    st.info(f"预计时长: {result_data.get('duration', 0):.1f} 秒")
                    
                    if result_data.get("audio_url"):
                        st.audio(result_data["audio_url"])
                else:
                    st.error(f"❌ 生成失败: {result.get('error')}")
    
    st.divider()
    st.subheader("🏆 技术亮点")
    st.markdown("""
    - 🎯 **中文词错率0.99**: 全球首个突破1.0的模型
    - 📝 **片段级编辑**: 像改Word一样修语音
    - 🌍 **Zero-Shot跨语种克隆**: 无需训练数据
    - 🎭 **词级情绪控制**: 精确控制情感表达
    - ⚡ **首帧延迟<60ms**: 极速响应
    """)


# ---- Multimodal Page ----
elif page == "🖼️ 多模态":
    st.title("🖼️ 多模态交互")
    st.caption("图片 + 音频 + 视频 + 文本对话 + AI 分析")
    
    if "multimodal_messages" not in st.session_state:
        st.session_state.multimodal_messages = []
    if "multimodal_session_id" not in st.session_state:
        st.session_state.multimodal_session_id = None
    if "uploaded_image" not in st.session_state:
        st.session_state.uploaded_image = None
    if "uploaded_audio" not in st.session_state:
        st.session_state.uploaded_audio = None
    if "uploaded_video" not in st.session_state:
        st.session_state.uploaded_video = None
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.subheader("📤 图片上传")
        uploaded_file = st.file_uploader("选择图片", type=["jpg", "jpeg", "png", "gif"], 
                                        help="支持 JPG, JPEG, PNG, GIF 格式",
                                        key="image_uploader")
        
        if uploaded_file:
            image_bytes = uploaded_file.read()
            st.image(image_bytes, caption=f"{uploaded_file.name} ({len(image_bytes)} bytes)", width=200)
            st.session_state.uploaded_image = image_bytes
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.session_state.multimodal_messages.append({
                "role": "user",
                "content": f"📷 [上传图片: {uploaded_file.name}]",
                "image": image_bytes,
                "timestamp": timestamp
            })
            st.rerun()
        
        st.subheader("🎨 分析模式")
        analysis_mode = st.selectbox("选择模式", ["通用分析", "目标检测", "图像分类", "OCR识别", "风格迁移"])
    
    with col2:
        st.subheader("🎵 音频上传")
        audio_file = st.file_uploader("选择音频", type=["mp3", "wav", "ogg"],
                                      help="支持 MP3, WAV, OGG 格式",
                                      key="audio_uploader")
        
        if audio_file:
            audio_bytes = audio_file.read()
            st.audio(audio_bytes, format=f"audio/{audio_file.name.split('.')[-1]}")
            st.session_state.uploaded_audio = audio_bytes
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.session_state.multimodal_messages.append({
                "role": "user",
                "content": f"🎵 [上传音频: {audio_file.name} ({len(audio_bytes)} bytes)]",
                "audio": audio_bytes,
                "timestamp": timestamp
            })
            st.rerun()
        
        st.subheader("🎙️ 语音操作")
        audio_action = st.selectbox("语音功能", ["语音识别", "语音合成", "语音翻译"])
    
    with col3:
        st.subheader("🎬 视频上传")
        video_file = st.file_uploader("选择视频", type=["mp4", "avi", "mov", "mkv"],
                                      help="支持 MP4, AVI, MOV, MKV 格式",
                                      key="video_uploader")
        
        if video_file:
            video_bytes = video_file.read()
            st.video(video_bytes, format=f"video/{video_file.name.split('.')[-1]}")
            st.session_state.uploaded_video = video_bytes
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            st.session_state.multimodal_messages.append({
                "role": "user",
                "content": f"🎬 [上传视频: {video_file.name} ({len(video_bytes)} bytes)]",
                "video": video_bytes,
                "timestamp": timestamp
            })
            st.rerun()
        
        st.subheader("⚙️ 参数设置")
        confidence = st.slider("置信度阈值", 0.5, 0.95, 0.8, step=0.05)
        max_results = st.slider("最大结果数", 1, 10, 5, step=1)
    
    with col4:
        st.subheader("🖼️ 当前媒体")
        if st.session_state.uploaded_image:
            st.image(st.session_state.uploaded_image, width=150, caption="图片")
        if st.session_state.uploaded_audio:
            st.audio(st.session_state.uploaded_audio, format="audio/mp3")
        if st.session_state.uploaded_video:
            st.video(st.session_state.uploaded_video, format="video/mp4")
        if not st.session_state.uploaded_image and not st.session_state.uploaded_audio and not st.session_state.uploaded_video:
            st.info("请上传图片、音频或视频")
        
        st.subheader("📊 文件信息")
        media_count = sum([1 for m in [st.session_state.uploaded_image, st.session_state.uploaded_audio, st.session_state.uploaded_video] if m])
        st.metric("已上传媒体", media_count)
    
    st.divider()
    
    st.subheader("💬 对话历史")
    for msg in st.session_state.multimodal_messages:
        render_chat_message(msg)
    
    st.divider()
    
    prompt = st.chat_input("描述你想让 AOS 做什么...")
    
    if prompt:
        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.multimodal_messages.append({"role": "user", "content": prompt, "timestamp": timestamp})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
            st.caption(timestamp)
        
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner("处理中..."):
                try:
                    media_info = ""
                    if st.session_state.uploaded_image:
                        media_info += "【已上传图片】"
                    if st.session_state.uploaded_audio:
                        media_info += "【已上传音频】"
                    if st.session_state.uploaded_video:
                        media_info += "【已上传视频】"
                    
                    full_prompt = f"{media_info}【模式: {analysis_mode}】【置信度: {confidence}】【最大结果: {max_results}】\n{prompt}"
                    result = brain.chat(
                        message=full_prompt,
                        session_id=st.session_state.multimodal_session_id,
                    )
                    response = result.get("response", str(result))
                    st.session_state.multimodal_session_id = result.get("session_id")
                    response_timestamp = datetime.now().strftime("%H:%M:%S")
                    st.markdown(response)
                    st.caption(response_timestamp)
                    st.session_state.multimodal_messages.append(
                        {"role": "assistant", "content": response, "timestamp": response_timestamp}
                    )
                except Exception as e:
                    st.error(f"错误: {e}")
    
    if st.button("🧹 清空对话"):
        st.session_state.multimodal_messages = []
        st.session_state.multimodal_session_id = None
        st.session_state.uploaded_image = None
        st.session_state.uploaded_audio = None
        st.session_state.uploaded_video = None
        st.rerun()


# ---- Skills Page ----
elif page == "🛠️ 技能中心":
    st.title("🛠️ 技能中心")
    
    try:
        skills = brain.hermes.list_skills()
        
        col1, col2, col3 = st.columns(3)
        col1.metric("总技能数", skills.get("total", 0))
        col2.metric("分类数", len(skills.get("categories", {})))
        col3.metric("活跃技能", len([s for s in skills.get("skills", []) if s.get("enabled", True)]))
        
        if skills.get("skills"):
            categories = skills.get("categories", {})
            selected_category = st.selectbox("选择分类", ["全部"] + list(categories.keys()))
            
            filtered_skills = skills["skills"]
            if selected_category != "全部":
                filtered_skills = categories.get(selected_category, [])
            
            skill_grid = st.columns(3)
            for idx, skill in enumerate(filtered_skills):
                with skill_grid[idx % 3]:
                    with st.container():
                        st.markdown("---")
                        st.subheader(skill.get("name", "unknown"))
                        st.write(f"{skill.get('description', '')[:100]}...")
                        st.caption(f"分类: {skill.get('category', '')}")
                        if st.button(f"执行", key=f"exec_{skill.get('name')}"):
                            with st.spinner("执行中..."):
                                result = brain.hermes.execute_skill(skill.get('name'), {})
                                st.json(result)
    except Exception as e:
        st.error(f"加载技能失败: {e}")


# ---- SubAgents Page ----
elif page == "🤖 子智能体":
    st.title("🤖 子智能体管理")
    
    tab1, tab2 = st.tabs(["已注册子智能体", "深度子智能体 (DeerFlow)"])
    
    with tab1:
        try:
            agents = brain.subagents.list_agents()
            if agents:
                df = pd.DataFrame(agents)
                st.dataframe(df[["name", "description", "status", "invoke_count"]], use_container_width=True)
                
                selected_agent = st.selectbox("选择子智能体", [a["name"] for a in agents])
                task = st.text_input("执行任务", "你好，做个自我介绍")
                if st.button("执行", key="invoke_subagent"):
                    with st.spinner("执行中..."):
                        result = brain.subagents.invoke(selected_agent, {"message": task})
                        st.json(result)
            else:
                st.info("暂无注册的子智能体")
        except Exception as e:
            st.error(f"加载子智能体失败: {e}")
    
    with tab2:
        try:
            deep_agents = brain.deerflow.list_subagents()
            if deep_agents:
                st.dataframe(pd.DataFrame(deep_agents), use_container_width=True)
            else:
                st.info("暂无深度子智能体，使用 API /api/subagents/deep/register 注册")
            
            st.divider()
            st.subheader("➕ 注册新子智能体")
            with st.form("register_subagent"):
                name = st.text_input("名称", "code-reviewer")
                desc = st.text_input("描述", "代码审查和改进")
                task = st.text_input("测试任务", "审查代码中的问题")
                if st.form_submit_button("注册并测试"):
                    with st.spinner("注册中..."):
                        brain.deerflow.register_subagent(name, desc, max_turns=30)
                        thread_id = f"aos-{name}-{int(time.time())}"
                        result = brain.deerflow.execute_subagent(name, task, thread_id=thread_id)
                        st.json(result)
        except Exception as e:
            st.error(f"深度子智能体操作失败: {e}")


# ---- Sandbox Page ----
elif page == "🗂️ 沙盒终端":
    st.title("🗂️ 沙盒控制台")
    st.caption("DeerFlow 沙盒 — 隔离的代码执行环境")
    
    if "sandbox_output" not in st.session_state:
        st.session_state.sandbox_output = ""
    if "sandbox_history" not in st.session_state:
        st.session_state.sandbox_history = []
    if "sandbox_preview" not in st.session_state:
        st.session_state.sandbox_preview = ""
    if "sandbox_code" not in st.session_state:
        st.session_state.sandbox_code = ""
    
    tab1, tab2 = st.tabs(["🖥️ 命令终端", "💻 代码编辑器"])
    
    with tab1:
        cmd = st.text_area("命令", "echo 'Hello from AOS Sandbox!'", height=68)
        col1, col2, col3 = st.columns([1, 1, 5])
        with col1:
            if st.button("▶️ 执行", use_container_width=True):
                with st.spinner("执行中..."):
                    try:
                        sb = brain.deerflow.create_sandbox()
                        output = sb.execute_command(cmd)
                        st.session_state.sandbox_output = output
                        st.session_state.sandbox_history.append({
                            "command": cmd,
                            "output": output,
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
                        sb.release()
                    except Exception as e:
                        st.session_state.sandbox_output = f"错误: {e}"
                        st.session_state.sandbox_history.append({
                            "command": cmd,
                            "output": f"错误: {e}",
                            "timestamp": datetime.now().strftime("%H:%M:%S")
                        })
        with col2:
            if st.button("📋 复制输出", use_container_width=True):
                if st.session_state.sandbox_output:
                    st.copy_to_clipboard(st.session_state.sandbox_output)
                    st.success("已复制到剪贴板")
        
        if st.session_state.sandbox_output:
            output_bytes = st.session_state.sandbox_output.encode('utf-8')
            st.download_button(
                label="📥 下载输出",
                data=output_bytes,
                file_name=f"sandbox_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        
        st.code(st.session_state.sandbox_output or "// 输出显示在这里", language="bash")
        
        if st.session_state.sandbox_history:
            st.divider()
            st.subheader("📜 执行历史")
            for entry in reversed(st.session_state.sandbox_history[-5:]):
                with st.expander(f"⏰ {entry['timestamp']}"):
                    st.code(entry["command"], language="bash")
                    st.code(entry["output"], language="bash")
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button(f"📋 复制", key=f"copy_{entry['timestamp']}", use_container_width=True):
                            st.copy_to_clipboard(entry["output"])
                            st.success("已复制")
    
    with tab2:
        col1, col2 = st.columns([1, 1])
        with col1:
            language = st.selectbox("语言", ["python", "javascript", "bash"], index=0)
        with col2:
            theme = st.selectbox("主题", ["dark", "light"], index=0)
        
        code = st.text_area(
            "代码",
            st.session_state.sandbox_code or "print('Hello World!')",
            height=200,
        )
        
        col1, col2, col3 = st.columns([1, 1, 5])
        with col1:
            if st.button("▶️ 运行代码", use_container_width=True, type="primary"):
                st.session_state.sandbox_code = code
                with st.spinner("执行中..."):
                    try:
                        from skills.sandbox import get_sandbox
                        sandbox = get_sandbox()
                        result = sandbox.execute_code(code, language=language)
                        
                        st.session_state.sandbox_output = result.output or result.error
                        st.session_state.sandbox_history.append({
                            "command": f"[{language}] {code[:50]}...",
                            "output": result.output or result.error,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                            "language": language,
                        })
                        
                        preview_content = f"<pre style='background: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 4px;'>{result.output or ''}</pre>"
                        if language == "python":
                            if "<html" in (result.output or "").lower() or "</html>" in (result.output or "").lower():
                                preview_content = result.output
                            elif "import matplotlib" in code or "import plotly" in code:
                                preview_content = f"<div style='padding: 20px;'>图表输出需要在支持的环境中查看</div>"
                        
                        st.session_state.sandbox_preview = preview_content
                        
                        sandbox.cleanup()
                    except Exception as e:
                        st.session_state.sandbox_output = f"错误: {e}"
                        st.session_state.sandbox_preview = f"<pre style='background: #2d1f1f; color: #ff6b6b; padding: 10px; border-radius: 4px;'>错误: {e}</pre>"
        
        with col2:
            if st.button("📋 复制代码", use_container_width=True):
                st.copy_to_clipboard(code)
                st.success("已复制到剪贴板")
        
        if code:
            code_bytes = code.encode('utf-8')
            ext = {"python": "py", "javascript": "js", "bash": "sh"}.get(language, "txt")
            st.download_button(
                label="📥 下载代码",
                data=code_bytes,
                file_name=f"code_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}",
                mime=f"text/{language}",
                use_container_width=True,
            )
        
        st.divider()
        
        col1, col2 = st.columns([1, 1])
        
        with col1:
            st.subheader("📝 输出")
            st.code(st.session_state.sandbox_output or "// 输出显示在这里", language=language)
        
        with col2:
            st.subheader("👁️ 预览")
            try:
                if st.session_state.sandbox_preview:
                    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False)
                    temp_file.write(st.session_state.sandbox_preview)
                    temp_file.close()
                    try:
                        st.iframe(f"file:///{temp_file.name.replace(os.sep, '/')}", height=400)
                    finally:
                        os.unlink(temp_file.name)
                else:
                    st.info("执行代码后将在此显示预览")
            except Exception as e:
                st.warning(f"预览加载失败: {e}")
                if st.session_state.sandbox_output:
                    st.code(st.session_state.sandbox_output, language=language)


# ---- Project Import Page ----
elif page == "📁 项目导入":
    st.title("📁 项目导入")
    st.caption("导入其他项目代码，让 AOS 分析和借鉴")
    
    if "project_files" not in st.session_state:
        st.session_state.project_files = {}
    
    tab1, tab2 = st.tabs(["📂 目录扫描", "📤 文件上传"])
    
    with tab1:
        st.subheader("扫描本地项目目录")
        project_path = st.text_input("项目路径", config.BASE_DIR, help="输入你想要分析的项目目录")
        
        if st.button("🔍 扫描目录", type="primary"):
            if os.path.exists(project_path):
                files = []
                for root, dirs, filenames in os.walk(project_path):
                    dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv', 'env']]
                    for f in filenames:
                        if f.endswith(('.py', '.js', '.ts', '.tsx', '.html', '.css', '.md', '.json', '.yaml', '.yml')):
                            full_path = os.path.join(root, f)
                            try:
                                rel_path = os.path.relpath(full_path, project_path)
                                size = os.path.getsize(full_path)
                                files.append({
                                    "path": rel_path,
                                    "full_path": full_path,
                                    "size": size,
                                    "modified": os.path.getmtime(full_path)
                                })
                            except Exception:
                                pass
                
                st.session_state.project_files = {f["full_path"]: f for f in files}
                st.success(f"扫描完成！发现 {len(files)} 个文件")
                
                df = pd.DataFrame(files)
                df['modified'] = pd.to_datetime(df['modified'], unit='s')
                df['size'] = df['size'].apply(lambda x: f"{x/1024:.1f} KB")
                st.dataframe(df[["path", "size", "modified"]], use_container_width=True, height=300)
            else:
                st.error(f"路径不存在: {project_path}")
        
        if st.session_state.project_files:
            st.divider()
            st.subheader("📖 文件内容预览")
            selected_file = st.selectbox("选择文件", 
                                        [f["path"] for f in st.session_state.project_files.values()])
            
            for full_path, info in st.session_state.project_files.items():
                if info["path"] == selected_file:
                    try:
                        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                        
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.code(content, language="python" if full_path.endswith('.py') else 
                                    "javascript" if full_path.endswith(('.js', '.ts', '.tsx')) else
                                    "html" if full_path.endswith('.html') else
                                    "css" if full_path.endswith('.css') else
                                    "markdown" if full_path.endswith('.md') else "text")
                        with col2:
                            st.subheader("💡 分析建议")
                            if st.button("让 AOS 分析", key=f"analyze_{selected_file}"):
                                with st.spinner("分析中..."):
                                    analysis = brain.chat(
                                        message=f"请分析以下代码文件，并提供改进建议：\n\n文件路径: {selected_file}\n\n```\n{content[:2000]}\n```\n\n请从以下方面分析：\n1. 代码结构和架构设计\n2. 潜在的 bug 或问题\n3. 性能优化建议\n4. 安全隐患\n5. 代码风格改进",
                                        session_id="project-analysis"
                                    )
                                    st.markdown(analysis.get("response", ""))
                    
                    except Exception as e:
                        st.error(f"读取文件失败: {e}")
    
    with tab2:
        st.subheader("上传项目文件")
        uploaded_files = st.file_uploader("选择文件", type=["py", "js", "ts", "tsx", "html", "css", "md", "json", "yaml", "yml"],
                                         accept_multiple_files=True)
        
        if uploaded_files:
            st.success(f"已上传 {len(uploaded_files)} 个文件")
            
            for file in uploaded_files:
                content = file.read().decode('utf-8', errors='ignore')
                
                with st.expander(f"📄 {file.name}"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        st.code(content, language="python" if file.name.endswith('.py') else 
                                "javascript" if file.name.endswith(('.js', '.ts', '.tsx')) else
                                "html" if file.name.endswith('.html') else
                                "css" if file.name.endswith('.css') else
                                "markdown" if file.name.endswith('.md') else "text")
                    with col2:
                        if st.button(f"💡 分析", key=f"analyze_upload_{file.name}"):
                            with st.spinner("分析中..."):
                                analysis = brain.chat(
                                    message=f"请分析以下代码文件，并提供改进建议：\n\n文件名: {file.name}\n\n```\n{content[:2000]}\n```\n\n请从以下方面分析：\n1. 代码结构和架构设计\n2. 潜在的 bug 或问题\n3. 性能优化建议\n4. 安全隐患\n5. 代码风格改进",
                                    session_id="project-analysis-upload"
                                )
                                st.markdown(analysis.get("response", ""))
    
    st.divider()
    st.subheader("🎯 批量分析")
    if st.button("让 AOS 分析整个项目", type="primary"):
        if st.session_state.project_files:
            with st.spinner("正在分析项目..."):
                files_summary = "\n".join([f"- {info['path']} ({info['size']} bytes)" 
                                          for info in st.session_state.project_files.values()][:20])
                if len(st.session_state.project_files) > 20:
                    files_summary += f"\n... 还有 {len(st.session_state.project_files) - 20} 个文件"
                
                analysis = brain.chat(
                    message=f"请分析以下项目结构，并提供整体架构评估和改进建议：\n\n项目文件列表：\n{files_summary}\n\n请分析：\n1. 项目整体架构设计\n2. 模块划分是否合理\n3. 技术栈选择是否合适\n4. 潜在的架构问题\n5. 改进建议",
                    session_id="project-full-analysis"
                )
                st.markdown(analysis.get("response", ""))
        else:
            st.warning("请先扫描目录或上传文件")


# ---- Audit Log Page ----
elif page == "📊 审计日志":
    st.title("📊 审计日志")
    st.caption("GB/Z 185-2026 合规审计追踪")
    
    try:
        stats = brain.audit.get_stats()
        col1, col2, col3 = st.columns(3)
        col1.metric("总事件数", stats["total_events"])
        col2.metric("数据库条目", stats["db_entries"])
        col3.metric("缓冲条目", stats["buffered"])
        
        event_types = ["全部"] + [e.value for e in AuditEvent]
        selected_type = st.selectbox("事件类型", event_types)
        
        entries = brain.audit.query(
            event_type=None if selected_type == "全部" else selected_type,
            limit=50
        )
        
        if entries:
            df = pd.DataFrame(entries)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            st.dataframe(df[["event_type", "user_id", "agent_id", "timestamp"]], 
                        use_container_width=True)
            
            st.subheader("详细信息")
            selected_entry = st.selectbox("选择条目", range(len(entries)))
            if selected_entry >= 0:
                st.json(entries[selected_entry])
                
                entry_str = json.dumps(entries[selected_entry], indent=2, ensure_ascii=False)
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("📋 复制详情"):
                        st.copy_to_clipboard(entry_str)
                        st.success("已复制")
                with col2:
                    st.download_button(
                        "📥 下载详情",
                        data=entry_str.encode('utf-8'),
                        file_name=f"audit_entry_{entries[selected_entry]['id']}.json",
                        mime="application/json",
                    )
        else:
            st.info("暂无审计日志")
    except Exception as e:
        st.error(f"加载审计日志失败: {e}")


# ---- Real-time Logs Page ----
elif page == "📝 实时日志":
    st.title("📝 实时日志")
    st.caption("查看系统运行日志，调试问题")
    
    log_level = st.selectbox("日志级别", ["INFO", "DEBUG", "WARNING", "ERROR"], index=0)
    
    log_container = st.container(height=500)
    
    def get_logs():
        log_dir = os.path.join(config.BASE_DIR, "logs")
        latest_log = ""
        if os.path.exists(log_dir):
            log_files = [f for f in os.listdir(log_dir) if f.endswith(".log")]
            if log_files:
                latest_log = sorted(log_files)[-1]
        
        if latest_log:
            log_path = os.path.join(log_dir, latest_log)
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    level_filter = log_level.upper()
                    filtered = []
                    for line in lines[-500:]:
                        if level_filter in line or level_filter == "INFO":
                            filtered.append(line)
                    return "\n".join(filtered[-100:])
            except Exception as e:
                return f"读取日志失败: {e}"
        return "暂无日志文件"
    
    logs = get_logs()
    log_container.code(logs, language="text")
    
    if st.button("🔄 刷新日志"):
        st.rerun()
    
    st.subheader("📂 日志文件")
    log_dir = os.path.join(config.BASE_DIR, "logs")
    if os.path.exists(log_dir):
        log_files = sorted([f for f in os.listdir(log_dir) if f.endswith(".log")])
        for log_file in log_files[-5:]:
            file_path = os.path.join(log_dir, log_file)
            file_size = os.path.getsize(file_path)
            st.markdown(f"- `{log_file}` ({file_size} bytes)")
    else:
        st.info("日志目录不存在")


# ---- System Status Page ----
elif page == "📈 系统状态":
    st.title("📈 系统状态")
    
    try:
        stats = brain.get_full_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("应用名称", stats["app"]["name"])
        col2.metric("AID", stats["app"]["aid"][:16] + "...")
        col3.metric("活跃会话", stats["hermes"].get("active_sessions", 0))
        col4.metric("注册技能", stats["hermes"].get("skills_registered", 0))
        
        st.divider()
        st.subheader("🔗 DeerFlow 深度集成")
        deep = stats.get("deerflow_deep", {})
        cols = st.columns(4)
        cols[0].metric("沙盒", "✅" if deep.get("sandbox_ready") else "❌")
        cols[1].metric("护栏", "✅" if deep.get("guardrails_ready") else "❌")
        cols[2].metric("代理工厂", "✅" if deep.get("agents_factory_ready") else "❌")
        cols[3].metric("子代理执行器", "✅" if deep.get("subagent_executor_ready") else "❌")
        
        st.divider()
        st.subheader("🧠 Deep Hermes")
        hermes_deep = stats.get("deep_hermes", {})
        col1, col2 = st.columns(2)
        col1.metric("自进化技能", "✅" if hermes_deep.get("self_evolving_skills") else "❌")
        col2.metric("Nudge 引擎", "✅" if hermes_deep.get("nudge_engine") else "❌")
        col1.metric("记忆生命周期", "✅" if hermes_deep.get("memory_lifecycle") else "❌")
        col2.metric("上下文引擎", "✅" if hermes_deep.get("context_engine") else "❌")
        
        st.divider()
        st.subheader("📋 完整统计")
        with st.expander("展开完整统计"):
            st.json(stats)
            
            stats_str = json.dumps(stats, indent=2, ensure_ascii=False)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📋 复制统计"):
                    st.copy_to_clipboard(stats_str)
                    st.success("已复制")
            with col2:
                st.download_button(
                    "📥 下载统计",
                    data=stats_str.encode('utf-8'),
                    file_name=f"system_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json",
                )
    except Exception as e:
        st.error(f"加载系统状态失败: {e}")

st.divider()
st.caption(f"AOS v5.0 | {brain.identity.aid}")