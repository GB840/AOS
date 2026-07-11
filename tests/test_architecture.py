import asyncio
import sys
import pytest
sys.path.insert(0, str(__file__).rsplit('/', 1)[0] if '/' in str(__file__) else str(__file__).rsplit('\\', 1)[0])

pytest.importorskip("deerflow.graph")
from deerflow.graph import PlannerAgent
from common import registry, event_bus, EventType, ProtocolType, ProtocolFactory, translator, china_adapter


async def test_protocol_layer():
    print("\n" + "="*60)
    print("测试1: 协议层 (Protocol Layer)")
    print("="*60)
    
    factory = ProtocolFactory()
    
    a2a_adapter = factory.create_adapter(ProtocolType.A2A)
    mcp_adapter = factory.create_adapter(ProtocolType.MCP)
    fc_adapter = factory.create_adapter(ProtocolType.FUNCTION_CALLING)
    
    print(f"✓ A2A 适配器: {type(a2a_adapter).__name__}")
    print(f"✓ MCP 适配器: {type(mcp_adapter).__name__}")
    print(f"✓ FC 适配器: {type(fc_adapter).__name__}")
    
    test_message = {
        "message_id": "test-123",
        "type": "task",
        "protocol": ProtocolType.A2A,
        "sender_id": "planner",
        "receiver_id": "worker",
        "content": {"capability": "test", "params": {"key": "value"}},
        "context": {"trace_id": "abc"},
        "timestamp": 1234567890.0,
    }
    
    serialized = a2a_adapter.serialize(test_message)
    print("✓ A2A 序列化测试通过")
    
    translated = translator.translate(serialized, ProtocolType.A2A, ProtocolType.MCP)
    print("✓ A2A → MCP 转换测试通过")
    
    translated_back = translator.translate(translated, ProtocolType.MCP, ProtocolType.A2A)
    print("✓ MCP → A2A 转换测试通过")


async def test_registry():
    print("\n" + "="*60)
    print("测试2: Agent Registry (动态发现)")
    print("="*60)
    
    agents = registry.get_all_agents()
    print(f"✓ 已注册 Agent 数量: {len(agents)}")
    
    for agent in agents:
        print(f"  - {agent['agent_name']}: {agent['capabilities']}")
    
    code_agents = registry.find_agents_by_capability("code_generation")
    print(f"✓ 代码生成能力 Agent: {len(code_agents)}个")
    
    best_agent = registry.find_best_agent("写一个Python脚本", ["code_generation", "script_execution"])
    if best_agent:
        print(f"✓ 最佳匹配 Agent: {best_agent['agent_name']}")


async def test_event_bus():
    print("\n" + "="*60)
    print("测试3: Event Bus (事件总线)")
    print("="*60)
    
    received_events = []
    
    def test_handler(event):
        received_events.append(event)
    
    event_bus.subscribe(EventType.TASK_CREATED, test_handler)
    print("✓ 订阅测试事件成功")
    
    event_bus.publish(
        EventType.TASK_CREATED,
        source="test",
        payload={"task_id": "test-001", "task": "测试任务"},
    )
    
    await asyncio.sleep(0.1)
    
    assert len(received_events) == 1
    print("✓ 事件发布/订阅测试通过")
    
    event_bus.unsubscribe(EventType.TASK_CREATED, test_handler)
    print("✓ 取消订阅测试成功")


async def test_china_adapter():
    print("\n" + "="*60)
    print("测试4: 国产适配层 (China Adaptation Layer)")
    print("="*60)
    
    bridges = china_adapter.bridges
    print(f"✓ 已注册模型桥接器: {len(bridges)}个")
    
    for provider, bridge in bridges.items():
        print(f"  - {provider.value}: {type(bridge).__name__}")
    
    result = await china_adapter.chat([{"role": "user", "content": "你好"}])
    print("✓ 中文任务路由测试通过")
    print(f"  结果: {result.get('content', '')[:50]}...")


async def test_planner():
    print("\n" + "="*60)
    print("测试5: Planner Agent (规划引擎)")
    print("="*60)
    
    planner = PlannerAgent(ollama_base_url="http://localhost:11434", model="qwen2.5:7b")
    
    task = "帮我写一个Python脚本，计算1到100的和"
    
    print(f"任务: {task}")
    print("执行中...")
    
    try:
        result = await planner.run(task)
        print("✓ 任务执行完成")
        print(f"  状态: {result['task_status']}")
        print(f"  步骤数: {len(result['plan'])}")
        
        for i, step in enumerate(result['plan']):
            print(f"  步骤{i+1}: [{step['worker_type']}] {step['description']} - {step['status']}")
        
        if 'final_summary' in result['results']:
            print(f"  总结: {result['results']['final_summary'][:100]}...")
            
    except Exception as e:
        print(f"✗ 执行失败: {e}")


async def main():
    await test_protocol_layer()
    await test_registry()
    await test_event_bus()
    await test_china_adapter()
    await test_planner()
    
    print("\n" + "="*60)
    print("所有测试完成!")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())