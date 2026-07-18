FROM python:3.14-slim

WORKDIR /app

# 依赖: 标准
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

# 依赖: Python 3.14 环境
# 注意: requirements.lock 是 2026-07-10 的历史快照, 此后 requirements.txt 又补充了
# fastapi/uvicorn/pydantic/aiosqlite/bcrypt/psycopg2-binary 等核心依赖, 当前 lock 并不完整。
# 若直接 `pip install -r requirements.lock` 会"安装成功却漏装核心包" -> 镜像启动即崩。
# 因此以人工维护且完整的 requirements.txt 为权威安装源; lock 仅作可复现参考(需先按
# 下方命令重新生成): python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/pip freeze > requirements.lock
COPY requirements.txt ./
COPY requirements.lock ./

# 完整清单优先安装
RUN pip install --no-cache-dir -r requirements.txt

# 代码
COPY . .

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# 零成本启动: mem0 本地优先
ENV AOS_MEM0_LOCAL=1

CMD ["uvicorn", "src.api.main:app", "--host=0.0.0.0", "--port=8000"]
