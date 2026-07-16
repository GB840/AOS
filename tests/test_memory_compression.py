"""MemoryCompressor 单元测试（真实 numpy，无网络，无外部服务）。

验证：TF-IDF 向量化、自编码器训练收敛、低维编码维度正确、
注入的离群 trace 重构误差显著高于正常样本（异常检测可用）。
"""
from __future__ import annotations

import json
import os
import tempfile

import numpy as np

from kernel.memory_compression import (
    Autoencoder,
    MemoryCompressor,
    TextVectorizer,
    compress_semantic_memory,
)

# 一组高度同质的正常 trace（共享大量 token，便于 AE 学出「常规模式」）
_NORMAL = [
    f"AOS 任务执行成功 子任务编号 {i} 已完成 状态正常"
    for i in range(25)
]

# 一条词分布与上面完全不相交的离群 trace（自编码器应能识别为高重构误差）
_OUTLIER = "量子纠缠态贝尔不等式破缺实验在低温稀释制冷机下观测到非定域关联超导光子"


def _write_jsonl(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for i, text in enumerate(records):
            rec = {
                "ts": f"2026-07-1{i%9}T10:00:00",
                "hash": f"h{i}",
                "task": text[:20],
                "preview": text[:60],
                "content": text,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_text_vectorizer_shape_and_stable_dim():
    v = TextVectorizer(vocab_size=64).fit(_NORMAL)
    vec = v.transform(_NORMAL[0])
    assert vec.ndim == 1
    # 不同文本产同维度（压缩要求稳定维度）
    assert v.transform(_NORMAL[1]).shape == vec.shape
    assert vec.shape[0] > 0
    # 正常文本非空向量
    assert np.any(vec != 0)


def test_autoencoder_reduces_dim_and_reconstructs():
    rng = np.random.default_rng(0)
    X = rng.random((30, 40))
    ae = Autoencoder(input_dim=40, hidden_dim=8).fit(X, epochs=150, lr=0.05)
    codes = ae.encode(X)
    assert codes.shape == (30, 8)  # 压缩到低维
    err = ae.score(X)
    assert err.shape == (30,)
    assert float(np.mean(err)) < 0.05  # 训练后重构误差应较小


def test_memory_compressor_detects_outlier(tmp_path):
    path = tmp_path / "semantic_memory.jsonl"
    # 多数正常 + 末尾 1 条离群
    records = list(_NORMAL) + [_OUTLIER]
    _write_jsonl(records, str(path))

    comp = MemoryCompressor(
        str(path), hidden_dim=8, vocab_size=1024, min_samples=10, keep_recent=5
    )
    res = comp.run()
    assert res.ok is True
    assert res.n_samples == len(records)
    # sidecar 落盘
    assert os.path.exists(comp.compressed_path)
    lines = open(comp.compressed_path, encoding="utf-8").read().splitlines()
    assert len(lines) == len(records)
    sidecar = [json.loads(l) for l in lines]
    # 旧条目压成低维码；最近 keep_recent 条保留原文（无 code 字段）
    old_entries = [e for e in sidecar if e["is_old"]]
    assert len(old_entries) == len(records) - 5
    assert "code" in old_entries[0]
    assert len(old_entries[0]["code"]) == 8

    # 异常检测：离群条（最后一条，hash=h25）应被标记
    assert res.anomaly_count >= 1
    anomaly_hashes = {a["hash"] for a in res.anomalies}
    assert "h25" in anomaly_hashes  # 离群 trace 的 hash


def test_insufficient_samples_returns_honest_status(tmp_path):
    path = tmp_path / "few.jsonl"
    _write_jsonl(_NORMAL[:5], str(path))  # 仅 5 条 < min_samples=20
    comp = MemoryCompressor(str(path), min_samples=20)
    res = comp.run()
    assert res.ok is False
    assert "样本不足" in res.reason
    assert res.n_samples == 5


def test_compress_semantic_memory_default_no_crash():
    # 默认路径可能不存在 / 样本不足 —— 必须诚实返回而非抛异常
    res = compress_semantic_memory(path=__file__)  # __file__ 不是 JSONL，load 返 0
    assert res.ok is False
    assert res.n_samples == 0
