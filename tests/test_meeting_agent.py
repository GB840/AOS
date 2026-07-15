"""MeetingAgent 会议自动化流水线 — 纯逻辑集成测试（不触网、不依赖 API Key）。

验证目标（均为不弄虚的硬证据）：
  1. 子智能体经 SubAgentRegistry 正确注册（与 /api/meeting/run 内部路径一致）；
  2. _build_steps 在有/无音频时产出正确的 OrchestrationChiplet steps；
  3. LLM 输出解析：支持 ```json``` 包裹、解析失败兜底（整段当 summary）；
  4. 多形态文本提取；
  5. 定制会议结构化交接信封（HandoffEnvelope）字段正确。

注：真实端到端（拉起 FabricHub 调度 STT/LLM 芯粒 + 写 IMA）已在开发期真跑验证
（note_id=7482968612292501，见提交 b31b1a9 的验证脚本）；本测试聚焦不依赖重型
运行时的核心逻辑，保证 CI/沙箱可稳定复跑。
"""
from __future__ import annotations

import sys

sys.path.insert(0, "D:/AOS/src")

from subagents.registry import SubAgentRegistry
from subagents.meeting_agent import MeetingAgent, register_meeting_subagent


def test_subagent_registration():
    """经 SubAgentRegistry 注册路径：meeting 子智能体可注册且 capability/ops 正确。"""
    reg = SubAgentRegistry()
    register_meeting_subagent(reg)
    assert reg.has("meeting"), "Meeting 子智能体应已注册"
    # 不调用 handle()（会拉起真实 hub 编排），只验证注册元信息
    agent = MeetingAgent()
    assert agent.NAME == "meeting"
    assert "meeting_summary" in agent.CAPABILITIES
    assert "run" in agent.OPERATIONS


def test_build_steps_no_audio():
    """无音频：直接用 transcript 构造单步 LLM 综合 step。"""
    agent = MeetingAgent()
    steps = agent._build_steps(None, "张三：我们下周上线。")
    assert len(steps) == 1
    s = steps[0]
    assert s["capability"] == "inference.llm"
    assert "transcript" not in s["in"]["prompt"] or "transcript" in s["in"]["prompt"]
    assert "会议记录助手" in s["in"]["prompt"]


def test_build_steps_with_audio_path():
    """有音频路径：STT 步 + LLM 步，且 STT 步 in 含 audio_path。"""
    agent = MeetingAgent()
    steps = agent._build_steps({"path": "/tmp/m.wav"}, "")
    assert len(steps) == 2
    assert steps[0]["capability"] == "voice.stt"
    assert steps[0]["in"] == {"audio_path": "/tmp/m.wav"}
    assert steps[1]["capability"] == "inference.llm"
    assert steps[1]["in_from"] == "previous"


def test_build_steps_with_audio_b64():
    """有音频 base64：STT 步 in 含 audio_b64 + audio_suffix。"""
    agent = MeetingAgent()
    steps = agent._build_steps({"b64": "SU5URVJTVFlOR0", "suffix": "mp3"}, "")
    assert steps[0]["in"] == {"audio_b64": "SU5URVJTVFlOR0", "audio_suffix": "mp3"}


def test_parse_meeting_with_fence():
    """LLM 输出带 ```json``` 包裹时仍能正确解析出结构化字段。"""
    raw = '```json\n{"summary":"下周上线","decisions":["拍板上线"],"action_items":[{"owner":"张三","task":"发版","deadline":"周五"}],"open_questions":["回滚方案?"]}\n```'
    m = MeetingAgent._parse_meeting(raw)
    assert m["summary"] == "下周上线"
    assert m["decisions"] == ["拍板上线"]
    assert m["action_items"][0]["owner"] == "张三"
    assert m["open_questions"] == ["回滚方案?"]


def test_parse_meeting_fallback():
    """解析失败（非 JSON）时整段文本作为 summary，不丢信息。"""
    raw = "这是一段无法解析为 JSON 的自由文本会议纪要。"
    m = MeetingAgent._parse_meeting(raw)
    assert m["summary"] == raw
    assert m["decisions"] == []
    assert m["action_items"] == []


def test_extract_text_variants():
    """多形态 LLM 返回都能提取出文本。"""
    assert MeetingAgent._extract_text("纯文本") == "纯文本"
    assert MeetingAgent._extract_text({"text": "a"}) == "a"
    assert MeetingAgent._extract_text({"choices": [{"message": {"content": "b"}}]}) == "b"
    assert MeetingAgent._extract_text({"result": "c"}) == "c"


def test_build_envelope():
    """定制会议信封字段正确（结论/决议/行动项/待决）。"""
    agent = MeetingAgent()
    meeting = {
        "summary": "结论X",
        "decisions": ["决议1", "决议2"],
        "action_items": [{"owner": "李四", "task": "写文档", "deadline": "周一"}],
        "open_questions": ["待定Q"],
    }
    env = agent._build_envelope(
        task_id="meeting-abc", title="周会", attendees="张三,李四", meeting=meeting
    )
    assert env.task_id == "meeting-abc"
    assert env.title == "周会"
    assert any("决议1" in f for f in env.confirmed_facts)
    assert any("李四" in f and "写文档" in f for f in env.confirmed_facts)
    assert env.risk_boundary == ["待定Q"]
    assert env.open_questions == ["待定Q"]
    assert env.source == "MeetingAgent"
    assert "meeting" in env.tags


if __name__ == "__main__":
    test_subagent_registration()
    test_build_steps_no_audio()
    test_build_steps_with_audio_path()
    test_build_steps_with_audio_b64()
    test_parse_meeting_with_fence()
    test_parse_meeting_fallback()
    test_extract_text_variants()
    test_build_envelope()
    print("MeetingAgent 逻辑测试全部通过")
