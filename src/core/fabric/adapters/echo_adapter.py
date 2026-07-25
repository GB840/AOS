"""全网回声采集适配器（Echo）—— AOS 内容飞轮的反馈层。

输入关键词/产品名 → 搜索全网讨论 → 抓取评论 → 情感分析 → 需求挖掘。

设计原则：
- 多源采集：web.search + web.fetch + 浏览器抓取
- 分级分析：关键词提取 → 情感分析 → 需求挖掘 → 竞品对比
- 诚实：数据来源可追溯，不伪造评论
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from ..capability import Capability, TIER_HIGH

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.environ.get(
    "AOS_ECHO_OUTPUT_DIR",
    os.path.join("data", "workspaces", "fabric", "echo"),
)


def _output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


@dataclass
class FeedbackItem:
    """单条反馈。"""
    source: str  # 来源平台
    content: str  # 内容
    sentiment: str = "neutral"  # positive / negative / neutral
    keywords: List[str] = field(default_factory=list)
    url: str = ""
    author: str = ""


@dataclass
class EchoResult:
    """一次采集的完整结果。"""
    task_id: str
    keyword: str
    total_count: int = 0
    positive_count: int = 0
    negative_count: int = 0
    neutral_count: int = 0
    feedbacks: List[FeedbackItem] = field(default_factory=list)
    top_keywords: List[str] = field(default_factory=list)
    needs: List[str] = field(default_factory=list)
    summary: str = ""
    ok: bool = False
    error: str = ""


class EchoAdapter(BaseAgentAdapter):
    """全网回声采集适配器。

    MVP 阶段：web.search 搜索相关讨论，web.fetch 抓内容，基础关键词+情感分析。
    后续阶段：接入各平台 API / 浏览器抓取评论区，VLM 读图识别弹幕。
    """

    @property
    def engine_id(self) -> str:
        return "echo"

    def __init__(self, route_fn=None, pulse=None) -> None:
        self._route_fn = route_fn
        self._pulse = pulse  # 可选：PulseCollector，用于上报内容反馈数据

    def set_route_fn(self, route_fn) -> None:
        self._route_fn = route_fn

    def set_pulse(self, pulse) -> None:
        """注入 PulseCollector（可选，不注入就不上报）。"""
        self._pulse = pulse

    def advertise_capabilities(self) -> list[Capability]:
        return [Capability.CONTENT_FEEDBACK, Capability.CONTENT_SENTIMENT, Capability.CONTENT_NEED_MINING]

    def health(self) -> bool:
        return self._route_fn is not None

    def tier(self) -> str:
        return TIER_HIGH

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if self._route_fn is None:
            return InvokeResult(
                ok=False,
                error="echo 未注入 route_fn",
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        keyword = (payload.get("keyword") or payload.get("topic") or payload.get("query") or "").strip()
        if not keyword:
            return InvokeResult(
                ok=False,
                error="缺少 keyword（搜索关键词）",
                engine_id=self.engine_id,
            )
        max_results = payload.get("max_results") or 20
        deep_analysis = payload.get("deep_analysis", False)
        use_llm = payload.get("use_llm", True)

        try:
            result = self.collect(
                keyword=keyword,
                max_results=max_results,
                deep_analysis=deep_analysis,
                use_llm=use_llm,
            )
            # 可选：上报到 Pulse（内容飞轮数据 → Evolve 自动优化）
            if self._pulse is not None and result.ok:
                try:
                    self._pulse.record_feedback(
                        f"echo:{keyword}",
                        {
                            "type": "content_feedback",
                            "keyword": keyword,
                            "total_count": result.total_count,
                            "positive_count": result.positive_count,
                            "negative_count": result.negative_count,
                            "neutral_count": result.neutral_count,
                            "top_keywords": result.top_keywords,
                            "needs": result.needs,
                            "summary": result.summary,
                            "task_id": result.task_id,
                        }
                    )
                except Exception:  # noqa: BLE001 - Pulse 上报失败不影响主流程
                    pass
            return InvokeResult(
                ok=result.ok,
                data={
                    "task_id": result.task_id,
                    "keyword": result.keyword,
                    "total_count": result.total_count,
                    "positive_count": result.positive_count,
                    "negative_count": result.negative_count,
                    "neutral_count": result.neutral_count,
                    "top_keywords": result.top_keywords,
                    "needs": result.needs,
                    "summary": result.summary,
                    "feedbacks": [
                        {
                            "source": f.source,
                            "content": f.content,
                            "sentiment": f.sentiment,
                            "keywords": f.keywords,
                            "url": f.url,
                        }
                        for f in result.feedbacks
                    ],
                },
                engine_id=self.engine_id,
                error=result.error,
            )
        except Exception as e:  # noqa: BLE001
            return InvokeResult(
                ok=False,
                error=f"采集失败: {e}",
                engine_id=self.engine_id,
            )

    def collect(self, *, keyword: str, max_results: int = 20,
                deep_analysis: bool = False, use_llm: bool = True) -> EchoResult:
        """采集全网反馈。"""
        task_id = uuid.uuid4().hex[:8]
        result = EchoResult(task_id=task_id, keyword=keyword)

        # 第 1 步：搜索相关内容
        search_results = self._search(keyword, max_results=max_results)
        if not search_results:
            result.error = "未搜索到相关内容"
            result.ok = False
            return result

        # 第 2 步：抓取并解析内容
        feedbacks = self._extract_feedbacks(search_results, keyword)
        result.feedbacks = feedbacks
        result.total_count = len(feedbacks)

        # 第 3 步：情感分析（规则版）
        self._analyze_sentiment(result)

        # 第 4 步：关键词提取
        self._extract_keywords(result)

        # 第 5 步：需求挖掘
        self._mine_needs(result)

        # 第 6 步：LLM 深度分析（可选）
        if use_llm and deep_analysis:
            self._llm_deep_analysis(result)

        # 第 7 步：生成总结
        result.summary = self._generate_summary(result)

        # 保存结果
        self._save_result(result)

        result.ok = len(result.feedbacks) > 0
        return result

    def _search(self, keyword: str, max_results: int = 20) -> List[Dict]:
        """搜索相关内容。"""
        if not self._route_fn:
            return []

        try:
            # 用多种 query 搜索，增加覆盖面
            queries = [
                keyword,
                f"{keyword} 怎么样",
                f"{keyword} 评测",
                f"{keyword} 体验",
            ]

            all_results = []
            seen_urls = set()

            for query in queries[:2]:  # MVP 先搜 2 个 query，避免太慢
                res = self._route_fn("web.search", {
                    "query": query,
                    "max_results": min(max_results, 10),
                })
                data = res.data if hasattr(res, "data") and res.ok else {}
                items = data.get("results") or data.get("items") or []
                for item in items:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_results.append(item)
                    if len(all_results) >= max_results:
                        break
                if len(all_results) >= max_results:
                    break

            return all_results[:max_results]
        except Exception as e:
            logger.warning("搜索失败: %s", e)
            return []

    def _extract_feedbacks(self, search_results: List[Dict], keyword: str) -> List[FeedbackItem]:
        """从搜索结果中提取反馈。"""
        feedbacks = []

        for item in search_results:
            try:
                title = item.get("title", "")
                snippet = item.get("snippet") or item.get("description", "")
                url = item.get("url", "")
                source = self._guess_source(url)

                # 标题本身可能就是一条反馈
                if title:
                    feedbacks.append(FeedbackItem(
                        source=source,
                        content=title,
                        url=url,
                    ))

                # 摘要也是反馈
                if snippet and snippet != title:
                    feedbacks.append(FeedbackItem(
                        source=source,
                        content=snippet,
                        url=url,
                    ))
            except Exception as e:
                logger.debug("解析搜索结果失败: %s", e)
                continue

        return feedbacks

    @staticmethod
    def _guess_source(url: str) -> str:
        """从 URL 猜测来源平台。"""
        if not url:
            return "unknown"
        if "douyin" in url or "iesdouyin" in url:
            return "抖音"
        if "bilibili" in url:
            return "B站"
        if "xiaohongshu" in url or "xhslink" in url:
            return "小红书"
        if "weibo" in url:
            return "微博"
        if "zhihu" in url:
            return "知乎"
        if "youtube" in url:
            return "YouTube"
        if "twitter" in url or "x.com" in url:
            return "X"
        if "csdn" in url:
            return "CSDN"
        if "juejin" in url:
            return "掘金"
        if "baidu" in url:
            return "百度"
        return "网页"

    def _analyze_sentiment(self, result: EchoResult) -> None:
        """基础情感分析（关键词规则）。"""
        positive_words = [
            "好用", "很棒", "优秀", "厉害", "推荐", "喜欢", "不错", "牛",
            "强", "赞", "惊喜", "满意", "方便", "高效", "智能", "牛逼",
            "yyds", "绝了", "神", "超棒", "完美", "真香", "爱了",
        ]
        negative_words = [
            "难用", "垃圾", "坑爹", "失望", "不行", "差", "慢", "卡",
            "bug", "崩溃", "失败", "坑", "骗", "垃圾", "劝退", "踩雷",
            "不好", "差劲", "麻烦", "复杂", "贵", "不值",
        ]

        for fb in result.feedbacks:
            content = fb.content.lower()
            pos_score = sum(1 for w in positive_words if w in content)
            neg_score = sum(1 for w in negative_words if w in content)

            if pos_score > neg_score and pos_score > 0:
                fb.sentiment = "positive"
                result.positive_count += 1
            elif neg_score > pos_score and neg_score > 0:
                fb.sentiment = "negative"
                result.negative_count += 1
            else:
                fb.sentiment = "neutral"
                result.neutral_count += 1

    def _extract_keywords(self, result: EchoResult) -> None:
        """提取高频关键词。"""
        # 简单的词频统计（MVP 版，用常见中文词）
        word_freq: Dict[str, int] = {}

        common_words = [
            "智能", "效率", "体验", "功能", "速度", "质量", "价格", "免费",
            "好用", "难用", "推荐", "更新", "优化", "问题", "bug", "卡",
            "慢", "快", "方便", "复杂", "简单", "自动", "手动",
            "教程", "入门", "进阶", "评测", "对比", "测评",
        ]

        for fb in result.feedbacks:
            content = fb.content
            for word in common_words:
                if word in content:
                    word_freq[word] = word_freq.get(word, 0) + 1
                    if word not in fb.keywords:
                        fb.keywords.append(word)

        # 按频率排序，取前 10
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
        result.top_keywords = [w for w, c in sorted_words[:10]]

    def _mine_needs(self, result: EchoResult) -> None:
        """挖掘用户需求。"""
        need_patterns = [
            ("希望", "功能期望"),
            ("能不能", "功能期望"),
            ("要是", "功能期望"),
            ("什么时候", "时间期望"),
            ("支持", "功能期望"),
            ("怎么", "使用疑问"),
            ("为什么", "使用疑问"),
            ("求", "功能期望"),
            ("建议", "改进建议"),
            ("问题", "问题反馈"),
            ("bug", "问题反馈"),
            ("报错", "问题反馈"),
        ]

        needs_set = set()

        for fb in result.feedbacks:
            content = fb.content
            for pattern, category in need_patterns:
                if pattern in content:
                    needs_set.add(f"[{category}] {content[:50]}...")
                    break

        result.needs = list(needs_set)[:10]

    def _generate_summary(self, result: EchoResult) -> str:
        """生成总结。"""
        total = result.total_count
        if total == 0:
            return "无相关讨论"

        pos_pct = int(result.positive_count / total * 100) if total > 0 else 0
        neg_pct = int(result.negative_count / total * 100) if total > 0 else 0
        neu_pct = 100 - pos_pct - neg_pct

        lines = [
            f"关键词「{result.keyword}」全网反馈总结：",
            f"共采集 {total} 条相关讨论。",
            f"正面 {result.positive_count} 条（{pos_pct}%），"
            f"负面 {result.negative_count} 条（{neg_pct}%），"
            f"中性 {result.neutral_count} 条（{neu_pct}%）。",
        ]

        if result.top_keywords:
            lines.append(f"高频关键词：{', '.join(result.top_keywords[:5])}")

        if result.needs:
            lines.append(f"发现 {len(result.needs)} 条潜在需求/问题。")

        return "\n".join(lines)

    def _llm_deep_analysis(self, result: EchoResult) -> None:
        """LLM 深度分析（本地 ollama）。"""
        try:
            from core.fabric.utils.ollama_utils import llm_chat, llm_available
            if not llm_available():
                logger.debug("本地 LLM 不可用，跳过深度分析")
                return

            # 准备分析材料
            feedback_texts = [f.content for f in result.feedbacks[:30]]
            feedback_sample = "\n".join(f"{i+1}. {t}" for i, t in enumerate(feedback_texts))

            prompt = f"""你是一个用户反馈分析师。请分析以下关于「{result.keyword}」的用户反馈，给出深度洞察。

用户反馈（{len(feedback_texts)} 条）:
{feedback_sample}

请输出以下内容：
1. 整体评价：用户对这个产品/话题的整体态度如何？
2. 核心痛点：用户最不满的 3 个问题是什么？
3. 核心亮点：用户最喜欢的 3 个点是什么？
4. 需求建议：用户最希望增加/改进的 5 个功能是什么？
5. 内容建议：针对这些反馈，下一期内容应该做什么主题？

请用简洁的中文回答，每点不超过 50 字。
"""

            analysis = llm_chat(prompt, temperature=0.5, max_tokens=1500, timeout=120)
            if analysis:
                result.summary = f"【LLM 深度分析】\n{analysis}\n\n【基础统计】\n{result.summary}"
                logger.info("LLM 深度分析完成")
        except Exception as e:
            logger.warning("LLM 深度分析失败: %s", e)

    def _save_result(self, result: EchoResult) -> str:
        """保存结果到 JSON 文件。"""
        task_dir = os.path.join(_output_dir(), result.task_id)
        os.makedirs(task_dir, exist_ok=True)

        data = {
            "task_id": result.task_id,
            "keyword": result.keyword,
            "total_count": result.total_count,
            "positive_count": result.positive_count,
            "negative_count": result.negative_count,
            "neutral_count": result.neutral_count,
            "top_keywords": result.top_keywords,
            "needs": result.needs,
            "summary": result.summary,
            "feedbacks": [
                {
                    "source": f.source,
                    "content": f.content,
                    "sentiment": f.sentiment,
                    "keywords": f.keywords,
                    "url": f.url,
                }
                for f in result.feedbacks
            ],
        }

        json_path = os.path.join(task_dir, "echo_result.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return json_path
