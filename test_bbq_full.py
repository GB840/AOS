import sys
sys.path.insert(0, 'd:/AOS/src')

from kernel.industry.restaurant.bbq_shop import create_bbq_system

print('=' * 60)
print('🍢 烧烤店 AI 运营闭环系统 - 完整测试')
print('=' * 60)

# 创建系统
system = create_bbq_system('老王烧烤')
print(f'\n✅ 系统创建成功: {system.shop_name} (ID: {system.shop_id})')

# 每日运营
print('\n' + '=' * 60)
print('📋 第一步：生成今日运营计划')
print('=' * 60)
result = system.daily_operation()
plan = result['plan']

print(f'\n📅 计划ID: {plan["id"]}')
print(f'\n📊 数据分析:')
analysis = plan['analysis']
print(f'   - 7日营收: {analysis["sales"]["total_revenue"]}')
print(f'   - 订单数: {analysis["sales"]["order_count"]}')
print(f'   - 活跃会员: {analysis["members"]["active_members"]}')

print(f'\n🎯 今日目标:')
targets = plan['targets']
print(f'   - 营收目标: {targets["daily_revenue"]}')
print(f'   - 新增会员: {targets["new_members"]}')

print(f'\n📝 内容计划 ({len(plan["content_plans"])}条):')
for cp in plan['content_plans']:
    print(f'   - [{cp["priority"]}] {cp["channel"]}: {cp["topic"]}')

# 处理客户咨询
print('\n' + '=' * 60)
print('💬 第二步：智能客服接待')
print('=' * 60)

queries = [
    '今天有什么好吃的？',
    '羊肉串多少钱？',
    '可以预订吗？',
    '有什么优惠？',
]

for query in queries:
    response = system.handle_consultation('douyin', query)
    print(f'\n👤 客户: {query}')
    print(f'🤖 回复: {response["response"][:80]}...')

# 处理订单
print('\n' + '=' * 60)
print('🛒 第三步：订单处理')
print('=' * 60)

order_result = system.handle_order('offline', [
    {'dish_name': '招牌羊肉串', 'quantity': 20},
    {'dish_name': '秘制烤翅', 'quantity': 10},
    {'dish_name': '拍黄瓜', 'quantity': 2},
    {'dish_name': '啤酒', 'quantity': 10},
], member_id='m123')

print(f'\n✅ 订单创建成功: {order_result["order_id"]}')
print(f'\n📦 订单详情:')
print(f'   - 原价: {order_result["total_amount"]}')
print(f'   - 优惠: {order_result["discount"]}')
print(f'   - 实付: {order_result["actual_amount"]}')
print(f'\n✨ 智能推荐:')
for rec in order_result['recommendations']:
    print(f'   - {rec}')

# 获取运营报告
print('\n' + '=' * 60)
print('📈 第四步：获取智能运营报告')
print('=' * 60)

report = system.get_report()
sales = report['sales_analysis']

print(f'\n📊 销售分析:')
print(f'   - 7日营收: {sales["total_revenue"]}')
print(f'   - 订单数: {sales["order_count"]}')
print(f'   - 客单价: {sales["avg_order_value"]}')

print(f'\n🔥 热销菜品:')
for dish in sales['top_dishes'][:5]:
    print(f'   - {dish["name"]}: {dish["sales"]}份')

members = report['member_analysis']
print(f'\n👥 会员分析:')
print(f'   - 总会员: {members["total_members"]}')
print(f'   - 活跃会员: {members["active_members"]}')
print(f'   - 活跃率: {members["active_rate"]}%')

print(f'\n💡 智能建议 ({len(report["smart_suggestions"])}条):')
for suggestion in report['smart_suggestions']:
    print(f'   - [{suggestion["priority"]}] {suggestion["title"]}:')
    print(f'     {suggestion["suggestion"]}')

# 获取仪表盘
print('\n' + '=' * 60)
print('📺 第五步：实时数据仪表盘')
print('=' * 60)

dashboard = system.get_dashboard()
realtime = dashboard['realtime']

print(f'\n⚡ 实时数据:')
print(f'   - 今日订单: {realtime["today_orders"]}')
print(f'   - 今日营收: {realtime["today_revenue"]}')
print(f'   - 活跃会话: {realtime["active_sessions"]}')
print(f'   - 待发布内容: {realtime["pending_contents"]}')

# 保存数据
print('\n' + '=' * 60)
print('💾 第六步：数据备份')
print('=' * 60)

system.save_data()
backup_path = system.backup_data()
print(f'\n✅ 数据已保存')
print(f'✅ 备份文件: {backup_path}')

print('\n' + '=' * 60)
print('🎉 烧烤店 AI 运营闭环测试完成！')
print('=' * 60)
print('\n核心流程验证通过:')
print('  [AI运营官] ──策划──> [内容生产] ──发布──> [客服承接] ──数据──> [运营官]')
