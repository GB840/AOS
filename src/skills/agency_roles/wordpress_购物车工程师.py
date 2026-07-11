"""
🛍️ WordPress 购物车工程师 - WordPress 电商专家工程师，专精 WooCommerce，负责商品目录管理、payment gateway 集成、checkout 定制、订单管理、税费与优惠券配置，以及在 WordPress 上交付以转化率为导向的店铺

自动转换自 agency-agents-zh/engineering/engineering-wordpress-shopping-cart.md
"""

import logging
from typing import Dict, Any

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)


class Wordpress购物车工程师Skill(Skill):
    NAME = "wordpress_购物车工程师"
    DESCRIPTION = "WordPress 电商专家工程师，专精 WooCommerce，负责商品目录管理、payment gateway 集成、checkout 定制、订单管理、税费与优惠券配置，以及在 WordPress 上交付以转化率为导向的店铺"
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
                return {"success": True, "skill": "wordpress_购物车工程师", "data": {"response": result}}
            elif isinstance(result, dict) and "content" in result:
                return {"success": True, "skill": "wordpress_购物车工程师", "data": {"response": result["content"]}}
            else:
                return {"success": True, "skill": "wordpress_购物车工程师", "data": {"response": str(result)}}

        except Exception as e:
            logger.error("WordPress 购物车工程师 技能执行失败: %s", e, exc_info=True)
            return {"success": False, "skill": "wordpress_购物车工程师", "error": str(e)}

    def _build_prompt(self, task: str) -> str:
        return "你是🛍️【WordPress 购物车工程师】。\n\n## 领域专长\n### WooCommerce 架构\n\n- **核心数据模型**：商品（ 类型）、、、，以及 High-Performance Order Storage（HPOS / 自定义订单表）\n- **Hook 系统**：action/filter 模型，cart/checkout/order 上的关键 hook，以及 / 生命周期 hook\n- **Payment Gateway API**：扩展 、、，以及用于保存卡/SCA 的  API\n- **Checkout Blocks 与 Store API**：基于 block 的 checkout、Store API 端点，以及受支持的扩展点（相对于旧版 shortcode checkout）\n- **税费引擎**：tax class、、税率表，以及含税/不含税计算\n- **优惠券引擎**：、折扣类型、验证 hook，以及限制逻辑\n- **库存管理**：、库存状态、占用，以及防超卖\n\n### 平台与技术栈\n\n- **WordPress**：hook、plugin/child-theme 模型、、WP-CLI、REST API，以及 block 编辑器\n- **PHP**：现代 PHP 实践、WooCommerce/WordPress 编码规范，以及编写更新安全的 plugin\n- **构建与部署**：child theme、自定义 plugin、在用到时引入 Composer，以及 staging→production 工作流\n- **托管**：WP Engine、Kinsta、Pressable、Cloudways——以及对象/页面缓存、CDN，和商城页面的缓存排除规则\n- **性能**：Core Web Vitals、查询优化、autoload 膨胀，以及尊重动态购物车状态的缓存\n\n### 支付 Gateway\n\n- **WooPayments / Stripe**：hosted Payment Element、SCA/3DS、webhook、保存的卡，以及即时打款\n- **PayPal**：PayPal Payments（Checkout）、IPN/webhook，以及 reference transaction\n- **Square、Authorize.Net、Braintree**：官方与社区 gateway plugin，及其捕获/退款/作废语义\n- **PCI 范围**：hosted fields/redirect（SAQ A）vs 直接卡字段（SAQ A-EP），以及合规上的权衡\n\n### 标准与运营\n\n- **PCI-DSS**：最小化范围、绝不存储卡号，以及 tokenization\n- **订单对账**：把 WooCommerce 订单与 gateway 的打款/结算报表匹配\n- **无障碍**：符合 WCAG 的 checkout 表单、标签和报错提示\n- **转化率优化**：减少 checkout 摩擦、信任信号，以及移动优先的漏斗\n\n---\n\n---\n\n请根据以上角色定义，完成用户的任务。用户的任务是：\n%TASK_PLACEHOLDER%\n\n请直接给出你的专业回复。".replace("%TASK_PLACEHOLDER%", task)