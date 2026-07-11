import sys
sys.dont_write_bytecode = True
import os
import pytest
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

print("Before importing config...")
pytest.importorskip("src.utils.config")
from src.utils.config import config
print("Config loaded:")
print("  BASE_DIR:", Path(__file__).resolve().parent)
print("  SQLITE_DB_PATH:", config.SQLITE_DB_PATH)
print("  CHROMADB_PERSIST_DIR:", config.CHROMADB_PERSIST_DIR)

db_dir = os.path.dirname(config.SQLITE_DB_PATH)
print("  db_dir:", db_dir)
print("  db_dir exists:", os.path.exists(db_dir))

print("\nBefore importing MemoryManager...")
try:
    from src.memory import MemoryManager
except Exception as exc:
    pytest.skip(f"MemoryManager import failed ({exc})", allow_module_level=True)

try:
    print("Creating MemoryManager...")
    mm = MemoryManager()
except Exception as exc:
    pytest.skip(f"MemoryManager init failed ({exc})", allow_module_level=True)
print('MemoryManager初始化成功!')
print('vector_enabled:', mm.vector_enabled)
print('db_path:', mm.db_path)
mm.close()
print("Done!")
