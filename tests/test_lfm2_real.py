"""LFM2 真权重适配器测试：诚实健康判定 + invoke 路径（假管道注入）。

真权重下载需联网 HF（沙箱被墙），故不在此真加载 LFM2；重点验证：
1. 无权重时 health() 诚实 False（不谎报 live）；
2. 本地权重文件存在性判定；
3. HF 缓存目录检测；
4. 加载成功后 invoke 的 prompt 前缀剥离逻辑（注入假管道证明路径正确）。
"""
import os


from core.fabric.adapters.lfm_adapter import LFMAdapter
from core.fabric.adapter import InvokeRequest


def test_health_false_without_weights():
    a = LFMAdapter(model="LiquidAI/LFM2.5-230M")
    assert a.health() is False


def test_local_gguf_weights_ready(tmp_path):
    f = tmp_path / "m.gguf"
    f.write_bytes(b"dummy")
    a = LFMAdapter(model=str(f))
    assert a._weights_ready() is True
    # llama_cpp 未装 → runtime 缺 → 整体 health False（诚实）
    assert a.health() is False


def test_hf_cache_dir_detection(monkeypatch, tmp_path):
    repo = "LiquidAI/LFM2.5-230M"
    # _hf_cache_dir 在 ~/.cache/huggingface/hub 下找 models--<repo>
    cache = (tmp_path / ".cache" / "huggingface" / "hub"
             / f"models--{repo.replace('/', '--')}")
    cache.mkdir(parents=True)
    monkeypatch.setattr(os.path, "expanduser",
                        lambda p: p.replace("~", str(tmp_path)))
    assert LFMAdapter._hf_cache_dir(repo) is not None
    assert LFMAdapter._hf_cache_dir("Nope/Nonexistent") is None


def test_invoke_path_strips_prompt_prefix(monkeypatch):
    a = LFMAdapter(model="LiquidAI/LFM2.5-230M")
    monkeypatch.setattr(a, "_have_runtime", lambda: True)
    monkeypatch.setattr(a, "_weights_ready", lambda: True)

    class FakePipe:
        def __call__(self, prompt, max_new_tokens=128):
            return [{"generated_text": prompt + " 你好世界"}]

    monkeypatch.setattr(a, "_ensure_loaded", lambda: FakePipe())
    r = a.invoke(InvokeRequest(
        capability="inference.llm", payload={"prompt": "hi"}))
    assert r.ok is True
    assert r.data["text"] == "你好世界"  # 输入前缀被剥离
    assert r.data["engine"] == "lfm2"


def test_tier_is_edge():
    a = LFMAdapter()
    assert a.tier() == "edge"  # tier 是方法（覆盖基类），需调用而非属性访问
