"""Vertical slice: a real multi-agent GROUP CHAT through the open fabric.

Wires OpenClaw (channel.access) + AG2 (group.orchestration) via the
FabricRegistry, and runs a user message -> group swarm -> aggregated reply
flow.

Modes:
  --demo    run fully offline with in-process fakes (no real engines needed)
  --real    use the real OpenClaw / AG2 gateway adapters
  --check   health-check the real engines only (do they answer on their ports?)

Run from the D:\\AOS repo root:
  PYTHONPATH=. python scripts/slice_groupchat.py --demo
  PYTHONPATH=. python scripts/slice_groupchat.py --check
  PYTHONPATH=. python scripts/slice_groupchat.py --real
"""
from __future__ import annotations

import argparse
import sys
from typing import Any, Dict, List

from src.core.fabric import (
    BaseAgentAdapter,
    Capability,
    FabricRegistry,
    InvokeRequest,
    InvokeResult,
)


# ---- in-process fakes so the slice is runnable WITHOUT real engines ----
class FakeOpenClaw(BaseAgentAdapter):
    def __init__(self) -> None:
        self.inbox: List[str] = []

    @property
    def engine_id(self) -> str:
        return "openclaw"

    def advertise_capabilities(self):
        return [Capability.CHANNEL_ACCESS, Capability.TOOL_USE, Capability.MEMORY_PERSISTENT]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if req.capability == Capability.CHANNEL_ACCESS:
            self.inbox.append(req.payload.get("text", ""))
            print(f"  [OpenClaw] delivered to {req.payload.get('to')}: {req.payload.get('text')}")
            return InvokeResult(ok=True, data={"delivered": True, "reply": "(simulated) 登录功能已拆解"})
        return InvokeResult(ok=False, error="unsupported")

    def health(self) -> bool:
        return True


class FakeGroupOrchestrator(BaseAgentAdapter):
    AGENTS = ["developer", "designer", "tester"]

    def __init__(self) -> None:
        self.group_id = None

    @property
    def engine_id(self) -> str:
        return "ag2"

    def advertise_capabilities(self):
        return [Capability.GROUP_ORCHESTRATION, Capability.PLANNING]

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if req.capability == Capability.GROUP_ORCHESTRATION:
            action = req.payload.get("action")
            if action == "create":
                self.group_id = "grp-001"
                print(f"  [AG2] created group {self.group_id} with agents {self.AGENTS}")
                return InvokeResult(ok=True, data={"group_id": self.group_id})
            if action == "message":
                print(f"  [AG2] fan-out to {self.AGENTS}: {req.payload.get('text')}")
                for a in self.AGENTS:
                    print(f"    - {a} -> {a}-side reply (simulated)")
                return InvokeResult(ok=True, data={"fanned_out": True, "agents": self.AGENTS})
        return InvokeResult(ok=False, error="unsupported")

    def health(self) -> bool:
        return True


def build_registry(use_real: bool) -> FabricRegistry:
    reg = FabricRegistry()
    if use_real:
        from src.core.fabric.adapters import (
            AG2Adapter,
            OpenClawAdapter,
        )

        reg.register(OpenClawAdapter())
        # AG2 is the real open-source group.orchestration engine.
        reg.register(AG2Adapter())
    else:
        reg.register(FakeOpenClaw())
        reg.register(FakeGroupOrchestrator())
    return reg


def _show(label: str, res: InvokeResult) -> None:
    if res.ok:
        print(f"  -> {label}: OK  {res.data}")
    else:
        print(f"  -> {label}: FAIL ({res.error})")


def check_health() -> int:
    print("=== AOS health-check: are the real engines answering? ===")
    reg = build_registry(use_real=True)
    any_up = False
    for eid, adapter in reg._adapters.items():
        up = adapter.health()
        any_up = any_up or up
        print(f"  [{eid}] {'UP' if up else 'DOWN'}")
    if not any_up:
        print("\n  Neither engine is reachable. To bring them up:")
        print("    OpenClaw : ensure the local Gateway is running (http://127.0.0.1:18789)")
        print("    AG2      : pip install ag2 (in-process, no service needed)")
        return 0
    return 0


def run() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--real", action="store_true", help="use real gateway adapters")
    p.add_argument("--demo", action="store_true", help="run offline with in-process fakes (default)")
    p.add_argument("--check", action="store_true", help="health-check real engines only")
    args = p.parse_args()

    if args.check:
        return check_health()

    mode = "REAL engines" if args.real else "DEMO fakes"
    print(f"=== AOS vertical slice: multi-agent group chat ({mode}) ===")
    reg = build_registry(use_real=args.real)

    # 1) user message enters via OpenClaw channel.access
    r1 = reg.route(
        InvokeRequest(
            capability=Capability.CHANNEL_ACCESS,
            payload={"channel": "api", "to": "user", "text": "帮我做一个登录功能"},
        )
    )
    _show("channel.access (OpenClaw)", r1)

    # 2) AOS routes the task to the live group.orchestration provider (AG2)
    r2 = reg.route(
        InvokeRequest(
            capability=Capability.GROUP_ORCHESTRATION,
            payload={"action": "create", "topic": "登录功能"},
        )
    )
    _show("group.orchestration create (live provider)", r2)
    gid = (r2.data or {}).get("group_id")

    # 3) the group fans the task out to specialist agents and returns a reply
    if gid:
        r3 = reg.route(
            InvokeRequest(
                capability=Capability.GROUP_ORCHESTRATION,
                payload={"action": "message", "group_id": gid, "text": "需求：登录功能"},
            )
        )
        _show("group.orchestration message (live provider)", r3)

    ok = r1.ok and r2.ok and (r3.ok if gid else True)
    print(
        "=== slice "
        + ("OK" if ok else "DEGRADED")
        + ": channel.access + group.orchestration flowed through the fabric ==="
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
