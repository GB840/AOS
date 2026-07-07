"""从 SQLModel metadata 内省生成 38 表 schema 文档 (docs/DATABASE_SCHEMA.md)。

设计要点:
  - 直接读取 `core.database.models.ALL_MODELS`，不手抄 schema，因此与代码永远一致、不会漂移。
  - 不需要真实数据库：仅解析 `SQLModel.metadata` 的表/列元数据。
  - 运行: `python scripts/gen_schema_doc.py` (需 sqlmodel + pydantic-settings)
"""
import os
import sys
import tempfile
from collections import OrderedDict

sys.path.insert(0, "src")

# 用临时库路径，避免触碰真实数据 (本脚本不会真正建库，仅保险)。
tmp = tempfile.mkdtemp()
from utils.config import config  # noqa: E402

config.SQLITE_DB_PATH = os.path.join(tmp, "aos.db")

from sqlmodel import SQLModel  # noqa: E402,F401

from core.database import models  # noqa: F401  (触发全部 38 表注册)
from core.database.models import ALL_MODELS  # noqa: E402

LAYER_NAMES = OrderedDict(
    [
        ("infra", "基础设施层 (infra)"),
        ("ecosystem", "生态层 (ecosystem)"),
        ("evolution", "进化层 (evolution)"),
        ("economy", "经济层 (economy)"),
        ("immune", "免疫层 (immune)"),
    ]
)


def layer_of(cls) -> str:
    # cls.__module__ 形如 core.database.models.infra
    return cls.__module__.split(".")[-1]


def type_str(col) -> str:
    try:
        return str(col.type)
    except Exception:  # pragma: no cover
        return "?"


def default_str(col) -> str:
    parts = []
    if col.default is not None:
        try:
            a = col.default.arg
            parts.append("default=factory" if callable(a) else f"default={a!r}")
        except Exception:
            parts.append("default=set")
    if col.server_default is not None:
        try:
            parts.append(f"server_default={_sd_repr(col.server_default)}")
        except Exception:
            parts.append("server_default=set")
    return "; ".join(parts)


def _sd_repr(sd) -> str:
    """把 server_default 渲染成可读 SQL (避免 <TextClause object> 之类)。"""
    from sqlalchemy.sql.elements import TextClause, True_ as SQLTrue, False_ as SQLFalse
    from sqlalchemy.sql.functions import FunctionElement

    a = sd.arg
    if isinstance(a, TextClause):
        return a.text
    if isinstance(a, SQLTrue):
        return "TRUE"
    if isinstance(a, SQLFalse):
        return "FALSE"
    if isinstance(a, FunctionElement):
        return str(a)
    return repr(a)


def fk_str(col) -> str:
    if not col.foreign_keys:
        return ""
    return ", ".join(f"{fk.column.table.name}.{fk.column.name}" for fk in col.foreign_keys)


def main() -> None:
    lines = []
    lines.append("# AOS v5.0 数据库 Schema（38 张表 · 单一真相层）")
    lines.append("")
    lines.append(
        "> 本文件由 `scripts/gen_schema_doc.py` 从 "
        "`src/core/database/models/*.py` 的 SQLModel 定义**自动内省**生成，"
        "与代码严格一致，修改模型后重跑脚本即可更新，不会漂移。"
    )
    lines.append("")
    lines.append(
        "AOS 全部结构化状态存于**单一 SQLite 数据库**"
        "（`config.SQLITE_DB_PATH`，WAL 模式，并开启外键约束），"
        "是系统唯一真相来源。全文检索（FTS5）由 `memory` 层的虚拟表提供，"
        "不计入下方 38 张 ORM 表。"
    )
    lines.append("")
    lines.append(f"**表总数：{models.TABLE_COUNT}**")
    lines.append("")
    lines.append("分层与 `README` 的架构叙事一致：")
    for k, v in LAY_NAME_ITEMS():
        lines.append(f"- **{v}**")
    lines.append("")

    groups: "OrderedDict[str, list]" = OrderedDict()
    for cls in ALL_MODELS:
        groups.setdefault(layer_of(cls), []).append(cls)

    for g, clss in groups.items():
        title = LAYER_NAMES.get(g, g)
        lines.append(f"## {title}")
        lines.append("")
        for cls in clss:
            table = cls.__table__
            lines.append(f"### `{table.name}` — `{cls.__name__}`")
            lines.append("")
            lines.append("| 列 | 类型 | 可空 | 主键 | 外键 | 默认 |")
            lines.append("|---|---|---|---|---|---|")
            for col in table.columns:
                lines.append(
                    f"| {col.name} | {type_str(col)} | "
                    f"{'Y' if col.nullable else 'N'} | "
                    f"{'Y' if col.primary_key else ''} | "
                    f"{fk_str(col)} | {default_str(col)} |"
                )
            lines.append("")

    out = os.path.join("docs", "DATABASE_SCHEMA.md")
    os.makedirs("docs", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Wrote {out}  (tables={models.TABLE_COUNT}, models={len(ALL_MODELS)})")


def LAY_NAME_ITEMS():
    return list(LAYER_NAMES.items())


if __name__ == "__main__":
    main()
