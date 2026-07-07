"""
真实注册 AOS 开源资产进 DeerFlow 子智能体系统。

运行方式（必须用 DeerFlow 自带的 backend venv，其 Python 3.12 已装 deerflow）:
  D:/AOS/external/deer-flow/backend/.venv/Scripts/python.exe scripts/register_deerflow_assets.py

设计要点:
- 不把 AOS `src` 加进 sys.path，避免 AOS 自己的 `src/deerflow` 包与 harness 的
  `deerflow` 引擎撞名；改为用 importlib 按文件路径加载本脚本需要的 AOS 模块。
- 只注册「子智能体 + 角色模板」这 273 项（= build_catalog 的 to_deerflow_registrations）。
  34 个领域技能归到 Mem0 / browser-use / fabric 等平面，另行出清单，不塞进子智能体注册表。
- 真实注册 = 用 DeerFlow 真实的 SubagentConfig 构造并存入 AOSSubagentBridge._configs。
  不执行任何 LLM 调用。
"""
import sys
import os
import importlib.util
from pathlib import Path

AOS_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_FILE = AOS_ROOT / "src" / "deerflow" / "subagent_executor.py"
ASSETS_FILE = AOS_ROOT / "src" / "deerflow" / "aos_assets.py"


def _load(module_path: Path, module_name: str):
    """按文件路径加载模块（绕开 sys.path 包名冲突）。"""
    spec = importlib.util.spec_from_file_location(module_name, str(module_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def main():
    # 1) 确认 harness deerflow 可导入（backend venv 自带）
    import deerflow  # harness
    print(f"[ok] deerflow 引擎可导入: {deerflow.__file__}")

    # 2) 加载 AOS 桥接（真实 AOSSubagentBridge，内部会导入 DeerFlow SubagentConfig）
    bridge_mod = _load(BRIDGE_FILE, "aos_subagent_executor")
    AOSSubagentBridge = bridge_mod.AOSSubagentBridge
    SubagentConfig = bridge_mod.SubagentConfig
    if SubagentConfig is None:
        print("[FAIL] DeerFlow SubagentConfig 不可用，无法注册。请确认 backend venv 的 deerflow 完整。")
        sys.exit(2)
    print("[ok] AOSSubagentBridge + DeerFlow SubagentConfig 就绪")

    # 3) 加载资产目录（纯静态解析，不依赖 deerflow）
    assets_mod = _load(ASSETS_FILE, "aos_assets_mod")
    cat = assets_mod.build_catalog()
    regs = assets_mod.to_deerflow_registrations(cat)
    print(f"[info] 待注册项(子智能体+角色模板): {len(regs)}  "
          f"(subagents={len(cat['subagents'])}, roles={len(cat['roles'])})")

    # 4) 真实注册
    bridge = AOSSubagentBridge()
    ok, skipped, failed = 0, 0, []
    seen = set()
    for r in regs:
        name = r["name"]
        if name in seen:  # 最终重名保护
            skipped += 1
            continue
        try:
            bridge.register_subagent(
                name,
                r["description"],
                system_prompt=r.get("system_prompt"),
                skills=r.get("skills"),
                model=r.get("model", "inherit"),
            )
            seen.add(name)
            ok += 1
        except Exception as e:  # noqa: BLE001
            failed.append((name, repr(e)))

    print("=" * 60)
    print(f"真实注册完成: 成功 {ok} / 跳过重名 {skipped} / 失败 {len(failed)}")
    if failed:
        print("失败项:")
        for n, e in failed[:30]:
            print(f"  - {n}: {e}")
    print("=" * 60)

    # 5) 列出现注册的子智能体
    listed = bridge.list_subagents()
    print(f"DeerFlow 子智能体注册表当前条目数: {len(listed)}")
    # 取样前 10 个名字
    for item in listed[:10]:
        print(f"   · {item['name']}  (model={item['model']})")
    if len(listed) > 10:
        print(f"   … 其余 {len(listed) - 10} 个")

    # 6) 写一份注册结果清单
    out = AOS_ROOT / "docs" / "DEERFLOW_REGISTRY.md"
    lines = [
        "# DeerFlow 子智能体真实注册结果",
        "",
        f"- 注册时间运行环境: `external/deer-flow/backend/.venv` (Python 3.12, deerflow 已装)",
        f"- 成功注册: **{ok}** 项（子智能体 + 角色模板）",
        f"- 跳过重名: {skipped} 项",
        f"- 失败: {len(failed)} 项",
        "",
        "## 注册项（节选前 60）",
        "",
        "| # | 名称 | 模型 |",
        "|---|---|---|",
    ]
    for i, item in enumerate(listed[:60], 1):
        lines.append(f"| {i} | `{item['name']}` | {item['model']} |")
    if len(listed) > 60:
        lines.append(f"| … | 其余 {len(listed) - 60} 项同结构省略 | … |")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[ok] 已写出注册清单: {out}")


if __name__ == "__main__":
    main()
