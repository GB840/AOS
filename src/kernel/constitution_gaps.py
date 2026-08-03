"""母纲能力真实度追踪（原则 7 方言平等 / 原则 10 灵魂唯一）。

诚实纪律（理念 9 可验证即真理）：没有的能力绝不谎称有，有的能力也不含糊其辞。
本模块是这两条原则的**唯一真值口径**：随时能查「现在到底真支持几样」，
并设闸门防止任何人虚假宣称。

原则 7 方言平等（目标 22 种中文方言）
    能力层已真落地于 `kernel.dialect_asr`：真实能力矩阵 + 引擎就绪真探测 +
    按方言真分派 + 缺失时给可照敲的落地命令。
    本模块的 `supported_dialects()` 直接委托它，返回**此刻真能识别**的方言：
    引擎没装 / 模型没下 → 一个都不算。所以这个数字会随机器状态变化，
    这正是「可验证」的含义，不是写死的 22/22 也不是写死的 0。

原则 10 灵魂唯一（跨设备同一灵魂）
    协议层已真落地于 `kernel.soul_sync`：标准 .aospkg 包 + 落盘加密（复用
    utils.keystore Fernet）+ 可插拔传输（本地目录/U 盘零联网默认，WebDAV 选配）
    + Lamport 版本 + 冲突不丢数据 + 新设备 adopt 认领同一灵魂。
    `soul_identity()["sync_protocol"]` 现在回报**真实协议名**，
    不再是 NOT_IMPLEMENTED；但若模块导入失败仍如实回落到 NOT_IMPLEMENTED。
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Dict, List

# 22 种中文方言（母纲原则 7 的「目标清单」，非「已支持清单」）。
# 依据《中国语言地图集》主要方言区及分支枚举。
DIALECT_TARGETS: List[str] = [
    "官话-东北", "官话-北京", "官话-中原", "官话-兰银",
    "官话-西南", "官话-江淮", "晋语", "吴语-太湖(上海话)",
    "吴语-温州", "吴语-台州", "徽语", "赣语",
    "湘语-长益", "湘语-娄邵", "闽语-闽北", "闽语-闽东(福州话)",
    "闽语-闽南(厦门/台语)", "闽语-莆仙", "客家话", "粤语",
    "平话", "儋州话",
]


# ===========================================================================
# 原则 7：委托给真能力层 kernel.dialect_asr
# ===========================================================================

def supported_dialects() -> List[str]:
    """**此刻真能识别**的方言列表（不是矩阵上写了的）。

    委托 `kernel.dialect_asr.supported_dialects()`：只统计**引擎已装且模型已在本地**
    的覆盖并集。模块导入失败 → 返回空列表（宁可少报，绝不多报）。
    """
    try:
        from kernel.dialect_asr import supported_dialects as _real
    except Exception:
        return []
    try:
        return [d for d in _real() if d in DIALECT_TARGETS]
    except Exception:
        return []


def dialect_coverage() -> Dict[str, bool]:
    sup = set(supported_dialects())
    return {d: (d in sup) for d in DIALECT_TARGETS}


def dialect_summary() -> Dict[str, object]:
    """方言能力快照。

    字段含义（三层，别混）：
        targets           宪法目标方言数（22，固定）
        supported         **此刻真能识别**的数量（随机器状态变化）
        missing           还没能识别的数量
        declared_covered  已核实开源引擎**官方声明**能覆盖的数量（装上就能用）
        no_engine         全世界暂无已核实引擎声明支持的（真缺口，不脑补）
        ready_engines     此刻真就绪的引擎名
        capability_layer  能力层是否已落地（True=有真路由代码，非占位）
    """
    cov = dialect_coverage()
    out: Dict[str, object] = {
        "targets": len(DIALECT_TARGETS),
        "supported": sum(1 for v in cov.values() if v),
        "missing": sum(1 for v in cov.values() if not v),
        "capability_layer": False,
        "declared_covered": 0,
        "no_engine": len(DIALECT_TARGETS),
        "ready_engines": [],
    }
    try:
        from kernel import dialect_asr

        rep = dialect_asr.coverage_report()
        out["capability_layer"] = True
        out["declared_covered"] = rep.get("declared_covered", 0)
        out["no_engine"] = len(rep.get("missing_no_engine", []))
        out["ready_engines"] = rep.get("ready_engines", [])
    except Exception:
        pass
    return out


def dialect_install_plan(dialect: str) -> Dict[str, object]:
    """某方言暂不可用时的**照敲落地命令**（原则 7 的态度：不撂一句「不支持」）。"""
    try:
        from kernel.dialect_asr import install_plan
    except Exception:
        return {"dialect": dialect, "known_target": dialect in DIALECT_TARGETS,
                "error": "能力层 kernel.dialect_asr 不可用"}
    return install_plan(dialect)


# ===========================================================================
# 原则 10 灵魂唯一：本地稳定灵魂 ID 原语
# ===========================================================================

def _soul_file() -> Path:
    env = os.environ.get("AOS_SOUL_ID_PATH")
    if env:
        return Path(env)
    try:
        root = Path(__file__).resolve().parents[2]  # src/kernel/constitution_gaps.py -> 回溯2层
    except Exception:
        root = Path(os.getcwd())
    return root / "data" / "soul" / "soul_id.txt"


def get_or_create_soul_id() -> str:
    """返回跨设备稳定的灵魂 ID：本地生成、持久化、可随导出带走（灵魂唯一原语）。"""
    p = _soul_file()
    if p.exists():
        try:
            sid = p.read_text(encoding="utf-8").strip()
            if sid:
                return sid
        except Exception:
            pass
    sid = uuid.uuid4().hex
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(sid, encoding="utf-8")
    except Exception:
        pass
    return sid


def soul_identity() -> Dict[str, object]:
    """灵魂身份快照。

        soul_id           跨设备稳定的灵魂标识
        portable          可经 sovereignty.export_all 整体带走
        sync_protocol     真实同步协议名（"local_dir" / "webdav" / ...）；
                          能力层缺失才回落 "NOT_IMPLEMENTED"
        transports        当前可用传输方式
        requires_network  默认路径是否需要联网（False = 断网检验通过）
        encrypted_at_rest 同步包落盘是否加密
    """
    out: Dict[str, object] = {
        "soul_id": get_or_create_soul_id(),
        "portable": True,
        "sync_protocol": "NOT_IMPLEMENTED",
        "transports": [],
        "requires_network": False,
        "encrypted_at_rest": False,
    }
    try:
        from kernel import soul_sync

        out["sync_protocol"] = soul_sync.protocol_name()
        out["transports"] = soul_sync.available_transports()
        out["requires_network"] = soul_sync.default_requires_network()
        out["encrypted_at_rest"] = soul_sync.encryption_available()
    except Exception:
        pass
    return out
