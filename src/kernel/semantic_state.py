"""语义记忆共享状态：单一路径 + 并发锁（零内部依赖，避免 kernel 包内循环 import）。

autopilot（写侧，_save_semantic_memory）与 fabric_hub（读 / 回退写侧，
memory_recall / memory_store）共用同一份 ``_traces/semantic_memory.jsonl``。
必须用**同一把锁**串行化，否则 API 并发多任务 / recall 并发读时会：

  * 写侧读-改-写-追加过程中被另一写打断 → JSONL 丢更新或被截断；
  * 读侧在写侧 ``f.write`` 中途读到半行 → ``json.loads`` 失败、记忆召回漏条。

本模块只依赖 ``os`` / ``threading``，不 import 任何 AOS 业务模块，
因此 autopilot 与 fabric_hub 各自 ``from kernel.semantic_state import ...`` 都不会形成环。
"""

import os
import threading

# 本文件位于 src/kernel/semantic_state.py：
#   abspath(__file__)            -> D:/AOS/src/kernel/semantic_state.py
#   dirname x1                   -> D:/AOS/src/kernel
#   dirname x2                   -> D:/AOS/src
#   dirname x3                   -> D:/AOS
# 与 autopilot（``..,..`` 两级）/ fabric_hub（``..,..,..`` 三级）的旧拼法结果一致，
# 统一到此处后，三处路径永不再漂移。
SEMANTIC_MEMORY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "_traces", "semantic_memory.jsonl",
)

# 写侧（autopilot）与读 / 回退写侧（fabric_hub）共用此锁对象。
SEMANTIC_LOCK = threading.Lock()
