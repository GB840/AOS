import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

"""SLA监控测试。"""
import pytest
from kernel.monitoring.sla import SLAMonitor, SLAReport, record_request, get_sla_report


class TestSLAMonitor:
    def setup_method(self):
        self.monitor = SLAMonitor()
        self.monitor._records.clear()

    def test_record_request(self):
        """记录请求。"""
        self.monitor.record_request("/api/test", 200, 100.0)
        assert len(self.monitor._records) == 1

    def test_get_report(self):
        """获取报告。"""
        for i in range(10):
            self.monitor.record_request("/api/test", 200, 50.0 + i * 10)
        report = self.monitor.get_sla_report()
        assert isinstance(report, SLAReport)
        assert report.total_requests == 10
        assert report.failed_requests == 0
        assert report.availability == 100.0

    def test_availability_with_failures(self):
        """有失败时可用性计算。"""
        for _ in range(8):
            self.monitor.record_request("/api/test", 200, 50.0)
        for _ in range(2):
            self.monitor.record_request("/api/test", 500, 50.0)
        report = self.monitor.get_sla_report()
        assert report.availability == 80.0
        assert report.failed_requests == 2

    def test_percentiles(self):
        """百分位计算。"""
        for i in range(100):
            self.monitor.record_request("/api/test", 200, float(i))
        report = self.monitor.get_sla_report()
        assert report.p95_latency_ms >= 0
        assert report.p99_latency_ms >= 0

    def test_global_functions(self):
        """全局函数。"""
        record_request("/api/data", 201, 200.0)
        report = get_sla_report()
        assert isinstance(report, SLAReport)
