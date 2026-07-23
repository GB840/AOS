import sys
sys.path.insert(0, 'src')

print('检查集成模块...')

try:
    from kernel.danchuang.integrations import LangGraphWorkflowEngine, CrewAIOrchestrator
    print('✅ LangGraph + CrewAI 集成模块导入成功')
except Exception as e:
    print(f'❌ 导入失败: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

from kernel.danchuang.engine.playbook_library import PlaybookLibrary

lib = PlaybookLibrary()
template = lib.get_template('hardware_dev')
print(f'模板: {template.name}, 步骤数: {len(template.steps)}')

print('\n--- 测试 LangGraph 引擎 ---')
lg = LangGraphWorkflowEngine()
result = lg.run(
    template=template,
    goal='低成本量产西南方言青少年坐姿矫正AI音频眼镜',
    tenant_id='test_tenant',
    workflow_id='test_wf_001',
    context={'industry': 'hardware'}
)
print(f'完成步骤: {len(result["completed_steps"])}/{result["completed_steps"]}')
print(f'最终输出前100字: {result["final_output"][:100]}...')

print('\n--- 测试 CrewAI 引擎 ---')
crew = CrewAIOrchestrator(verbose=False)
result2 = crew.run_from_template(
    template=template,
    goal='低成本量产西南方言青少年坐姿矫正AI音频眼镜',
    tenant_id='test_tenant',
    context={'industry': 'hardware'}
)
print(f'CrewAI 执行状态: {result2["success"]}')
print(f'任务数: {result2["task_count"]}')
print(f'输出前100字: {result2["raw_output"][:100]}...')

print('\n✅ 集成模块全部可用')
