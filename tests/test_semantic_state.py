"""共享记忆文件锁并发读写测试。"""
from __future__ import annotations
import sys
sys.path.insert(0, "D:/AOS/src")
import pytest
import threading
import time
import json
import tempfile
import os


def test_semantic_lock_prevents_concurrent_writes():
    from kernel.semantic_state import SEMANTIC_LOCK

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
        temp_path = f.name

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write('{"test": "initial"}\n')

        write_count = 0
        errors = []

        def worker(worker_id):
            nonlocal write_count, errors
            for i in range(100):
                record = {"worker": worker_id, "iter": i, "ts": time.time()}
                try:
                    with SEMANTIC_LOCK:
                        with open(temp_path, "r", encoding="utf-8") as f:
                            lines = f.readlines()
                        lines.append(json.dumps(record, ensure_ascii=False) + "\n")
                        with open(temp_path, "w", encoding="utf-8") as f:
                            f.writelines(lines)
                        write_count += 1
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert write_count == 500

        with open(temp_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                try:
                    json.loads(line)
                except json.JSONDecodeError as e:
                    raise AssertionError(f"第{line_num}行JSON格式错误: {e}")

    finally:
        os.unlink(temp_path)


def test_semantic_lock_prevents_read_during_write():
    from kernel.semantic_state import SEMANTIC_LOCK

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".jsonl") as f:
        temp_path = f.name

    try:
        read_errors = []
        write_completed = threading.Event()

        def writer():
            for i in range(50):
                record = {"iter": i, "data": "x" * 1000}
                with SEMANTIC_LOCK:
                    with open(temp_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps(record, ensure_ascii=False) + "\n")
            write_completed.set()

        def reader():
            while not write_completed.is_set():
                try:
                    with SEMANTIC_LOCK:
                        with open(temp_path, "r", encoding="utf-8") as f:
                            for line in f:
                                json.loads(line)
                except json.JSONDecodeError as e:
                    read_errors.append(e)
                except FileNotFoundError:
                    pass

        t_write = threading.Thread(target=writer)
        t_read = threading.Thread(target=reader)
        t_write.start()
        t_read.start()
        t_write.join()
        t_read.join()

        assert len(read_errors) == 0

    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
