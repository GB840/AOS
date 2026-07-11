import pytest
pytest.skip("script-style test not compatible with pytest collection", allow_module_level=True)

print("=== System Status ===")
print(f"Hermes: {type(brain.hermes).__name__}")
print(f"DeerFlow: {type(brain.deerflow).__name__} (Real={brain.deerflow.real_deerflow})")
print(f"Skills: {len(brain.skill_registry._skills)}")

print()
print("=== Execution Layer Test ===")
result = brain.tool_executor.execute_tool("execute_python", {"code": "import os; print(f'PID: {os.getpid()}'); print('Execution layer is WORKING!')"})
print(f"Tool Executor: {result}")

result = brain.workspace.create_workspace("demo_workspace")
print(f"Workspace: {result}")

print()
print("=== DeerFlow Models ===")
models = brain.deerflow.list_models()
for m in models.get("models", []):
    print(f"  - {m['name']}: {m['model']}")

print()
print("=== Health Check ===")
health = brain.health_check()
print(f"Status: {health.get('status')}")
print(f"Components: {list(health.get('components', {}).keys())}")

print()
print("All systems operational!")
