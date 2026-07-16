FROM python:3.14-slim

WORKDIR /app

# 依赖: 标准
RUN apt-get update && \
    apt-get install -y curl && \
    rm -rf /var/lib/apt/lists/*

# 依赖: Python 3.14 环境
COPY requirements.lock ./
COPY requirements.txt ./

# 冻结 lock 优先
RUN pip install --no-cache-dir -r requirements.lock || pip install --no-cache-dir -r requirements.txt

# 代码
COPY . .

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/src

# 零成本启动: mem0 本地优先
ENV AOS_MEM0_LOCAL=1

CMD ["uvicorn", "src.api.main:app", "--host=0.0.0.0", "--port=8000"]
