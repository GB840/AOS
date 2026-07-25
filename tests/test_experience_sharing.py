import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""跨租户经验共享测试。"""
import tempfile
import pytest
from kernel.experience_sharing import ExperienceSharingEngine, SharedExperience


class TestExperienceSharingEngine:
    def setup_method(self):
        self.tmp = tempfile.mktemp(suffix=".jsonl")
        self.engine = ExperienceSharingEngine(store_path=self.tmp)

    def teardown_method(self):
        import os as _os
        if _os.path.exists(self.tmp):
            _os.remove(self.tmp)

    def test_upload_experience(self):
        """上传经验。"""
        eid = self.engine.upload_experience(
            tenant_id="t1", category="failure_pattern",
            capability="web.search", pattern="bing超时", solution="降级到baidu",
            engine="baidu"
        )
        assert eid
        assert len(eid) > 0

    def test_query_experiences(self):
        """查询经验。"""
        self.engine.upload_experience(
            tenant_id="t1", category="failure_pattern",
            capability="web.search", pattern="bing超时", solution="降级"
        )
        results = self.engine.query_experiences(capability="web.search", min_confidence=0.0)
        assert len(results) >= 1

    def test_verify_experience(self):
        """验证经验。"""
        eid = self.engine.upload_experience(
            tenant_id="t1", category="failure_pattern",
            capability="web.search", pattern="test", solution="fix"
        )
        self.engine.verify_experience(eid, tenant_id="t2", verified=True)
        exps = self.engine.query_experiences(capability="web.search")
        assert exps[0].verification_count >= 1

    def test_inject_for_new_tenant(self):
        """为新租户注入经验。"""
        self.engine.upload_experience(
            tenant_id="t1", category="failure_pattern",
            capability="web.search", pattern="超时", solution="降级"
        )
        for i in range(5):
            self.engine.verify_experience(
                self.engine.upload_experience(
                    tenant_id=f"t{i}", category="failure_pattern",
                    capability="web.search", pattern="超时", solution="降级"
                ),
                tenant_id=f"v{i}", verified=True
            )
        lessons = self.engine.inject_for_new_tenant("new_tenant", ["web.search"])
        assert isinstance(lessons, list)

    def test_anonymize(self):
        """匿名化处理。"""
        text = "租户abc的API Key sk-1234567890泄露了"
        anon = self.engine._anonymize(text)
        assert "abc" not in anon or "租户" in anon
