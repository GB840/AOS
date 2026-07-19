"""投标分析智能体 — AOS 首个商业落地场景 MVP。

输入：招标文件 PDF 路径（+ 可选的企业资质清单）
输出：结构化分析报告（需求提取 + 资质匹配 + 合规风险清单 + 投标策略建议）

设计原则（Ponytail 阶梯）：
- PDF 解析用 pymupdf（已安装，标准库级）
- 合规检查用结构化规则引擎（非纯 LLM 猜测）
- LLM 仅用于"理解性"任务（需求归纳、策略建议）
- 全链路 trace 可复核（理念 8/9）
- 反思学习：每次分析结果 + 用户反馈 → 持久化教训（理念 2）

用法：
    from skills.bidding_agent import BiddingAgent
    agent = BiddingAgent()
    result = agent.execute({"pdf_path": "招标文件.pdf", "company_profile": {...}})
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
# 合规规则定义（结构化，非 LLM 猜测）
# ---------------------------------------------------------------------------

@dataclass
class ComplianceRule:
    """一条合规检查规则。"""
    rule_id: str
    category: str  # 资质/格式/条款/报价/程序
    description: str
    severity: str  # critical / major / minor
    check_type: str  # keyword_absent / keyword_present / date_valid / amount_check
    pattern: str = ""  # 正则或关键词
    hint: str = ""  # 命中时的提示


# 32 类常见废标风险规则（首批 16 条核心规则，后续可扩展）
COMPLIANCE_RULES: List[ComplianceRule] = [
    # --- 资质类 ---
    ComplianceRule("Q01", "资质", "营业执照有效期", "critical", "keyword_present",
                   r"营业执照", "需确认营业执照在投标有效期内"),
    ComplianceRule("Q02", "资质", "资质证书等级匹配", "critical", "keyword_present",
                   r"(资质|等级|甲级|乙级|丙级|一级|二级|三级)", "核对资质等级是否满足招标要求"),
    ComplianceRule("Q03", "资质", "安全生产许可证", "critical", "keyword_present",
                   r"安全生产许可", "工程类项目必须提供安全生产许可证"),
    ComplianceRule("Q04", "资质", "项目经理资格", "major", "keyword_present",
                   r"(项目经理|注册.*?师|建造师)", "核对项目经理证书类型和等级"),
    ComplianceRule("Q05", "资质", "业绩要求", "major", "keyword_present",
                   r"(业绩|类似项目|近\d+年)", "核对业绩年限和金额是否满足"),
    # --- 格式类 ---
    ComplianceRule("F01", "格式", "投标文件份数", "major", "keyword_present",
                   r"(正本|副本|份|套)", "确认正副本份数符合要求"),
    ComplianceRule("F02", "格式", "密封要求", "critical", "keyword_present",
                   r"(密封|封口|骑缝章)", "未按要求密封直接废标"),
    ComplianceRule("F03", "格式", "签字盖章", "critical", "keyword_present",
                   r"(签字|盖章|公章|法人章|授权)", "缺少签字盖章直接废标"),
    ComplianceRule("F04", "格式", "页码/目录", "minor", "keyword_present",
                   r"(页码|目录|编页)", "建议编制目录和连续页码"),
    # --- 条款响应类 ---
    ComplianceRule("T01", "条款", "实质性条款响应", "critical", "keyword_present",
                   r"(实质性|星号|★|不得偏离|必须响应)", "实质性条款未响应直接废标"),
    ComplianceRule("T02", "条款", "工期/交货期", "major", "keyword_present",
                   r"(工期|交货期|完成时间|日历天)", "工期不得超过招标要求"),
    ComplianceRule("T03", "条款", "质保期/保修", "major", "keyword_present",
                   r"(质保|保修|缺陷责任期)", "质保期不得低于招标要求"),
    ComplianceRule("T04", "条款", "付款方式响应", "minor", "keyword_present",
                   r"(付款|支付|进度款|结算)", "确认付款方式响应"),
    # --- 报价类 ---
    ComplianceRule("P01", "报价", "报价唯一性", "critical", "keyword_present",
                   r"(唯一报价|选择性报价|备选方案)", "不得提交选择性报价"),
    ComplianceRule("P02", "报价", "报价不超过控制价", "critical", "keyword_present",
                   r"(控制价|最高限价|预算|拦标价)", "报价不得超过最高限价"),
    ComplianceRule("P03", "报价", "大小写金额一致", "major", "keyword_present",
                   r"(大写|小写|人民币|元整)", "大小写金额不一致废标"),
    # --- 程序类 ---
    ComplianceRule("X01", "程序", "投标保证金", "critical", "keyword_present",
                   r"(保证金|投标保证金|保函)", "未按时缴纳保证金废标"),
]


# ---------------------------------------------------------------------------
# PDF 解析器（pymupdf 薄封装）
# ---------------------------------------------------------------------------

def parse_bidding_pdf(pdf_path: str) -> Dict[str, Any]:
    """解析招标文件 PDF，提取文本 + 结构信息。

    Returns:
        {
            "pages": int,
            "full_text": str,
            "sections": [{"title": str, "content": str, "page": int}],
            "tables_hint": int,  # 疑似表格区域数
            "keywords_found": [str],
        }
    """
    try:
        import fitz  # pymupdf
    except ImportError:
        return {"error": "pymupdf 未安装，请 pip install pymupdf", "pages": 0}

    if not pdf_path or not pdf_path.strip():
        return {"error": "pdf_path 不能为空", "pages": 0}

    path = Path(pdf_path).resolve()
    if not path.exists():
        return {"error": f"文件不存在: {pdf_path}", "pages": 0}
    if not path.is_file():
        return {"error": f"路径不是文件: {pdf_path}", "pages": 0}
    if path.suffix.lower() not in (".pdf", ".PDF"):
        return {"error": f"非 PDF 文件（扩展名 {path.suffix}）: {pdf_path}", "pages": 0}

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        return {"error": f"PDF 打开失败（可能损坏/加密）: {e}", "pages": 0}

    pages_text: List[str] = []
    sections: List[Dict[str, Any]] = []
    tables_hint = 0

    try:
        for page_num, page in enumerate(doc, 1):
            text = page.get_text("text")
            pages_text.append(text)

            # 简单结构检测：以"第X章"/"X、"/数字编号开头的行视为章节标题
            for line in text.split("\n"):
                line = line.strip()
                if re.match(r"^(第[一二三四五六七八九十]+[章节]|[一二三四五六七八九十]+、|\d+[.、])", line):
                    if len(line) < 80:  # 标题通常不长
                        sections.append({"title": line, "content": "", "page": page_num})

            # 表格检测：连续多行含多个制表符/多空格分隔
            table_lines = [l for l in text.split("\n") if l.count("\t") >= 2 or len(re.findall(r"\s{3,}", l)) >= 2]
            if len(table_lines) > 3:
                tables_hint += 1
    finally:
        doc.close()

    full_text = "\n".join(pages_text)

    # 关键词提取
    key_patterns = [
        r"投标截止[时日]间[：:]\s*(.+)",
        r"开标[时日]间[：:]\s*(.+)",
        r"投标保证金[：:]\s*(.+)",
        r"(?:最高限价|控制价|预算金额)[：:]\s*(.+)",
        r"工期[：:]\s*(.+)",
        r"质保期[：:]\s*(.+)",
    ]
    keywords_found = []
    for pat in key_patterns:
        m = re.search(pat, full_text)
        if m:
            keywords_found.append(m.group(0).strip())

    return {
        "pages": len(pages_text),
        "full_text": full_text,
        "sections": sections,
        "tables_hint": tables_hint,
        "keywords_found": keywords_found,
    }


# ---------------------------------------------------------------------------
# 合规检查引擎
# ---------------------------------------------------------------------------

def run_compliance_checks(full_text: str,
                          rules: List[ComplianceRule] = None) -> List[Dict[str, Any]]:
    """对招标文件全文执行结构化合规检查。

    返回每条规则的命中/未命中状态 + 风险等级 + 建议。
    """
    if rules is None:
        rules = COMPLIANCE_RULES

    results = []
    for rule in rules:
        hit = bool(re.search(rule.pattern, full_text, re.IGNORECASE))
        results.append({
            "rule_id": rule.rule_id,
            "category": rule.category,
            "description": rule.description,
            "severity": rule.severity,
            "mentioned_in_doc": hit,
            "risk_note": rule.hint if hit else f"招标文件未明确提及「{rule.description}」——需人工确认是否适用",
        })
    return results


# ---------------------------------------------------------------------------
# 主技能类
# ---------------------------------------------------------------------------

class BiddingAgent(Skill):
    """投标分析智能体：PDF → 需求提取 + 资质匹配 + 合规风险 + 策略建议。"""

    NAME = "bidding-agent"
    DESCRIPTION = "投标文件智能分析：解析招标PDF，提取核心需求，匹配资质，识别合规风险，生成投标策略建议"
    VERSION = "0.1.0"
    AUTHOR = "AOS"
    LICENSE = "MIT"
    CATEGORY = "business"
    TAGS = ["投标", "标书", "合规", "招标", "bidding"]
    CAPABILITIES = ["bidding.analyze", "bidding.compliance"]

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
        self._lessons_path = Path(__file__).parent.parent.parent / "_traces" / "bidding_lessons.jsonl"

    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """主入口。

        context:
            pdf_path: str — 招标文件 PDF 路径（必须）
            company_profile: dict — 企业资质信息（可选）
                {"name", "qualifications": [], "past_projects": [], "certificates": []}
            focus_areas: list — 重点关注领域（可选）

        Returns:
            {
                "ok": bool,
                "analysis": {...},
                "compliance": [...],
                "strategy": str,
                "trace": {...},
            }
        """
        t0 = time.time()
        pdf_path = context.get("pdf_path", "")
        company = context.get("company_profile", {})
        trace_steps: List[Dict[str, Any]] = []

        # Step 1: PDF 解析
        self._log.info("Step 1: 解析招标文件 PDF: %s", pdf_path)
        parsed = parse_bidding_pdf(pdf_path)
        trace_steps.append({
            "step": "pdf_parse", "ok": "error" not in parsed,
            "pages": parsed.get("pages", 0),
            "sections": len(parsed.get("sections", [])),
        })

        if "error" in parsed:
            return {"ok": False, "error": parsed["error"], "trace": {"steps": trace_steps}}

        full_text = parsed["full_text"]

        try:
            # Step 2: 需求提取（结构化正则 + 关键词）
            self._log.info("Step 2: 提取招标核心需求")
            requirements = self._extract_requirements(full_text, parsed)
            trace_steps.append({
                "step": "requirements_extract", "ok": True,
                "items_found": len(requirements),
            })

            # Step 3: 合规检查（结构化规则引擎）
            self._log.info("Step 3: 执行合规检查（%d 条规则）", len(COMPLIANCE_RULES))
            compliance = run_compliance_checks(full_text)
            critical_risks = [c for c in compliance if c["severity"] == "critical" and c["mentioned_in_doc"]]
            trace_steps.append({
                "step": "compliance_check", "ok": True,
                "rules_checked": len(compliance),
                "critical_risks": len(critical_risks),
            })

            # Step 4: 资质匹配（如果提供了企业信息）
            match_result = {}
            if company:
                self._log.info("Step 4: 资质匹配")
                match_result = self._match_qualifications(requirements, company)
                trace_steps.append({
                    "step": "qualification_match", "ok": True,
                    "matched": match_result.get("matched", 0),
                    "missing": match_result.get("missing", 0),
                })

            # Step 5: 策略建议（基于规则 + 历史教训）
            self._log.info("Step 5: 生成投标策略建议")
            lessons = self._load_lessons()
            strategy = self._generate_strategy(requirements, compliance, match_result, lessons)
            trace_steps.append({"step": "strategy", "ok": True})
        except Exception as e:
            self._log.error("分析过程异常: %s", e, exc_info=True)
            return {"ok": False, "error": f"分析过程异常: {e}", "trace": {"steps": trace_steps}}

        elapsed = round(time.time() - t0, 2)
        self._log.info("分析完成，耗时 %.2fs", elapsed)

        return {
            "ok": True,
            "analysis": {
                "pdf_pages": parsed["pages"],
                "sections_detected": len(parsed["sections"]),
                "tables_hint": parsed["tables_hint"],
                "key_info": parsed["keywords_found"],
                "requirements": requirements,
            },
            "compliance": compliance,
            "critical_risks": critical_risks,
            "qualification_match": match_result,
            "strategy": strategy,
            "trace": {
                "steps": trace_steps,
                "elapsed_sec": elapsed,
                "pdf_path": pdf_path,
            },
        }

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _extract_requirements(self, text: str, parsed: Dict) -> List[Dict[str, str]]:
        """从招标文件文本中提取核心需求条目。"""
        requirements = []
        _seen: set = set()  # O(1) 去重

        # 1. 资质要求
        qual_patterns = [
            r"(?:资质|资格)[要求条件]*[：:]\s*(.+?)(?:\n|$)",
            r"(?:投标人|供应商)(?:应|须|需)(?:具备|具有|持有)(.+?)(?:[。；\n])",
            r"(?:甲级|乙级|一级|二级|三级).{0,20}(?:资质|资格)",
        ]
        for pat in qual_patterns:
            for m in re.finditer(pat, text):
                req = m.group(0).strip()
                if len(req) > 5 and req not in _seen:
                    _seen.add(req)
                    requirements.append({"type": "资质", "detail": req[:200]})

        # 2. 业绩要求
        perf_patterns = [
            r"(?:近|最近)\s*\d+\s*年.{0,30}(?:业绩|项目|合同)",
            r"(?:类似|同类|相同).{0,20}(?:项目|工程|业绩)",
            r"(?:合同金额|单项).{0,10}(?:不低于|≥|大于)\s*[\d.]+\s*(?:万元|亿元)",
        ]
        for pat in perf_patterns:
            for m in re.finditer(pat, text):
                req = m.group(0).strip()
                if req not in _seen:
                    _seen.add(req)
                    requirements.append({"type": "业绩", "detail": req[:200]})

        # 3. 技术要求
        tech_patterns = [
            r"(?:技术参数|技术指标|技术规格)[：:].{10,100}",
            r"(?:必须|应当|需要)(?:满足|达到|符合).{5,80}(?:标准|规范|要求)",
        ]
        for pat in tech_patterns:
            for m in re.finditer(pat, text):
                req = m.group(0).strip()
                if req not in _seen:
                    _seen.add(req)
                    requirements.append({"type": "技术", "detail": req[:200]})

        # 4. 商务要求（工期、付款、质保）
        biz_patterns = [
            r"(?:工期|交货期|完成时间)[：:为]\s*(.+?)(?:[。\n])",
            r"(?:质保期|保修期|缺陷责任期)[：:为]\s*(.+?)(?:[。\n])",
            r"(?:付款方式|支付)[：:].{5,100}",
        ]
        for pat in biz_patterns:
            for m in re.finditer(pat, text):
                req = m.group(0).strip()
                if req not in _seen:
                    _seen.add(req)
                    requirements.append({"type": "商务", "detail": req[:200]})

        # 5. 关键时间节点（从 keywords_found 补充）
        for kw in parsed.get("keywords_found", []):
            requirements.append({"type": "时间", "detail": kw})

        return requirements

    def _match_qualifications(self, requirements: List[Dict],
                              company: Dict) -> Dict[str, Any]:
        """将企业已有资质与招标要求做匹配。"""
        company_quals = set()
        for q in company.get("qualifications", []):
            company_quals.add(q.lower())
        for c in company.get("certificates", []):
            company_quals.add(c.lower())

        matched = []
        missing = []
        uncertain = []

        for req in requirements:
            if req["type"] not in ("资质", "业绩"):
                continue
            detail_lower = req["detail"].lower()
            # 简单关键词匹配
            found = any(q in detail_lower for q in company_quals if len(q) > 2)
            if found:
                matched.append(req)
            elif any(kw in detail_lower for kw in ("必须", "应当", "不得", "强制")):
                missing.append(req)
            else:
                uncertain.append(req)

        return {
            "matched": len(matched),
            "missing": len(missing),
            "uncertain": len(uncertain),
            "matched_items": matched,
            "missing_items": missing,
            "uncertain_items": uncertain,
        }

    def _generate_strategy(self, requirements: List[Dict],
                           compliance: List[Dict],
                           match_result: Dict,
                           lessons: List[Dict]) -> str:
        """基于分析结果 + 历史教训生成策略建议。"""
        parts = []

        # 关键风险提醒
        criticals = [c for c in compliance if c["severity"] == "critical" and c["mentioned_in_doc"]]
        if criticals:
            parts.append(f"⚠️ 发现 {len(criticals)} 项关键合规要求：")
            for c in criticals[:5]:
                parts.append(f"  - [{c['rule_id']}] {c['description']}：{c['risk_note']}")

        # 资质缺口
        if match_result.get("missing"):
            parts.append(f"\n❌ 资质缺口 {match_result['missing']} 项（硬性要求未满足）：")
            for item in match_result.get("missing_items", [])[:3]:
                parts.append(f"  - {item['detail'][:80]}")
            parts.append("  建议：评估是否可联合体投标或放弃本项目。")

        # 历史教训
        if lessons:
            parts.append(f"\n📚 历史教训（{len(lessons)} 条）：")
            for l in lessons[-3:]:
                parts.append(f"  - {l.get('lesson', '')}")

        # 通用建议
        parts.append("\n📋 通用建议：")
        parts.append("  1. 逐条响应实质性条款（★标记），不得遗漏")
        parts.append("  2. 报价前确认最高限价，大小写金额核对三遍")
        parts.append("  3. 投标保证金提前 2 个工作日缴纳")
        parts.append("  4. 正副本分别密封，骑缝章 + 法人章缺一不可")
        parts.append("  5. 投标截止前 1 小时到达开标现场")

        return "\n".join(parts)

    def _load_lessons(self) -> List[Dict]:
        """加载历史投标教训（反思记忆）。"""
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
        return lessons[-20:]  # 只保留最近 20 条

    _MAX_LESSONS = 50  # 有界轮转上限

    def save_lesson(self, lesson: str, context: str = ""):
        """保存一条投标教训（反思闭环写入，有锁+有界）。"""
        import threading
        if not hasattr(self, "_write_lock"):
            self._write_lock = threading.Lock()
        with self._write_lock:
            self._lessons_path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "lesson": lesson[:500],  # 限制单条长度
                "context": context[:200],
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(self._lessons_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            # 有界轮转：超过上限时只保留最近 N 条
            try:
                lines = self._lessons_path.read_text(encoding="utf-8").strip().split("\n")
                if len(lines) > self._MAX_LESSONS:
                    keep = lines[-self._MAX_LESSONS:]
                    self._lessons_path.write_text("\n".join(keep) + "\n", encoding="utf-8")
            except Exception:
                pass
        self._log.info("教训已保存: %s", lesson[:50])
