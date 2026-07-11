"""
AOS Agency Roles Skills
========================

自动转换自 agency-agents-zh 的部门角色技能。

包含 271 个专业角色技能，覆盖 26 个领域。
"""

import logging
from skills.base import SkillRegistry

registry = SkillRegistry()

# ── Layer 2: agency_roles 收口薄壳（feature flag 驱动，默认关闭，零侵入）──
# 角色文件 opt-in: from skills.agency_roles import get_agency_runtime
from ._kernel_bridge import (  # noqa: E402,F401
    get_agency_runtime,
    is_kernel_consolidation_enabled,
    _KernelRuntime,
    _LegacyRuntime,
)

from .agent_list import AgentListSkill
from .catalog import CatalogSkill
from .contributing import ContributingSkill
from .readmezh_tw import ReadmezhTwSkill
from .人类学家 import 人类学家Skill
from .地理学家 import 地理学家Skill
from .历史学家 import 历史学家Skill
from .叙事学家 import 叙事学家Skill
from .心理学家 import 心理学家Skill
from .学习规划师 import 学习规划师Skill
from .品牌守护者 import 品牌守护者Skill
from .图像提示词工程师 import 图像提示词工程师Skill
from .包容性视觉专家 import 包容性视觉专家Skill
from .persona_走查专家 import Persona走查专家Skill
from .ui_设计师 import Ui设计师Skill
from .ux_架构师 import Ux架构师Skill
from .ux_研究员 import Ux研究员Skill
from .视觉叙事师 import 视觉叙事师Skill
from .趣味注入师 import 趣味注入师Skill
from .ai_数据修复工程师 import Ai数据修复工程师Skill
from .ai_工程师 import Ai工程师Skill
from .自主优化架构师 import 自主优化架构师Skill
from .后端架构师 import 后端架构师Skill
from .cms_开发者 import Cms开发者Skill
from .代码审查员 import 代码审查员Skill
from .代码库入职引导工程师 import 代码库入职引导工程师Skill
from .数据工程师 import 数据工程师Skill
from .数据库优化师 import 数据库优化师Skill
from .devops_自动化师 import Devops自动化师Skill
from .钉钉集成开发工程师 import 钉钉集成开发工程师Skill
from .drupal_购物车工程师 import Drupal购物车工程师Skill
from .邮件智能工程师 import 邮件智能工程师Skill
from .嵌入式固件工程师 import 嵌入式固件工程师Skill
from .嵌入式_linux_驱动工程师 import 嵌入式Linux驱动工程师Skill
from .飞书集成开发工程师 import 飞书集成开发工程师Skill
from .filament_优化专家 import Filament优化专家Skill
from .fpgaasic_数字设计工程师 import Fpgaasic数字设计工程师Skill
from .前端开发者 import 前端开发者Skill
from .git_工作流大师 import Git工作流大师Skill
from .故障响应指挥官 import 故障响应指挥官Skill
from .iot_方案架构师 import Iot方案架构师Skill
from .it_服务经理 import It服务经理Skill
from .机械设计工程师 import 机械设计工程师Skill
from .最小变更工程师 import 最小变更工程师Skill
from .移动应用开发者 import 移动应用开发者Skill
from .多智能体系统架构师 import 多智能体系统架构师Skill
from .orgscript_工程师 import Orgscript工程师Skill
from .上位机工程师 import 上位机工程师Skill
from .prompt_工程师 import Prompt工程师Skill
from .快速原型师 import 快速原型师Skill
from .安全工程师 import 安全工程师Skill
from .高级开发者 import 高级开发者Skill
from .软件架构师 import 软件架构师Skill
from .solidity_智能合约工程师 import Solidity智能合约工程师Skill
from .sre_站点可靠性工程师 import Sre站点可靠性工程师Skill
from .技术文档工程师 import 技术文档工程师Skill
from .威胁检测工程师 import 威胁检测工程师Skill
from .语音_ai_集成工程师 import 语音Ai集成工程师Skill
from .微信小程序开发者 import 微信小程序开发者Skill
from .wordpress_购物车工程师 import Wordpress购物车工程师Skill
from .簿记与财务总监 import 簿记与财务总监Skill
from .财务分析师 import 财务分析师Skill
from .财务预测分析师 import 财务预测分析师Skill
from .fpa_分析师 import Fpa分析师Skill
from .金融风控分析师 import 金融风控分析师Skill
from .投资研究员 import 投资研究员Skill
from .发票管理专家 import 发票管理专家Skill
from .税务策略师 import 税务策略师Skill
from .游戏音频工程师 import 游戏音频工程师Skill
from .游戏设计师 import 游戏设计师Skill
from .关卡设计师 import 关卡设计师Skill
from .叙事设计师 import 叙事设计师Skill
from .技术美术 import 技术美术Skill
from .blender_插件工程师 import Blender插件工程师Skill
from .godot_游戏脚本开发者 import Godot游戏脚本开发者Skill
from .godot_多人游戏工程师 import Godot多人游戏工程师Skill
from .godot_shader_开发者 import GodotShader开发者Skill
from .roblox_虚拟形象创作者 import Roblox虚拟形象创作者Skill
from .roblox_体验设计师 import Roblox体验设计师Skill
from .roblox_系统脚本工程师 import Roblox系统脚本工程师Skill
from .unity_架构师 import Unity架构师Skill
from .unity_编辑器工具开发者 import Unity编辑器工具开发者Skill
from .unity_多人游戏工程师 import Unity多人游戏工程师Skill
from .unity_shader_graph_美术师 import UnityShaderGraph美术师Skill
from .unreal_多人游戏架构师 import Unreal多人游戏架构师Skill
from .unreal_系统工程师 import Unreal系统工程师Skill
from .unreal_技术美术 import Unreal技术美术Skill
from .unreal_世界构建师 import Unreal世界构建师Skill
from .三维场景开发者 import 三维场景开发者Skill
from .gis_分析师 import Gis分析师Skill
from .bimgis_专家 import Bimgis专家Skill
from .地图制图设计师 import 地图制图设计师Skill
from .无人机实景测绘专家 import 无人机实景测绘专家Skill
from .geoaiml_工程师 import Geoaiml工程师Skill
from .地理处理专家 import 地理处理专家Skill
from .gis_质检工程师 import Gis质检工程师Skill
from .解决方案工程师 import 解决方案工程师Skill
from .空间数据工程师 import 空间数据工程师Skill
from .空间数据科学家 import 空间数据科学家Skill
from .技术顾问 import 技术顾问Skill
from .web_gis_开发工程师 import WebGis开发工程师Skill
from .绩效管理专家 import 绩效管理专家Skill
from .招聘专家 import 招聘专家Skill
from .backend_architect import BackendArchitectSkill
from .合同审查专家 import 合同审查专家Skill
from .制度文件撰写专家 import 制度文件撰写专家Skill
from .aeo_基础架构师 import Aeo基础架构师Skill
from .智能搜索优化师 import 智能搜索优化师Skill
from .ai_引文策略师 import Ai引文策略师Skill
from .应用商店优化师 import 应用商店优化师Skill
from .百度_seo_专家 import 百度Seo专家Skill
from .b站内容策略师 import B站内容策略师Skill
from .图书联合作者 import 图书联合作者Skill
from .轮播图增长引擎 import 轮播图增长引擎Skill
from .中国电商运营专家 import 中国电商运营专家Skill
from .中国市场本地化策略师 import 中国市场本地化策略师Skill
from .内容创作者 import 内容创作者Skill
from .跨境电商运营专家 import 跨境电商运营专家Skill
from .新闻情报官 import 新闻情报官Skill
from .抖音策略师 import 抖音策略师Skill
from .电商运营师 import 电商运营师Skill
from .邮件营销策略师 import 邮件营销策略师Skill
from .全球播客策略师 import 全球播客策略师Skill
from .增长黑客 import 增长黑客Skill
from .instagram_策展师 import Instagram策展师Skill
from .知识付费产品策划师 import 知识付费产品策划师Skill
from .快手策略师 import 快手策略师Skill
from .linkedin_内容创作专家 import Linkedin内容创作专家Skill
from .直播电商主播教练 import 直播电商主播教练Skill
from .多平台发布编排官 import 多平台发布编排官Skill
from .播客内容策略师 import 播客内容策略师Skill
from .pr_与传播经理 import Pr与传播经理Skill
from .私域流量运营师 import 私域流量运营师Skill
from .reddit_社区运营 import Reddit社区运营Skill
from .seo专家 import Seo专家Skill
from .短视频剪辑指导师 import 短视频剪辑指导师Skill
from .社交媒体策略师 import 社交媒体策略师Skill
from .tiktok_策略师 import Tiktok策略师Skill
from .twitter_互动官 import Twitter互动官Skill
from .视频优化专家 import 视频优化专家Skill
from .微信公众号管理 import 微信公众号管理Skill
from .微信公众号运营 import 微信公众号运营Skill
from .微博运营策略师 import 微博运营策略师Skill
from .微信视频号运营策略师 import 微信视频号运营策略师Skill
from .xtwitter_情报分析师 import Xtwitter情报分析师Skill
from .小红书运营专家 import 小红书运营专家Skill
from .小红书专家 import 小红书专家Skill
from .知乎策略师 import 知乎策略师Skill
from .付费媒体审计师 import 付费媒体审计师Skill
from .广告创意策略师 import 广告创意策略师Skill
from .社交广告策略师 import 社交广告策略师Skill
from .ppc_竞价策略师 import Ppc竞价策略师Skill
from .程序化广告采买专家 import 程序化广告采买专家Skill
from .搜索词分析师 import 搜索词分析师Skill
from .追踪与归因专家 import 追踪与归因专家Skill
from .行为助推引擎 import 行为助推引擎Skill
from .反馈分析师 import 反馈分析师Skill
from .产品经理 import 产品经理Skill
from .sprint_排序师 import Sprint排序师Skill
from .趋势研究员 import 趋势研究员Skill
from .实验追踪员 import 实验追踪员Skill
from .jira工作流管家 import Jira工作流管家Skill
from .会议纪要专家 import 会议纪要专家Skill
from .项目牧羊人 import 项目牧羊人Skill
from .工作室运营 import 工作室运营Skill
from .工作室制片人 import 工作室制片人Skill
from .高级项目经理 import 高级项目经理Skill
from .客户拓展策略师 import 客户拓展策略师Skill
from .销售教练 import 销售教练Skill
from .赢单策略师 import 赢单策略师Skill
from .discovery_教练 import Discovery教练Skill
from .售前工程师 import 售前工程师Skill
from .offer_与_lead_gen_策略师 import Offer与LeadGen策略师Skill
from .outbound_策略师 import Outbound策略师Skill
from .pipeline_分析师 import Pipeline分析师Skill
from .投标策略师 import 投标策略师Skill
from .应用安全工程师 import 应用安全工程师Skill
from .安全架构师 import 安全架构师Skill
from .区块链安全审计师 import 区块链安全审计师Skill
from .云安全架构师 import 云安全架构师Skill
from .合规审计师 import 合规审计师Skill
from .事件响应专家 import 事件响应专家Skill
from .渗透测试员 import 渗透测试员Skill
from .高级安全运营工程师 import 高级安全运营工程师Skill
from .威胁情报分析师 import 威胁情报分析师Skill
from .macos_metal_空间工程师 import MacosMetal空间工程师Skill
from .终端集成专家 import 终端集成专家Skill
from .visionos_空间工程师 import Visionos空间工程师Skill
from .xr_座舱交互专家 import Xr座舱交互专家Skill
from .xr_沉浸式开发者 import Xr沉浸式开发者Skill
from .xr_界面架构师 import Xr界面架构师Skill
from .应付账款智能体 import 应付账款智能体Skill
from .身份信任架构师 import 身份信任架构师Skill
from .智能体编排者 import 智能体编排者Skill
from .自动化治理架构师 import 自动化治理架构师Skill
from .商业战略家 import 商业战略家Skill
from .变革管理顾问 import 变革管理顾问Skill
from .首席财务官 import 首席财务官Skill
from .企业培训课程设计师 import 企业培训课程设计师Skill
from .客户成功经理 import 客户成功经理Skill
from .数据整合师 import 数据整合师Skill
from .数据隐私官 import 数据隐私官Skill
from .esg_与可持续发展官 import Esg与可持续发展官Skill
from .高考志愿填报顾问 import 高考志愿填报顾问Skill
from .政务数字化售前顾问 import 政务数字化售前顾问Skill
from .资助申请撰稿人 import 资助申请撰稿人Skill
from .医疗客服专家 import 医疗客服专家Skill
from .医疗健康营销合规师 import 医疗健康营销合规师Skill
from .酒店宾客服务专家 import 酒店宾客服务专家Skill
from .hr_入职管理专家 import Hr入职管理专家Skill
from .身份图谱操作员 import 身份图谱操作员Skill
from .语言翻译专家 import 语言翻译专家Skill
from .律所计费与工时专家 import 律所计费与工时专家Skill
from .律所客户接案专家 import 律所客户接案专家Skill
from .法律文书审查专家 import 法律文书审查专家Skill
from .养殖档案核对员 import 养殖档案核对员Skill
from .信贷经理助手 import 信贷经理助手Skill
from .lsp_索引工程师 import Lsp索引工程师Skill
from .ma_整合经理 import Ma整合经理Skill
from .医疗账单与编码专员 import 医疗账单与编码专员Skill
from .运营经理 import 运营经理Skill
from .组织心理学家 import 组织心理学家Skill
from .个人成长导师 import 个人成长导师Skill
from .提示词工程师 import 提示词工程师Skill
from .房地产经纪助手 import 房地产经纪助手Skill
from .报告分发师 import 报告分发师Skill
from .零售退货专家 import 零售退货专家Skill
from .销售数据提取师 import 销售数据提取师Skill
from .ai_治理政策专家 import Ai治理政策专家Skill
from .幕僚长 import 幕僚长Skill
from .土木工程师 import 土木工程师Skill
from .文化智能策略师 import 文化智能策略师Skill
from .开发者布道师 import 开发者布道师Skill
from .文档生成器 import 文档生成器Skill
from .法国咨询市场专家 import 法国咨询市场专家Skill
from .韩国商务专家 import 韩国商务专家Skill
from .mcp_构建器 import Mcp构建器Skill
from .会议效率专家 import 会议效率专家Skill
from .模型_qa_专家 import 模型Qa专家Skill
from .定价分析师 import 定价分析师Skill
from .动态定价策略师 import 动态定价策略师Skill
from .企业风险评估师 import 企业风险评估师Skill
from .salesforce_架构师 import Salesforce架构师Skill
from .策略对决推演师 import 策略对决推演师Skill
from .工作流架构师 import 工作流架构师Skill
from .留学规划顾问 import 留学规划顾问Skill
from .技术翻译专家 import 技术翻译专家Skill
from .zk_管家 import Zk管家Skill
from .服装工厂规划工程师 import 服装工厂规划工程师Skill
from .库存预测专家 import 库存预测专家Skill
from .物流路线优化师 import 物流路线优化师Skill
from .供应链采购策略师 import 供应链采购策略师Skill
from .供应商评估专家 import 供应商评估专家Skill
from .数据分析师 import 数据分析师Skill
from .高管摘要师 import 高管摘要师Skill
from .财务追踪员 import 财务追踪员Skill
from .基础设施运维师 import 基础设施运维师Skill
from .法务合规员 import 法务合规员Skill
from .招聘运营专家 import 招聘运营专家Skill
from .客服响应者 import 客服响应者Skill
from .无障碍审核员 import 无障碍审核员Skill
from .api_测试员 import Api测试员Skill
from .嵌入式测试工程师 import 嵌入式测试工程师Skill
from .证据收集者 import 证据收集者Skill
from .性能基准师 import 性能基准师Skill
from .现实检验者 import 现实检验者Skill
from .测试结果分析师 import 测试结果分析师Skill
from .工具评估师 import 工具评估师Skill
from .工作流优化师 import 工作流优化师Skill

def register_agency_roles():
    """注册所有部门角色技能"""
    registry.register(AgentListSkill())
    registry.register(CatalogSkill())
    registry.register(ContributingSkill())
    registry.register(ReadmezhTwSkill())
    registry.register(人类学家Skill())
    registry.register(地理学家Skill())
    registry.register(历史学家Skill())
    registry.register(叙事学家Skill())
    registry.register(心理学家Skill())
    registry.register(学习规划师Skill())
    registry.register(品牌守护者Skill())
    registry.register(图像提示词工程师Skill())
    registry.register(包容性视觉专家Skill())
    registry.register(Persona走查专家Skill())
    registry.register(Ui设计师Skill())
    registry.register(Ux架构师Skill())
    registry.register(Ux研究员Skill())
    registry.register(视觉叙事师Skill())
    registry.register(趣味注入师Skill())
    registry.register(Ai数据修复工程师Skill())
    registry.register(Ai工程师Skill())
    registry.register(自主优化架构师Skill())
    registry.register(后端架构师Skill())
    registry.register(Cms开发者Skill())
    registry.register(代码审查员Skill())
    registry.register(代码库入职引导工程师Skill())
    registry.register(数据工程师Skill())
    registry.register(数据库优化师Skill())
    registry.register(Devops自动化师Skill())
    registry.register(钉钉集成开发工程师Skill())
    registry.register(Drupal购物车工程师Skill())
    registry.register(邮件智能工程师Skill())
    registry.register(嵌入式固件工程师Skill())
    registry.register(嵌入式Linux驱动工程师Skill())
    registry.register(飞书集成开发工程师Skill())
    registry.register(Filament优化专家Skill())
    registry.register(Fpgaasic数字设计工程师Skill())
    registry.register(前端开发者Skill())
    registry.register(Git工作流大师Skill())
    registry.register(故障响应指挥官Skill())
    registry.register(Iot方案架构师Skill())
    registry.register(It服务经理Skill())
    registry.register(机械设计工程师Skill())
    registry.register(最小变更工程师Skill())
    registry.register(移动应用开发者Skill())
    registry.register(多智能体系统架构师Skill())
    registry.register(Orgscript工程师Skill())
    registry.register(上位机工程师Skill())
    registry.register(Prompt工程师Skill())
    registry.register(快速原型师Skill())
    registry.register(安全工程师Skill())
    registry.register(高级开发者Skill())
    registry.register(软件架构师Skill())
    registry.register(Solidity智能合约工程师Skill())
    registry.register(Sre站点可靠性工程师Skill())
    registry.register(技术文档工程师Skill())
    registry.register(威胁检测工程师Skill())
    registry.register(语音Ai集成工程师Skill())
    registry.register(微信小程序开发者Skill())
    registry.register(Wordpress购物车工程师Skill())
    registry.register(簿记与财务总监Skill())
    registry.register(财务分析师Skill())
    registry.register(财务预测分析师Skill())
    registry.register(Fpa分析师Skill())
    registry.register(金融风控分析师Skill())
    registry.register(投资研究员Skill())
    registry.register(发票管理专家Skill())
    registry.register(税务策略师Skill())
    registry.register(游戏音频工程师Skill())
    registry.register(游戏设计师Skill())
    registry.register(关卡设计师Skill())
    registry.register(叙事设计师Skill())
    registry.register(技术美术Skill())
    registry.register(Blender插件工程师Skill())
    registry.register(Godot游戏脚本开发者Skill())
    registry.register(Godot多人游戏工程师Skill())
    registry.register(GodotShader开发者Skill())
    registry.register(Roblox虚拟形象创作者Skill())
    registry.register(Roblox体验设计师Skill())
    registry.register(Roblox系统脚本工程师Skill())
    registry.register(Unity架构师Skill())
    registry.register(Unity编辑器工具开发者Skill())
    registry.register(Unity多人游戏工程师Skill())
    registry.register(UnityShaderGraph美术师Skill())
    registry.register(Unreal多人游戏架构师Skill())
    registry.register(Unreal系统工程师Skill())
    registry.register(Unreal技术美术Skill())
    registry.register(Unreal世界构建师Skill())
    registry.register(三维场景开发者Skill())
    registry.register(Gis分析师Skill())
    registry.register(Bimgis专家Skill())
    registry.register(地图制图设计师Skill())
    registry.register(无人机实景测绘专家Skill())
    registry.register(Geoaiml工程师Skill())
    registry.register(地理处理专家Skill())
    registry.register(Gis质检工程师Skill())
    registry.register(解决方案工程师Skill())
    registry.register(空间数据工程师Skill())
    registry.register(空间数据科学家Skill())
    registry.register(技术顾问Skill())
    registry.register(WebGis开发工程师Skill())
    registry.register(绩效管理专家Skill())
    registry.register(招聘专家Skill())
    registry.register(BackendArchitectSkill())
    registry.register(合同审查专家Skill())
    registry.register(制度文件撰写专家Skill())
    registry.register(Aeo基础架构师Skill())
    registry.register(智能搜索优化师Skill())
    registry.register(Ai引文策略师Skill())
    registry.register(应用商店优化师Skill())
    registry.register(百度Seo专家Skill())
    registry.register(B站内容策略师Skill())
    registry.register(图书联合作者Skill())
    registry.register(轮播图增长引擎Skill())
    registry.register(中国电商运营专家Skill())
    registry.register(中国市场本地化策略师Skill())
    registry.register(内容创作者Skill())
    registry.register(跨境电商运营专家Skill())
    registry.register(新闻情报官Skill())
    registry.register(抖音策略师Skill())
    registry.register(电商运营师Skill())
    registry.register(邮件营销策略师Skill())
    registry.register(全球播客策略师Skill())
    registry.register(增长黑客Skill())
    registry.register(Instagram策展师Skill())
    registry.register(知识付费产品策划师Skill())
    registry.register(快手策略师Skill())
    registry.register(Linkedin内容创作专家Skill())
    registry.register(直播电商主播教练Skill())
    registry.register(多平台发布编排官Skill())
    registry.register(播客内容策略师Skill())
    registry.register(Pr与传播经理Skill())
    registry.register(私域流量运营师Skill())
    registry.register(Reddit社区运营Skill())
    registry.register(Seo专家Skill())
    registry.register(短视频剪辑指导师Skill())
    registry.register(社交媒体策略师Skill())
    registry.register(Tiktok策略师Skill())
    registry.register(Twitter互动官Skill())
    registry.register(视频优化专家Skill())
    registry.register(微信公众号管理Skill())
    registry.register(微信公众号运营Skill())
    registry.register(微博运营策略师Skill())
    registry.register(微信视频号运营策略师Skill())
    registry.register(Xtwitter情报分析师Skill())
    registry.register(小红书运营专家Skill())
    registry.register(小红书专家Skill())
    registry.register(知乎策略师Skill())
    registry.register(付费媒体审计师Skill())
    registry.register(广告创意策略师Skill())
    registry.register(社交广告策略师Skill())
    registry.register(Ppc竞价策略师Skill())
    registry.register(程序化广告采买专家Skill())
    registry.register(搜索词分析师Skill())
    registry.register(追踪与归因专家Skill())
    registry.register(行为助推引擎Skill())
    registry.register(反馈分析师Skill())
    registry.register(产品经理Skill())
    registry.register(Sprint排序师Skill())
    registry.register(趋势研究员Skill())
    registry.register(实验追踪员Skill())
    registry.register(Jira工作流管家Skill())
    registry.register(会议纪要专家Skill())
    registry.register(项目牧羊人Skill())
    registry.register(工作室运营Skill())
    registry.register(工作室制片人Skill())
    registry.register(高级项目经理Skill())
    registry.register(客户拓展策略师Skill())
    registry.register(销售教练Skill())
    registry.register(赢单策略师Skill())
    registry.register(Discovery教练Skill())
    registry.register(售前工程师Skill())
    registry.register(Offer与LeadGen策略师Skill())
    registry.register(Outbound策略师Skill())
    registry.register(Pipeline分析师Skill())
    registry.register(投标策略师Skill())
    registry.register(应用安全工程师Skill())
    registry.register(安全架构师Skill())
    registry.register(区块链安全审计师Skill())
    registry.register(云安全架构师Skill())
    registry.register(合规审计师Skill())
    registry.register(事件响应专家Skill())
    registry.register(渗透测试员Skill())
    registry.register(高级安全运营工程师Skill())
    registry.register(威胁检测工程师Skill())
    registry.register(威胁情报分析师Skill())
    registry.register(MacosMetal空间工程师Skill())
    registry.register(终端集成专家Skill())
    registry.register(Visionos空间工程师Skill())
    registry.register(Xr座舱交互专家Skill())
    registry.register(Xr沉浸式开发者Skill())
    registry.register(Xr界面架构师Skill())
    registry.register(应付账款智能体Skill())
    registry.register(身份信任架构师Skill())
    registry.register(智能体编排者Skill())
    registry.register(自动化治理架构师Skill())
    registry.register(商业战略家Skill())
    registry.register(变革管理顾问Skill())
    registry.register(首席财务官Skill())
    registry.register(企业培训课程设计师Skill())
    registry.register(客户成功经理Skill())
    registry.register(数据整合师Skill())
    registry.register(数据隐私官Skill())
    registry.register(Esg与可持续发展官Skill())
    registry.register(高考志愿填报顾问Skill())
    registry.register(政务数字化售前顾问Skill())
    registry.register(资助申请撰稿人Skill())
    registry.register(医疗客服专家Skill())
    registry.register(医疗健康营销合规师Skill())
    registry.register(酒店宾客服务专家Skill())
    registry.register(Hr入职管理专家Skill())
    registry.register(身份图谱操作员Skill())
    registry.register(语言翻译专家Skill())
    registry.register(律所计费与工时专家Skill())
    registry.register(律所客户接案专家Skill())
    registry.register(法律文书审查专家Skill())
    registry.register(养殖档案核对员Skill())
    registry.register(信贷经理助手Skill())
    registry.register(Lsp索引工程师Skill())
    registry.register(Ma整合经理Skill())
    registry.register(医疗账单与编码专员Skill())
    registry.register(运营经理Skill())
    registry.register(组织心理学家Skill())
    registry.register(个人成长导师Skill())
    registry.register(提示词工程师Skill())
    registry.register(房地产经纪助手Skill())
    registry.register(招聘专家Skill())
    registry.register(报告分发师Skill())
    registry.register(零售退货专家Skill())
    registry.register(销售数据提取师Skill())
    registry.register(Ai治理政策专家Skill())
    registry.register(幕僚长Skill())
    registry.register(土木工程师Skill())
    registry.register(文化智能策略师Skill())
    registry.register(开发者布道师Skill())
    registry.register(文档生成器Skill())
    registry.register(法国咨询市场专家Skill())
    registry.register(韩国商务专家Skill())
    registry.register(Mcp构建器Skill())
    registry.register(会议效率专家Skill())
    registry.register(模型Qa专家Skill())
    registry.register(定价分析师Skill())
    registry.register(动态定价策略师Skill())
    registry.register(企业风险评估师Skill())
    registry.register(Salesforce架构师Skill())
    registry.register(策略对决推演师Skill())
    registry.register(工作流架构师Skill())
    registry.register(留学规划顾问Skill())
    registry.register(技术翻译专家Skill())
    registry.register(Zk管家Skill())
    registry.register(服装工厂规划工程师Skill())
    registry.register(库存预测专家Skill())
    registry.register(物流路线优化师Skill())
    registry.register(供应链采购策略师Skill())
    registry.register(供应商评估专家Skill())
    registry.register(数据分析师Skill())
    registry.register(高管摘要师Skill())
    registry.register(财务追踪员Skill())
    registry.register(基础设施运维师Skill())
    registry.register(法务合规员Skill())
    registry.register(招聘运营专家Skill())
    registry.register(客服响应者Skill())
    registry.register(无障碍审核员Skill())
    registry.register(Api测试员Skill())
    registry.register(嵌入式测试工程师Skill())
    registry.register(证据收集者Skill())
    registry.register(性能基准师Skill())
    registry.register(现实检验者Skill())
    registry.register(测试结果分析师Skill())
    registry.register(工具评估师Skill())
    registry.register(工作流优化师Skill())
    logger.info("已注册 {len(registry.list_all())} 个部门角色技能")

logger = logging.getLogger(__name__)