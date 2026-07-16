"""RoutePredictor — 从路由结果学 P(成功 | 能力, 引擎, 档位) 的 MLP。

借鉴「十大模型」里最后一个还没用上的架构：DNN / MLP。
用 numpy 手写单隐层前馈网络，把 (能力 one-hot, 引擎 one-hot, 档位 one-hot)
映射到成功概率。这是路由从「写死的偏好表」走向「数据驱动进化」的真实落点，
对应 AOS 第 8 条理念（黑盒不可训，白盒才可进化）。

设计约束：
- 无 GPU 依赖，纯 numpy；默认环境无 GPU 也能跑。
- 白盒可进化：词汇表与权重可 save / load，永不黑盒。
- 数据不足 / 未训练时 predict 返回中性 0.5，由调用方诚实回落静态策略，绝不瞎编。
- 绝不伪造：只在 RouteOutcomeStore 提供的真实记录上训练。
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any, Dict, List, Optional

import numpy as np


class RoutePredictor:
    """单隐层 MLP：P(ok) = sigmoid(tanh(X·W1+b1)·W2+b2)。"""

    def __init__(
        self,
        hidden: int = 16,
        lr: float = 0.1,
        epochs: int = 300,
        seed: int = 0,
    ) -> None:
        self.hidden = hidden
        self.lr = lr
        self.epochs = epochs
        self._rng = np.random.default_rng(seed)
        self._vocab_cap: List[str] = []
        self._vocab_eng: List[str] = []
        self._vocab_tier: List[str] = []
        self.W1 = None
        self.b1 = None
        self.W2 = None
        self.b2 = None
        self._trained = False
        self._lock = threading.Lock()

    # ---- 词汇表（从训练数据动态构建）----
    def _build_vocab(self, records: List[Dict[str, Any]]) -> None:
        self._vocab_cap = sorted({r["capability"] for r in records})
        self._vocab_eng = sorted({r["engine"] for r in records})
        self._vocab_tier = sorted({r["tier"] for r in records})

    def _onehot(self, vocab: List[str], val: str) -> np.ndarray:
        v = np.zeros(len(vocab), dtype=float)
        if val in vocab:
            v[vocab.index(val)] = 1.0
        return v

    def _encode(self, capability: str, engine: str, tier: str) -> np.ndarray:
        return np.concatenate([
            self._onehot(self._vocab_cap, capability),
            self._onehot(self._vocab_eng, engine),
            self._onehot(self._vocab_tier, tier),
        ])

    def _features(self, records: List[Dict[str, Any]]):
        X = np.stack([
            self._encode(r["capability"], r["engine"], r["tier"])
            for r in records
        ])
        y = np.array(
            [1.0 if r.get("ok") else 0.0 for r in records], dtype=float
        )
        return X, y

    # ---- 训练 ----
    def fit(self, records: List[Dict[str, Any]]) -> None:
        """在真实路由记录上训练。无记录则静默放弃。"""
        if not records:
            return
        with self._lock:
            self._build_vocab(records)
            X, y = self._features(records)
            n_in = X.shape[1]
            # 小初始化，避免 sigmoid/tanh 饱和
            self.W1 = self._rng.normal(0.0, 0.1, (n_in, self.hidden))
            self.b1 = np.zeros(self.hidden)
            self.W2 = self._rng.normal(0.0, 0.1, (self.hidden, 1))
            self.b2 = np.zeros(1)
            n = max(len(y), 1)
            for _ in range(self.epochs):
                z1 = X @ self.W1 + self.b1
                a1 = np.tanh(z1)
                z2 = a1 @ self.W2 + self.b2
                p = 1.0 / (1.0 + np.exp(-z2))  # sigmoid
                # 反向传播（二分类交叉熵梯度 = p - y）
                dp = p - y.reshape(-1, 1)
                dW2 = a1.T @ dp / n
                db2 = dp.mean()
                da1 = dp @ self.W2.T
                dz1 = da1 * (1.0 - a1 ** 2)  # tanh 导数
                dW1 = X.T @ dz1 / n
                db1 = dz1.mean(axis=0)
                self.W1 -= self.lr * dW1
                self.b1 -= self.lr * db1
                self.W2 -= self.lr * dW2
                self.b2 -= self.lr * db2
            self._trained = True

    # ---- 预测 ----
    def predict(self, capability: str, engine: str, tier: str) -> float:
        """返回 P(成功) ∈ [0,1]。

        未训练 → 0.5；任一维度（能力 / 引擎 / 档位）从未在训练集中出现过
        → 0.5（诚实：不假装知道一个从没路由过的组合，由调用方回落静态策略）。
        仅对训练集覆盖范围内的组合给出学到的概率。
        """
        if not self._trained or self.W1 is None:
            return 0.5
        with self._lock:
            if (capability not in self._vocab_cap
                    or engine not in self._vocab_eng
                    or tier not in self._vocab_tier):
                return 0.5
            x = self._encode(capability, engine, tier).reshape(1, -1)
            z1 = x @ self.W1 + self.b1
            a1 = np.tanh(z1)
            z2 = a1 @ self.W2 + self.b2
            p = 1.0 / (1.0 + np.exp(-z2))
            return float(p[0, 0])

    @property
    def trained(self) -> bool:
        return self._trained

    # ---- 持久化 ----
    def save(self, path: str) -> None:
        with self._lock:
            state = {
                "hidden": self.hidden,
                "lr": self.lr,
                "epochs": self.epochs,
                "vocab_cap": self._vocab_cap,
                "vocab_eng": self._vocab_eng,
                "vocab_tier": self._vocab_tier,
                "W1": self.W1.tolist() if self.W1 is not None else None,
                "b1": self.b1.tolist() if self.b1 is not None else None,
                "W2": self.W2.tolist() if self.W2 is not None else None,
                "b2": self.b2.tolist() if self.b2 is not None else None,
                "trained": self._trained,
            }
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "RoutePredictor":
        with open(path, "r", encoding="utf-8") as f:
            s = json.load(f)
        p = cls(
            hidden=s.get("hidden", 16),
            lr=s.get("lr", 0.1),
            epochs=s.get("epochs", 300),
        )
        p._vocab_cap = s.get("vocab_cap", [])
        p._vocab_eng = s.get("vocab_eng", [])
        p._vocab_tier = s.get("vocab_tier", [])
        if s.get("W1") is not None:
            p.W1 = np.array(s["W1"], dtype=float)
            p.b1 = np.array(s["b1"], dtype=float)
            p.W2 = np.array(s["W2"], dtype=float)
            p.b2 = np.array(s["b2"], dtype=float)
            p._trained = bool(s.get("trained", False))
        return p
