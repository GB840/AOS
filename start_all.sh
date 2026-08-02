#!/usr/bin/env bash
# AOS 一键启动脚本（个人级 → 团队级可演进）
# 启动: AOS API (:8000) + Web 控制台 (:8501) + OpenClaw Gateway (:18789)
# 用法: bash start_all.sh   (在 D:\AOS 目录下运行)
set -e

AOS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AOS_DIR"

VENV_PY="$USERPROFILE/.workbuddy/binaries/python/envs/aos/Scripts/python.exe"
VENV_PY_DIR="$USERPROFILE/.workbuddy/binaries/python/envs/aos/Scripts"

# --- 从 .env 读取密钥（不打印值）---
read_env() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- ; }

ZHIPU_API_KEY="$(read_env ZHIPU_API_KEY)"
SILICONFLOW_API_KEY="$(read_env SILICONFLOW_API_KEY)"
OPENCLAW_GATEWAY_TOKEN="$(read_env OPENCLAW_GATEWAY_TOKEN)"
[ -z "$OPENCLAW_GATEWAY_TOKEN" ] && OPENCLAW_GATEWAY_TOKEN="aos-fabric-2026local"

export ZHIPU_API_KEY SILICONFLOW_API_KEY OPENCLAW_GATEWAY_TOKEN
export AOS_LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export AOS_LLM_MODEL="glm-4-flash"
export AOS_AUTH_JWT_SECRET="aos-jwt-secret-$( "$VENV_PY" -c 'import secrets;print(secrets.token_hex(16))' )"
export PYTHONPATH="$AOS_DIR/src;$AOS_DIR"
export AOS_API_BASE="http://127.0.0.1:8000"

# mem0 / langfuse 装在 default venv (sandbox 禁止在 aos venv 落地 pip),
# 低优先级追加其 site-packages, 让 aos 进程能 import 这两个真实 OSS。
export AOS_EXTRA_SITE="$USERPROFILE/.workbuddy/binaries/python/envs/default/Lib/site-packages"

# --- 0) 确保 litellm 推理平面依赖（缺失则最佳努力安装，失败不阻断）---
if ! "$VENV_PY" -c "import litellm" >/dev/null 2>&1; then
  echo "[start_all] 安装 litellm (+zhipuai) 推理平面依赖..."
  "$VENV_PY_DIR/pip" install --quiet litellm zhipuai 2>/dev/null || echo "[start_all] litellm 安装失败(可稍后手动装), fabric 仍会优雅降级"
fi

echo "[start_all] env ready (ZK=${#ZHIPU_API_KEY} SK=${#SILICONFLOW_API_KEY})"

# --- 1) OpenClaw Gateway (外部引擎, 真实接线) ---
if curl -s -m 4 -o /dev/null http://127.0.0.1:18789/ 2>/dev/null; then
  echo "[start_all] OpenClaw Gateway 已在运行"
else
  echo "[start_all] 启动 OpenClaw Gateway (:18789)..."
  ( openclaw gateway run --bind loopback --port 18789 --token "$OPENCLAW_GATEWAY_TOKEN" > openclaw_gw.log 2>&1 & )
  sleep 12
fi

# --- 1.5) DeerFlow Gateway (外部引擎, 真实接线 @2026) ---
DF_DIR="$AOS_DIR/external/deer-flow"
DF_BACKEND="$DF_DIR/backend"
if curl -s -m 4 -o /dev/null http://127.0.0.1:2026/health 2>/dev/null; then
  echo "[start_all] DeerFlow Gateway 已在运行"
else
  echo "[start_all] 启动 DeerFlow Gateway (:2026)..."
  (
    cd "$DF_DIR" || exit 1
    set -a; [ -f .env ] && . ./.env; set +a
    cd "$DF_BACKEND" || exit 1
    if [ -x "$DF_BACKEND/.venv/Scripts/python.exe" ]; then
      "$DF_BACKEND/.venv/Scripts/python.exe" -u -m uvicorn app.gateway.app:app --host 127.0.0.1 --port 2026 --log-level info > "$AOS_DIR/logs/deerflow_gateway.log" 2>&1 &
    else
      echo "[start_all] DeerFlow venv 缺失, 跳过 (AOS 将优雅降级到内置 DeerFlow)"
    fi
  )
  sleep 15
fi

# --- 2) AOS API (:8000) ---
if curl -s -m 4 -o /dev/null http://127.0.0.1:8000/health 2>/dev/null; then
  echo "[start_all] AOS API 已在运行"
else
  echo "[start_all] 启动 AOS API (:8000)..."
  ( "$VENV_PY" -u -m uvicorn src.api.main:app --host 127.0.0.1 --port 8000 --log-level info > aos_live.log 2>&1 & )
  # 等待健康
  for i in $(seq 1 24); do
    c=$(curl -s -m 4 -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health 2>/dev/null || echo 000)
    [ "$c" = "200" ] && { echo "[start_all] AOS API 就绪 (${i}x5s)"; break; }
    sleep 5
  done
fi

# --- 3) Web 控制台 (:8501, 仅回环 + baseUrlPath=/web 收编进 AOS 单端口) ---
if curl -s -m 4 -o /dev/null http://127.0.0.1:8501/web/ 2>/dev/null; then
  echo "[start_all] Web 控制台已在运行"
else
  echo "[start_all] 启动 Web 控制台 (:8501, baseUrlPath=/web)..."
  ( "$VENV_PY_DIR/streamlit" run src/web/app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false --server.address 127.0.0.1 --server.baseUrlPath=/web > web_console.log 2>&1 & )
  sleep 8
fi

echo
echo "[start_all] === 全部启动完成 (统一单端口) ==="
echo "  >>> 唯一对外入口: http://127.0.0.1:8000  (AOS 统一前门) <<<"
echo "      Web 控制台  : http://127.0.0.1:8000/web/"
echo "      OpenClaw 网关: http://127.0.0.1:8000/openclaw/   (内部 18789)"
echo "      DeerFlow 网关: http://127.0.0.1:8000/deerflow/  (内部 2026)"
echo "      AOS API     : http://127.0.0.1:8000/api/...      (health: $(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health))"
