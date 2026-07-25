"""跨租户经验共享——全网'已知失败模式库'。

核心思路：
- 每个租户的失败教训匿名化后上传到共享池
- 新租户首次使用时，自动注入全网已知的失败模式
- 隐私保护：只共享失败模式和解决方案，不共享具体数据
- 置信度门控：只有被多个租户验证过的经验才注入

这是SaaS模式的真正护城河：用的人越多，系统越聪明。

典型工作流：
1. autopilot反思失败时，upload_experience()上传教训
2. 新租户注册时，inject_for_new_tenant()注入全网经验
3. 租户验证经验后，verify_experience()更新置信度
4. query_experiences()按需查询高置信度经验
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# 需要脱敏的敏感模式
_SENSITIVE_PATTERNS = [
    re.compile(r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'),  # 信用卡号
    re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),  # 邮箱
    re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'),  # 电话号码
    re.compile(r'\b\d{6}(?:19|20)\d{2}(?:0[1-9]|1[012])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b'),  # 身份证号
    re.compile(r'(?:password|passwd|pwd|secret|token|key)\s*[=:]\s*\S+', re.IGNORECASE),  # 密钥
    re.compile(r'(?:api[_-]?key|access[_-]?key)\s*[=:]\s*\S+', re.IGNORECASE),  # API key
]


@dataclass
class SharedExperience:
    """一条共享经验。

    置信度计算：
    confidence = verification_count / upload_count
    当多个租户验证后，confidence会逐步上升。
    只有confidence >= threshold的经验才会被注入给新租户。
    """
    experience_id: str
    category: str           # failure_pattern / best_practice / optimization
    capability: str         # 涉及的能力
    pattern: str            # 失败模式描述（匿名化）
    solution: str           # 解决方案
    engine: str             # 推荐引擎
    confidence: float       # 置信度（被验证次数/总上传次数）
    verification_count: int # 被验证次数
    upload_count: int       # 总上传次数
    tenant_count: int       # 贡献租户数（匿名计数）
    created_at: float = field(default_factory=time.time)
    updated_at: float = 0.0
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "category": self.category,
            "capability": self.capability,
            "pattern": self.pattern,
            "solution": self.solution,
            "engine": self.engine,
            "confidence": self.confidence,
            "verification_count": self.verification_count,
            "upload_count": self.upload_count,
            "tenant_count": self.tenant_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tags": self.tags,
        }


class ExperienceSharingEngine:
    """跨租户经验共享引擎。

    存储格式：JSONL文件，每行一条SharedExperience。
    同一经验（相同category+capability+pattern）只创建一次，后续上传只更新计数。

    典型用法：
    ```python
    engine = ExperienceSharingEngine()

    # 上传经验（匿名化后）
    exp_id = engine.upload_experience(
        tenant_id="tenant_abc",
        category="failure_pattern",
        capability="web.search",
        pattern="引擎X在中文搜索时返回空结果",
        solution="切换到引擎Y",
        engine="baidu",
    )

    # 新租户注入
    lessons = engine.inject_for_new_tenant("tenant_new", ["web.search"])

    # 验证经验
    engine.verify_experience(exp_id, "tenant_xyz", verified=True)
    ```
    """

    def __init__(self, store_path: str = None):
        self._store_path = store_path or os.path.join(
            os.path.dirname(__file__), "..", "..", "data",
            "workspaces", "experience", "shared.jsonl")
        self._experiences: Dict[str, SharedExperience] = {}
        self._tenant_seen: Dict[str, set] = {}  # tenant_id -> set of experience_ids
        self._lock = threading.Lock()
        self._load()

    def upload_experience(self, tenant_id: str, category: str,
                          capability: str, pattern: str, solution: str,
                          engine: str = "") -> str:
        """上传一条经验（匿名化后进入共享池）。

        隐私处理：
        - tenant_id 只用于去重（同一租户不重复计数）
        - 不存储任何租户特定数据
        - pattern 和 solution 中的敏感信息自动脱敏

        Args:
            tenant_id: 租户ID（仅用于去重，不存储）
            category: 类别（failure_pattern/best_practice/optimization）
            capability: 涉及的能力（如 web.search）
            pattern: 失败模式描述
            solution: 解决方案
            engine: 推荐引擎

        Returns:
            experience_id
        """
        # 匿名化
        pattern_clean = self._anonymize(pattern)
        solution_clean = self._anonymize(solution)

        # 生成幂等ID
        exp_id = self._generate_id(category, capability, pattern_clean)

        with self._lock:
            if exp_id in self._experiences:
                # 已存在：更新计数
                exp = self._experiences[exp_id]
                exp.upload_count += 1
                # 同一租户不重复计入tenant_count
                if tenant_id not in self._tenant_seen.get(exp_id, set()):
                    exp.tenant_count += 1
                    self._tenant_seen.setdefault(exp_id, set()).add(tenant_id)
                exp.confidence = exp.verification_count / exp.upload_count if exp.upload_count else 0
                exp.updated_at = time.time()
            else:
                # 新建
                exp = SharedExperience(
                    experience_id=exp_id,
                    category=category,
                    capability=capability,
                    pattern=pattern_clean,
                    solution=solution_clean,
                    engine=engine,
                    confidence=0.0,
                    verification_count=0,
                    upload_count=1,
                    tenant_count=1,
                    tags=self._extract_tags(pattern_clean, solution_clean),
                )
                self._experiences[exp_id] = exp
                self._tenant_seen[exp_id] = {tenant_id}

            self._save()
            return exp_id

    def query_experiences(self, capability: str = None,
                         category: str = None,
                         min_confidence: float = 0.3,
                         limit: int = 10) -> List[SharedExperience]:
        """查询共享经验（按置信度排序）。

        Args:
            capability: 按能力过滤
            category: 按类别过滤
            min_confidence: 最低置信度
            limit: 返回数量上限

        Returns:
            符合条件的经验列表，按置信度降序
        """
        with self._lock:
            results = list(self._experiences.values())

        # 过滤
        if capability:
            results = [e for e in results if e.capability == capability]
        if category:
            results = [e for e in results if e.category == category]
        results = [e for e in results if e.confidence >= min_confidence]

        # 按置信度排序
        results.sort(key=lambda e: (-e.confidence, -e.verification_count))

        return results[:limit]

    def verify_experience(self, experience_id: str, tenant_id: str,
                          verified: bool = True) -> None:
        """验证一条经验（租户确认该经验是否有效）。

        每个租户对每条经验只能验证一次（verified和unverified都算）。
        verified=True增加verification_count，verified=False不增加。

        Args:
            experience_id: 经验ID
            tenant_id: 租户ID（用于防重复验证）
            verified: 是否确认有效
        """
        verify_key = f"{experience_id}:{tenant_id}"

        with self._lock:
            exp = self._experiences.get(experience_id)
            if exp is None:
                return

            # 检查是否已验证过
            seen = self._tenant_seen.get(experience_id, set())
            if tenant_id in seen:
                return  # 同一租户只验证一次

            # 记录验证
            seen.add(tenant_id)
            self._tenant_seen[experience_id] = seen

            if verified:
                exp.verification_count += 1

            # 更新置信度
            exp.confidence = exp.verification_count / exp.upload_count if exp.upload_count else 0
            exp.updated_at = time.time()

            self._save()

    def inject_for_new_tenant(self, tenant_id: str,
                              capabilities: List[str] = None) -> List[Dict]:
        """为新租户注入全网已知经验。

        返回：需要在autopilot反思中注入的教训列表。

        注入条件：
        - confidence >= 0.3（至少30%验证率）
        - category == failure_pattern（只注入失败模式，best_practice需主动查询）
        - capability在指定范围内（若指定）

        Args:
            tenant_id: 新租户ID
            capabilities: 可选的能力过滤列表

        Returns:
            教训列表，格式适配autopilot反思注入
        """
        # 查询高置信度失败模式
        candidates = self.query_experiences(
            category="failure_pattern",
            min_confidence=0.3,
            limit=50,
        )

        # 按能力过滤
        if capabilities:
            cap_set = set(capabilities)
            candidates = [e for e in candidates if e.capability in cap_set]

        # 转换为autopilot反思格式
        lessons = []
        for exp in candidates:
            lesson = {
                "source": "global_shared",
                "experience_id": exp.experience_id,
                "category": exp.category,
                "capability": exp.capability,
                "lesson": f"已知失败模式: {exp.pattern}\n解决方案: {exp.solution}",
                "engine": exp.engine,
                "confidence": exp.confidence,
                "verification_count": exp.verification_count,
            }
            lessons.append(lesson)

            # 记录该租户已注入（防重复注入）
            with self._lock:
                self._tenant_seen.setdefault(exp.experience_id, set()).add(tenant_id)

        return lessons

    def get_experience_stats(self) -> Dict[str, Any]:
        """获取共享经验统计。"""
        with self._lock:
            experiences = list(self._experiences.values())

        total = len(experiences)
        if total == 0:
            return {"total": 0}

        by_category = {}
        by_capability = {}
        total_verifications = 0
        total_uploads = 0

        for exp in experiences:
            by_category[exp.category] = by_category.get(exp.category, 0) + 1
            by_capability[exp.capability] = by_capability.get(exp.capability, 0) + 1
            total_verifications += exp.verification_count
            total_uploads += exp.upload_count

        avg_confidence = sum(e.confidence for e in experiences) / total
        high_confidence = sum(1 for e in experiences if e.confidence >= 0.5)

        return {
            "total": total,
            "by_category": by_category,
            "by_capability": by_capability,
            "avg_confidence": round(avg_confidence, 4),
            "high_confidence_count": high_confidence,
            "total_verifications": total_verifications,
            "total_uploads": total_uploads,
        }

    def _anonymize(self, text: str) -> str:
        """匿名化：移除租户特定信息。

        处理：
        1. 移除敏感模式（信用卡、邮箱、电话、身份证、密钥）
        2. 移除文件路径中的用户名部分
        3. 移除IP地址
        """
        result = text

        # 移除敏感模式
        for pattern in _SENSITIVE_PATTERNS:
            result = pattern.sub("[REDACTED]", result)

        # 移除文件路径中的用户名
        result = re.sub(r'/Users/[^/]+/', '/Users/[USER]/', result)
        result = re.sub(r'C:[/\\]Users[/\\][^/\\]+[/\\]', 'C:/Users/[USER]/', result)
        result = re.sub(r'/home/[^/]+/', '/home/[USER]/', result)

        # 移除IP地址
        result = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '[IP]', result)

        # 移除URL中的认证信息
        result = re.sub(r'://[^:]+:[^@]+@', '://[AUTH]@', result)

        return result

    def _generate_id(self, category: str, capability: str, pattern: str) -> str:
        """生成幂等ID（相同内容不重复创建）。"""
        content = f"{category}:{capability}:{pattern}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]

    def _extract_tags(self, pattern: str, solution: str) -> List[str]:
        """从模式和解决方案中提取标签。"""
        tags = set()

        # 常见关键词
        keywords = [
            "timeout", "超时", "空结果", "empty", "rate limit", "限流",
            "memory", "内存", "disk", "磁盘", "network", "网络",
            "auth", "认证", "permission", "权限", "deprecated", "弃用",
            "bug", "error", "错误", "crash", "崩溃",
        ]
        text = (pattern + " " + solution).lower()
        for kw in keywords:
            if kw in text:
                tags.add(kw)

        return sorted(tags)

    def _load(self) -> None:
        """从JSONL文件加载共享经验。"""
        if not os.path.exists(self._store_path):
            return

        try:
            with open(self._store_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        exp = SharedExperience(
                            experience_id=data["experience_id"],
                            category=data["category"],
                            capability=data["capability"],
                            pattern=data["pattern"],
                            solution=data["solution"],
                            engine=data.get("engine", ""),
                            confidence=data.get("confidence", 0),
                            verification_count=data.get("verification_count", 0),
                            upload_count=data.get("upload_count", 1),
                            tenant_count=data.get("tenant_count", 1),
                            created_at=data.get("created_at", 0),
                            updated_at=data.get("updated_at", 0),
                            tags=data.get("tags", []),
                        )
                        self._experiences[exp.experience_id] = exp
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception:
            pass

    def _save(self) -> None:
        """保存共享经验到JSONL文件。"""
        os.makedirs(os.path.dirname(self._store_path), exist_ok=True)

        with open(self._store_path, "w", encoding="utf-8") as f:
            for exp in self._experiences.values():
                f.write(json.dumps(exp.to_dict(), ensure_ascii=False) + "\n")
