"""财务核算芯粒（OPC 财务岗位工具缺口补位）。

用户铁律：没有的用最新开源技术。本芯粒用开源 openpyxl 生成 xlsx 财务报表；
openpyxl 不可用时自动降级 CSV（零付费依赖、零闭源依赖）。

能力标签：finance.report（已被 opc_roles.finance 引用）。
"""
from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Optional

try:
    from openpyxl import Workbook
    _HAS_OPENPYXL = True
except Exception:
    _HAS_OPENPYXL = False


def bom_cost(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """BOM 成本汇总。items: [{name, unit_price, qty}] -> {total, items}。

    例：bom_cost([{"name":"RK3566","unit_price":45,"qty":1},
                  {"name":"摄像头","unit_price":12,"qty":2}])
        -> {"total": 69.0, "items": [...]}
    """
    total = sum(float(i.get("unit_price", 0)) * float(i.get("qty", 0)) for i in items)
    return {"total": round(total, 2), "items": items, "engine": "openpyxl" if _HAS_OPENPYXL else "csv"}


def generate_report(records: List[Dict[str, Any]], fmt: str = "xlsx",
                    path: Optional[str] = None) -> Dict[str, Any]:
    """生成财务收支报表。

    fmt="xlsx" 且 openpyxl 可用 -> xlsx；否则降级 csv。
    返回 {ok, engine, path?/content?}。
    """
    if not records:
        return {"ok": False, "error": "empty records", "engine": "none"}

    if fmt == "xlsx" and _HAS_OPENPYXL:
        wb = Workbook()
        ws = wb.active
        ws.title = "财务收支"
        cols = list(records[0].keys())
        ws.append(cols)
        for r in records:
            ws.append([r.get(c, "") for c in cols])
        if path:
            wb.save(path)
            return {"ok": True, "path": path, "engine": "openpyxl"}
        buf = io.BytesIO()
        wb.save(buf)
        return {"ok": True, "content": buf.getvalue(), "engine": "openpyxl"}

    # CSV 降级
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(records[0].keys()))
    w.writeheader()
    for r in records:
        w.writerow(r)
    csv_text = buf.getvalue()
    if path:
        with open(path, "w", newline="", encoding="utf-8") as f:
            f.write(csv_text)
        return {"ok": True, "path": path, "engine": "csv"}
    return {"ok": True, "content": csv_text, "engine": "csv"}


def profit_estimate(revenue: float, cost: float) -> Dict[str, Any]:
    """利润预估。"""
    profit = round(float(revenue) - float(cost), 2)
    margin = round((profit / float(revenue)) * 100, 2) if revenue else 0.0
    return {"revenue": revenue, "cost": cost, "profit": profit, "margin_pct": margin}
