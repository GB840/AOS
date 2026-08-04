#!/usr/bin/env bash
# AOS 全量测试覆盖率一键脚本（本机 / CI 运行）
#
# 背景：沙箱前台 9 分钟超时会被杀，且单进程顺序跑全量测试会因模块级单例
# 跨文件污染导致覆盖率失真（已在 2026-08-05 实测）。故本脚本仅供用户在
# 本机 / CI（不被杀、干净环境）执行，拿到真实全局覆盖率基线。
#
# 用法（Git Bash / Linux / macOS）：
#   VENV=/path/to/venv  bash scripts/run_full_coverage.sh
# Windows PowerShell 用户见文档内等价命令。
#
# 默认 venv 为仓库根 .venv；脚本自动适配 Windows(Scripts/python.exe) 与 Unix(bin/python)。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VENV="${VENV:-$ROOT/.venv}"
if [ -f "$VENV/Scripts/python.exe" ]; then
  PY="$VENV/Scripts/python.exe"
elif [ -f "$VENV/bin/python" ]; then
  PY="$VENV/bin/python"
else
  echo "找不到 venv，请通过 VENV= 指向你的虚拟环境（如 VENV=.venv）" >&2
  exit 1
fi

export PYTHONPATH="$ROOT/src"

echo "==> 安装/更新覆盖率工具链"
"$PY" -m pip install -q -U coverage pytest pytest-xdist 2>/dev/null || true

echo "==> 清空旧数据"
"$PY" -m coverage erase

if [ "${SEQUENTIAL:-0}" = "1" ]; then
  # 顺序 + 分批 --append：完全规避单例污染，本机不被杀也能跑完。
  # 每批 30 个文件，进度写入 cov_progress.log 支持断点续跑。
  echo "==> 顺序分批模式（SEQUENTIAL=1）"
  files=(tests/*.py)
  n=${#files[@]}; batch=30
  : > cov_progress.log
  for ((i=0; i<n; i+=batch)); do
    if grep -q "DONE $i" cov_progress.log 2>/dev/null; then continue; fi
    chunk=("${files[@]:i:batch}")
    "$PY" -m coverage run --append --source=src -m pytest "${chunk[@]}" -q -p no:cacheprovider || true
    echo "DONE $i" >> cov_progress.log
  done
else
  # 默认：xdist 并行（-n auto），多进程天然隔离模块级单例，一次性 coverage。
  echo "==> xdist 并行模式（默认）"
  "$PY" -m coverage run --source=src -m pytest tests/ -q -n auto
fi

echo "==> 生成报告"
"$PY" -m coverage report
"$PY" -m coverage html -d htmlcov
echo "✅ 全量覆盖率报告已生成：htmlcov/index.html"
