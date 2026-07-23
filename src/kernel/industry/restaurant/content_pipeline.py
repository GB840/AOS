"""烧烤店内容生产流水线 —— AI 内容自动生成。

核心能力：
1. 视频脚本生成：抖音/快手短视频脚本
2. 图文内容生成：小红书/朋友圈文案
3. 活动策划生成：优惠券/活动方案
4. 自动发布调度：按计划推送内容

数据流：
    [运营计划] → [内容生成器] → [审核] → [发布]
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 内容模板库
# ─────────────────────────────────────────────────────────────

# 抖音视频脚本模板
DOUYIN_TEMPLATES = {
    "dish_recommend": {
        "title": "招牌推荐：{dish_name}",
        "hook": "每天卖出{sales_count}份！{dish_name}到底有多好吃？",
        "script": """
【开场】（镜头对准菜品）
"兄弟们！今天带你们看看这家烧烤店的扛把子——{dish_name}！"

【展示】（特写烤制过程）
"看看这烤法，外焦里嫩，{features}..."

【品尝】（大口吃）
"嗯！这味道，{taste_desc}！"

【结尾】（展示店铺）
"就在{shop_name}，人均{avg_price}块，地址评论区见！"
        """,
        "cta": "点赞关注，下期带你吃{next_dish}！",
    },
    "new_dish": {
        "title": "新品首发：{dish_name}",
        "hook": "老板疯了！这道菜居然只要{price}块钱？",
        "script": """
【开场】（神秘兮兮）
"今天给大家整个新活的——{dish_name}！"

【悬念】（慢动作展示）
"别看价格便宜，这用料可一点不含糊..."

【高潮】（吃后反应）
"卧槽！这也太香了吧！{taste_desc}"

【结尾】
"限时尝鲜价，想吃的抓紧来{shop_name}！"
        """,
        "cta": "评论区说说你最想尝试哪个新品？",
    },
    "environment": {
        "title": "探店：{shop_name}",
        "hook": "这家烧烤店，凭什么火了{years}年？",
        "script": """
【开场】（店铺外景）
"今天带你们探一家老字号——{shop_name}！"

【环境】（店内镜头）
"看看这环境，{env_desc}，难怪天天爆满..."

【人气】（顾客镜头）
"工作日都排队，这人气没话说！"

【总结】
"人均{avg_price}，性价比拉满，{shop_name}，不亏是老字号！"
        """,
        "cta": "你有多久没吃烧烤了？评论区告诉我！",
    },
}

# 小红书图文模板
XIAOHONGSHU_TEMPLATES = {
    "dish_recommend": {
        "title": "🔥这家烧烤店{dish_name}绝了！人均{avg_price}吃到撑",
        "content": """
姐妹们！发现一家宝藏烧烤店！

📍 {shop_name}
💰 人均：{avg_price}元

✨ 必点推荐：
1️⃣ {dish_name}：{dish_desc}
2️⃣ {side_dish}：{side_desc}
3️⃣ {drink}：{drink_desc}

💡 点单攻略：
{order_tips}

📸 拍照打卡点：
{photo_spots}

⏰ 营业时间：{open_hours}
🚗 停车：{parking_info}

#烧烤探店 #美食推荐 #{city}美食
        """,
    },
    "coupon_share": {
        "title": "羊毛！{shop_name}优惠券来了！",
        "content": """
宝子们！今天给大家薅到的福利！

🎁 {shop_name}专属优惠：
• 满{min_spend}减{discount}
• 使用时间：{valid_period}
• 领取方式：评论区扣"1"

🔥 推荐搭配：
{combo_recommend}

⚠️ 注意事项：
{notes}

快点收藏，周末安排上！

#优惠券 #烧烤 #{city}探店
        """,
    },
}

# 朋友圈文案模板
WECHAT_TEMPLATES = {
    "daily": [
        "🔥 今日推荐：{dish_name}，{sales_count}份已售出！来晚了真没有~",
        "🌙 夜宵时间到！{shop_name}等你，{discount_info}",
        "🍻 好消息！今天{activity_info}，抓紧来！",
    ],
    "activity": [
        "🎉 {activity_name}开始啦！{activity_desc}\n活动时间：{activity_period}\n快点来{shop_name}！",
        "📢 老顾客专属福利！{offer}\n仅限本周，错过等一年！",
    ],
}


@dataclass
class GeneratedContent:
    """生成的内容"""
    id: str = ""
    type: str = ""           # video_script/image_text/coupon/activity
    channel: str = ""        # douyin/xiaohongshu/wechat
    title: str = ""
    content: str = ""
    images_prompts: List[str] = field(default_factory=list)
    status: str = "draft"    # draft/reviewing/approved/published
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    published_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class BBQShopContentPipeline:
    """烧烤店内容生产流水线。
    
    负责：
    1. 根据运营计划生成内容
    2. 生成视频脚本、图文、活动方案
    3. 管理内容状态流转
    """
    
    def __init__(self, shop_name: str = "烧烤店"):
        self.shop_name = shop_name
        self._lock = threading.RLock()
        self._contents: Dict[str, GeneratedContent] = {}
        self._shop_info: Dict[str, Any] = {
            "name": shop_name,
            "avg_price": 80,
            "open_hours": "11:00-02:00",
            "address": "",
            "years": 5,
        }
        self._content_counter = 0
    
    def set_shop_info(self, info: Dict[str, Any]) -> None:
        """设置店铺信息"""
        with self._lock:
            self._shop_info.update(info)
    
    # ─────────────────────────────────────────────────────────────
    # 内容生成
    # ─────────────────────────────────────────────────────────────
    
    def generate_from_plan(self, plan: Dict[str, Any]) -> List[GeneratedContent]:
        """根据运营计划生成内容"""
        contents = []
        
        for content_plan in plan.get("content_plans", []):
            content = self._generate_single(content_plan, plan.get("analysis", {}))
            if content:
                contents.append(content)
                with self._lock:
                    self._contents[content.id] = content
        
        return contents
    
    def _generate_single(self, plan: Dict, analysis: Dict) -> Optional[GeneratedContent]:
        """生成单条内容"""
        channel = plan.get("channel", "douyin")
        content_type = plan.get("type", "video")
        topic = plan.get("topic", "")
        
        with self._lock:
            self._content_counter += 1
            content_id = f"content_{int(time.time()*1000)}_{self._content_counter}"
        
        if channel == "douyin":
            return self._generate_douyin(content_id, plan, analysis)
        elif channel == "xiaohongshu":
            return self._generate_xiaohongshu(content_id, plan, analysis)
        elif channel == "wechat":
            return self._generate_wechat(content_id, plan, analysis)
        else:
            # 默认生成通用内容
            return GeneratedContent(
                id=content_id,
                type=content_type,
                channel=channel,
                title=topic,
                content=f"自动生成内容：{topic}",
                metadata={"plan": plan},
                created_at=datetime.now().isoformat(),
            )
    
    def _generate_douyin(self, content_id: str, plan: Dict, analysis: Dict) -> GeneratedContent:
        """生成抖音内容"""
        topic = plan.get("topic", "")
        dish = plan.get("dish", "")
        
        # 选择模板
        if "推荐" in topic or dish:
            template = DOUYIN_TEMPLATES["dish_recommend"]
            top_dishes = analysis.get("sales", {}).get("top_dishes", [])
            sales_count = top_dishes[0].get("sales", 100) if top_dishes else 100
            content = template["script"].format(
                dish_name=dish or "招牌烤串",
                sales_count=sales_count,
                features="香气四溢，油而不腻",
                taste_desc="一口下去，满嘴留香",
                shop_name=self.shop_name,
                avg_price=self._shop_info.get("avg_price", 80),
                next_dish="秘制烤翅",
            )
            title = template["title"].format(dish_name=dish or "招牌烤串")
        elif "新" in topic:
            template = DOUYIN_TEMPLATES["new_dish"]
            content = template["script"].format(
                dish_name=dish or "新品",
                price=38,
                taste_desc="这味道绝了",
                shop_name=self.shop_name,
            )
            title = template["title"].format(dish_name=dish or "新品", price=38)
        else:
            template = DOUYIN_TEMPLATES["environment"]
            content = template["script"].format(
                shop_name=self.shop_name,
                years=self._shop_info.get("years", 5),
                env_desc="干净整洁，氛围感拉满",
                avg_price=self._shop_info.get("avg_price", 80),
            )
            title = template["title"].format(shop_name=self.shop_name)
        
        return GeneratedContent(
            id=content_id,
            type="video",
            channel="douyin",
            title=title,
            content=content.strip(),
            images_prompts=[f"拍摄{self.shop_name}环境", f"展示{dish or '招牌菜'}制作过程"],
            metadata={"plan": plan, "hook": plan.get("hook", "")},
            created_at=datetime.now().isoformat(),
        )
    
    def _generate_xiaohongshu(self, content_id: str, plan: Dict, analysis: Dict) -> GeneratedContent:
        """生成小红书内容"""
        topic = plan.get("topic", "")
        
        if "福利" in topic or "优惠" in topic:
            template = XIAOHONGSHU_TEMPLATES["coupon_share"]
            content = template["content"].format(
                shop_name=self.shop_name,
                min_spend=100,
                discount=20,
                valid_period="本周内",
                combo_recommend="招牌烤串+凉菜+啤酒，绝配！",
                notes="每人限领一张，不可与其他优惠同享",
                city="",
            )
            title = template["title"].format(shop_name=self.shop_name)
        else:
            template = XIAOHONGSHU_TEMPLATES["dish_recommend"]
            dish = plan.get("dish", "招牌烤串")
            content = template["content"].format(
                dish_name=dish,
                avg_price=self._shop_info.get("avg_price", 80),
                shop_name=self.shop_name,
                dish_desc="外焦里嫩，香气扑鼻",
                side_dish="拍黄瓜",
                side_desc="爽口解腻",
                drink="冰啤酒",
                drink_desc="冰镇畅爽",
                order_tips="先点招牌，再点凉菜，最后加酒水",
                photo_spots="门口招牌、烤炉前、菜品特写",
                open_hours=self._shop_info.get("open_hours", "11:00-02:00"),
                parking_info="门口可停，建议公共交通",
                city="",
            )
            title = template["title"].format(dish_name=dish, avg_price=self._shop_info.get("avg_price", 80))
        
        return GeneratedContent(
            id=content_id,
            type="image_text",
            channel="xiaohongshu",
            title=title.strip(),
            content=content.strip(),
            images_prompts=["菜品特写图", "环境氛围图", "店铺外观图"],
            metadata={"plan": plan},
            created_at=datetime.now().isoformat(),
        )
    
    def _generate_wechat(self, content_id: str, plan: Dict, analysis: Dict) -> GeneratedContent:
        """生成朋友圈内容"""
        templates = WECHAT_TEMPLATES["daily"]
        
        # 根据计划选择模板
        if "activity" in plan.get("topic", "").lower() or "活动" in plan.get("topic", ""):
            templates = WECHAT_TEMPLATES["activity"]
        
        # 填充模板
        template = templates[0]  # 简化：取第一个
        dish = plan.get("dish", "招牌烤串")
        sales_count = analysis.get("sales", {}).get("top_dishes", [{}])[0].get("sales", 50)
        
        content = template.format(
            dish_name=dish,
            sales_count=sales_count,
            shop_name=self.shop_name,
            discount_info="今日特惠，满100减20",
            activity_info="新品尝鲜价",
            activity_name="",
            activity_desc="",
            activity_period="",
            offer="满100减20",
        )
        
        return GeneratedContent(
            id=content_id,
            type="image_text",
            channel="wechat",
            title="",  # 朋友圈无标题
            content=content.strip(),
            images_prompts=[f"{dish}特写图"],
            metadata={"plan": plan},
            created_at=datetime.now().isoformat(),
        )
    
    # ─────────────────────────────────────────────────────────────
    # 活动内容生成
    # ─────────────────────────────────────────────────────────────
    
    def generate_activity(self, activity_plan: Dict) -> GeneratedContent:
        """生成活动内容"""
        content_id = f"activity_{int(time.time()*1000)}"
        
        activity_type = activity_plan.get("type", "discount")
        
        if activity_type == "discount":
            content = self._generate_discount_activity(activity_plan)
        elif activity_type == "new_member":
            content = self._generate_new_member_activity(activity_plan)
        else:
            content = f"活动：{activity_plan.get('offer', '敬请期待')}"
        
        return GeneratedContent(
            id=content_id,
            type="activity",
            channel="all",
            title=f"【{self.shop_name}】{activity_plan.get('offer', '限时活动')}",
            content=content,
            metadata={"plan": activity_plan},
            created_at=datetime.now().isoformat(),
        )
    
    def _generate_discount_activity(self, plan: Dict) -> str:
        """生成折扣活动文案"""
        dish = plan.get("dish", "招牌菜")
        discount = plan.get("discount_rate", 0.8)
        days = plan.get("expire_days", 3)
        
        return f"""
🎉 {self.shop_name} 限时特惠！

🔥 {dish} 限时{int(discount*10)}折！

⏰ 活动时间：即日起{days}天内有效

📍 店铺地址：{self._shop_info.get('address', '欢迎到店咨询')}

数量有限，先到先得！
        """.strip()
    
    def _generate_new_member_activity(self, plan: Dict) -> str:
        """生成新会员活动文案"""
        offer = plan.get("offer", "首单立减")
        min_spend = plan.get("min_spend", 50)
        days = plan.get("expire_days", 7)
        
        return f"""
🎁 新会员专属福利！

✨ {offer}！
💰 消费满{min_spend}元即可使用

⏰ 有效期：注册后{days}天内

📱 扫码注册会员，立享优惠！

{self.shop_name} 欢迎您！
        """.strip()
    
    # ─────────────────────────────────────────────────────────────
    # 内容管理
    # ─────────────────────────────────────────────────────────────
    
    def get_content(self, content_id: str) -> Optional[GeneratedContent]:
        """获取内容"""
        with self._lock:
            return self._contents.get(content_id)
    
    def list_contents(self, status: str = None, channel: str = None) -> List[GeneratedContent]:
        """列出内容"""
        with self._lock:
            contents = list(self._contents.values())
            if status:
                contents = [c for c in contents if c.status == status]
            if channel:
                contents = [c for c in contents if c.channel == channel]
            return contents
    
    def update_status(self, content_id: str, status: str) -> bool:
        """更新内容状态"""
        with self._lock:
            if content_id in self._contents:
                self._contents[content_id].status = status
                if status == "published":
                    self._contents[content_id].published_at = datetime.now().isoformat()
                return True
            return False


# ─────────────────────────────────────────────────────────────
# 单例
# ─────────────────────────────────────────────────────────────

_pipeline: Optional[BBQShopContentPipeline] = None
_pipeline_lock = threading.Lock()


def get_content_pipeline(shop_name: str = "烧烤店") -> BBQShopContentPipeline:
    """获取内容流水线单例"""
    global _pipeline
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                _pipeline = BBQShopContentPipeline(shop_name=shop_name)
    return _pipeline