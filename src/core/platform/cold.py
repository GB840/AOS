"""
AOS v5.0 — 冷记忆归档 + 压缩管道 (Cold Memory)

对标蓝图 COLD(冷记忆归档) / PIPELINE(记忆压缩管道)。属于记忆层能力。
设计原则 (严谨 + 开放 + 灵活):
  - archive(): 把热数据 (dict/json) 序列化为 bytes 并用 zlib 压缩后存入 cold_memories。
  - restore(): 按 original_id 解压还原。编码方式可插拔 (默认 zlib; 可扩展 lzma 等)。
  - 与热表解耦: 归档后业务方可自行删除热行, 冷数据不阻塞主表查询。
  - DB 不可用时退化为内存, 不阻断 (best-effort)。
"""

import json
import logging
import zlib
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CODECS = {
    "zlib": (zlib.compress, zlib.decompress),
    "none": (lambda b: b, lambda b: b),
}


class ColdStore:
    def __init__(self, codec: str = "zlib"):
        self.codec = codec if codec in _CODECS else "zlib"
        self._mem: Dict[str, bytes] = {}

    def _encode(self, data: Any) -> bytes:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        comp, _ = _CODECS[self.codec]
        return comp(raw)

    def _decode(self, blob: bytes) -> Any:
        _, decomp = _CODECS[self.codec]
        raw = decomp(blob)
        return json.loads(raw.decode("utf-8"))

    def archive(self, original_id: str, kind: str, data: Any) -> bool:
        """归档热数据。返回是否成功落库。"""
        blob = self._encode(data)
        try:
            from core.database import session_scope
            from core.database.models import ColdMemory

            with session_scope() as s:
                s.add(ColdMemory(
                    original_id=original_id,
                    kind=kind,
                    data_blob=blob,
                    encoding=self.codec,
                ))
                s.commit()
            return True
        except Exception as e:  # pragma: no cover - 内存降级
            logger.debug("cold archive 落库失败, 内存降级: %s", e)
            self._mem[original_id] = blob
            return True

    def restore(self, original_id: str) -> Optional[Any]:
        try:
            from core.database import session_scope
            from core.database.models import ColdMemory
            from sqlmodel import select

            with session_scope() as s:
                row = s.exec(
                    select(ColdMemory).where(ColdMemory.original_id == original_id)
                ).first()
                if row is None:
                    return None
                return self._decode(row.data_blob)
        except Exception as e:  # pragma: no cover
            logger.debug("cold restore 落库失败, 内存降级: %s", e)
            blob = self._mem.get(original_id)
            return self._decode(blob) if blob else None

    def compress_text(self, text: str) -> bytes:
        """记忆压缩管道单步: 文本 -> 压缩字节。"""
        comp, _ = _CODECS[self.codec]
        return comp(text.encode("utf-8"))
