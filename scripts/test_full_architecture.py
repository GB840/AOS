"""
完整架构测试脚本 - 测试所有新增模块

测试内容:
1. OpenClaw 任务入口 (L1)
2. AgentCARD 成本优化策略
3. LightNegotiation 轻量协商 (L3)
4. FinalDelivery 终审交付 (L4)
5. 完整端到端流程
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import logging
logging.basicConfig(level=logging.INFO)

from core.brain import UnifiedBrain


def test_open_claw(brain):
    print("\n" + "="*70)
    print("🎯 测试1: OpenClaw 任务入口 (L1)")
    print("="*70)
    
    open_claw = brain.open_claw
    
    ticket = open_claw.process_request("帮我开发一个电商平台的用户认证系统")
    
    print(f"工单ID: {ticket.ticket_id}")
    print(f"任务ID: {ticket.task_id}")
    print(f"清洗后需求: {ticket.cleaned_requirement.cleaned_text[:100]}...")
    print(f"意图识别: {ticket.cleaned_requirement.intent}")
    print(f"实体提取: {ticket.cleaned_requirement.entities}")
    print(f"需求点: {ticket.cleaned_requirement.requirements}")
    print(f"约束条件: {ticket.cleaned_requirement.constraints}")
    print(f"优先级: {ticket.cleaned_requirement.priority}")
    print(f"分级结果: {ticket.classification.get('level') if ticket.classification else 'unknown'}")
    print(f"路由通道: {ticket.routing_channel}")
    
    if ticket.cleaned_requirement.missing_info:
        prompt = open_claw.get_missing_info_prompt(ticket.cleaned_requirement)
        print(f"\n缺失信息提示: {prompt}")


def test_agent_card(brain):
    print("\n" + "="*70)
    print("🎯 测试2: AgentCARD 成本优化策略")
    print("="*70)
    
    card = brain.agent_card
    
    strategy = card.determine_strategy("开发一个复杂的电商系统架构设计", "L5")
    print(f"策略确定: 初稿模型={strategy.draft_model.value}, 定稿模型={strategy.polish_model.value}")
    
    result = card.execute_full_pipeline("写一个Python函数计算斐波那契数列", "L2")
    print(f"生成阶段: {result.phase.value}")
    print(f"使用模型: {result.model_used}")
    print(f"成本估算: ${result.cost_usd:.4f}")
    print(f"质量评分: {result.quality_score:.2f}")
    print(f"是否润色: {'是' if result.revised else '否'}")
    
    cost_saving = card.calculate_cost_saving("L4")
    print(f"\n成本节省比例: {cost_saving:.1%}")
    
    stats = card.get_strategy_stats()
    print(f"策略统计: {stats}")


def test_light_negotiation(brain):
    print("\n" + "="*70)
    print("🎯 测试3: LightNegotiation 轻量协商 (L3)")
    print("="*70)
    
    negotiation = brain.light_negotiation
    
    result = negotiation.run_negotiation(
        main_role="backend_dev",
        support_role="frontend_dev",
        task="开发一个待办事项应用"
    )
    
    print(f"协商状态: {result.status.value}")
    print(f"主角色: {result.main_role}")
    print(f"辅助角色: {result.support_role}")
    print(f"备注: {result.notes}")
    print(f"\n任务拆分 ({len(result.tasks)}个):")
    for i, task in enumerate(result.tasks, 1):
        print(f"  {i}. [{task['role']}] {task['description']}")
        if task.get('dependencies'):
            print(f"     ← 依赖: {task['dependencies']}")


def test_final_delivery(brain):
    print("\n" + "="*70)
    print("🎯 测试4: FinalDelivery 终审交付 (L4)")
    print("="*70)
    
    delivery_system = brain.final_delivery
    
    outputs = {
        "core_code": """```python
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
```""",
        "documentation": "## 斐波那契函数文档\n\n### 功能说明\n计算斐波那契数列第n项",
    }
    
    quality_report = delivery_system.run_quality_checks("写斐波那契函数", outputs)
    print(f"质量审核结果:")
    print(f"  总分: {quality_report['overall_score']:.2f}")
    print(f"  通过数: {quality_report['passed']}/{quality_report['total_checks']}")
    print(f"  状态: {quality_report['status']}")
    print(f"\n审核详情:")
    for check in quality_report['details']:
        status = "✅" if check['passed'] else "❌"
        print(f"  {status} [{check['category']}] {check['description']} - {check['score']:.2f}分")
    
    deliverables = delivery_system.package_deliverables("写斐波那契函数", outputs, quality_report)
    print(f"\n打包交付物 ({len(deliverables)}个):")
    for d in deliverables:
        print(f"  - [{d.type.value}] {d.name} ({d.format})")
    
    delivery = delivery_system.execute_full_delivery(
        task_id="TASK-001",
        ticket_id="TKT-20260706-abc123",
        task_description="写斐波那契函数",
        outputs=outputs,
        level="L2",
        role_whitelist=["backend_dev"],
    )
    
    print(f"\n交付完成:")
    print(f"  交付ID: {delivery.delivery_id}")
    print(f"  状态: {delivery.status}")
    print(f"  是否存入记忆: {'是' if delivery.stored_in_memory else '否'}")
    print(f"\n交付摘要:\n{delivery.summary}")


def test_full_pipeline(brain):
    print("\n" + "="*70)
    print("🎯 测试5: 完整端到端流程 (OpenClaw→分级→执行→交付)")
    print("="*70)
    
    task = "设计一个电商平台的数据库架构"
    
    print(f"步骤1: OpenClaw接单清洗...")
    ticket = brain.open_claw.process_request(task)
    level = ticket.classification.get('level')
    
    print(f"步骤2: 任务分级 → {level}")
    
    if level == "L4":
        print(f"步骤3: 元辩论选角色...")
        debate_result = brain.meta_debate.run_full_debate(task)
        print(f"  选中角色: {debate_result.role_whitelist}")
        
        print(f"步骤4: LEMON生成编排说明书...")
        spec = brain.lemon_orchestrator.generate_spec(task, debate_result.role_whitelist)
        print(f"  说明书ID: {spec.task_id}")
        
        print(f"步骤5: SwarmFlow执行工作流...")
        result = brain.swarm_flow.execute_workflow(spec)
        print(f"  工作流状态: {result.status.value}")
        
        print(f"步骤6: FinalDelivery终审交付...")
        outputs = {"workflow_result": result.summary}
        delivery = brain.final_delivery.execute_full_delivery(
            task_id=ticket.task_id,
            ticket_id=ticket.ticket_id,
            task_description=task,
            outputs=outputs,
            level=level,
            role_whitelist=debate_result.role_whitelist,
        )
        print(f"  交付完成: {delivery.delivery_id}")
    
    elif level == "L3":
        print(f"步骤3: 轻量协商...")
        roles = ["backend_dev", "frontend_dev"]
        result = brain.light_negotiation.run_negotiation(roles[0], roles[1], task)
        print(f"  协商结果: {result.status.value}")
        
        print(f"步骤4: 执行任务...")
        print(f"  任务已拆分执行")
        
        print(f"步骤5: FinalDelivery交付...")
        outputs = {"result": "任务执行完成"}
        delivery = brain.final_delivery.execute_full_delivery(
            task_id=ticket.task_id,
            ticket_id=ticket.ticket_id,
            task_description=task,
            outputs=outputs,
            level=level,
            role_whitelist=roles,
        )
        print(f"  交付完成: {delivery.delivery_id}")
    
    else:
        print(f"步骤3: {level}任务直接执行...")
        print(f"  执行完成")


def test_task_fingerprint_reuse(brain):
    print("\n" + "="*70)
    print("🎯 测试6: 任务指纹记忆复用")
    print("="*70)
    
    fp = brain.task_fingerprint
    
    task1 = "开发一个待办事项应用"
    task2 = "开发一个todo任务管理系统"
    
    fp.store_template(
        task=task1,
        level='L3',
        role_whitelist=['backend_dev', 'frontend_dev'],
        orchestration_spec={'version': '1.0'},
        model_strategy={'backend_dev': 'local', 'frontend_dev': 'medium'},
    )
    
    similar = fp.search_similar(task2)
    print(f"相似任务检索: '{task2}'")
    print(f"找到相似模板: {len(similar)}个")
    for s in similar:
        print(f"  - 级别: {s.level}, 角色: {s.role_whitelist}")
    
    stats = fp.get_stats()
    print(f"\n记忆库统计: {stats}")


if __name__ == "__main__":
    print("="*70)
    print("🏗️  AOS v5.0 完整架构测试")
    print("="*70)
    
    brain = UnifiedBrain()
    
    test_open_claw(brain)
    test_agent_card(brain)
    test_light_negotiation(brain)
    test_final_delivery(brain)
    test_full_pipeline(brain)
    test_task_fingerprint_reuse(brain)
    
    print("\n" + "="*70)
    print("✅ 所有测试完成!")
    print("="*70)