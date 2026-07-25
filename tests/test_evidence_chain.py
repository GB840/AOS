import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""证据溯源链测试。"""
import pytest
from kernel.evidence_chain import EvidenceChainBuilder, EvidenceNode, EvidenceChain


class TestEvidenceChainBuilder:
    def setup_method(self):
        self.builder = EvidenceChainBuilder()

    def test_build_from_trace(self):
        """从Trace构建证据链。"""
        trace = {
            "task": "测试任务",
            "steps": [
                {"capability": "web.search", "engine": "baidu", "ok": True,
                 "output": {"results": [{"title": "结果1", "url": "http://example.com"}]}},
                {"capability": "inference.llm", "engine": "zhipu", "ok": True,
                 "output": {"content": "分析结论"}},
            ],
            "final": "最终结论",
        }
        chain = self.builder.build_from_trace(trace)
        assert chain.conclusion == "最终结论"
        assert len(chain.nodes) > 0
        assert chain.chain_id

    def test_verify_integrity(self):
        """验证证据链完整性。"""
        trace = {
            "task": "验证任务",
            "steps": [{"capability": "web.search", "engine": "baidu", "ok": True,
                        "output": {"results": []}}],
            "final": "结论",
        }
        chain = self.builder.build_from_trace(trace)
        result = self.builder.verify_chain(chain.chain_id)
        assert "valid" in result
        assert "node_details" in result

    def test_traverse_chain(self):
        """遍历证据链到根节点。"""
        trace = {
            "task": "遍历任务",
            "steps": [{"capability": "web.search", "engine": "baidu", "ok": True,
                        "output": {"results": [{"title": "R1", "url": "http://a.com"}]}}],
            "final": "结论",
        }
        chain = self.builder.build_from_trace(trace)
        if chain.root_nodes:
            nodes = self.builder.traverse_chain(chain.chain_id, chain.root_nodes[0])
            assert isinstance(nodes, list)

    def test_export_for_audit(self):
        """导出审计报告。"""
        trace = {
            "task": "审计任务",
            "steps": [{"capability": "web.search", "engine": "baidu", "ok": True,
                        "output": {"results": []}}],
            "final": "结论",
        }
        chain = self.builder.build_from_trace(trace)
        report = self.builder.export_for_audit(chain.chain_id)
        assert isinstance(report, str)
        assert len(report) > 0
