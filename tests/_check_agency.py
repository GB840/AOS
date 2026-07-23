import sys
sys.path.insert(0, 'src')
from kernel.danchuang.opc.agency_registry import get_agency_registry

reg = get_agency_registry()
hier = reg.get_full_hierarchy()
total = sum(v.get('agent_count', 0) for v in hier.values())
print(f'从文件加载的角色数: {total}')
print()
print('各部门映射:')
for role, data in hier.items():
    count = data["agent_count"]
    print(f'  {role}: {count} 个')
    agents = data.get('agents', [])
    if agents:
        names = [a["name"] for a in agents[:3]]
        print(f'    示例: {names}')
