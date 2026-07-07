"""
AOS v5.0 — 文件处理 (File Processing)

对标蓝图 FILE(文本/PDF/OCR)。满足蓝图节点: FILE。
设计原则 (严谨 + 开放 + 灵活):
  - 文本类 (.txt/.md/.json/.csv/.py 等) 用标准库, 零依赖。
  - PDF / OCR 为可选能力: 探测到 pdfplumber/PyPDF2/pytesseract 才启用, 否则返回清晰的
    "能力未安装" 信息, 绝不假装成功。
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TEXT_EXTS = {".txt", ".md", ".markdown", ".json", ".csv", ".py", ".js", ".ts",
              ".yaml", ".yml", ".toml", ".html", ".xml", ".log", ".rst"}
_PDF_EXTS = {".pdf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


def extract_text(path_or_bytes: Any, mime: Optional[str] = None) -> Dict[str, Any]:
    """从文件/字节抽取文本。统一返回 {ok, text/error, engine}。

    纯文本走标准库; PDF/OCR 在依赖可用时启用, 否则明确报错 (开放: 可随时装依赖启用)。
    """
    data: Optional[bytes] = None
    ext = ""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        data = bytes(path_or_bytes)
    elif isinstance(path_or_bytes, str):
        ext = os.path.splitext(path_or_bytes)[1].lower()
        try:
            with open(path_or_bytes, "rb") as f:
                data = f.read()
        except Exception as e:
            return {"ok": False, "error": f"read failed: {e}"}
    else:
        return {"ok": False, "error": "unsupported input type"}

    if ext in _TEXT_EXTS or (mime and mime.startswith("text")):
        try:
            return {"ok": True, "text": data.decode("utf-8", errors="replace"), "engine": "stdlib"}
        except Exception as e:
            return {"ok": False, "error": f"decode failed: {e}"}

    if ext in _PDF_EXTS or mime == "application/pdf":
        return _extract_pdf(data)

    if ext in _IMAGE_EXTS or (mime and mime.startswith("image/")):
        return _ocr(data)

    return {"ok": False, "error": f"unsupported type: ext={ext or None}, mime={mime}"}


def _extract_pdf(data: bytes) -> Dict[str, Any]:
    try:
        import pdfplumber  # type: ignore
        import io
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        return {"ok": True, "text": text, "engine": "pdfplumber"}
    except Exception:
        pass
    try:
        import PyPDF2  # type: ignore
        import io
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return {"ok": True, "text": text, "engine": "PyPDF2"}
    except Exception as e:
        return {"ok": False, "error": f"PDF 依赖未安装 (需 pdfplumber 或 PyPDF2): {e}"}


def _ocr(data: bytes) -> Dict[str, Any]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image  # type: ignore
        import io
        img = Image.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img)
        return {"ok": True, "text": text, "engine": "pytesseract"}
    except Exception as e:
        return {"ok": False, "error": f"OCR 依赖未安装 (需 pytesseract + Pillow): {e}"}
