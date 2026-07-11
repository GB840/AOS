"""
🛒 Drupal 购物车工程师 - 资深 Drupal 电商工程师，精通 Drupal Commerce，负责商品目录管理、支付网关集成、checkout 流程设计、订单管理、税费与促销配置，以及在 Drupal 10/11 上交付高可靠的店面

自动转换自 agency-agents-zh/engineering/engineering-drupal-shopping-cart.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Drupal购物车工程师Skill(Skill):
    NAME = "drupal_购物车工程师"
    DESCRIPTION = "资深 Drupal 电商工程师，精通 Drupal Commerce，负责商品目录管理、支付网关集成、checkout 流程设计、订单管理、税费与促销配置，以及在 Drupal 10/11 上交付高可靠的店面"
    VERSION = "1.0.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "engineering"
    TAGS = ["engineering", "consulting", "expert"]
    CAPABILITIES = ["code_generation", "system_design", "technical_analysis"]
    PLATFORMS = ["python"]

    def __init__(self):
        super().__init__(SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version=self.VERSION,
            author=self.AUTHOR,
            license=self.LICENSE,
            category=self.CATEGORY,
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
            platforms=self.PLATFORMS,
        ))

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task", "")
        inputs_data = context.get("inputs", "")

        if not task:
            return {"success": False, "error": "缺少任务描述（task 参数）"}

        try:
            from skills.agency_roles import get_agency_runtime
            rt = get_agency_runtime(role_id=self.NAME)
            prompt = self._build_prompt(task)

            if inputs_data:
                prompt += "\n\n## 相关输入数据:\n" + inputs_data

            result = rt.chat(prompt, model="default")

            if isinstance(result, str):
                return {"success": True, "skill": "drupal_购物车工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "drupal_购物车工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "drupal_购物车工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("Drupal 购物车工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "drupal_购物车工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛒【Drupal 购物车工程师】。\n\n## 领域专长\n### Drupal Commerce 架构\n\n- **Commerce Core**：Order、Product、Price、Store、Payment、Promotion、Tax、Checkout 子模块及其实体模型\n- **Entity & Field API**：product/variation 实体、 字段、属性实体与 bundle 架构\n- **价格链（Price Chain）**：、price list、币种解析，以及 / 值对象\n- **Checkout 系统**：checkout flow、checkout pane、，以及订单刷新/处理事件\n- **Payment API**：、on-site 与 off-site 网关、支付方式，以及 SupportsRefunds/SupportsVoids 能力接口\n- **订单工作流**：State Machine module、订单状态、转换、guard 与转换事件\n- **库存**：Commerce Stock module、stock provider 与原子扣减策略\n\n### 平台与技术栈\n\n- **Drupal 10 / 11**：核心 API、recipe、配置管理，以及 Symfony 基础（service、event、依赖注入）\n- **Composer 工作流**：管理 Commerce 与 contrib module、patch 与版本约束\n- **Drush**：、、，以及 commerce 专用命令\n- **主题（Theming）**：用于 product/cart/checkout 模板的 Twig、render array，以及缓存元数据/contexts\n- **托管（Hosting）**：Pantheon、Acquia、Platform.sh——以及它们所隐含的部署流水线与环境配置\n\n### 支付网关\n\n- **Stripe**：Commerce Stripe——on-site Payment Element/Intents、SCA/3DS、webhook 与 tokenization\n- **PayPal**：Commerce PayPal——Checkout（off-site）与 on-site 流程、IPN/webhook\n- **Braintree、Authorize.Net、Square**：contrib 网关 module 及其捕获/退款/作废语义\n- **PCI 范围**：SAQ A（跳转）与 SAQ A-EP（on-site 字段）的区别，以及集成方式如何改变合规负担\n\n### 标准与运维\n\n- **PCI-DSS**：范围最小化、绝不存储 PAN，以及 tokenization\n- **订单对账**：将 Commerce 支付与网关结算报表匹配\n- **无障碍（Accessibility）**：符合 WCAG 的 checkout 表单与错误提示\n- **性能**：Big Pipe、render 缓存，以及购物车/checkout 不可缓存的本质\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)