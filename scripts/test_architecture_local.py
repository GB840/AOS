import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import time
from core.brain import UnifiedBrain
from core.task_classifier import TaskClassifier, TaskLevel, TaskChannel

def test_task_classifier():
    print("\n" + "="*70)
    print("🎯 测试1: 任务分级器 (L1-L5)")
    print("="*70)
    
    classifier = TaskClassifier()
    
    test_cases = [
        ("今天天气怎么样", "L1 - 简单问答"),
        ("帮我搜索一下机器学习", "L1 - 知识查询"),
        ("帮我创建一个用户注册API", "L2 - 单步任务"),
        ("写一个Python脚本处理CSV数据", "L2 - 单步任务"),
        ("设计一个电商平台的系统架构，包含前端、后端、数据库", "L3 - 多步骤单角色"),
        ("开发一个完整的博客系统，包括用户认证、文章管理、评论功能", "L4 - 多角色协作"),
        ("开发一个企业级电商平台，包含用户系统、商品管理、订单系统、支付集成、物流跟踪、数据分析", "L5 - 复杂项目"),
    ]
    
    for task, expected in test_cases:
        result = classifier.classify(task)
        print(f"任务: {task[:40]}...")
        print(f"  → 级别: {result.level.value}, 通道: {result.channel.value}, 步骤: {result.estimated_steps}")
        print(f"  → 原因: {result.reason}")
        print()

def test_meta_debate(brain):
    print("\n" + "="*70)
    print("🎯 测试2: 元辩论引擎 (动态角色分配)")
    print("="*70)
    
    debate = brain.meta_debate
    candidates = debate.prepare_candidates("开发一个完整的博客系统")
    
    print(f"候选角色 ({len(candidates)}个):")
    for i, candidate in enumerate(candidates[:5], 1):
        print(f"  {i}. {candidate.name} - 匹配度: {candidate.score:.2f}")
    
    debate_result = debate.run_full_debate("开发一个完整的博客系统", max_candidates=5, top_k=3)
    
    print(f"\n元辩论结果:")
    print(f"  选中角色: {[r.name for r in debate_result.selected_roles]}")
    print(f"  角色白名单: {debate_result.role_whitelist}")
    print(f"  成本预算: {debate_result.cost_budget}")
    print(f"  模型策略: {debate_result.model_strategy}")

def test_lemon_orchestrator(brain):
    print("\n" + "="*70)
    print("🎯 测试3: LEMON学习型编排器")
    print("="*70)
    
    lemon = brain.lemon_orchestrator
    spec = lemon.generate_spec("开发一个简单的待办事项应用", ["backend_dev", "frontend_dev"])
    
    print(f"编排说明书 ID: {spec.task_id}")
    print(f"任务描述: {spec.task_description}")
    print(f"角色白名单: {spec.roles}")
    print(f"\n步骤 ({len(spec.steps)}个):")
    for i, step in enumerate(spec.steps, 1):
        print(f"  {i}. [{step.executor}] {step.description}")
        if step.dependencies:
            print(f"     ← 依赖: {step.dependencies}")

def test_swarm_flow(brain):
    print("\n" + "="*70)
    print("🎯 测试4: SwarmFlow工作流引擎")
    print("="*70)
    
    lemon = brain.lemon_orchestrator
    spec = lemon.generate_spec("开发一个简单的待办事项应用", ["backend_dev", "frontend_dev"])
    
    swarm = brain.swarm_flow
    result = swarm.execute_workflow(spec)
    
    print(f"工作流状态: {result.status.value}")
    print(f"执行步骤: {len(result.step_results)}个")
    for step_result in result.step_results:
        print(f"  [{step_result.step_id}] {step_result.status.value}: {step_result.output[:50]}...")
    
    print(f"\n汇总输出: {result.summary[:100]}...")

def test_task_fingerprint(brain):
    print("\n" + "="*70)
    print("🎯 测试5: 任务指纹记忆系统")
    print("="*70)
    
    fp = brain.task_fingerprint
    
    task1 = "开发一个待办事项应用"
    task2 = "开发一个待办任务管理系统"
    
    fp1 = fp.generate_fingerprint(task1)
    fp2 = fp.generate_fingerprint(task2)
    
    print(f"任务1: {task1}")
    print(f"  指纹: {fp1}")
    print(f"任务2: {task2}")
    print(f"  指纹: {fp2}")
    
    fp.store_template(
        task=task1,
        level='L3',
        role_whitelist=['backend_dev', 'frontend_dev'],
        orchestration_spec={'id': 'spec_123'},
        model_strategy={'backend_dev': 'low', 'frontend_dev': 'medium'}
    )
    
    template = fp.get_template(fp1)
    print(f"\n检索模板: {template}")
    
    similar = fp.search_similar(task2)
    print(f"相似模板: {len(similar)}个")

def test_brain_routing(brain):
    print("\n" + "="*70)
    print("🎯 测试6: UnifiedBrain通道路由")
    print("="*70)
    
    test_messages = [
        "今天什么日子",
        "帮我写一个Python函数计算斐波那契数列",
        "设计一个电商系统的数据库架构",
    ]
    
    for msg in test_messages:
        print(f"\n用户消息: {msg}")
        start = time.time()
        result = brain.chat(msg)
        elapsed = time.time() - start
        
        print(f"  → 级别: {result.get('level', 'N/A')}")
        print(f"  → 通道: {result.get('channel', 'N/A')}")
        print(f"  → 耗时: {elapsed:.2f}秒")
        response = result.get('response', '')
        print(f"  → 响应: {response[:80]}...")

if __name__ == "__main__":
    print("\n🚀 AOS v5.0 四层架构完整测试")
    print("="*70)
    
    try:
        brain = UnifiedBrain()
        
        test_task_classifier()
        test_meta_debate(brain)
        test_lemon_orchestrator(brain)
        test_swarm_flow(brain)
        test_task_fingerprint(brain)
        test_brain_routing(brain)
        
        print("\n" + "="*70)
        print("✅ 所有测试完成!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
