"""Hippo-Scroll 可信长期记忆引擎 —— 真跑集成测试（零环境依赖、秒级）。

验证：引擎被真实接电后能 deposit / retrieve / arbitrate / patrol，
且 get_hippo_scroll() 返回进程内单例。沙箱无 GPU/LLM/外网亦可跑。
"""
import pytest

from kernel.hippo_scroll import (
    Confidence,
    EvidenceAnchor,
    HippoScrollEngine,
    Modality,
    get_hippo_scroll,
)

# 取任一模态枚举值（retrieve 按内容匹配，与 modality 无关）
MOD = list(Modality)[0]


def test_engine_deposit_and_retrieve_real():
    hs = HippoScrollEngine()
    aid = hs.deposit_evidence(EvidenceAnchor.create("img_a.jpg", MOD))
    hs.cognition.add_consensus(aid, "图中为一只猫", source="user_a")
    hs.cognition.add_interpretation(aid, "可能是一只豹猫", source="user_b")
    hs.cognition.add_conclusion(aid, "综合判断：猫科动物", basis="多方印证")

    assert hs.evidence.total_anchors == 1
    assert hs.cognition.total_nodes == 3

    res = hs.retrieve("猫", top_k=5)
    assert isinstance(res, dict)
    assert "top_concepts" in res
    assert "light_modalities" in res
    # 文本匹配真实命中：共识节点内容含"猫"
    assert len(res["top_concepts"]) >= 1
    assert res["top_concepts"][0]["content_snippet"]
    assert res["top_concepts"][0]["type"] == "consensus"


def test_arbitrate_four_segment_output():
    hs = HippoScrollEngine()
    aid = hs.deposit_evidence(EvidenceAnchor.create("doc1.txt", MOD))
    hs.cognition.add_consensus(aid, "这是一只猫", source="cam1")
    hs.cognition.add_interpretation(aid, "可能是豹猫", source="cam2")

    arb = hs.arbitrate("图中的动物是什么", aid)
    # 四段式结构化输出
    assert arb.consensus == ["这是一只猫"]
    assert len(arb.disputes) == 1
    assert arb.disputes[0]["topic"] == "图中的动物是什么"
    assert "豹猫" in arb.disputes[0]["viewpoints"][0]
    assert arb.conclusion == "暂无综合结论"  # 未加 conclusion → 默认
    assert arb.confidence == Confidence.DISPUTED  # 有 interpretation → 争议态


def test_patrol_detects_conflict():
    hs = HippoScrollEngine()
    aid = hs.deposit_evidence(EvidenceAnchor.create("x.png", MOD))
    # 同一锚点上两个 interpretation → 潜在分歧
    hs.cognition.add_interpretation(aid, "观点A：是狗", source="s1")
    hs.cognition.add_interpretation(aid, "观点B：是猫", source="s2")

    conflicts = hs.cognition.find_conflicts()
    assert len(conflicts) == 1

    findings = hs.patrol.daily_scan()
    conflict_findings = [f for f in findings if f.finding_type == "conflict"]
    assert len(conflict_findings) == 1
    assert conflict_findings[0].severity == "medium"


def test_get_hippo_scroll_singleton():
    a = get_hippo_scroll()
    b = get_hippo_scroll()
    assert a is b
    assert isinstance(a, HippoScrollEngine)
