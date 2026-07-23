"""单创OS v2.0 综合验证测试 - 快速验证版。"""
import sys
sys.path.insert(0, 'src')
import uuid
from kernel.danchuang import DanchuangOS

passed = 0
failed = 0

def test(name, func):
    global passed, failed
    try:
        func()
        print(f'  ✅ {name}')
        passed += 1
    except Exception as e:
        print(f'  ❌ {name}: {e}')
        failed += 1

print('=== 初始化 DanchuangOS v2.0 ===')
os = DanchuangOS()
print('初始化完成')

print()
print('=== 系统状态 ===')
status = os.system_status()
print(f'  专业角色数: {status.total_agents}')
print(f'  工作流模板数: {status.total_playbooks}')
print(f'  支持行业: {len(status.supported_industries)}个')

test_email = f'test_{uuid.uuid4().hex[:8]}@hw.com'
t = os.create_tenant('测试租户', test_email, 'standard', 'hardware')
tid = t['tenant_id']

print()
print('=== 核心模块验证 ===')

def test_agency():
    hier = os.get_agency_hierarchy()
    assert len(hier) == 5, f'OPC岗位数应为5，实际{len(hier)}'
    total = sum(v.get('agent_count', 0) for v in hier.values())
    assert total > 100, f'专业角色数应>100，实际{total}'
    agents = os.list_agency_agents(limit=3)
    assert len(agents) == 3
    results = os.search_agents('产品经理')
    assert len(results) >= 1

test('Agency角色库（267个专业角色）', test_agency)

def test_industry():
    industries = os.list_industries()
    assert len(industries) >= 5
    hw = os.get_industry_template('hardware')
    assert hw is not None
    assert 'role_config' in hw

test('行业模板（5大行业）', test_industry)

def test_tenant():
    t2 = os.get_tenant(tid)
    assert t2 is not None
    assert t2['name'] == '测试租户'
    all_t = os.list_tenants()
    assert len(all_t) >= 1

test('租户管理', test_tenant)

def test_plans():
    plans = os.list_plans()
    assert len(plans) == 4
    quota = os.check_quota(tid, 'goal_set_count', 1)
    assert 'allowed' in quota
    assert 'remaining' in quota

test('套餐与用量（4档套餐）', test_plans)

def test_playbook():
    pbs = os.list_playbooks()
    assert len(pbs) >= 5
    hw_pbs = os.list_playbooks(industry='hardware')
    assert len(hw_pbs) >= 1
    sug = os.suggest_playbook('开发青少年护眼眼镜', 'hardware')
    assert sug is not None

test('Playbook工作流模板（5套）', test_playbook)

def test_workflow():
    wf = os.create_workflow(tid, '开发护眼眼镜MVP')
    assert 'workflow_id' in wf
    wf_id = wf['workflow_id']
    prog = os.get_workflow_progress(wf_id)
    assert 'progress_percent' in prog
    steps = wf.get('steps', [])
    if steps:
        step_id = steps[0]['step_id']
        os.start_workflow_step(wf_id, step_id)
        os.complete_workflow_step(wf_id, step_id, output='完成')
    cps = os.list_checkpoints(wf_id)
    assert isinstance(cps, list)

test('工作流实例 + 检查点', test_workflow)

def test_crew():
    result = os.run_crew_from_template(tid, 'startup_mvp')
    assert result.get('success') == True
    assert 'result' in result

test('Crew协作编排', test_crew)

def test_startup_engine():
    result = os.set_goal(tid, '开发青少年坐姿矫正眼镜')
    assert result is not None
    st = os.get_status(tid)
    assert st is not None

test('创业目标调度引擎', test_startup_engine)

def test_admin():
    dash = os.admin_dashboard()
    assert 'tenant_stats' in dash, f'dashboard keys: {list(dash.keys())}'
    assert 'total' in dash['tenant_stats'] or 'total_tenants' in dash['tenant_stats']
    health = os.admin_system_health()
    assert 'status' in health, f'health keys: {list(health.keys())}'

test('平台管理员API', test_admin)

def test_opc_roles():
    roles = os.get_opc_roles()
    assert len(roles) == 5
    tenant_roles = os.get_tenant_roles(tid)
    assert len(tenant_roles) == 5

test('OPC 5大岗位体系', test_opc_roles)

print()
print('=' * 60)
print(f'测试结果: {passed} 通过, {failed} 失败')
if failed == 0:
    print('✅ 全部模块测试通过！单创OS v2.0 炼化融合完成')
else:
    print(f'⚠️  有 {failed} 个模块需要修复')
print('=' * 60)
