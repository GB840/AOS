"""Cost Tracker —— Token 用量与成本可观测。

落地「Task 1: Cost Observability」：
- count_tokens：用已装的 tiktoken 算 OpenAI/GPT/Claude 系模型的 token；其余模型回退字符估算
- estimate_cost：按模型定价表（USD/1K tokens）估算单次成本
- CostTracker：累计 token 用量事件 + 持久化 + 按 user/agent/workflow/model 维度汇总
- CostAlert：阈值告警（按 daily/monthly 周期、按 workflow/user/agent/global 作用域）

设计原则（Ponytail §10）：
- 复用已装 tiktoken（0.12.0），不新增依赖
- 标准 JSONL 追加写，便于回放/重算
- 非侵入：调用方传 token_usage 字段即可，不传则跳过

成本数据落盘路径：data/workspaces/fabric/pulse/costs.jsonl（事件）+ cost_summary.json（聚合）
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Token 计数 ──

_TIKTOKEN_ENC = None  # 懒加载的 cl100k_base 编码器
_TIKTOKEN_LOCK = threading.Lock()


def _get_tiktoken():
    """懒加载 tiktoken 的 cl100k_base 编码（GPT-4/4o/Claude 系通用近似）。"""
    global _TIKTOKEN_ENC
    if _TIKTOKEN_ENC is not None:
        return _TIKTOKEN_ENC
    with _TIKTOKEN_LOCK:
        if _TIKTOKEN_ENC is not None:
            return _TIKTOKEN_ENC
        try:
            import tiktoken  # type: ignore
            _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")
        except Exception as e:  # noqa: BLE001
            logger.debug("tiktoken 不可用，回退字符估算: %s", e)
            _TIKTOKEN_ENC = False  # 标记不可用，避免反复 import
    return _TIKTOKEN_ENC if _TIKTOKEN_ENC is not False else None


def count_tokens(text: str, model: str = "") -> int:
    """估算文本的 token 数。

    优先用 tiktoken（cl100k_base）；不可用时按字符估算：
    - 中文字符按 1 字 ≈ 1 token（GPT 系实测中文字 token 比约 1:1）
    - 英文/拉丁字符按 4 字符 ≈ 1 token
    """
    if not text:
        return 0
    enc = _get_tiktoken()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:  # noqa: BLE001
            pass

    # 回退：中文字符逐个计 1，其余按 4:1
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return chinese + (other + 3) // 4


# ── 模型定价（USD per 1K tokens）──
# 内置默认值，可用 AOS_MODEL_PRICING_JSON 环境变量整体覆盖或追加。
# 缺失模型按 0.002/1K 兜底（OpenAI small 档近似值）。

_DEFAULT_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4": {"prompt": 0.03, "completion": 0.06},
    "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
    "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
    "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
    "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
    "claude-3.5-sonnet": {"prompt": 0.003, "completion": 0.015},
    "qwen2.5:7b": {"prompt": 0.0, "completion": 0.0},  # 本地模型零成本
    "qwen2.5-coder:7b": {"prompt": 0.0, "completion": 0.0},
    "llama3:8b": {"prompt": 0.0, "completion": 0.0},
    "default": {"prompt": 0.002, "completion": 0.006},
}

_PRICING_LOCK = threading.Lock()
_PRICING_CACHE: Optional[Dict[str, Dict[str, float]]] = None


def _get_pricing() -> Dict[str, Dict[str, float]]:
    """读取定价表，支持环境变量覆盖。"""
    global _PRICING_CACHE
    if _PRICING_CACHE is not None:
        return _PRICING_CACHE
    with _PRICING_LOCK:
        if _PRICING_CACHE is not None:
            return _PRICING_CACHE
        pricing = dict(_DEFAULT_PRICING)  # 浅拷贝
        env_json = os.environ.get("AOS_MODEL_PRICING_JSON", "")
        if env_json:
            try:
                override = json.loads(env_json)
                pricing.update(override)
            except Exception as e:  # noqa: BLE001
                logger.warning("AOS_MODEL_PRICING_JSON 解析失败: %s", e)
        _PRICING_CACHE = pricing
    return _PRICING_CACHE


def estimate_cost(prompt_tokens: int, completion_tokens: int,
                  model: str = "") -> float:
    """按模型定价估算单次调用的 USD 成本。

    匹配规则：
    - 完全匹配模型名
    - 模型名前缀匹配（如 "gpt-4o-2024-08-06" 匹配 "gpt-4o"）
      按 key 长度倒序匹配，避免短前缀（如 "gpt-4"）抢匹配长前缀（"gpt-4o"）
    - 否则用 "default" 兜底
    """
    pricing = _get_pricing()
    model_lower = (model or "").lower().strip()

    # 完全匹配
    rates = pricing.get(model_lower)
    # 前缀匹配（按 key 长度倒序，长的优先）
    if rates is None:
        sorted_keys = sorted(
            (k for k in pricing if k != "default"),
            key=len, reverse=True,
        )
        for key in sorted_keys:
            if model_lower.startswith(key):
                rates = pricing[key]
                break
    # 兜底
    if rates is None:
        rates = pricing["default"]

    cost = (prompt_tokens / 1000.0) * rates["prompt"] + \
           (completion_tokens / 1000.0) * rates["completion"]
    return round(cost, 6)


# ── 成本记录 ──

@dataclass
class CostRecord:
    """单次 token 用量事件。"""
    id: str = ""
    timestamp: str = ""
    workflow_id: str = ""
    user_id: str = "anonymous"
    agent_id: str = ""  # 引擎/适配器名（如 litellm / ollama / agnes）
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    run_id: str = ""  # 关联工作流运行 ID（可选）


@dataclass
class CostAlert:
    """成本告警配置。"""
    id: str = ""
    name: str = ""
    scope: str = "global"  # global / workflow / user / agent
    scope_id: str = ""  # scope 对应的 ID（如 workflow_id / user_id）
    period: str = "daily"  # daily / monthly
    threshold_usd: float = 1.0  # 超过该阈值触发
    enabled: bool = True
    created_at: str = ""
    last_triggered: str = ""
    trigger_count: int = 0


@dataclass
class CostBreakdown:
    """成本聚合结果。"""
    total_cost: float = 0.0
    total_tokens: int = 0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    record_count: int = 0
    by_model: Dict[str, float] = field(default_factory=dict)
    by_workflow: Dict[str, float] = field(default_factory=dict)
    by_user: Dict[str, float] = field(default_factory=dict)
    by_agent: Dict[str, float] = field(default_factory=dict)


class CostTracker:
    """Token 用量与成本跟踪器。

    单例模式（get_cost_tracker()），落盘到 Pulse 目录下的 costs.jsonl + cost_summary.json。
    """

    def __init__(self, costs_path: str = "", alerts_path: str = ""):
        base = os.environ.get("AOS_PULSE_DIR",
                              os.path.join("data", "workspaces", "fabric", "pulse"))
        os.makedirs(base, exist_ok=True)
        self._costs_path = costs_path or os.path.join(base, "costs.jsonl")
        self._alerts_path = alerts_path or os.path.join(base, "cost_alerts.json")
        self._summary_path = os.path.join(base, "cost_summary.json")
        self._lock = threading.Lock()
        self._alerts: Dict[str, CostAlert] = {}
        self._load_alerts()

    # ── 记录 ──

    def record(self, *,
               workflow_id: str = "",
               user_id: str = "anonymous",
               agent_id: str = "",
               model: str = "",
               prompt_tokens: int = 0,
               completion_tokens: int = 0,
               duration_ms: float = 0.0,
               run_id: str = "") -> CostRecord:
        """记录一次 token 用量事件，并检查告警。

        Returns:
            CostRecord（含生成的 id、cost_usd、timestamp）
        """
        total = prompt_tokens + completion_tokens
        cost = estimate_cost(prompt_tokens, completion_tokens, model)

        record = CostRecord(
            id=uuid.uuid4().hex[:12],
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            workflow_id=workflow_id,
            user_id=user_id or "anonymous",
            agent_id=agent_id,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            cost_usd=cost,
            duration_ms=duration_ms,
            run_id=run_id,
        )

        with self._lock:
            try:
                with open(self._costs_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
            except Exception as e:  # noqa: BLE001
                logger.debug("写入成本事件失败: %s", e)

        # best-effort 告警检查
        try:
            self._check_alerts(record)
        except Exception as e:  # noqa: BLE001
            logger.debug("成本告警检查失败: %s", e)

        return record

    # ── 查询 ──

    def get_breakdown(self, *,
                      workflow_id: str = "",
                      user_id: str = "",
                      agent_id: str = "",
                      since: str = "",
                      until: str = "",
                      limit: int = 10000) -> CostBreakdown:
        """聚合查询成本数据。

        Args:
            workflow_id/user_id/agent_id: 过滤维度（空字符串=不过滤）
            since/until: 时间过滤（ISO 字符串前缀比较，如 "2026-07" 过滤整月）
            limit: 最多扫描多少条事件
        """
        bd = CostBreakdown()
        for record in self._iter_records(limit=limit):
            # 过滤
            if workflow_id and record.get("workflow_id") != workflow_id:
                continue
            if user_id and record.get("user_id") != user_id:
                continue
            if agent_id and record.get("agent_id") != agent_id:
                continue
            ts = record.get("timestamp", "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue

            cost = record.get("cost_usd", 0)
            pt = record.get("prompt_tokens", 0)
            ct = record.get("completion_tokens", 0)
            tt = record.get("total_tokens", 0)

            bd.total_cost += cost
            bd.total_tokens += tt
            bd.total_prompt_tokens += pt
            bd.total_completion_tokens += ct
            bd.record_count += 1

            model = record.get("model", "unknown") or "unknown"
            wf = record.get("workflow_id", "unknown") or "unknown"
            uid = record.get("user_id", "anonymous") or "anonymous"
            agt = record.get("agent_id", "unknown") or "unknown"

            bd.by_model[model] = round(bd.by_model.get(model, 0) + cost, 6)
            bd.by_workflow[wf] = round(bd.by_workflow.get(wf, 0) + cost, 6)
            bd.by_user[uid] = round(bd.by_user.get(uid, 0) + cost, 6)
            bd.by_agent[agt] = round(bd.by_agent.get(agt, 0) + cost, 6)

        bd.total_cost = round(bd.total_cost, 6)
        return bd

    def get_recent_records(self, limit: int = 50,
                           workflow_id: str = "") -> List[Dict[str, Any]]:
        """获取最近 N 条成本事件（按时间倒序）。"""
        records = list(self._iter_records(limit=limit * 3 if workflow_id else limit))
        if workflow_id:
            records = [r for r in records if r.get("workflow_id") == workflow_id]
        records.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return records[:limit]

    # ── 告警 ──

    def add_alert(self, alert: CostAlert) -> CostAlert:
        """添加一个成本告警。"""
        if not alert.id:
            alert.id = uuid.uuid4().hex[:8]
        if not alert.created_at:
            alert.created_at = time.strftime("%Y-%m-%dT%H:%M:%S")
        with self._lock:
            self._alerts[alert.id] = alert
            self._save_alerts()
        return alert

    def list_alerts(self, enabled_only: bool = False) -> List[CostAlert]:
        """列出所有告警配置。"""
        alerts = list(self._alerts.values())
        if enabled_only:
            alerts = [a for a in alerts if a.enabled]
        return alerts

    def delete_alert(self, alert_id: str) -> bool:
        """删除一个告警。"""
        with self._lock:
            if alert_id not in self._alerts:
                return False
            del self._alerts[alert_id]
            self._save_alerts()
            return True

    def toggle_alert(self, alert_id: str, enabled: bool) -> bool:
        """启用/禁用一个告警。"""
        with self._lock:
            alert = self._alerts.get(alert_id)
            if not alert:
                return False
            alert.enabled = enabled
            self._save_alerts()
            return True

    def check_alerts(self) -> List[Dict[str, Any]]:
        """主动检查所有告警，返回触发的告警列表。

        每个告警按其 period（daily/monthly）聚合成本，超阈值即触发。
        """
        triggered = []
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        today_prefix = now[:10]  # YYYY-MM-DD
        month_prefix = now[:7]   # YYYY-MM

        for alert in list(self._alerts.values()):
            if not alert.enabled:
                continue

            since = today_prefix if alert.period == "daily" else month_prefix
            bd = self.get_breakdown(
                workflow_id=alert.scope_id if alert.scope == "workflow" else "",
                user_id=alert.scope_id if alert.scope == "user" else "",
                agent_id=alert.scope_id if alert.scope == "agent" else "",
                since=since,
            )

            if bd.total_cost > alert.threshold_usd:
                triggered.append({
                    "alert_id": alert.id,
                    "alert_name": alert.name,
                    "scope": alert.scope,
                    "scope_id": alert.scope_id,
                    "period": alert.period,
                    "threshold_usd": alert.threshold_usd,
                    "actual_cost": bd.total_cost,
                    "records": bd.record_count,
                    "checked_at": now,
                })
                # 更新告警触发记录
                with self._lock:
                    if alert.id in self._alerts:
                        self._alerts[alert.id].last_triggered = now
                        self._alerts[alert.id].trigger_count += 1
                        self._save_alerts()

        return triggered

    # ── 内部 ──

    def _check_alerts(self, record: CostRecord) -> None:
        """新事件到达时做轻量告警检查（只查相关 scope）。"""
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        today_prefix = now[:10]
        month_prefix = now[:7]

        for alert in list(self._alerts.values()):
            if not alert.enabled:
                continue
            # 只查与本次记录相关的 scope
            if alert.scope == "workflow" and alert.scope_id != record.workflow_id:
                continue
            if alert.scope == "user" and alert.scope_id != record.user_id:
                continue
            if alert.scope == "agent" and alert.scope_id != record.agent_id:
                continue

            since = today_prefix if alert.period == "daily" else month_prefix
            bd = self.get_breakdown(
                workflow_id=record.workflow_id if alert.scope == "workflow" else "",
                user_id=record.user_id if alert.scope == "user" else "",
                agent_id=record.agent_id if alert.scope == "agent" else "",
                since=since,
            )

            if bd.total_cost > alert.threshold_usd:
                with self._lock:
                    if alert.id in self._alerts:
                        self._alerts[alert.id].last_triggered = now
                        self._alerts[alert.id].trigger_count += 1
                        self._save_alerts()
                logger.warning(
                    "成本告警触发: %s (scope=%s/%s, period=%s, actual=$%.4f > threshold=$%.4f)",
                    alert.name, alert.scope, alert.scope_id,
                    alert.period, bd.total_cost, alert.threshold_usd,
                )

    def _iter_records(self, limit: int = 10000):
        """迭代所有成本事件（从文件读）。"""
        if not os.path.exists(self._costs_path):
            return
        count = 0
        try:
            with open(self._costs_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    count += 1
                    if count >= limit:
                        break
        except Exception as e:  # noqa: BLE001
            logger.debug("读取成本事件失败: %s", e)

    def _load_alerts(self) -> None:
        if not os.path.exists(self._alerts_path):
            return
        try:
            with open(self._alerts_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for aid, ad in data.items():
                    self._alerts[aid] = CostAlert(**ad)
        except Exception as e:  # noqa: BLE001
            logger.debug("加载成本告警失败: %s", e)

    def _save_alerts(self) -> None:
        try:
            data = {aid: asdict(a) for aid, a in self._alerts.items()}
            with open(self._alerts_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:  # noqa: BLE001
            logger.debug("保存成本告警失败: %s", e)


# 单例
_tracker: Optional[CostTracker] = None
_tracker_lock = threading.Lock()


def get_cost_tracker() -> CostTracker:
    global _tracker
    if _tracker is not None:
        return _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = CostTracker()
    return _tracker


def reset_cost_tracker_for_test() -> None:
    """测试辅助：重置单例（仅在测试中调用）。"""
    global _tracker
    with _tracker_lock:
        _tracker = None
