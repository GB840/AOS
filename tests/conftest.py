"""pytest conftest — ensures v5.0 Config won't crash during collection."""
import os
import sys
from pathlib import Path

# 将 src/ 加入 sys.path, 使 src 内部模块的非前缀 import
# (如 from utils.config import ...) 在测试环境中可用.
_src_dir = str(Path(__file__).resolve().parent.parent / "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Must run before ANY import touches utils/config.py
_fields = ["API_KEY_HASH", "ADMIN_USERNAME", "ADMIN_PASSWORD", "POSTGRES_PASSWORD", "AOS_TOKEN_SECRET"]
for f in _fields:
    os.environ.setdefault(f, "conftest-placeholder")

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass
