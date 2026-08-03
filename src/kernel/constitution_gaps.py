"""母纲缺口诚实追踪（原则 7 方言平等 / 原则 10 灵魂唯一）。

诚实纪律（理念 9 可验证即真理）：没有的能力绝不谎称有。
本模块把「尚未真实落地」的能力变成 **可检测的诚实缺口**——
随时能查「现在到底支持几样」，并设闸门防止任何人虚假宣称已支持。

原则 7 方言平等：目标 22 种中文方言。当前真实支持 = 0
（Vosk 仅普通话 / 英语，方言模型未下载也未集成）。追踪器如实回报，
不写假 22/22。要真落地需引入各地方言 ASR 模型并接线，属未来工程。

原则 10 灵魂唯一：跨设备同一灵魂。当前真实支持 = 灵魂 ID 原语
（本地稳定、可随导出带走），但 **实时跨设备同步协议未做**。
原语已就位，整协议为缺口——任何「已支持多设备同步」的宣称都是假的，
由本模块的 soul_identity()["sync_protocol"] == "NOT_IMPLEMENTED" 揭穿。
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


def supported_dialects() -> List[str]:
    """真实支持列表（当前为空；普通话/英语不算方言，方言模型未集成）。

    未来接入：从 Vosk 模型目录 / 配置读取真实加载的方言模型名返回。
    """
    return []


def dialect_coverage() -> Dict[str, bool]:
    sup = set(supported_dialects())
    return {d: (d in sup) for d in DIALECT_TARGETS}


def dialect_summary() -> Dict[str, int]:
    cov = dialect_coverage()
    return {
        "targets": len(DIALECT_TARGETS),
        "supported": sum(1 for v in cov.values() if v),
        "missing": sum(1 for v in cov.values() if not v),
    }


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


def soul_identity() -> Dict[str, str]:
    """灵魂身份快照。portable=True 表示可经 sovereignty.export_all 带走；
    sync_protocol=NOT_IMPLEMENTED 诚实声明：实时跨设备同步协议未做。"""
    return {
        "soul_id": get_or_create_soul_id(),
        "portable": True,
        "sync_protocol": "NOT_IMPLEMENTED",
    }
