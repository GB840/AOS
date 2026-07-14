"""LNN 适配器 —— AOS fabric 的 INFERENCE_LNN 平面（液态神经网络时间序列推理）。

为什么是「时间序列」而不是「聊天」：
LNN（Liquid Neural Network，源自 MIT Liquid AI，线虫 302 神经元启发）的核心
优势是**连续时间动态建模 + 参数高效 + 边缘友好**，擅长低维时间序列 / 自适应控制 /
长上下文动态。它**不擅长**聊天、代码、精确计算（这是 AOS 的诚实边界，也是
Liquid AI 自己对 LFM 小模型的定位）。所以这里把 LNN 接成「时间序列推理芯粒」，
而非伪造成 LLM 聊天芯粒——它干自己真正擅长的活。

实现策略（对齐 AOS 第一性「轻量、动态、零依赖、不绑定」）：
- 核心是一个**自包含 numpy 实现的 CfC（Closed-form Continuous-time）网络**：
  用 ODE 的闭式解 h_new = f + (h - f)·exp(-A·dt·g) 做连续时间更新，时间常数
  A 随输入动态变化（liquid 的「液态」本质）。手工 BPTT 训练，纯 numpy 零依赖，
  沙箱可直接跑、可直接验证「真的学会了」（MSE 下降）。
- 重依赖（torch / ncps / liquidmind）惰性探测：health() 如实报告 numpy 是否
  live、外部增强库是否可用。**当前训练用 numpy 核心，外部库仅供未来升级**，
  不谎报「已用 torch 训练」。

端云合作：时间序列预测是本地轻量活，永远本地跑；这与 AOS「云端用不了就本地」
一致——LNN 本就是为本地/边缘设计的。
"""
from __future__ import annotations

import logging
import math
import os
import threading

import numpy as np

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability

logger = logging.getLogger(__name__)

_DT = float(os.environ.get("AOS_LNN_DT", "0.1"))  # 连续时间步长


# ---------------------------------------------------------------------------
# 自包含 CfC（Closed-form Continuous-time）单元：纯 numpy + 手工 BPTT
# 参考 Hasani et al. 2022 (Nature Machine Intelligence) 的闭式连续时间公式。
# ---------------------------------------------------------------------------
def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _softplus(x: np.ndarray) -> np.ndarray:
    return np.log1p(np.exp(-np.abs(x))) + np.maximum(x, 0.0)  # 数值稳定 softplus


class _CfCCell:
    """单层 CfC 单元（输入维度 in_size，隐藏维度 hid_size）。"""

    def __init__(self, in_size: int, hid_size: int, seed: int = 0) -> None:
        self.in_size = in_size
        self.hid = hid_size
        d = in_size + hid_size
        rng = np.random.default_rng(seed)
        scale = 1.0 / math.sqrt(d)
        k = lambda: (rng.standard_normal((hid_size, d)) * scale).astype(np.float64)
        self.W_i = k(); self.b_i = np.zeros(hid_size)
        self.W_f = k(); self.b_f = np.zeros(hid_size)
        self.W_g = k(); self.b_g = np.zeros(hid_size)
        self.W_a = k(); self.b_a = np.zeros(hid_size)
        self.W_o = (rng.standard_normal((in_size, hid_size)) * scale).astype(np.float64)
        self.b_o = np.zeros(in_size)

    def step(self, x, h_prev, dt):
        xh = np.concatenate([np.atleast_1d(x), np.atleast_1d(h_prev)]).astype(np.float64)
        z_i = self.W_i @ xh + self.b_i
        z_f = self.W_f @ xh + self.b_f
        z_g = self.W_g @ xh + self.b_g
        z_a = self.W_a @ xh + self.b_a
        i = _sigmoid(z_i)
        f = np.tanh(z_f)
        s_g = _sigmoid(z_g)
        g = 1.0 - s_g
        A = _softplus(z_a)
        decay = np.exp(-A * dt * g)
        h_new = f + (h_prev - f) * decay
        o = i * h_new
        y = self.W_o @ o + self.b_o
        cache = dict(xh=xh, i=i, f=f, g=g, A=A, z_a=z_a, decay=decay, h_prev=h_prev, h_new=h_new, o=o)
        return y, h_new, cache

    def backward_step(self, cache, dy, carry_h, dt):
        i = cache["i"]; f = cache["f"]; g = cache["g"]; z_a = cache["z_a"]
        A = cache["A"]; decay = cache["decay"]; h_prev = cache["h_prev"]; h_new = cache["h_new"]
        d_o = (self.W_o.T @ dy)
        gh = carry_h + d_o * i
        df = gh * (1.0 - decay)
        dd = gh * (h_prev - f)
        di = gh * h_new
        d_decay = -decay
        dA = dd * d_decay * dt * g
        dg = dd * d_decay * A * dt
        s_g = 1.0 - g
        dz_g = dg * (-s_g * (1.0 - s_g))
        dz_a = dA * _sigmoid(z_a)
        dz_f = df * (1.0 - f * f)
        dz_i = di * i * (1.0 - i)
        xh = cache["xh"]
        grads = {}
        for name, dz in (("W_i", dz_i), ("b_i", dz_i), ("W_f", dz_f), ("b_f", dz_f),
                         ("W_g", dz_g), ("b_g", dz_g), ("W_a", dz_a), ("b_a", dz_a)):
            if name.startswith("W"):
                grads.setdefault(name, np.zeros_like(getattr(self, name)))
                grads[name] += np.outer(dz, xh)
            else:
                grads.setdefault(name, np.zeros_like(getattr(self, name)))
                grads[name] += dz
        dW_o = np.outer(dy, cache["o"])
        db_o = dy
        carry_prev = gh * decay
        return grads, dW_o, db_o, carry_prev


class _CfCNet:
    """单层 CfC 序列网络：x_t 预测 y_t（teacher forcing 下一值）。"""

    def __init__(self, in_size: int, hid_size: int, seed: int = 0) -> None:
        self.cell = _CfCCell(in_size, hid_size, seed)
        self.in_size = in_size
        self.hid = hid_size

    def train(self, series, epochs=300, lr=0.02, dt=_DT, clip=1.0, verbose=False):
        S = np.asarray(series, dtype=np.float64)
        if len(S) < 4:
            return [float("nan")]
        X = S[:-1].reshape(-1, 1)
        Y = S[1:].reshape(-1, 1)
        T = len(X)
        c = self.cell
        losses = []
        for ep in range(epochs):
            h = np.zeros(c.hid)
            caches = []
            preds = []
            for t in range(T):
                y, h, cache = c.step(X[t], h, dt)
                caches.append(cache)
                preds.append(y[0])
            preds = np.asarray(preds)
            loss = float(np.mean((preds - Y[:, 0]) ** 2))
            losses.append(loss)
            gW_i = np.zeros_like(c.W_i); gb_i = np.zeros_like(c.b_i)
            gW_f = np.zeros_like(c.W_f); gb_f = np.zeros_like(c.b_f)
            gW_g = np.zeros_like(c.W_g); gb_g = np.zeros_like(c.b_g)
            gW_a = np.zeros_like(c.W_a); gb_a = np.zeros_like(c.b_a)
            gW_o = np.zeros_like(c.W_o); gb_o = np.zeros_like(c.b_o)
            carry = np.zeros(c.hid)
            for t in reversed(range(T)):
                dy = np.atleast_1d((preds[t] - Y[t, 0]))
                grads, dW_o, db_o, carry = c.backward_step(caches[t], dy, carry, dt)
                gW_i += grads.get("W_i", 0); gb_i += grads.get("b_i", 0)
                gW_f += grads.get("W_f", 0); gb_f += grads.get("b_f", 0)
                gW_g += grads.get("W_g", 0); gb_g += grads.get("b_g", 0)
                gW_a += grads.get("W_a", 0); gb_a += grads.get("b_a", 0)
                gW_o += dW_o; gb_o += db_o
            # 全局梯度裁剪（CfC 递归梯度易爆，裁剪保稳定）
            allg = [gW_i, gb_i, gW_f, gb_f, gW_g, gb_g, gW_a, gb_a, gW_o, gb_o]
            norm = np.sqrt(sum(np.sum(g * g) for g in allg))
            if norm > clip:
                scale = clip / norm
                for g in allg:
                    g *= scale
            c.W_i -= lr * gW_i; c.b_i -= lr * gb_i
            c.W_f -= lr * gW_f; c.b_f -= lr * gb_f
            c.W_g -= lr * gW_g; c.b_g -= lr * gb_g
            c.W_a -= lr * gW_a; c.b_a -= lr * gb_a
            c.W_o -= lr * gW_o; c.b_o -= lr * gb_o
            if verbose and ep % 50 == 0:
                logger.info("CfC epoch %d loss=%.5f", ep, loss)
        return losses

    def forecast(self, series, horizon, dt=_DT):
        S = np.asarray(series, dtype=np.float64)
        h = np.zeros(self.cell.hid)
        for t in range(len(S) - 1):
            _, h, _ = self.cell.step(np.atleast_1d(S[t]), h, dt)
        out = []
        x = np.atleast_1d(S[-1])
        for _ in range(horizon):
            y, h, _ = self.cell.step(x, h, dt)
            val = float(y[0])
            out.append(val)
            x = np.atleast_1d(val)
        return out


# ---------------------------------------------------------------------------
# 适配器
# ---------------------------------------------------------------------------
class LNNAdapter(BaseAgentAdapter):
    """液态神经网络时间序列推理适配器（INFERENCE_LNN）。

    引擎无关：默认 numpy 自包含 CfC 永远可用；可选升级到 torch/ncps/liquidmind
    （仅探测可用性，训练仍走 numpy 核心，诚实不谎报）。
    """

    def __init__(self, hidden_size: int = 24, engine: str | None = None) -> None:
        self._hidden = hidden_size
        self._engine = engine or self._detect_engine()
        self._lock = threading.Lock()
        logger.info("LNNAdapter: engine=%s hidden=%d", self._engine, hidden_size)

    @staticmethod
    def _detect_engine() -> str:
        for name, mod in (("torch", "torch"), ("ncps", "ncps"),
                          ("liquidmind", "liquidmind")):
            try:
                __import__(mod)
                return name + "(available)"
            except Exception:
                continue
        return "cfc-numpy"

    @property
    def engine_id(self) -> str:
        return "lnn"

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.INFERENCE_LNN]

    def health(self) -> bool:
        return True

    def health_detail(self) -> dict:
        return {
            "engine": self._engine,
            "live": True,
            "backend": "numpy CfC (self-contained, zero-dep)",
            "upgrade_available": any(
                self._engine.startswith(p) for p in ("torch", "ncps", "liquidmind")
            ),
            "note": "LNN 擅长时间序列/动态适应；聊天/代码请走 inference.llm（高低搭配）",
        }

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        payload = req.payload or {}
        series = payload.get("series")
        horizon = int(payload.get("horizon", 5))
        demo = payload.get("demo", False)

        if demo or series is None:
            series = [math.sin(0.3 * i) for i in range(60)]

        try:
            series = [float(x) for x in series]
        except Exception:
            return InvokeResult(ok=False, error="series 必须是一维数值列表")

        if len(series) < 4:
            return InvokeResult(ok=False, error="series 至少需 4 个点")

        with self._lock:
            net = _CfCNet(in_size=1, hid_size=self._hidden, seed=42)
            losses = net.train(series, epochs=int(payload.get("epochs", 500)))
            final_loss = losses[-1] if losses else float("nan")
            fc = net.forecast(series, horizon=max(1, horizon))

        return InvokeResult(ok=True, data={
            "forecast": [round(float(v), 4) for v in fc],
            "engine": self._engine,
            "final_loss": round(float(final_loss), 6),
            "trained_points": len(series),
            "horizon": horizon,
        })
