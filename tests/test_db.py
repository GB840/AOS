import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path('.').resolve()))

from src.utils.config import config
import os
import sqlite3

db_path = config.SQLITE_DB_PATH
print('db_path:', db_path)

print('Step 0: Calling Path.mkdir like memory.py does...')
Path(os.path.dirname(db_path)).mkdir(parents=True, exist_ok=True)
print('mkdir done')

print('Step 1: Trying sqlite3.connect...')
conn = sqlite3.connect(db_path, check_same_thread=False)
print('Connected!')

print('Step 2: PRAGMA journal_mode=WAL...')
conn.execute("PRAGMA journal_mode=WAL")
print('journal_mode=WAL set!')

print('Step 3: PRAGMA foreign_keys=ON...')
conn.execute("PRAGMA foreign_keys=ON")
print('foreign_keys=ON set!')

conn.close()
print('All OK!')
