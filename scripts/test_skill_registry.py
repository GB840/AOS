"""测试技能注册系统"""
import sys
sys.path.insert(0, str(__file__).rsplit("\\", 2)[0])

from src.skills.agency_roles import register_agency_roles, registry

register_agency_roles()
stats = registry.get_stats()

print(f"技能总数: {stats['total']}")
print(f"分类数: {len(stats['categories'])}")
print("\n分类统计:")
for k, v in sorted(stats["categories"].items()):
    print(f"  {k}: {v}")

print("\n前10个技能名称:")
for name in stats["skill_names"][:10]:
    print(f"  - {name}")
