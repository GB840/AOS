"""全链路三级量化置信（任务279）。

验证理念6 的统一置信口径：低/中/高 + emoji + 量化依据，
且搜索适配器真实结果会带上 confidence 字段（全链路挂接）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapter import InvokeRequest
from core.fabric.adapters.search_adapter import SearchAdapter
from kernel.confidence import assess, assess_command, assess_search


def test_assess_search_three_tiers():
    assert assess_search(0)["level"] == 0   # 🔴 低
    assert assess_search(3)["level"] == 1   # 🟡 中
    assert assess_search(5)["level"] == 2   # 🟢 高
    assert "高" in assess_search(7)["label"]


def test_assess_search_carries_emoji_and_reason():
    c = assess_search(0)
    assert c["emoji"] == "🔴"
    assert "0" in c["reason"]
    assert "低" in c["label"]


def test_assess_command():
    assert assess_command(0)["level"] == 2       # exit 0 有输出 → 高
    assert assess_command(2)["level"] == 0       # 非零退出 → 低
    assert assess_command(0, had_output=False)["level"] == 0  # 无输出 → 低
    assert assess_command(0, had_output=True)["level"] == 2   # 高


def test_assess_custom_threshold():
    assert assess(2, threshold_high=3).level == 1  # 2<3 → 中
    assert assess(3, threshold_high=3).level == 2  # 3>=3 → 高


def test_search_adapter_attaches_confidence(monkeypatch):
    ad = SearchAdapter()
    fake = {"content": "x", "query": "q",
            "results": [{"title": "t", "url": "http://e.com", "body": ""}],
            "count": 3}
    monkeypatch.setattr(ad, "_search_anysearch", lambda q, n: fake)
    res = ad.invoke(InvokeRequest(capability="web.search",
                                  payload={"query": "test"}))
    assert res.ok is True
    assert "confidence" in res.data
    assert res.data["confidence"]["level"] == 1  # 3 条 → 中
