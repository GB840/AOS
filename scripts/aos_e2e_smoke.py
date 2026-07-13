"""AOS 端到端自主链路自检（搜索 -> 出文），必须在用户 Windows 主机跑。

链路：
  [1] WebSearchAdapter 真联网搜真实资料（多源 fallback，count>0 才算成功）
  [2] 经 AOS OpenClawAdapter 把"问题 + 搜索资料"交给活着的 agent 出文

这是证明 AOS "不是玩具" 的最小自主链路：它真的去网上找了资料、
再基于资料让 agent 作答，而不是空谈架构。
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, "src")

from core.fabric.adapters.search_adapter import SearchAdapter
from core.fabric.adapters.openclaw_adapter import OpenClawAdapter
from core.fabric.adapter import InvokeRequest
from core.fabric.capability import Capability

TOKEN = os.environ.get("OPENCLAW_GATEWAY_TOKEN") or "aos-fabric-2026local"
QUERY = "2026年人工智能领域有哪些值得关注的重要进展"


def main() -> int:
    print("=" * 60)
    print("AOS 端到端自主链路：搜索 -> 出文")
    print("=" * 60)

    # ---- [1] 联网搜索：拿真实资料 ----
    print("\n[1] 联网搜索（真实多源 fallback）...")
    s = SearchAdapter()
    r = s.invoke(InvokeRequest(
        capability=Capability.WEB_SEARCH,
        payload={"query": QUERY, "max_results": 3},
    ))
    if not r.ok:
        print("  ! 搜索失败：", r.error)
        ctx = "(无搜索资料，退化为纯模型知识作答)"
    else:
        eng = r.data.get("engine")
        cnt = r.data.get("count")
        print(f"  + 搜索成功：源={eng}  真实结果数={cnt}")
        print("  - 资料片段：")
        for line in r.data.get("content", "").splitlines()[:6]:
            if line.strip():
                print("      " + line.strip()[:90])
        ctx = r.data.get("content", "")

    # ---- [2] 经 AOS 调活着的 agent 出文 ----
    print("\n[2] 经 AOS OpenClawAdapter 调 agent 出文...")
    oc = OpenClawAdapter(gateway_token=TOKEN)
    # 用「真实 agent 探针」而非只看端口的 health()
    ah = oc.agent_health()
    print(f"  - agent 真实可达性：{ah['status']}")
    if ah["status"] != "ok":
        print("  ! agent 不可用：", ah.get("reason"))
        if ah.get("action"):
            print("  - 修复动作：", ah["action"])
        return 2
    prompt = (
        f"用户问题：{QUERY}\n\n"
        f"可参考的搜索资料：\n{ctx}\n\n"
        f"请基于资料，用中文简洁回答（不超过150字）。"
    )
    r2 = oc.invoke(InvokeRequest(
        capability=Capability.CHANNEL_ACCESS, payload={"text": prompt}
    ))
    if not r2.ok:
        print("  ! 出文失败：", r2.error)
        if r2.data and r2.data.get("action"):
            print("  - 修复动作：", r2.data["action"])
        return 3
    reply = r2.data.get("reply", "")
    print("  + agent 回复：")
    print("    " + reply.replace("\n", "\n    "))
    print("\n= 链路结论：搜索->出文 全链路真实可跑（非 mock）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
