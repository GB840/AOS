"""SearchAdapter 多源 fallback 测试：百度/Bing（国内可达）优先 → DDG/Jina（墙外兜底）→ 智谱。

不真实联网（monkeypatch 各 _search_*），只验证：能力注册、产出可被下游消费的
content 摘要、fallback 顺序（百度/Bing 优先）、全失败优雅报错、plan_bridge 路由、
hub 注册、ag2 尖括号噪声剥离。
"""
from __future__ import annotations

import pytest

from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability
from core.fabric.adapters import search_adapter as m


def _baidu_ok(self, query, n):
    return {"content": f"{query} 百度结果：晴 26度", "query": query,
            "results": [{"title": "天气", "url": "http://b", "body": "晴 26度"}], "count": 1}


def _bing_ok(self, query, n):
    return {"content": f"{query} Bing结果：晴 26度", "query": query,
            "results": [{"title": "temp", "url": "http://x", "body": "晴"}], "count": 1}


def _zhipu_ok(self, query, n):
    return {"content": f"{query} 智谱联网结果：晴 26度", "query": query,
            "results": [{"title": "天气", "url": "http://z", "body": "晴 26度"}], "count": 1}


def _ddg_ok(self, query, n):
    return {"content": f"{query} DDG结果", "query": query,
            "results": [{"title": "r", "url": "http://d", "body": "晴"}], "count": 1}


def _jina_ok(self, query, n):
    return {"content": f"{query} jina结果", "query": query,
            "results": [{"title": "j", "url": "http://j", "body": "晴"}], "count": 1}


def _anysearch_ok(self, query, n):
    return {"content": f"{query} AnySearch结果：晴 26度 [天气](http://a1)",
            "query": query,
            "results": [{"title": "天气", "url": "http://a1", "body": ""}], "count": 1}


@pytest.fixture
def patch_all_ok(monkeypatch):
    monkeypatch.setattr(m.SearchAdapter, "_search_anysearch", _anysearch_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_baidu", _baidu_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_bing", _bing_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _zhipu_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _ddg_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    yield


def test_search_adapter_advertises_web_search():
    a = m.SearchAdapter()
    assert Capability.WEB_SEARCH in a.advertise_capabilities()
    assert a.health() is True


def test_search_adapter_returns_content_summary(patch_all_ok):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert "content" in res.data
    assert "AnySearch结果" in res.data["content"]  # 第0源（质量最高）优先
    assert res.data["query"] == "北京天气"
    assert res.data["engine"] == "anysearch"  # AnySearch 排第一
    assert res.data["count"] == 1


def test_search_adapter_accepts_task_field(patch_all_ok):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"task": "上海温度"})
    )
    assert res.ok is True
    assert res.data["query"] == "上海温度"


def test_search_adapter_fallback_to_jina(monkeypatch):
    # AnySearch/百度/Bing/DDG 挂 → 跳 Jina
    def _fail(self, q, n):
        raise RuntimeError("boom")
    monkeypatch.setattr(m.SearchAdapter, "_search_anysearch", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_baidu", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_bing", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert res.data["engine"] == "jina"


def test_search_adapter_skips_zhipu_refusal(monkeypatch):
    # 智谱返回「套话 + 无真实结果(count=0)」→ 不得冒成功，必须跳百度
    def _zhipu_refusal(self, q, n):
        return {"content": "很抱歉，我无法直接联网搜索实时信息",
                "query": q, "results": [], "count": 0}
    def _fail(self, q, n):
        raise RuntimeError("boom")
    monkeypatch.setattr(m.SearchAdapter, "_search_anysearch", _fail)
    monkeypatch.setattr(m.SearchAdapter, "_search_baidu", _baidu_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_bing", _bing_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _zhipu_refusal)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _ddg_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert res.data["engine"] == "baidu"   # 智谱拒绝 → 如实跳过 → 百度


def test_search_adapter_all_fail(monkeypatch):
    def _fail(self, q, n):
        raise RuntimeError("boom")
    for name in ("_search_anysearch", "_search_baidu", "_search_bing", "_search_zhipu",
                 "_search_ddg", "_search_jina"):
        monkeypatch.setattr(m.SearchAdapter, name, _fail)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "x"})
    )
    assert res.ok is False
    assert "所有搜索源均失败" in res.error


def test_search_adapter_missing_query():
    res = m.SearchAdapter().invoke(InvokeRequest(capability="web.search", payload={}))
    assert res.ok is False
    assert "query" in res.error


def test_plan_bridge_maps_search_to_web_search():
    from kernel.plugins.plan_bridge import heuristic_plan

    caps = ["web.search", "media.image", "inference.llm", "action.aci"]
    steps = heuristic_plan("搜索天气并画一张示意图", caps)
    # 首步：搜索意图 → web.search，带原始 task 入参
    assert steps[0]["capability"] == "web.search"
    assert steps[0]["in"] == {"task": "搜索天气"}
    # 画图意图 → media.image（桥接增强会在中间插入 LLM 步，但意图映射必须保留）
    img_steps = [s for s in steps if s["capability"] == "media.image"]
    assert img_steps, "画图意图未映射到 media.image"
    assert img_steps[0].get("in_from") == "previous"
    # 跨能力桥接：搜索(非 LLM 源) → 画图 之间应插入 LLM 推理步生成图像提示词
    llm_steps = [s for s in steps if s["capability"] == "inference.llm"]
    assert llm_steps, "搜索→画图应插入 LLM 桥接步"
    assert "提示词" in llm_steps[0].get("prompt", "")


def test_plan_bridge_strips_ag2_angle_brackets():
    from kernel.plugins.plan_bridge import parse_plan_to_steps

    plan = (
        '1. [web.search] <search for "Beijing weather" in English>\n'
        "2. [media.image] <generate a weather diagram from the results>"
    )
    caps = ["web.search", "media.image"]
    steps = parse_plan_to_steps(plan, caps)
    assert steps[0]["capability"] == "web.search"
    # 尖括号与标签都应被剥离，只留实质查询
    assert steps[0]["in"]["task"] == 'search for "Beijing weather" in English'
    assert steps[1]["capability"] == "media.image"
    assert steps[1]["in_from"] == "previous"


def test_fabric_hub_registers_search():
    from kernel.plugins.fabric_hub import FabricHub

    hub = FabricHub(adapters=(m.SearchAdapter,))
    assert hub.resolve_engine("web.search") == "web-search"


class _FakeResp:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


_BAIDU_HTML = """
<div class="result-molecule">
  <h3><a href="http://weather.example/1">北京天气预报15天</a></h3>
  <div class="c-abstract">今天北京晴，26度，北风3级，空气质量良</div>
</div>
<div class="result-molecule">
  <h3><a href="http://weather.example/2">北京天气实时</a></h3>
  <div>明天多云转阴，最高28度</div>
</div>
"""

_BING_HTML = """
<li class="b_algo">
  <h2><a href="http://bing.example/a">Beijing Weather</a></h2>
  <p class="b_lineclamp2">Today in Beijing: sunny, 26C</p>
</li>
<li class="b_algo">
  <h2><a href="http://bing.example/b">北京 天气</a></h2>
  <p>明天多云</p>
</li>
"""


def test_search_baidu_parses_real_html(monkeypatch):
    # 用样本 HTML 锁死块切解析（百度 class 名为随机哈希，按 <h3> 切块）
    def _get(url, **kw):
        return _FakeResp(_BAIDU_HTML)
    monkeypatch.setattr(m.requests, "get", _get)
    res = m.SearchAdapter()._search_baidu("北京天气", 5)
    assert res["count"] == 2
    assert res["results"][0]["url"].startswith("http")
    assert "晴" in res["results"][0]["body"]   # 摘要抓到了真实天气文本
    assert "北京天气预报15天" in res["content"]


def test_search_bing_parses_real_html(monkeypatch):
    def _get(url, **kw):
        return _FakeResp(_BING_HTML)
    monkeypatch.setattr(m.requests, "get", _get)
    res = m.SearchAdapter()._search_bing("北京天气", 5)
    assert res["count"] == 2
    assert "sunny" in res["results"][0]["body"]
    assert "Beijing Weather" in res["content"]


# ---- AnySearch（第0源：实时外脑） ----
class _FakePostResp:
    """模拟 requests.post 返回（JSON-RPC 形态）。"""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_anysearch_parses_jsonrpc(monkeypatch):
    # 锁死：AnySearch 返回 JSON-RPC，从 text 抽真实链接
    def _post(url, **kw):
        assert url == "https://api.anysearch.com/mcp"
        body = kw["json"]
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == "search"
        assert body["params"]["arguments"]["query"] == "北京天气"
        return _FakePostResp({
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{
                "type": "text",
                "text": "北京今日晴 26度\n- [15天预报](http://a1)\n- [实时天气](http://a2)",
            }]},
        })
    monkeypatch.setattr(m.requests, "post", _post)
    res = m.SearchAdapter()._search_anysearch("北京天气", 5)
    assert res["count"] == 2
    assert res["results"][0]["url"].startswith("http")
    assert "晴" in res["content"]
    assert res["query"] == "北京天气"


def test_search_anysearch_api_error_raises(monkeypatch):
    def _post(url, **kw):
        return _FakePostResp({"jsonrpc": "2.0", "id": 1,
                              "error": {"message": "invalid api key"}})
    monkeypatch.setattr(m.requests, "post", _post)
    with pytest.raises(RuntimeError):
        m.SearchAdapter()._search_anysearch("x", 5)


def test_search_anysearch_no_links_falls_through(monkeypatch):
    # AnySearch 返回套话（无链接）→ 不得冒成功，必须跳百度
    def _post(url, **kw):
        return _FakePostResp({
            "jsonrpc": "2.0", "id": 1,
            "result": {"content": [{"type": "text",
                                    "text": "抱歉，我无法联网搜索实时信息。"}]},
        })
    monkeypatch.setattr(m.requests, "post", _post)
    monkeypatch.setattr(m.SearchAdapter, "_search_baidu", _baidu_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_bing", _bing_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_ddg", _ddg_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_jina", _jina_ok)
    monkeypatch.setattr(m.SearchAdapter, "_search_zhipu", _zhipu_ok)
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert res.data["engine"] == "baidu"   # AnySearch 无链接 → 如实跳过 → 百度


def test_search_adapter_anysearch_is_first_source(patch_all_ok):
    res = m.SearchAdapter().invoke(
        InvokeRequest(capability="web.search", payload={"query": "北京天气"})
    )
    assert res.ok is True
    assert res.data["engine"] == "anysearch"  # 第0源排第一
