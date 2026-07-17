"""测试PyramidRetriever倒排索引（O6修复验证）"""
import pytest
import time
from kernel.hippo_scroll import EvidenceTrack, CognitionTrack, PyramidRetriever


def test_pyramid_retriever_inverted_index():
    """测试倒排索引正确性"""
    evidence = EvidenceTrack()
    cognition = CognitionTrack(evidence)
    retriever = PyramidRetriever(evidence, cognition)

    # 添加节点
    cognition.add_consensus("anchor1", "Python is a programming language", "source1")
    cognition.add_consensus("anchor2", "JavaScript is a programming language", "source2")
    cognition.add_consensus("anchor3", "Python is widely used for data science", "source3")

    # 验证倒排索引
    assert "python" in cognition._inverted_index
    assert "programming" in cognition._inverted_index
    assert "language" in cognition._inverted_index
    assert len(cognition._inverted_index["python"]) == 2


def test_pyramid_retriever_performance():
    """测试检索1000个节点响应时间<500ms"""
    evidence = EvidenceTrack()
    cognition = CognitionTrack(evidence)
    retriever = PyramidRetriever(evidence, cognition)

    # 添加1000个节点
    for i in range(1000):
        cognition.add_consensus(f"anchor{i}", f"Content {i} about Python programming", f"source{i}")

    # 测试检索性能
    start = time.time()
    result = retriever.retrieve("Python programming", need_deep_verify=False, top_k=5)
    end = time.time()

    # 验证响应时间<500ms
    elapsed = (end - start) * 1000  # 转换为毫秒
    assert elapsed < 500, f"检索响应时间{elapsed:.2f}ms超过500ms阈值"

    # 验证返回结果
    assert "top_concepts" in result
    assert len(result["top_concepts"]) <= 5