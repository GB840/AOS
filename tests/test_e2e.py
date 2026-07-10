from src.core.brain import get_brain
import time

print('=== System Init Test ===')
brain = get_brain()
print('Hermes type:', type(brain.hermes).__name__)
print('DeerFlow type:', type(brain.deerflow).__name__)
print('Real DeerFlow:', brain.deerflow.real_deerflow)
print('Skill count:', len(brain.skill_registry._skills))
print('Execution layer: sandbox=', brain.sandbox, ', tool_executor=', brain.tool_executor)

print()
print('=== Execution Test ===')
result = brain.sandbox.execute_code('test_sbx', 'print("Hello from sandbox!")', 'python')
print('Sandbox result:', result)

result = brain.tool_executor.execute_tool('execute_python', {'code': 'print("Hello from tool executor!")'})
print('Tool executor result:', result)

result = brain.workspace.create_workspace('test_workspace')
print('Workspace create:', result)

print()
print('=== DeerFlow Gateway Test ===')
if brain.deerflow.real_deerflow:
    print('Testing DeerFlow chat...')
    try:
        response = brain.deerflow.chat('Hello, what can you do?')
        print('DeerFlow response:', response[:100], '...')
    except Exception as e:
        print('DeerFlow chat error:', e)

print()
print('=== Health Check ===')
health = brain.health_check()
status = health.get('status', 'unknown')
components = list(health.get('components', {}).keys())
print('Status:', status)
print('Components:', components)

print()
print('All tests completed!')
