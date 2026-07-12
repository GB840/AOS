"""extract_text：把任意上游产出投影成下游文本消费型能力可用的可读文本。

覆盖真实 run 里出现的各种 out 形状，尤其是 media.image 的 images 字段被
序列化成字符串（"[{'url':...}]"）的情况——这是用户贴出的 trace 里
channel.access 拿空 message 的根因形状。
"""
import pytest

from core.fabric.adapter import extract_text


def test_extract_from_content():
    assert "北京" in extract_text({"content": "北京天气 28℃", "engine": "baidu"})


def test_extract_from_images_list():
    out = {"images": [{"url": "https://img/x.png"}], "model": "agnes"}
    assert "https://img/x.png" in extract_text(out)


def test_extract_from_stringified_images_and_raw():
    # 用户真实 run trace 形状：images 是字符串，raw.data 也是字符串
    out = {
        "images": "[{'b64_json': None, 'url': 'https://img/x.png'}]",
        "model": "agnes-image-2.1-flash",
        "raw": {"data": "[{'b64_json': None, 'url': 'https://img/z.png'}]"},
    }
    t = extract_text(out)
    assert "https://img/x.png" in t
    assert "https://img/z.png" in t


def test_extract_from_search_results():
    out = {
        "content": "北京 28℃",
        "results": [{"title": "AccuWeather", "url": "https://accu/a", "body": "晴"}],
    }
    t = extract_text(out)
    assert "AccuWeather" in t
    assert "https://accu/a" in t


def test_extract_empty_is_honest():
    assert extract_text({}) == ""
    assert extract_text(None) == ""
    assert extract_text("") == ""
    assert extract_text({"model": "agnes"}) == ""
