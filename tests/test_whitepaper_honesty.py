"""
白皮书诚实地图一致性校验（② 级：代码+可跑，无需 LLM）。

防止「架构图标注重构滞后 / 标注与统计不一致」这类问题复发：
- mermaid 架构图的每个节点标注（✅/🔁/🔗）必须与诚实地图表格一致；
- 诚实地图表格的 ✅/🔁/🔗 计数必须与底部「诚实统计」表一致；
- 总数为 61 节点。

用户铁律：凡贴标签必须逐个调研吃透；本测试把「文档内部自洽」钉死，
任何后续编辑若改了标注却忘改统计 / 表格，CI 直接红。
"""

import re
import os

WHITEPAPER = os.path.join(
    os.path.dirname(__file__), "..", "docs", "LIFEFORM_OS_WHITEPAPER_V6.md"
)

EXPECTED_TOTAL = 61
EXPECTED = {"✅": 46, "🔁": 4, "🔗": 11}


def _read():
    with open(os.path.abspath(WHITEPAPER), encoding="utf-8") as f:
        return f.read()


def _parse_mermaid_labels(text):
    """返回 {node_id: marker} 从 mermaid 节点 `L1C["... [🔗纯参考]..."]`。"""
    out = {}
    # 匹配行内 `Lxx[` / `L1E2[` / `CONSTx[`（允许尾部数字后缀）
    for m in re.finditer(r"(L[0-9][A-Z0-9]*|CONST[0-9])\s*\[", text):
        nid = m.group(1)
        # 取该 `[` 到对应 `]` 的内容里的第一个标注
        start = m.end() - 1
        depth = 0
        i = start
        while i < len(text):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        seg = text[start + 1 : i]
        mm = re.search(r"\[(🔁|🔗|✅)([^\]]*)\]", seg)
        if mm:
            out[nid] = mm.group(1)
    return out


def _parse_table_labels(text):
    """返回 {node_id: marker} 从诚实地图表格 `| L1C ... | L1 | 🔗纯参考 | ... |`。"""
    out = {}
    for line in text.splitlines():
        # 允许节点名被 ** 加粗（前版纠正的 3 个空壳节点高亮）与尾部数字后缀
        m = re.match(r"\|\s*\**\s*(L[0-9][A-Z0-9]*|CONST[0-9])\b", line)
        if not m:
            continue
        nid = m.group(1)
        cells = [c.strip() for c in line.split("|")]
        # cells[0]='' ; cells[1]=node ; cells[2]=layer ; cells[3]=status ; ...
        if len(cells) < 4:
            continue
        status = cells[3]
        mm = re.search(r"(🔁|🔗|✅)", status)
        if mm:
            out[nid] = mm.group(1)
    return out


def _parse_stats(text):
    """返回 {'✅':int,'🔁':int,'🔗':int} 从底部统计表 `| ✅ ... | **46** | ... |`"""
    counts = {}
    for marker in ("✅", "🔁", "🔗"):
        # 统计行形如：| ✅ AOS 已有真实代码 | **46** | 78.0% | ... |
        m = re.search(
            r"\|\s*" + re.escape(marker) + r".*?\|\s*\*\*(\d+)\*\*", text
        )
        assert m, f"统计表中未找到标记 {marker} 的计数行"
        counts[marker] = int(m.group(1))
    return counts


def test_mermaid_matches_table():
    text = _read()
    mer = _parse_mermaid_labels(text)
    tbl = _parse_table_labels(text)
    assert mer, "mermaid 未解析到任何节点标注"
    assert tbl, "诚实地图表格未解析到任何节点标注"
    # 节点集合应一致（忽略 mermaid 可能多/少）
    only_mer = set(mer) - set(tbl)
    only_tbl = set(tbl) - set(mer)
    assert not only_mer, f"mermaid 有但表格无: {sorted(only_mer)}"
    assert not only_tbl, f"表格有但 mermaid 无: {sorted(only_tbl)}"
    # 每个节点的标注必须一致
    mismatch = {n: (mer[n], tbl[n]) for n in mer if mer[n] != tbl[n]}
    assert not mismatch, f"标注不一致: {mismatch}"


def test_stats_consistency():
    text = _read()
    tbl = _parse_table_labels(text)
    stats = _parse_stats(text)
    # 表格计数
    from collections import Counter

    cnt = Counter(tbl.values())
    assert cnt["✅"] == stats["✅"], f"表格✅={cnt['✅']} 统计={stats['✅']}"
    assert cnt["🔁"] == stats["🔁"], f"表格🔁={cnt['🔁']} 统计={stats['🔁']}"
    assert cnt["🔗"] == stats["🔗"], f"表格🔗={cnt['🔗']} 统计={stats['🔗']}"
    assert sum(cnt.values()) == EXPECTED_TOTAL, f"节点总数 {sum(cnt.values())} != {EXPECTED_TOTAL}"
    assert stats == EXPECTED, f"统计与预期 {EXPECTED} 不符: {stats}"


def test_no_phantom_nodes():
    """L3C 等「外部未接」节点不得谎称已接（标记必须非 ✅AOS已接开源）。"""
    text = _read()
    tbl = _parse_table_labels(text)
    # L3C 历史上曾被误标 ✅AOS已接开源；此处钉死它只能是 🔁
    assert tbl.get("L3C") == "🔁", f"L3C 必须为 🔁 外部未接，实际 {tbl.get('L3C')}"
    # L1E Fish Speech 必须非 ✅（模型 NC 禁商用）
    assert tbl.get("L1E") == "🔗", f"L1E 必须为 🔗 纯参考，实际 {tbl.get('L1E')}"
    # L9B openKylin / L9C openEuler / L9D OpenHarmony 国产 OS 生态参考，仍属 🔗 大类
    # （已升级为「🔗已借鉴优化」，解析只取首个 emoji 故仍为 🔗，详见 test_native_os_borrowed）
    assert tbl.get("L9B") == "🔗", f"L9B 必须属 🔗 大类，实际 {tbl.get('L9B')}"
    assert tbl.get("L9C") == "🔗", f"L9C 必须属 🔗 大类，实际 {tbl.get('L9C')}"
    assert tbl.get("L9D") == "🔗", f"L9D 必须属 🔗 大类，实际 {tbl.get('L9D')}"


def test_native_os_borrowed():
    """L9B/L9C/L9D 国产 OS 生态必须标注『已借鉴优化』（融合对齐，非纯参考）。"""
    text = _read()
    # 1) 表格状态列须含「已借鉴优化」
    for nid in ("L9B", "L9C", "L9D"):
        line = next((ln for ln in text.splitlines()
                     if re.match(rf"\|\s*\**\s*{nid}\b", ln)), None)
        assert line is not None, f"找不到表格行 {nid}"
        assert "已借鉴优化" in line, f"{nid} 表格行须含『已借鉴优化』，实际：{line}"
    # 2) mermaid 节点标注须含「已借鉴优化」
    mermaid_block = re.search(r"```mermaid(.*?)```", text, re.S)
    assert mermaid_block, "找不到 mermaid 代码块"
    mb = mermaid_block.group(1)
    for nid in ("L9B", "L9C", "L9D"):
        assert re.search(rf"{nid}\[[^\]]*已借鉴优化", mb), f"{nid} mermaid 须含『已借鉴优化』"
    # 3) 借鉴对齐小节必须存在
    assert "国产开源 OS 生态借鉴对齐" in text, "白皮书须含『国产开源 OS 生态借鉴对齐』小节"
    # 4) 两个原型文件须存在（② 级轻量骨架）
    import os as _os
    for p in ("src/core/fabric/chiplet_sandbox.py",
              "src/core/fabric/intent_skill_router.py"):
        assert _os.path.exists(_os.path.join(_os.path.dirname(__file__), "..", p)), \
            f"借鉴原型文件缺失：{p}"
