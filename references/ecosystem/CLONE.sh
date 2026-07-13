#!/usr/bin/env bash
# 一键拉取 AOS 生态集成的「完整开源」真实仓库（本地参考副本，用于逐字对照）。
# 这些仓库不进 AOS 的 git（整仓入会撑爆仓库、拖垮 push），故用本脚本复现。
# 已核实真实存在、均支持 MCP：ExploreYC / Sim / Timbal（Auriko 为 PyPI SDK）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

clone() {
  local url="$1" name="$2"
  if [ -d "$name/.git" ] || [ -d "$name" ]; then
    echo "✓ $name 已存在，跳过"
  else
    echo "↓ 克隆 $name ..."
    git clone --depth 1 "$url" "$name"
    rm -rf "$name/.git"
  fi
}

clone "https://github.com/KonstantinMB/exploreyc" exploreyc
clone "https://github.com/simstudioai/sim"           sim
clone "https://github.com/timbal-ai/timbal"         timbal

echo
echo "完成。完整开源源码已落位到 references/ecosystem/{exploreyc,sim,timbal}/"
echo "对照契约见 INTEGRATIONS.md（已入库）。"
