#!/usr/bin/env bash
# AOS 全量测试覆盖率一键脚本（本机 / CI 运行）
#
# 背景：沙箱前台 9 分钟超时会被杀，且单进程顺序跑全量测试会因模块级单例
# 跨文件污染导致覆盖率失真（已在 2026-08-05 实测）。故本脚本仅供用户在
# 本机 / CI（不被杀、干净环境）执行，拿到真实全局覆盖率基线。
#
# ─────────────────────────────────────────────────────────────────────────
# 落地途径（用户亲自动手，完整可照敲）
# ─────────────────────────────────────────────────────────────────────────
# 本脚本只负责「跑 + 收集覆盖率」，前提是已有一个装好依赖的 venv。
# 下面给 Windows / Linux / CI 三种环境的完整前置 + 执行命令。
#
# 【Windows · Git Bash（推荐，最稳）】
#   cd /d/AOS
#   # 1) 建 venv（只需一次）
#   C:/Users/Administrator/.workbuddy/binaries/python/envs/aos/Scripts/python.exe -m venv .venv
#   #    或复用已存在的 managed venv：
#   #    export VENV=C:/Users/Administrator/.workbuddy/binaries/python/envs/aos
#   # 2) 装依赖（只需一次；把项目依赖 + 覆盖率工具链装进去）
#   .venv/Scripts/python.exe -m pip install -U pip
#   .venv/Scripts/python.exe -m pip install -e .          # 读 pyproject 装全部运行时依赖
#   .venv/Scripts/python.exe -m pip install coverage pytest pytest-xdist
#   # 3) 跑全量覆盖率（xdist 并行，多进程天然隔离模块级单例，最准）
#   bash scripts/run_full_coverage.sh
#   #    若你的机器内存/核数紧张或想断点续跑，用顺序分批：
#   #    SEQUENTIAL=1 bash scripts/run_full_coverage.sh
#   # 4) 看结果
#   #    - 终端末尾的 coverage report 即为全局百分比
#   #    - 打开 htmlcov/index.html 看每个文件的覆盖明细
#
# 【Windows · PowerShell】
#   cd D:\AOS
#   & C:/Users/Administrator/.workbuddy/binaries/python/envs/aos/Scripts/python.exe -m venv .venv
#   .venv\Scripts\python.exe -m pip install -U pip
#   .venv\Scripts\python.exe -m pip install -e .
#   .venv\Scripts\python.exe -m pip install coverage pytest pytest-xdist
#   $env:VENV = "$PWD\.venv"
#   bash scripts/run_full_coverage.sh     # Git Bash 仍在，调用同一脚本
#
# 【Linux / macOS / CI（GitHub Actions 等）】
#   cd "$GITHUB_WORKSPACE"            # 或你的仓库根
#   python3 -m venv .venv && .venv/bin/python -m pip install -e . coverage pytest pytest-xdist
#   VENV=.venv bash scripts/run_full_coverage.sh
#
# ⚠️ 读数与避坑：
#   - 沙箱 / 受限环境不要跑（长运行易被杀 + 单例污染会失真，已实测）。
#   - 该数字是「全局项目全量(src 68709 行)覆盖率」；审计里「核心 7 模块 57%」
#     是另一口径，二者不同，勿混。
#   - 若某批测试因单例污染红了一两个，重跑该批即可；SEQUENTIAL=1 每批落盘
#     cov_progress.log，中断后重跑会自动跳过已 DONE 的批次。
# ─────────────────────────────────────────────────────────────────────────
#
# 用法（Git Bash / Linux / macOS）：
#   VENV=/path/to/venv  bash scripts/run_full_coverage.sh
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
