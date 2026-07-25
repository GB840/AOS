"""
AOS 最小可运行 Demo -- 演示 5 个核心能力

运行方式:
    python examples/minimal_demo.py

不依赖外部服务，所有搜索使用 mock，所有组件均为内存实例。
"""

import sys
import os

# 确保 src 在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def demo_capability_routing():
    """(a) 能力路由: 构造 Registry，注册 SearchAdapter，route 一个 web.search"""
    print("=" * 60)
    print("(a) 能力路由 (Capability Routing)")
    print("=" * 60)

    from core.fabric.registry import FabricRegistry
    from core.fabric.capability import Capability

    registry = FabricRegistry()

    # 注册一个 mock SearchAdapter
    from unittest.mock import MagicMock
    from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult

    class MockSearchAdapter(BaseAgentAdapter):
        engine_id = "mock-search"

        def advertise_capabilities(self):
            return [Capability.WEB_SEARCH]

        def health(self) -> bool:
            return True

        def invoke(self, req: InvokeRequest) -> InvokeResult:
            query = req.payload.get("query", "")
            return InvokeResult(
                ok=True,
                data={
                    "results": [
                        {"title": f"Mock result for: {query}", "url": "https://example.com"},
                        {"title": f"Another result: {query}", "url": "https://example.org"},
                    ],
                    "engine": "mock-search",
                },
            )

    adapter = MockSearchAdapter()
    registry.register(adapter)
    print(f"  注册引擎: {adapter.engine_id}")
    print(f"  声明能力: {[c.value for c in adapter.advertise_capabilities()]}")

    # 路由查询
    from core.fabric.adapter import InvokeRequest

    providers = registry.providers_for(Capability.WEB_SEARCH)
    print(f"  可用供给方: {[p.engine_id for p in providers]}")

    if providers:
        result = providers[0].invoke(InvokeRequest(
            capability=Capability.WEB_SEARCH.value,
            payload={"query": "AOS agent framework"},
        ))
        print(f"  路由结果: ok={result.ok}, 返回 {len(result.data.get('results', []))} 条结果")
        for r in result.data.get("results", []):
            print(f"    - {r['title']} ({r['url']})")
    print()


def demo_kernel_three_pillars():
    """(b) 内核三职责: 构造 AOSKernel, register_agent -> send_message -> check_permission"""
    print("=" * 60)
    print("(b) 内核三职责 (Kernel Three Pillars)")
    print("=" * 60)

    from kernel.kernel import AOSKernel
    from kernel.types import AgentSpec, Message
    from core.fabric.adapter import InvokeRequest, InvokeResult

    kernel = AOSKernel()

    # 注册一个 mock runtime
    from kernel.interfaces import AgentRuntime
    from kernel.types import Response

    class MockRuntime(AgentRuntime):
        def create_agent(self, spec):
            return None

        def run_agent(self, instance, task):
            return Response(ok=True, data={"output": f"Mock handled: {task}"})

        async def stream_run(self, instance, task):
            yield {"output": f"Mock handled: {task}"}

        def get_status(self, instance_id):
            return "running"

    kernel.register_runtime("mock-engine", MockRuntime())
    print("  注册引擎 runtime: mock-engine")

    # 注册 agent
    spec = AgentSpec(
        agent_id="agent-001",
        name="TestAgent",
        engine="mock-engine",
        capabilities=["chat", "search"],
    )
    instance = kernel.register_agent(spec)
    print(f"  注册 Agent: {instance.agent_id}, 状态={instance.status.value}")

    # 消息路由
    kernel.grant_permission("agent-001", "receive", True)
    msg = Message(sender="user", recipient="agent-001", payload={"task": "帮我搜索"})
    resp = kernel.send_message(msg)
    print(f"  消息路由: ok={resp.ok}, 输出={resp.data.get('output', '')}")

    # 权限检查
    has_perm = kernel.check_permission("agent-001", "receive")
    no_perm = kernel.check_permission("agent-999", "receive")
    print(f"  权限检查: agent-001:receive={has_perm}, agent-999:receive={no_perm}")
    print()


def demo_species_evolution():
    """(c) 物种进化: 构造 AgentDNA, mutate, crossover"""
    print("=" * 60)
    print("(c) 物种进化 (Species Evolution)")
    print("=" * 60)

    from kernel.evolution import AgentDNA, Gene
    from kernel.types import AgentSpec

    # 构造 DNA
    dna = AgentDNA(
        genes=[
            Gene("agent_id", "evo-001", immutable=True),
            Gene("engine", "litellm", "discrete",
                 options=["litellm", "openclaw", "ag2"]),
            Gene("temperature", 0.7, "continuous", continuous_range=0.3),
            Gene("capabilities", ["chat", "search"], "discrete",
                 options=[["chat"], ["chat", "search"], ["chat", "code_exec"]]),
        ],
        generation=0,
    )
    print(f"  原始 DNA (gen={dna.generation}):")
    for g in dna.genes:
        mut = "immutable" if g.immutable else g.mutation_type
        print(f"    {g.name} = {g.value} ({mut})")

    # 变异
    child = dna.mutate()
    print(f"\n  变异后 DNA (gen={child.generation}):")
    for g in child.genes:
        print(f"    {g.name} = {g.value}")
    print(f"  变异记录: {child.mutation_history}")

    # 交叉
    dna2 = AgentDNA(
        genes=[
            Gene("agent_id", "evo-002", immutable=True),
            Gene("engine", "ag2", "discrete",
                 options=["litellm", "openclaw", "ag2"]),
            Gene("temperature", 0.3, "continuous", continuous_range=0.3),
            Gene("capabilities", ["code_exec"], "discrete",
                 options=[["chat"], ["chat", "search"], ["chat", "code_exec"]]),
        ],
        generation=0,
    )
    child2 = dna.crossover(dna2)
    print(f"\n  交叉后 DNA (gen={child2.generation}):")
    for g in child2.genes:
        print(f"    {g.name} = {g.value}")
    print()


def demo_immunity_system():
    """(d) 免疫系统: 构造 AnomalyDetector + CircuitBreaker"""
    print("=" * 60)
    print("(d) 免疫系统 (Immunity System)")
    print("=" * 60)

    from kernel.events import EventBus
    from kernel.immunity import AnomalyDetector, CircuitBreaker, CircuitBreakerOpenError

    bus = EventBus()

    # 异常检测器
    alerts = []
    detector = AnomalyDetector(
        event_bus=bus,
        window_seconds=60.0,
        error_threshold=0.5,
        consecutive_failures=3,
        on_alert=lambda rule, msg, detail: alerts.append({"rule": rule, "msg": msg}),
    )
    print(f"  异常检测器: 错误率阈值={detector._error_threshold}, 连续失败阈值={detector._consecutive_failures}")

    # 模拟失败事件
    from kernel.events import Event

    for i in range(4):
        bus.emit(Event(event_type="model.failed", source="test-model", payload={"model": "gpt-4"}))

    print(f"  触发 4 次 model.failed, 健康状态: {detector.is_healthy()}")
    print(f"  累计告警: {len(alerts)}")
    for a in alerts:
        print(f"    - [{a['rule']}] {a['msg']}")

    # 熔断器
    cb = CircuitBreaker(name="test-gw", failure_threshold=3, cooldown_seconds=5.0)
    print(f"\n  熔断器: name={cb.name}, 状态={cb.state}")

    # 正常调用
    for i in range(3):
        try:
            with cb:
                raise RuntimeError("simulated failure")
        except RuntimeError:
            pass
    print(f"  连续 3 次失败后状态: {cb.state}")

    # 熔断期间调用
    try:
        with cb:
            print("  这行不应该被执行")
    except CircuitBreakerOpenError as e:
        print(f"  熔断器打开, 拒绝请求: {e}")
    print()


def demo_compliance_audit():
    """(e) 合规审计: 构造 AuditTrail, record 几条, query"""
    print("=" * 60)
    print("(e) 合规审计 (Compliance Audit)")
    print("=" * 60)

    from kernel.compliance import AuditTrail

    trail = AuditTrail(max_entries=100)

    # 记录几条审计日志
    trail.record(actor="user-001", action="agent.registered",
                 resource="agent-001", result="ok",
                 detail={"engine": "mock-engine"})
    trail.record(actor="user-001", action="message.sent",
                 resource="agent-001", result="ok",
                 detail={"task": "帮我搜索"})
    trail.record(actor="user-002", action="message.sent",
                 resource="agent-001", result="denied",
                 detail={"reason": "permission denied"})
    trail.record(actor="system", action="agent.stopped",
                 resource="agent-001", result="ok")

    print(f"  总审计记录: {len(trail._entries)}")
    print(f"  审计链完整性校验: {trail.verify_integrity()}")

    # 按 actor 查询
    results = trail.query(actor="user-001")
    print(f"\n  查询 actor=user-001: {len(results)} 条")
    for r in results:
        print(f"    [{r.action}] {r.resource} -> {r.result}")

    # 按 result 查询
    denied = trail.query(result="denied")
    print(f"\n  查询 result=denied: {len(denied)} 条")
    for r in denied:
        print(f"    [{r.actor}] {r.action} -> {r.result}: {r.detail}")

    # 查看哈希链
    print("\n  审计哈希链:")
    for i, e in enumerate(trail._entries):
        print(f"    [{i}] prev={e.prev_hash[:8]}... -> hash={e.entry_hash[:8]}...")
    print()


def main():
    print("AOS 最小可运行 Demo")
    print("演示 5 个核心能力: 能力路由 / 内核三职责 / 物种进化 / 免疫系统 / 合规审计")
    print()

    demo_capability_routing()
    demo_kernel_three_pillars()
    demo_species_evolution()
    demo_immunity_system()
    demo_compliance_audit()

    print("=" * 60)
    print("全部 5 个演示完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
