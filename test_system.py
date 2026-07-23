import sys
sys.path.insert(0, 'd:/AOS/src')

from kernel.industry.restaurant.bbq_shop import create_bbq_system

system = create_bbq_system('老王烧烤')
print('System created')

result = system.daily_operation()
print('Plan:', result['plan']['id'])
print('Contents:', result['contents_generated'], 'items')

summary = result['summary']
print('Revenue 7d:', summary['analysis_summary']['total_revenue_7d'])

response = system.handle_consultation('douyin', 'what good today?')
print('Response:', response['response'][:50])

order = system.handle_order('offline', [
    {'dish_name': '招牌羊肉串', 'quantity': 10},
    {'dish_name': '拍黄瓜', 'quantity': 1},
], member_id='m123')
print('Order:', order['order_id'], 'amount:', order['actual_amount'])
print('Recommendations:', order['recommendations'])

report = system.get_report()
print('Smart suggestions:', len(report['smart_suggestions']))

dashboard = system.get_dashboard()
print('Today orders:', dashboard['realtime']['today_orders'])

print('All tests passed!')
