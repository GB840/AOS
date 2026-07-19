"""跨境合规智能体 — AOS 第二商业落地场景。

输入：商品描述 + 目的国 + 可选的已有资质
输出：合规要求清单 + 缺口分析 + 风险等级 + 行动计划

设计原则（同 bidding_agent）：
- 合规检查用结构化规则引擎（按目的国 × 品类）
- LLM 仅用于"理解性"任务（商品归类、描述解析）
- 全链路 trace 可复核
- 反思学习：每次被退/被查 → 持久化教训

用法：
    from skills.crossborder_compliance import CrossBorderAgent
    agent = CrossBorderAgent()
    result = agent.execute({
        "product": "蓝牙耳机，含锂电池，售价29.99欧元",
        "destination": "DE",  # 德国
        "channel": "amazon",
        "existing_certs": ["CE"],
    })
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skills.base import Skill, SkillMeta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 目的国合规规则库（结构化）
# ---------------------------------------------------------------------------

@dataclass
class ComplianceItem:
    """一条跨境合规要求。"""
    item_id: str
    country: str  # 目的国代码 DE/US/UK/JP/AU/ALL
    category: str  # 认证/标签/税务/海关/包装/安全/环保
    requirement: str
    severity: str  # mandatory / recommended / conditional
    applies_to: str = ""  # 适用品类关键词（正则），空=全品类
    cost_hint: str = ""  # 费用提示
    timeline_hint: str = ""  # 办理周期提示


# 首批规则：覆盖 EU(德/法) + US + UK + JP + AU，6 大品类
COMPLIANCE_DB: List[ComplianceItem] = [
    # === 欧盟/德国 ===
    ComplianceItem("EU01", "DE", "认证", "CE 标志（Conformité Européenne）", "mandatory",
                   r"(电子|电器|蓝牙|wifi|无线|充电|LED|玩具|机械)", "€2000-8000", "4-8周"),
    ComplianceItem("EU02", "DE", "环保", "WEEE 注册（电子废弃物回收）", "mandatory",
                   r"(电子|电器|蓝牙|wifi|充电|LED|电池)", "€200-500/年", "2-4周"),
    ComplianceItem("EU03", "DE", "环保", "VerpackG 包装法注册（LUCID）", "mandatory",
                   "", "€0-200/年", "1-2周"),
    ComplianceItem("EU04", "DE", "税务", "VAT 税号注册（19%标准税率）", "mandatory",
                   "", "€300-800", "4-12周"),
    ComplianceItem("EU05", "DE", "安全", "锂电池 UN38.3 运输认证", "mandatory",
                   r"(锂电|电池|充电宝|储能)", "€3000-6000", "6-10周"),
    ComplianceItem("EU06", "DE", "标签", "德语产品标签（制造商/进口商地址+警告语）", "mandatory",
                   "", "€0（自行制作）", "即时"),
    ComplianceItem("EU07", "DE", "认证", "RoHS 有害物质限制（2011/65/EU）", "mandatory",
                   r"(电子|电器|蓝牙|wifi|充电|LED)", "€500-2000", "2-4周"),
    ComplianceItem("EU08", "DE", "安全", "REACH 化学品注册（SVHC 清单）", "conditional",
                   r"(化学|涂料|塑料|橡胶|纺织)", "€1000-5000", "4-8周"),
    ComplianceItem("EU09", "DE", "海关", "HS 编码归类 + EORI 号", "mandatory",
                   "", "€0-200", "1-2周"),
    ComplianceItem("EU10", "DE", "平台", "Amazon/eBay 合规文件上传（DOC）", "mandatory",
                   "", "€0", "即时"),
    # === 美国 ===
    ComplianceItem("US01", "US", "认证", "FCC 认证（联邦通信委员会）", "mandatory",
                   r"(电子|蓝牙|wifi|无线|射频|LED)", "$3000-8000", "4-8周"),
    ComplianceItem("US02", "US", "安全", "UL 认证（电气安全）", "recommended",
                   r"(电器|充电|电源|电池)", "$5000-15000", "8-16周"),
    ComplianceItem("US03", "US", "税务", "Sales Tax（各州不同，需注册）", "mandatory",
                   "", "$0-500/州", "2-6周"),
    ComplianceItem("US04", "US", "海关", "FDA 注册（食品/药品/化妆品/医疗器械）", "conditional",
                   r"(食品|药品|化妆|医疗|保健)", "$5000+", "4-12周"),
    ComplianceItem("US05", "US", "标签", "英文标签 + 原产国标识（Made in China）", "mandatory",
                   "", "$0", "即时"),
    ComplianceItem("US06", "US", "安全", "CPSIA（消费品安全，儿童产品需 CPC）", "conditional",
                   r"(玩具|儿童|婴儿|童)", "$2000-5000", "4-6周"),
    ComplianceItem("US07", "US", "环保", "EPA 注册（含化学品/农药产品）", "conditional",
                   r"(化学|农药|清洁|消毒)", "$5000+", "8-16周"),
    ComplianceItem("US08", "US", "海关", "HS 编码 + 关税查询（Section 301 加征）", "mandatory",
                   "", "$0", "即时"),
    # === 英国 ===
    ComplianceItem("UK01", "UK", "认证", "UKCA 标志（脱欧后替代 CE）", "mandatory",
                   r"(电子|电器|蓝牙|wifi|无线|充电|LED|玩具|机械)", "£2000-6000", "4-8周"),
    ComplianceItem("UK02", "UK", "税务", "UK VAT 注册（20%标准税率）", "mandatory",
                   "", "£300-600", "4-8周"),
    ComplianceItem("UK03", "UK", "环保", "UK 包装废弃物法规（EPR）", "mandatory",
                   "", "£0-500/年", "2-4周"),
    # === 日本 ===
    ComplianceItem("JP01", "JP", "认证", "PSE 标志（电气用品安全法）", "mandatory",
                   r"(电子|电器|充电|电源|LED)", "¥300000-800000", "6-12周"),
    ComplianceItem("JP02", "JP", "认证", "TELEC/Giteki（无线设备技适）", "mandatory",
                   r"(蓝牙|wifi|无线|射频)", "¥200000-500000", "4-8周"),
    ComplianceItem("JP03", "JP", "税务", "日本消费税（JCT 10%）+ 发票制度", "mandatory",
                   "", "¥0-50000", "4-8周"),
    ComplianceItem("JP04", "JP", "标签", "日语标签（品名/材质/原产国/进口商）", "mandatory",
                   "", "¥0", "即时"),
    # === 澳大利亚 ===
    ComplianceItem("AU01", "AU", "认证", "RCM 标志（电气安全+EMC）", "mandatory",
                   r"(电子|电器|蓝牙|wifi|充电|LED)", "A$3000-8000", "4-8周"),
    ComplianceItem("AU02", "AU", "税务", "GST 注册（10%，年营业额≥A$75000）", "mandatory",
                   "", "A$0-500", "2-4周"),
    ComplianceItem("AU03", "AU", "安全", "ACMA 无线通信认证", "mandatory",
                   r"(蓝牙|wifi|无线|射频)", "A$2000-5000", "4-6周"),
    # === 通用 ===
    ComplianceItem("ALL01", "ALL", "海关", "商业发票 + 装箱单 + 提单", "mandatory",
                   "", "$0", "即时"),
    ComplianceItem("ALL02", "ALL", "保险", "货运保险（建议 CIF 条款）", "recommended",
                   "", "货值 0.3-1%", "即时"),
    ComplianceItem("ALL03", "ALL", "合规", "出口管制筛查（EAR/实体清单）", "mandatory",
                   r"(芯片|加密|军工|航天|AI)", "$0", "即时"),
]


# ---------------------------------------------------------------------------
# 主技能类
# ---------------------------------------------------------------------------

class CrossBorderAgent(Skill):
    """跨境合规智能体：商品+目的国 → 合规要求清单 + 缺口 + 风险 + 行动计划。"""

    NAME = "crossborder-compliance"
    DESCRIPTION = "跨境出海合规分析：输入商品和目的国，输出认证/税务/标签/海关全链路合规要求、缺口和风险"
    VERSION = "0.1.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "business"
    TAGS = ["跨境", "出海", "合规", "认证", "crossborder", "compliance"]
    CAPABILITIES = ["crossborder.analyze", "crossborder.compliance"]

    def __init__(self, meta: Optional[SkillMeta] = None):
        super().__init__(meta or SkillMeta(
            name=self.NAME,
            description=self.DESCRIPTION,
            version=self.VERSION,
            author=self.AUTHOR,
            license=self.LICENSE,
            category=self.CATEGORY,
            tags=self.TAGS,
            capabilities=self.CAPABILITIES,
        ))
        self._lessons_path = Path(__file__).parent.parent.parent / "_traces" / "crossborder_lessons.jsonl"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """主入口。

        context:
            product: str — 商品描述（必须）
            destination: str — 目的国代码 DE/US/UK/JP/AU（必须）
            channel: str — 销售渠道 amazon/ebay/shopify/独立站（可选）
            existing_certs: list — 已有认证/资质（可选）
            monthly_volume: str — 月销量级（可选，影响税务判断）

        Returns:
            {
                "ok": bool,
                "requirements": [...],
                "gaps": [...],
                "risk_level": str,
                "action_plan": [...],
                "trace": {...},
            }
        """
        t0 = time.time()
        product = context.get("product", "")
        dest = context.get("destination", "").upper()
        channel = context.get("channel", "")
        existing = set(c.upper() for c in context.get("existing_certs", []))
        trace_steps: List[Dict[str, Any]] = []

        if not product:
            return {"ok": False, "error": "缺少商品描述（product）"}
        if not dest:
            return {"ok": False, "error": "缺少目的国（destination）"}

        # 目的国验证
        _SUPPORTED = {"DE", "US", "UK", "JP", "AU"}
        dest_warning = ""
        if dest not in _SUPPORTED:
            dest_warning = (f"目的国 {dest} 暂无专属规则库，仅返回通用要求。"
                            f"当前支持：{', '.join(sorted(_SUPPORTED))}")
            self._log.warning(dest_warning)

        # Step 1: 商品品类识别
        self._log.info("Step 1: 识别商品品类: %s", product[:50])
        categories = self._identify_categories(product)
        trace_steps.append({
            "step": "category_identify", "ok": True,
            "categories": categories,
        })

        # Step 2: 匹配合规要求
        self._log.info("Step 2: 匹配 %s 合规要求", dest)
        applicable = self._match_requirements(dest, product, categories)
        trace_steps.append({
            "step": "requirements_match", "ok": True,
            "total_rules": len(COMPLIANCE_DB),
            "applicable": len(applicable),
        })

        # Step 3: 缺口分析
        self._log.info("Step 3: 缺口分析（已有 %d 项资质）", len(existing))
        gaps = self._analyze_gaps(applicable, existing)
        trace_steps.append({
            "step": "gap_analysis", "ok": True,
            "gaps": len(gaps),
            "already_have": len(applicable) - len(gaps),
        })

        # Step 4: 风险评估
        risk_level = self._assess_risk(gaps, applicable)
        trace_steps.append({"step": "risk_assess", "ok": True, "level": risk_level})

        # Step 5: 行动计划
        lessons = self._load_lessons()
        action_plan = self._build_action_plan(gaps, lessons, channel)
        trace_steps.append({"step": "action_plan", "ok": True, "items": len(action_plan)})

        elapsed = round(time.time() - t0, 2)
        self._log.info("分析完成，耗时 %.2fs", elapsed)

        return {
            "ok": True,
            "product": product,
            "destination": dest,
            "warning": dest_warning,
            "categories": categories,
            "requirements": [self._item_to_dict(i) for i in applicable],
            "gaps": [self._item_to_dict(i) for i in gaps],
            "already_compliant": [self._item_to_dict(i) for i in applicable if i not in gaps],
            "risk_level": risk_level,
            "action_plan": action_plan,
            "cost_estimate": self._estimate_cost(gaps),
            "timeline_estimate": self._estimate_timeline(gaps),
            "trace": {
                "steps": trace_steps,
                "elapsed_sec": elapsed,
                "destination": dest,
                "channel": channel,
            },
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _identify_categories(self, product: str) -> List[str]:
        """从商品描述中识别品类标签。"""
        categories = []
        cat_keywords = {
            "电子/无线": r"(蓝牙|wifi|无线|射频|2\.4g|5g|nfc)",
            "电气/充电": r"(充电|电源|电池|锂电|储能|适配器)",
            "LED/照明": r"(led|灯|照明|灯泡)",
            "玩具/儿童": r"(玩具|儿童|婴儿|童|积木)",
            "食品/保健": r"(食品|保健|营养|维生素|茶|咖啡)",
            "化妆品": r"(化妆|护肤|美妆|面膜|精华)",
            "纺织/服装": r"(服装|纺织|面料|鞋|包)",
            "机械/工具": r"(机械|工具|电动|钻|锯)",
            "化学品": r"(化学|涂料|胶|清洁|消毒)",
        }
        product_lower = product.lower()
        for cat, pat in cat_keywords.items():
            if re.search(pat, product_lower):
                categories.append(cat)
        if not categories:
            categories.append("通用消费品")
        return categories

    def _match_requirements(self, dest: str, product: str,
                            categories: List[str]) -> List[ComplianceItem]:
        """匹配适用的合规要求。"""
        applicable = []
        for item in COMPLIANCE_DB:
            # 国家匹配
            if item.country not in (dest, "ALL"):
                continue
            # 品类匹配（空 applies_to = 全品类适用）
            if item.applies_to:
                if not re.search(item.applies_to, product, re.IGNORECASE):
                    continue
            applicable.append(item)
        return applicable

    # 资质→规则 ID 显式映射（避免子串误匹配）
    _CERT_RULE_MAP = {
        "CE": {"EU01"},
        "FCC": {"US01"},
        "ROHS": {"EU07"},
        "UL": {"US02"},
        "PSE": {"JP01"},
        "TELEC": {"JP02"},
        "GITEKI": {"JP02"},
        "UKCA": {"UK01"},
        "RCM": {"AU01"},
        "ACMA": {"AU03"},
        "WEEE": {"EU02"},
        "REACH": {"EU08"},
        "UN38.3": {"EU05"},
        "CPC": {"US06"},
        "CPSIA": {"US06"},
        "FDA": {"US04"},
        "EPA": {"US07"},
        "ISO9001": set(),  # 通用资质，不直接满足特定规则
        "ISO27001": set(),
        "PMP": set(),
    }

    def _analyze_gaps(self, applicable: List[ComplianceItem],
                      existing: set) -> List[ComplianceItem]:
        """找出尚未满足的合规要求（显式映射，非子串匹配）。"""
        # 计算已有资质覆盖的规则 ID 集合
        covered_rules: set = set()
        for cert in existing:
            cert_upper = cert.upper().strip()
            if cert_upper in self._CERT_RULE_MAP:
                covered_rules.update(self._CERT_RULE_MAP[cert_upper])
            else:
                # 未知资质：仅当完整匹配规则 requirement 中的关键词时才覆盖
                for item in applicable:
                    if cert_upper == item.requirement.upper().split("（")[0].strip():
                        covered_rules.add(item.item_id)

        gaps = []
        for item in applicable:
            if item.item_id in covered_rules:
                continue
            if item.severity in ("mandatory", "conditional"):
                gaps.append(item)
        return gaps

    def _assess_risk(self, gaps: List[ComplianceItem],
                     applicable: List[ComplianceItem]) -> str:
        """评估整体风险等级。"""
        mandatory_gaps = [g for g in gaps if g.severity == "mandatory"]
        if len(mandatory_gaps) >= 3:
            return "HIGH"
        elif len(mandatory_gaps) >= 1:
            return "MEDIUM"
        elif gaps:
            return "LOW"
        return "COMPLIANT"

    def _build_action_plan(self, gaps: List[ComplianceItem],
                           lessons: List[Dict], channel: str) -> List[Dict[str, str]]:
        """生成行动计划（按紧急度排序）。"""
        plan = []

        # 按 severity 排序
        sorted_gaps = sorted(gaps, key=lambda g: (
            0 if g.severity == "mandatory" else 1,
            g.category,
        ))

        for i, gap in enumerate(sorted_gaps, 1):
            action = {
                "priority": i,
                "action": f"办理 {gap.requirement}",
                "category": gap.category,
                "severity": gap.severity,
                "cost": gap.cost_hint or "待确认",
                "timeline": gap.timeline_hint or "待确认",
            }
            plan.append(action)

        # 平台特殊要求
        if channel and channel.lower() in ("amazon", "ebay"):
            plan.append({
                "priority": len(plan) + 1,
                "action": f"上传合规文件到 {channel} 后台（DOC/合规声明）",
                "category": "平台",
                "severity": "mandatory",
                "cost": "€0",
                "timeline": "即时",
            })

        # 历史教训
        if lessons:
            plan.append({
                "priority": 0,
                "action": f"⚠️ 历史教训：{lessons[-1].get('lesson', '')}",
                "category": "经验",
                "severity": "info",
                "cost": "-",
                "timeline": "-",
            })

        return plan

    def _estimate_cost(self, gaps: List[ComplianceItem]) -> str:
        """估算总合规成本。"""
        if not gaps:
            return "已合规，无额外费用"
        # 简单汇总（取各项中间值）
        return f"{len(gaps)} 项待办理，预估总费用见各项 cost_hint"

    def _estimate_timeline(self, gaps: List[ComplianceItem]) -> str:
        """估算总办理周期。"""
        if not gaps:
            return "已合规"
        weeks = []
        for g in gaps:
            m = re.search(r"(\d+)-(\d+)周", g.timeline_hint)
            if m:
                weeks.append(int(m.group(2)))
        if weeks:
            return f"最长单项 {max(weeks)} 周（可并行办理）"
        return "待确认"

    def _item_to_dict(self, item: ComplianceItem) -> Dict[str, str]:
        return {
            "id": item.item_id,
            "category": item.category,
            "requirement": item.requirement,
            "severity": item.severity,
            "cost": item.cost_hint,
            "timeline": item.timeline_hint,
        }

    def _load_lessons(self) -> List[Dict]:
        if not self._lessons_path.exists():
            return []
        lessons = []
        try:
            for line in self._lessons_path.read_text(encoding="utf-8").strip().split("\n"):
                if line.strip():
                    try:
                        lessons.append(json.loads(line))
                    except json.JSONDecodeError:
                        self._log.warning("教训文件含损坏行，已跳过: %.40s", line)
        except Exception as e:
            self._log.warning("教训文件读取失败: %s", e)
        return lessons[-20:]

    _MAX_LESSONS = 50

    def save_lesson(self, lesson: str, context: str = ""):
        """保存跨境合规教训（有锁+有界）。"""
        import threading
        if not hasattr(self, "_write_lock"):
            self._write_lock = threading.Lock()
        with self._write_lock:
            self._lessons_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "lesson": lesson[:500],
                "context": context[:200],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self._lessons_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            try:
                lines = self._lessons_path.read_text(encoding="utf-8").strip().split("\n")
                if len(lines) > self._MAX_LESSONS:
                    keep = lines[-self._MAX_LESSONS:]
                    self._lessons_path.write_text("\n".join(keep) + "\n", encoding="utf-8")
            except Exception:
                pass
        self._log.info("教训已保存: %s", lesson[:50])
