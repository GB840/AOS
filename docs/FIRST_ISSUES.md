# Good First Issues

面向新贡献者的入门任务，按难度和预计耗时排序。

## 简单（预计1-2小时）

1. **新增行业模板** - 添加一个新的行业模板（如：教育培训、餐饮服务）
   - 难度：简单
   - 文件：src/kernel/danchuang/templates/__init__.py
   - 参考：已有模板（HARDWARE/ECOMMERCE等）
   - 完成标准：新增IndustryType枚举值 + IndustryTemplate实例

2. **修复文档typo** - 修正文档中的错别字或格式问题
   - 难度：简单
   - 文件：docs/ 目录下任意.md文件
   - 完成标准：ruff check无新增warning

3. **新增适配器测试** - 为缺少测试的适配器补充测试用例
   - 难度：简单
   - 文件：tests/ 目录
   - 参考：tests/test_search_adapter.py 的测试模式
   - 完成标准：pytest tests/test_xxx.py 全绿

4. **补充Capability枚举注释** - 为 core/fabric/capability.py 中缺少文档的能力添加docstring
   - 难度：简单
   - 文件：src/core/fabric/capability.py
   - 完成标准：每个Capability成员都有docstring

## 中等（预计3-5小时）

5. **新增搜索源** - 在SearchAdapter中添加一个新的免费搜索源
   - 难度：中等
   - 文件：src/core/fabric/adapters/search_adapter.py
   - 参考：已有源（anysearch/baidu/bing等）
   - 完成标准：新源在invoke()中被调用，失败时正确降级

6. **新增OPC行业角色** - 为单创OS添加一个垂直行业的专业角色
   - 难度：中等
   - 文件：src/kernel/danchuang/opc/agency_registry.py
   - 完成标准：新角色可被 plan_company() 调用

7. **SLA告警通知** - 在sla.py中添加异常告警回调机制
   - 难度：中等
   - 文件：src/kernel/monitoring/sla.py
   - 完成标准：可用性<99.9%或P95>500ms时触发回调

8. **支付回调集成** - 在FastAPI中注册billing_api的路由
   - 难度：中等
   - 文件：src/api/main.py + src/api/billing_api.py
   - 完成标准：POST /api/billing/callback/alipay 和 /wechat 可访问

## 进阶（预计1-2天）

9. **新增内容适配器** - 实现一个新内容生产能力的适配器
   - 难度：进阶
   - 文件：src/core/fabric/adapters/新适配器.py
   - 参考：src/core/fabric/adapters/content_marketer_adapter.py
   - 完成标准：继承BaseAgentAdapter，通过FabricHub可路由

10. **创业日历视图** - 为租户后台添加日历视图展示工单排期
    - 难度：进阶
    - 文件：web/tenant/index.html
    - 完成标准：月/周视图切换，工单状态颜色标注

## 如何认领

1. 在 GitHub Issues 中搜索对应编号
2. 评论 "I'd like to work on this"
3. 等待维护者确认后开始
4. 完成后创建PR，关联Issue
