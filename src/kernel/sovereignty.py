"""数据主权模块：一键完整导出用户的全部数据（出走检验的代码承接）。

宪法依据（AGENTS.md §0.0）：
    原则 1「本地优先·数据自持」/ 原则 4「主权归你·永不收割」
    §0.0.3 硬检验 2「出走检验」：用户能否一键完整导出全部数据
    （记忆 / trace / 模型配置），且导出物在别处可直接用？导不出即锁定。

设计铁律：
    1. **零网络**：全程本地文件操作，不上传、不遥测、不校验授权。
    2. **零依赖**：只用标准库，8G 内存旧机器也能跑（原则 7 技术普惠）。
    3. **通用格式**：JSON / JSONL / 原始文件原样拷贝，不用私有格式，
       导出物在没有 AOS 的机器上也能直接读——不可读就等于锁定。
    4. **默认脱敏**：API key 等凭据默认不导出（导出的是你的数据，不是你的密钥）；
       需要时显式 include_secrets=True。
    5. **绝不阻塞**：任一数据源缺失只记入清单的 missing，不抛错中断整体导出。

用法：
    from kernel.sovereignty import export_all
    manifest = export_all("D:/my_backup")     # 目录
    manifest = export_all("D:/my_backup.zip")  # 或 zip
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

EXPORT_FORMAT_VERSION = "1.0"

# 默认导出的数据源：(逻辑名, 仓库相对路径, 说明)
# 路径不存在不算错误，只记进 manifest["missing"]。
DEFAULT_SOURCES: List[tuple] = [
    ("memory", "data/memory", "长期记忆库（mem0 / chroma 落盘）"),
    ("distill", "data/workspaces/fabric", "白盒进化蒸馏记忆（引擎可靠性统计）"),
    ("value_ledger", "data/workspaces/value_ledger.jsonl",
     "本地价值账本（原则6 劳动有报：用户劳动产物归用户所有、可带走）"),
    ("soul", "data/soul/soul_id.txt",
     "灵魂 ID（原则10 灵魂唯一原语：跨设备稳定、可导出移植）"),
    ("soul_sync_state", "data/soul/sync_state.json",
     "灵魂同步状态（Lamport 版本序）。刻意**不含 device_id**："
     "换机后必须是新设备身份，否则两台机器同 ID 会互相覆盖同步包"),
    ("traces", "src/core/_traces", "执行 Trace（理念8 白盒才可进化的原始数据）"),
    ("workspaces", "data/workspaces", "工作区产物"),
    ("danchuang", "data/danchuang", "租户与用量数据"),
    ("evidence", "data/evidence", "证据链"),
    ("memory_notes", ".workbuddy/memory", "项目记忆笔记"),
]

# 凭据类文件：默认跳过（导出你的数据，不导出你的密钥）
SECRET_PATTERNS = (".env", ".secrets", "private.pem", "credentials", "token")


def _repo_root() -> Path:
    """仓库根目录（src/kernel/sovereignty.py -> 回溯 2 层）。"""
    return Path(__file__).resolve().parents[2]


def _is_secret(path: Path) -> bool:
    low = str(path).lower()
    return any(p in low for p in SECRET_PATTERNS)


def _copy_tree(src: Path, dst: Path, include_secrets: bool) -> Dict[str, Any]:
    """拷贝目录树，返回统计。跳过缓存与（默认）凭据文件。"""
    files = 0
    bytes_ = 0
    skipped_secrets = 0
    for root, dirs, names in os.walk(src):
        dirs[:] = [d for d in dirs
                   if d not in ("__pycache__", ".git", "node_modules")]
        for n in names:
            sp = Path(root) / n
            if not include_secrets and _is_secret(sp):
                skipped_secrets += 1
                continue
            rel = sp.relative_to(src)
            dp = dst / rel
            try:
                dp.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(sp, dp)
                files += 1
                bytes_ += sp.stat().st_size
            except Exception as e:  # noqa: BLE001 - 单文件失败不中断整体导出
                logger.warning("导出跳过 %s: %s", sp, e)
    return {"files": files, "bytes": bytes_,
            "skipped_secrets": skipped_secrets}


def export_all(dest: str,
               sources: Optional[List[tuple]] = None,
               include_secrets: bool = False,
               root: Optional[str] = None) -> Dict[str, Any]:
    """一键导出全部用户数据。

    Args:
        dest: 目标目录，或以 .zip 结尾的压缩包路径。
        sources: 自定义数据源列表 [(名称, 相对路径, 说明)]，默认 DEFAULT_SOURCES。
        include_secrets: 是否包含凭据类文件，默认 False（只导数据不导密钥）。
        root: 仓库根，默认自动推导。

    Returns:
        manifest 清单字典，同时以 MANIFEST.json 写进导出物根部——
        没有清单的备份等于黑箱，用户无法确认导全了没有。
    """
    base = Path(root) if root else _repo_root()
    srcs = sources if sources is not None else DEFAULT_SOURCES

    as_zip = str(dest).lower().endswith(".zip")
    out_dir = Path(str(dest)[:-4] + "_tmp") if as_zip else Path(dest)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "format_version": EXPORT_FORMAT_VERSION,
        "exported_at": time.time(),
        "exported_at_human": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_root": str(base),
        "include_secrets": include_secrets,
        "included": {},
        "missing": [],
        "total_files": 0,
        "total_bytes": 0,
        "readme": (
            "这是你的数据，完全属于你。全部为通用 JSON/JSONL/原始文件格式，"
            "不依赖 AOS 也能直接打开阅读。你可以随时带走、转移到任何地方，"
            "不需要任何授权、不需要联网、不需要付费。"
        ),
    }

    for name, rel, desc in srcs:
        sp = base / rel
        if not sp.exists():
            manifest["missing"].append({"name": name, "path": rel,
                                        "desc": desc})
            continue
        target = out_dir / name
        if sp.is_dir():
            stat = _copy_tree(sp, target, include_secrets)
        else:
            # 单文件源：在 name 子目录内保留原文件名（含扩展名），
            # 否则 value_ledger.jsonl 会变成无扩展名的 value_ledger，影响「无 AOS 也能直接读」。
            target = target / sp.name
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(sp, target)
                stat = {"files": 1, "bytes": sp.stat().st_size,
                        "skipped_secrets": 0}
            except Exception as e:  # noqa: BLE001
                manifest["missing"].append({"name": name, "path": rel,
                                            "error": repr(e)})
                continue
        stat["desc"] = desc
        stat["source"] = rel
        manifest["included"][name] = stat
        manifest["total_files"] += stat["files"]
        manifest["total_bytes"] += stat["bytes"]

    (out_dir / "MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if as_zip:
        zip_path = Path(dest)
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for r, _d, ns in os.walk(out_dir):
                for n in ns:
                    fp = Path(r) / n
                    zf.write(fp, fp.relative_to(out_dir))
        shutil.rmtree(out_dir, ignore_errors=True)
        manifest["archive"] = str(zip_path)
    else:
        manifest["directory"] = str(out_dir)

    logger.info("数据导出完成：%d 文件 / %d 字节 -> %s",
                manifest["total_files"], manifest["total_bytes"], dest)
    return manifest


def export_summary(root: Optional[str] = None) -> Dict[str, Any]:
    """只清点不拷贝：看看有哪些数据可以带走（导出前的预览）。"""
    base = Path(root) if root else _repo_root()
    out: Dict[str, Any] = {"available": [], "missing": []}
    for name, rel, desc in DEFAULT_SOURCES:
        sp = base / rel
        if not sp.exists():
            out["missing"].append(name)
            continue
        n = sum(1 for _ in sp.rglob("*") if _.is_file()) if sp.is_dir() else 1
        out["available"].append({"name": name, "path": rel,
                                 "desc": desc, "files": n})
    return out
