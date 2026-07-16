"""自编码器记忆压缩 + 异常检测（P1：把十大模型里的「自编码器」借鉴进 AOS）。

落地场景（对齐 AOS 理念「失败即训练数据」与「记忆是加速器」）：
- 语义记忆 ``_traces/semantic_memory.jsonl`` 只增不减、文本越堆越大。
- 用浅层自编码器把旧 trace 文本压成低维特征码（存 sidecar），并可用
  重构误差做**异常检测**（离群 trace 值得人工 review / 提炼为高价值记忆）。

设计原则（与 AOS 第一性一致）：
- 纯 CPU、零硬依赖（仅 numpy，已确认 2.4.6 可用）；不引入 torch/sklearn 重依赖。
- 非破坏性：绝不删除/改写原始 JSONL；压缩结果写独立 sidecar 文件。
- 诚实：样本不足（< MIN_SAMPLES）直接返回明确状态，不假装训出模型。

铁律：所有产物必须可复核——compress() 落盘 sidecar + summary() 给量化指标，
      绝不编造「压缩率 / 异常数」。
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 文本 -> 特征：ascii 词 + 单个 CJK 字（混合中英文都抓得到 token）
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


@dataclass
class CompressResult:
    ok: bool
    reason: str = ""
    n_samples: int = 0
    hidden_dim: int = 0
    compressed_count: int = 0
    anomaly_count: int = 0
    anomaly_threshold: float = 0.0
    compressed_path: str = ""
    anomalies: list[dict] = field(default_factory=list)


class TextVectorizer:
    """有界词表的 TF-IDF 向量化器（numpy 自包含，不依赖 sklearn）。

    词表上限 ``vocab_size``，按文档频率取 Top-K，避免维度爆炸、也保证
    不同批次产出同维度向量（压缩/异常检测要求稳定维度）。
    """

    def __init__(self, vocab_size: int = 512) -> None:
        self.vocab_size = vocab_size
        self._vocab: dict[str, int] = {}
        self._idf: np.ndarray | None = None

    def fit(self, texts: list[str]) -> "TextVectorizer":
        n = len(texts)
        df: dict[str, int] = {}
        for t in texts:
            seen = set(_tokenize(t))
            for tok in seen:
                df[tok] = df.get(tok, 0) + 1
        # 按文档频率取 Top-K 作为词表
        top = sorted(df.items(), key=lambda kv: kv[1], reverse=True)[: self.vocab_size]
        self._vocab = {tok: i for i, (tok, _) in enumerate(top)}
        # IDF（平滑）
        self._idf = np.array(
            [math.log((1 + n) / (1 + df[tok])) + 1.0 for tok in self._vocab],
            dtype=np.float64,
        )
        return self

    def transform(self, text: str) -> np.ndarray:
        if not self._vocab:
            return np.zeros(0, dtype=np.float64)
        vec = np.zeros(len(self._vocab), dtype=np.float64)
        toks = _tokenize(text)
        if not toks:
            return vec
        counts: dict[int, int] = {}
        for tok in toks:
            idx = self._vocab.get(tok)
            if idx is not None:
                counts[idx] = counts.get(idx, 0) + 1
        for idx, c in counts.items():
            vec[idx] = (c / len(toks)) * self._idf[idx]  # tf * idf
        return vec

    def transform_batch(self, texts: list[str]) -> np.ndarray:
        return np.stack([self.transform(t) for t in texts]) if texts else np.zeros((0, len(self._vocab)))


class Autoencoder:
    """浅层自编码器（输入 D -> 隐藏 H -> 输出 D），numpy SGD 训练。

    用途：压缩（encode 取隐藏层低维码）+ 异常检测（reconstruction MSE 高 = 离群）。
    """

    def __init__(self, input_dim: int, hidden_dim: int = 16, seed: int = 0) -> None:
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        rng = np.random.default_rng(seed)
        # 小随机初始化，避免对称权重
        self.W1 = rng.standard_normal((input_dim, hidden_dim)) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = rng.standard_normal((hidden_dim, input_dim)) * 0.1
        self.b2 = np.zeros(input_dim)

    @staticmethod
    def _tanh(x: np.ndarray) -> np.ndarray:
        return np.tanh(x)

    def encode(self, X: np.ndarray) -> np.ndarray:
        return self._tanh(X @ self.W1 + self.b1)

    def reconstruct(self, X: np.ndarray) -> np.ndarray:
        H = self.encode(X)
        return H @ self.W2 + self.b2

    def score(self, X: np.ndarray) -> np.ndarray:
        """每条样本的重构误差（MSE）。"""
        rec = self.reconstruct(X)
        return np.mean((X - rec) ** 2, axis=1)

    def fit(self, X: np.ndarray, epochs: int = 200, lr: float = 0.01) -> "Autoencoder":
        n = X.shape[0]
        idx = np.arange(n)
        for ep in range(epochs):
            rng = np.random.default_rng(ep)
            rng.shuffle(idx)
            total_loss = 0.0
            for i in idx:
                x = X[i]
                H = self._tanh(x @ self.W1 + self.b1)
                out = H @ self.W2 + self.b2
                err = out - x  # dL/dout = 2*err, 略 1/2
                # 反向：dW2 = H.T @ err ; db2 = err
                dW2 = np.outer(H, err)
                db2 = err
                # dH = err @ W2.T * (1 - H^2)
                dH = (err @ self.W2.T) * (1.0 - H ** 2)
                dW1 = np.outer(x, dH)
                db1 = dH
                self.W2 -= lr * dW2
                self.b2 -= lr * db2
                self.W1 -= lr * dW1
                self.b1 -= lr * db1
                total_loss += float(np.mean(err ** 2))
            if (ep + 1) % 50 == 0:
                logger.info("AE epoch %d loss=%.6f", ep + 1, total_loss / n)
        return self


class MemoryCompressor:
    """把语义记忆 JSONL 压缩为低维特征码 + 异常检测。

    非破坏性：原始 JSONL 不动；压缩码 + 重构误差写入独立 sidecar。
    """

    def __init__(
        self,
        source_path: str,
        compressed_path: Optional[str] = None,
        hidden_dim: int = 16,
        vocab_size: int = 512,
        min_samples: int = 20,
        keep_recent: int = 50,
    ) -> None:
        self.source_path = source_path
        self.compressed_path = compressed_path or (source_path + ".compressed.jsonl")
        self.hidden_dim = hidden_dim
        self.vocab_size = vocab_size
        self.min_samples = min_samples
        self.keep_recent = keep_recent
        self._vec: Optional[TextVectorizer] = None
        self._ae: Optional[Autoencoder] = None
        self._records: list[dict] = []
        self._texts: list[str] = []

    # ---- 读取 ----
    def load(self) -> int:
        """读取 JSONL 记录，抽取文本（task + content/preview）。返回条数。"""
        self._records = []
        self._texts = []
        if not os.path.exists(self.source_path):
            return 0
        with open(self.source_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                self._records.append(rec)
                text = " ".join(
                    str(rec.get(k, "")) for k in ("task", "content", "preview")
                )
                self._texts.append(text)
        return len(self._records)

    # ---- 训练 + 压缩 + 异常检测 ----
    def run(self) -> CompressResult:
        n = self.load()
        if n < self.min_samples:
            return CompressResult(
                ok=False,
                reason=f"样本不足：需 >= {self.min_samples}，当前 {n}",
                n_samples=n,
            )
        # 向量化
        self._vec = TextVectorizer(self.vocab_size).fit(self._texts)
        X = self._vec.transform_batch(self._texts)
        if X.shape[1] == 0:
            return CompressResult(
                ok=False, reason="词表为空（文本无可用 token）", n_samples=n
            )
        # 训练 AE
        self._ae = Autoencoder(X.shape[1], self.hidden_dim).fit(X)
        # 压缩：保留最近 keep_recent 条原文，旧条目压成低维码
        codes = self._ae.encode(X)
        scores = self._ae.score(X)
        # 异常阈值：重构误差的 95 分位
        thr = float(np.quantile(scores, 0.95))
        old_count = max(0, n - self.keep_recent)

        sidecar = []
        anomalies: list[dict] = []
        for i, rec in enumerate(self._records):
            is_old = i < old_count
            entry = {
                "ts": rec.get("ts"),
                "hash": rec.get("hash"),
                "is_old": is_old,
                "recon_err": round(float(scores[i]), 6),
                "is_anomaly": bool(scores[i] > thr),
            }
            if is_old:
                entry["code"] = codes[i].round(4).tolist()
            sidecar.append(entry)
            if scores[i] > thr:
                anomalies.append({
                    "ts": rec.get("ts"),
                    "hash": rec.get("hash"),
                    "recon_err": round(float(scores[i]), 6),
                    "preview": (rec.get("preview") or "")[:120],
                })

        # 落盘 sidecar（非破坏，原始 JSONL 不动）
        os.makedirs(os.path.dirname(self.compressed_path) or ".", exist_ok=True)
        with open(self.compressed_path, "w", encoding="utf-8") as f:
            for e in sidecar:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")

        return CompressResult(
            ok=True,
            n_samples=n,
            hidden_dim=self.hidden_dim,
            compressed_count=old_count,
            anomaly_count=len(anomalies),
            anomaly_threshold=round(thr, 6),
            compressed_path=self.compressed_path,
            anomalies=anomalies,
        )

    # ---- 便捷 API（供 autopilot / CLI 调用，非破坏）----
    def compress(self) -> CompressResult:
        return self.run()


def compress_semantic_memory(
    path: Optional[str] = None,
    hidden_dim: int = 16,
    keep_recent: int = 50,
) -> CompressResult:
    """对默认语义记忆文件做压缩 + 异常检测（非破坏，写 sidecar）。"""
    if path is None:
        from kernel.semantic_state import SEMANTIC_MEMORY_PATH
        path = SEMANTIC_MEMORY_PATH
    return MemoryCompressor(
        path, hidden_dim=hidden_dim, keep_recent=keep_recent
    ).run()


def _main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="AOS 语义记忆自编码器压缩（非破坏）")
    ap.add_argument("--path", default=None, help="语义记忆 JSONL 路径（默认用 AOS 真路径）")
    ap.add_argument("--hidden", type=int, default=16, help="隐藏层维度")
    ap.add_argument("--keep-recent", type=int, default=50, help="保留最近 N 条原文不压缩")
    args = ap.parse_args()
    res = compress_semantic_memory(
        path=args.path, hidden_dim=args.hidden, keep_recent=args.keep_recent
    )
    print(json.dumps(res.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
