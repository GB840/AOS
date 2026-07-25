#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AOS 共享记忆 MCP 服务器（多 Agent 共享外脑）

这是一个本地优先（local-first）、零外部依赖（仅标准库 + 官方 mcp SDK）的
MCP 服务器，把"记忆"集中存进一个 SQLite 文件，任何接入了本服务器的 MCP
客户端（WorkBuddy / Claude Code / CherryStudio / 其它智能体）都能读/写同一份
记忆 —— 这就是"多 Agent 共享外脑"。

能力（MCP tools）：
  - store_memory    存入 / 更新一条记忆
  - get_memory     按 namespace + key 取回一条记忆
  - search_memory  全文检索（FTS5，缺则降级 LIKE）
  - list_namespaces 列出所有命名空间
  - list_keys      列出某命名空间下的所有 key
  - delete_memory  删除一条记忆

传输：stdio（MCP 客户端以子进程方式拉起，command=python args=[本文件]）。
注意：stdio 模式下严禁向 stdout 写任何东西（会破坏 JSON-RPC），日志一律走 stderr。
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

# ── 存储层（本地 SQLite，多 Agent 共享同一文件）──────────────────────────
DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".aos", "shared_memory.db")
DB_PATH = os.environ.get("AOS_SHARED_MEMORY_DB") or DEFAULT_DB

mcp = FastMCP("aos-shared-memory")

# 模块级全局：当前 SQLite 是否支持 FTS5（初始化时探测一次）。
_FTS = False


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _fts_available(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(t, tokenize='trigram')")
        conn.execute("DROP TABLE _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def init_db() -> sqlite3.Connection:
    conn = _connect()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            namespace TEXT NOT NULL,
            key        TEXT NOT NULL,
            value      TEXT NOT NULL,
            tags       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            search_text TEXT NOT NULL DEFAULT '',
            UNIQUE (namespace, key)
        )
        """
    )
    conn.commit()
    global _FTS
    _FTS = _fts_available(conn)
    if _FTS:
        conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
            USING fts5(mem_id UNINDEXED, search_text, tokenize='trigram')
            """
        )
        conn.commit()
    return conn


_CONN = init_db()
print(f"[aos-shared-memory] DB={DB_PATH} fts5={'on' if _FTS else 'off'}", file=sys.stderr)


# ── 工具实现 ────────────────────────────────────────────────────────────
@mcp.tool()
def store_memory(namespace: str, key: str, value: str, tags: str = "") -> str:
    """存入或更新一条记忆。

    Args:
        namespace: 命名空间（如 agent 名 / 项目名 / 主题），用于隔离不同来源的记忆。
        key: 记忆的唯一键（同一 namespace 下不可重复，重复则覆盖更新）。
        value: 记忆内容（任意文本，如结论、偏好、决策、观测）。
        tags: 可选标签，逗号分隔，便于检索（如 "偏好,中文,财务"）。
    """
    namespace = (namespace or "").strip() or "default"
    key = (key or "").strip()
    if not key:
        return "错误：key 不能为空。"
    value = value or ""
    tags = tags or ""
    now = _now()
    search_text = f"{key} {tags} {value}"
    conn = _CONN
    cur = conn.execute(
        """
        INSERT INTO memories (namespace, key, value, tags, created_at, updated_at, search_text)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (namespace, key) DO UPDATE SET
            value=excluded.value, tags=excluded.tags,
            updated_at=excluded.updated_at, search_text=excluded.search_text
        """,
        (namespace, key, value, tags, now, now, search_text),
    )
    row_id = cur.lastrowid
    if _FTS:
        conn.execute("DELETE FROM memories_fts WHERE mem_id=?", (row_id,))
        conn.execute("INSERT INTO memories_fts (mem_id, search_text) VALUES (?, ?)", (row_id, search_text))
    conn.commit()
    return f"已存储：[{namespace}] {key}（tags={tags or '无'}）"


@mcp.tool()
def get_memory(namespace: str, key: str) -> str:
    """按命名空间 + 键取回一条记忆的内容。

    Args:
        namespace: 命名空间。
        key: 记忆的键。
    """
    namespace = (namespace or "").strip() or "default"
    key = (key or "").strip()
    row = _CONN.execute(
        "SELECT value, tags, updated_at FROM memories WHERE namespace=? AND key=?",
        (namespace, key),
    ).fetchone()
    if not row:
        return f"未找到：[{namespace}] {key}"
    value, tags, updated = row
    tag_line = f"  tags: {tags}\n" if tags else ""
    return f"[{namespace}] {key}\n  updated: {updated}\n{tag_line}  value: {value}"


@mcp.tool()
def search_memory(query: str, namespace: str = "", top_k: int = 5) -> str:
    """在共享记忆中全文检索（所有 Agent 可见的同一份记忆）。

    Args:
        query: 检索词（支持多关键词，FTS5 下自动分词匹配）。
        namespace: 可选，限定只搜某个命名空间；留空则搜全部。
        top_k: 返回条数上限，默认 5。
    """
    query = (query or "").strip()
    if not query:
        return "错误：query 不能为空。"
    top_k = max(1, min(int(top_k or 5), 50))
    conn = _CONN
    rows = []
    if _FTS:
        # trigram 按子串匹配，对中文/CJK 友好；直接传原串即可。
        mem_ids = [
            r[0] for r in conn.execute(
                "SELECT mem_id FROM memories_fts WHERE memories_fts MATCH ? ORDER BY rank LIMIT ?",
                (query, top_k),
            ).fetchall()
        ]
        if mem_ids:
            placeholders = ",".join("?" * len(mem_ids))
            nsql = (
                f"SELECT namespace, key, value, tags, updated_at "
                f"FROM memories WHERE id IN ({placeholders})"
            )
            nparams = list(mem_ids)
            if namespace.strip():
                nsql += " AND namespace=?"
                nparams.append(namespace.strip())
            rows = conn.execute(nsql, nparams).fetchall()
    if not rows:  # FTS 未命中 / 不可用时退回 LIKE（中文子串兜底，绝不漏）
        like = f"%{query}%"
        sql = (
            "SELECT namespace, key, value, tags, updated_at FROM memories WHERE search_text LIKE ?"
        )
        params = [like]
        if namespace.strip():
            sql += " AND namespace=?"
            params.append(namespace.strip())
        sql += " LIMIT ?"
        params.append(top_k)
        rows = conn.execute(sql, params).fetchall()

    if not rows:
        return f"未检索到匹配「{query}」的记忆。"
    out = [f"检索「{query}」命中 {len(rows)} 条："]
    for ns, k, v, tg, up in rows:
        snippet = v if len(v) <= 200 else v[:200] + "…"
        out.append(f"- [{ns}] {k} (updated {up}){(' tags=' + tg) if tg else ''}\n  {snippet}")
    return "\n".join(out)


@mcp.tool()
def list_namespaces() -> str:
    """列出所有已使用的命名空间（即哪些 Agent / 项目写过记忆）。"""
    rows = _CONN.execute(
        "SELECT namespace, COUNT(*) FROM memories GROUP BY namespace ORDER BY namespace"
    ).fetchall()
    if not rows:
        return "当前没有任何记忆。"
    return "命名空间：\n" + "\n".join(f"- {ns} ({cnt} 条)" for ns, cnt in rows)


@mcp.tool()
def list_keys(namespace: str) -> str:
    """列出某个命名空间下的所有记忆键。

    Args:
        namespace: 命名空间。
    """
    namespace = (namespace or "").strip() or "default"
    rows = _CONN.execute(
        "SELECT key, updated_at FROM memories WHERE namespace=? ORDER BY updated_at DESC",
        (namespace,),
    ).fetchall()
    if not rows:
        return f"命名空间 [{namespace}] 下没有任何记忆。"
    return f"[{namespace}] 下的记忆键（{len(rows)}）：\n" + "\n".join(
        f"- {k} (updated {up})" for k, up in rows
    )


@mcp.tool()
def delete_memory(namespace: str, key: str) -> str:
    """删除一条记忆。

    Args:
        namespace: 命名空间。
        key: 记忆的键。
    """
    namespace = (namespace or "").strip() or "default"
    key = (key or "").strip()
    conn = _CONN
    row = conn.execute(
        "SELECT id FROM memories WHERE namespace=? AND key=?", (namespace, key)
    ).fetchone()
    if not row:
        return f"未找到：[{namespace}] {key}"
    rid = row[0]
    conn.execute("DELETE FROM memories WHERE id=?", (rid,))
    if _FTS:
        conn.execute("DELETE FROM memories_fts WHERE mem_id=?", (rid,))
    conn.commit()
    return f"已删除：[{namespace}] {key}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
