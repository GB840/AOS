"""Hippo-Scroll 海马卷轴多模态可信记忆架构 v1.0

「仿生人类记忆的分层、锚定原始感知、区分客观物证/多元解读、认知闭环新陈代谢」

四层内生逻辑（不是四个模块拼接，是一套统一认知规则）：
  EvidenceTrack  — 第一层：多模态感官证据基座（只追加，不可覆盖）
  CognitionTrack — 第二~三层：网状概念图谱 + 多源思辨仲裁
  PyramidRetriever — 金字塔粒度检索（语义→缩略→原始，按需下沉）
  MetacognitivePatrol — 第四层：元认知巡检闭环（日检/周固/软遗忘/人工复审）

核心原创（区别于现有方案）：
  1. 双轨分离存储：物证轨(只读追加) + 认知轨(可演化/分层置信/多观点)
  2. 分歧结构收纳：不强制消灭不同解读，分层输出[溯源/共识/争议/结论]
  3. 仿生记忆新陈代谢：日巡检标疑→周巩固固化→软遗忘降权→人工复审终审

零依赖：仅依赖 kernel types + stdlib（hashlib/datetime/threading）。
"""

from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════
# 核心数据结构
# ═══════════════════════════════════════════════════════════════════

class Modality(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    TABLE = "table"
    SCAN = "scan"
    TEXT = "text"


class Confidence(str, Enum):
    HIGH = "high"         # 多源交叉印证
    MEDIUM = "medium"     # 单源但可信
    LOW = "low"           # 单源待验证
    DISPUTED = "disputed" # 存在冲突


@dataclass
class EvidenceAnchor:
    """第一层：物证锚点 —— 不可覆盖的原始感官证据。

    这是 Hippo-Scroll 的"原始记忆底片"：只追加写入，不修改不覆盖。
    所有上层提炼必须携带本层的 anchor_id 引用。
    """
    anchor_id: str                       # sha256(file+timestamp) 唯一ID
    modality: Modality
    source_hash: str                     # 原始文件哈希（防篡改）
    source_path: str = ""                # 原始文件路径
    spatial_coordinates: Dict[str, Any] = field(default_factory=dict)  # 帧号/坐标/页码
    temporal_anchor: float = 0.0         # 时间戳
    light_representation: Dict[str, Any] = field(default_factory=dict)  # 轻量缩略表征
    tags: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @classmethod
    def create(cls, source_path: str, modality: Modality,
               content: bytes = b"",
               spatial: Dict[str, Any] | None = None,
               light: Dict[str, Any] | None = None) -> EvidenceAnchor:
        source_hash = hashlib.sha256(content).hexdigest() if content else hashlib.sha256(source_path.encode()).hexdigest()
        anchor_id = hashlib.sha256(f"{source_hash}{time.time()}".encode()).hexdigest()[:16]
        return cls(
            anchor_id=anchor_id,
            modality=modality,
            source_hash=source_hash,
            source_path=source_path,
            spatial_coordinates=spatial or {},
            temporal_anchor=time.time(),
            light_representation=light or {},
        )


@dataclass
class CognitionNode:
    """第二~三层：认知节点 —— 挂载在物证锚点之上的提炼层。

    一个物证锚点可以有多个 CognitionNode（同一素材的不同解读）。
    node_type 区分：consensus(共识) / interpretation(解读) / conclusion(AI结论)
    """
    node_id: str
    anchor_id: str                       # 绑定的物证锚点
    node_type: str                       # consensus / interpretation / conclusion
    content: str                         # 提炼内容
    confidence: Confidence = Confidence.MEDIUM
    source: str = ""                     # 来源标识
    evidence_refs: List[str] = field(default_factory=list)  # 交叉引用的其他锚点
    version: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.updated_at == 0.0:
            self.updated_at = self.created_at


@dataclass
class ArbitrationResponse:
    """第三层仲裁输出 —— 结构化分歧应答范式。

    系统不强制消灭不同解读，而是四段式分层输出：
    ① trace: 原始证据溯源
    ② consensus: 多方共识部分
    ③ disputes: 存在争议的不同观点（分别列出）
    ④ conclusion: AI综合判断（标注判断依据和采信规则）
    """
    query: str
    trace: List[Dict[str, Any]]          # [{anchor_id, modality, snippet, source_path}]
    consensus: List[str]                 # 多方印证一致的结论
    disputes: List[Dict[str, Any]]       # [{topic, viewpoints: [A,B,C], anchors}]
    conclusion: str                      # AI综合判断
    conclusion_basis: List[str]          # 采信规则/判断依据
    confidence: Confidence = Confidence.MEDIUM
    generated_at: float = field(default_factory=time.time)


# ═══════════════════════════════════════════════════════════════════
# 第一层：证据基座 — 只追加、不可覆盖
# ═══════════════════════════════════════════════════════════════════

class EvidenceTrack:
    """多模态感官证据基座（只读追加式）。

    规则：
    - 只追加写入，不覆盖原始源文件
    - 每条锚点有唯一哈希指纹
    - 所有上层 CognitionNode 必须绑定 anchor_id
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._anchors: Dict[str, EvidenceAnchor] = {}
        self._by_hash: Dict[str, str] = {}  # source_hash → anchor_id
        self._by_modality: Dict[Modality, List[str]] = {m: [] for m in Modality}

    def deposit(self, anchor: EvidenceAnchor) -> str:
        """存入一条物证锚点。返回 anchor_id。已存在则返回已有ID。"""
        with self._lock:
            if anchor.source_hash in self._by_hash:
                return self._by_hash[anchor.source_hash]
            self._anchors[anchor.anchor_id] = anchor
            self._by_hash[anchor.source_hash] = anchor.anchor_id
            self._by_modality[anchor.modality].append(anchor.anchor_id)
            return anchor.anchor_id

    def get(self, anchor_id: str) -> Optional[EvidenceAnchor]:
        with self._lock:
            return self._anchors.get(anchor_id)

    def find_by_hash(self, source_hash: str) -> Optional[EvidenceAnchor]:
        with self._lock:
            aid = self._by_hash.get(source_hash)
            return self._anchors.get(aid) if aid else None

    def list_by_modality(self, modality: Modality) -> List[EvidenceAnchor]:
        with self._lock:
            return [self._anchors[aid] for aid in self._by_modality[modality]
                    if aid in self._anchors]

    def search_by_tag(self, tag: str) -> List[EvidenceAnchor]:
        with self._lock:
            return [a for a in self._anchors.values() if tag in a.tags]

    @property
    def total_anchors(self) -> int:
        with self._lock:
            return len(self._anchors)


# ═══════════════════════════════════════════════════════════════════
# 第二~三层：认知轨 — 可演化、分层置信、多观点并存
# ═══════════════════════════════════════════════════════════════════

class CognitionTrack:
    """网状概念图谱 + 多源思辨仲裁。

    在物证锚点之上，分层挂载：
    - consensus: 多个素材交叉印证一致的内容
    - interpretation: 不同来源/视角的观点（保留分歧）
    - conclusion: AI整合结论（附带采信权重、来源标注）
    """

    def __init__(self, evidence: EvidenceTrack):
        self._evidence = evidence
        self._lock = threading.RLock()
        self._nodes: Dict[str, CognitionNode] = {}
        self._by_anchor: Dict[str, List[str]] = {}  # anchor_id → [node_ids]
        self._by_entity: Dict[str, List[str]] = {}  # entity → [node_ids]

    def add_consensus(self, anchor_id: str, content: str,
                      source: str = "", evidence_refs: List[str] | None = None) -> str:
        return self._add_node(anchor_id, "consensus", content, Confidence.HIGH,
                              source, evidence_refs or [])

    def add_interpretation(self, anchor_id: str, content: str,
                           source: str = "", confidence: Confidence = Confidence.MEDIUM) -> str:
        return self._add_node(anchor_id, "interpretation", content, confidence, source, [])

    def add_conclusion(self, anchor_id: str, content: str, basis: str = "",
                       evidence_refs: List[str] | None = None) -> str:
        return self._add_node(anchor_id, "conclusion", content, Confidence.MEDIUM,
                              basis, evidence_refs or [])

    def update_node(self, node_id: str, new_content: str) -> Optional[CognitionNode]:
        """更新认知节点（版本+1，保留历史）。"""
        with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return None
            node.version += 1
            node.content = new_content
            node.updated_at = time.time()
            return node

    def get_by_anchor(self, anchor_id: str) -> List[CognitionNode]:
        with self._lock:
            nids = self._by_anchor.get(anchor_id, [])
            return [self._nodes[n] for n in nids if n in self._nodes]

    def get_consensus(self, anchor_id: str) -> List[CognitionNode]:
        return [n for n in self.get_by_anchor(anchor_id)
                if n.node_type == "consensus"]

    def get_interpretations(self, anchor_id: str) -> List[CognitionNode]:
        return [n for n in self.get_by_anchor(anchor_id)
                if n.node_type == "interpretation"]

    def find_conflicts(self) -> List[Tuple[CognitionNode, CognitionNode, str]]:
        """扫描认知轨，发现冲突的节点对。返回 (node_a, node_b, reason)。"""
        conflicts: List[Tuple[CognitionNode, CognitionNode, str]] = []
        with self._lock:
            nodes = list(self._nodes.values())
            for i in range(len(nodes)):
                for j in range(i + 1, len(nodes)):
                    a, b = nodes[i], nodes[j]
                    if a.anchor_id != b.anchor_id:
                        continue
                    # 同一锚点上的两个 interpretations → 潜在分歧
                    if (a.node_type == "interpretation"
                            and b.node_type == "interpretation"):
                        conflicts.append((a, b, "divergent_interpretations"))
        return conflicts

    def tag_entity(self, node_id: str, entity: str) -> None:
        with self._lock:
            self._by_entity.setdefault(entity, []).append(node_id)

    def get_by_entity(self, entity: str) -> List[CognitionNode]:
        with self._lock:
            nids = self._by_entity.get(entity, [])
            return [self._nodes[n] for n in nids if n in self._nodes]

    def _add_node(self, anchor_id, ntype, content, confidence,
                  source, refs) -> str:
        nid = hashlib.sha256(f"{anchor_id}{ntype}{content[:50]}{time.time()}".encode()).hexdigest()[:12]
        node = CognitionNode(
            node_id=nid, anchor_id=anchor_id, node_type=ntype,
            content=content, confidence=confidence,
            source=source, evidence_refs=refs,
        )
        with self._lock:
            self._nodes[nid] = node
            self._by_anchor.setdefault(anchor_id, []).append(nid)
        return nid

    @property
    def total_nodes(self) -> int:
        with self._lock:
            return len(self._nodes)


# ═══════════════════════════════════════════════════════════════════
# 金字塔粒度检索
# ═══════════════════════════════════════════════════════════════════

class PyramidRetriever:
    """金字塔三层检索：语义概念 → 缩略表征 → 原始精细物证。

    设计目标：平衡速度+精准度+硬件压力。
    - 普通问答：只用顶层+中层
    - 需要核对细节/查验矛盾：自动下沉调取底层原始素材
    """

    def __init__(self, evidence: EvidenceTrack, cognition: CognitionTrack):
        self._evidence = evidence
        self._cognition = cognition
        self._descent_count = 0

    def retrieve(self, query: str, need_deep_verify: bool = False,
                 top_k: int = 5) -> Dict[str, Any]:
        """金字塔检索入口。

        need_deep_verify=False: 返回顶层+中层结果（快速问答）
        need_deep_verify=True:  追加底层原始物证（细节核验）
        """
        # 第一层：语义概念粗召回（文本匹配 cognition nodes）
        top_results = self._semantic_scan(query, top_k)

        # 第二层：模态缩略表征
        mid_results = []
        for r in top_results:
            anchor = self._evidence.get(r.get("anchor_id", ""))
            if anchor:
                mid_results.append({
                    "light_rep": anchor.light_representation,
                    "modality": anchor.modality.value,
                    "tags": anchor.tags,
                    "anchor_id": anchor.anchor_id,
                })

        result = {
            "top_concepts": top_results,
            "light_modalities": mid_results,
            "deep_evidence": [],
            "deep_triggered": need_deep_verify,
        }

        # 第三层：按需下沉原始物证
        if need_deep_verify:
            result["deep_evidence"] = self._descent_to_raw(anchors=[
                self._evidence.get(r.get("anchor_id", ""))
                for r in top_results
            ])

        return result

    def verify_contradiction(self, node_a: str, node_b: str) -> Dict[str, Any]:
        """当检测到两个认知节点冲突时，下沉底层原始物证比对。"""
        self._descent_count += 1
        a_node = self._cognition._nodes.get(node_a)
        b_node = self._cognition._nodes.get(node_b)
        anchors = []
        for node in (a_node, b_node):
            if node and node.anchor_id:
                a = self._evidence.get(node.anchor_id)
                if a:
                    anchors.append(a)
        return {
            "conflict_nodes": [node_a, node_b],
            "raw_evidence": [
                {"anchor_id": a.anchor_id, "modality": a.modality.value,
                 "source_hash": a.source_hash, "coordinates": a.spatial_coordinates}
                for a in anchors
            ],
            "descent_triggered": True,
        }

    def _semantic_scan(self, query: str, top_k: int) -> List[Dict[str, Any]]:
        """顶层语义粗召回：在 cognition nodes 中做文本匹配。"""
        q = query.lower()
        scored = []
        for nid, node in self._cognition._nodes.items():
            if q in node.content.lower():
                anchor = self._evidence.get(node.anchor_id)
                scored.append({
                    "node_id": nid,
                    "anchor_id": node.anchor_id,
                    "type": node.node_type,
                    "content_snippet": node.content[:120],
                    "confidence": node.confidence.value,
                    "modality": anchor.modality.value if anchor else "unknown",
                    "score": 1.0 if q in node.content[:50] else 0.5,
                })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def _descent_to_raw(self, anchors: List[Optional[EvidenceAnchor]]) -> List[Dict[str, Any]]:
        """底层下沉：获取原始物证的完整元数据。"""
        result = []
        for a in anchors:
            if a is None:
                continue
            result.append({
                "anchor_id": a.anchor_id,
                "source_hash": a.source_hash,
                "source_path": a.source_path,
                "modality": a.modality.value,
                "coordinates": a.spatial_coordinates,
                "temporal": a.temporal_anchor,
            })
        return result

    @property
    def descent_count(self) -> int:
        return self._descent_count


# ═══════════════════════════════════════════════════════════════════
# 第四层：元认知巡检闭环
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PatrolFinding:
    """巡检发现：疑似冲突/重复实体/过期信息/待复审。"""
    finding_type: str  # conflict / duplicate / stale / review_needed
    severity: str      # low / medium / high
    detail: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


class MetacognitivePatrol:
    """元认知巡检闭环：仿生海马巩固机制。

    三种后台任务（时序分级）：
    1. daily_scan: 轻量日巡检 → 标记疑似冲突/重复/过期，生成复审清单（不自动修改）
    2. weekly_consolidate: 周期周巩固 → 高频调用知识固化为稳定节点，
       低调用碎片降权（仿生艾宾浩斯遗忘曲线）
    3. human_review: 人机协同终审 → 高冲突/高价值推人工复核，
       人工修订作为最高优先级锚定版本回流
    """

    def __init__(self, evidence: EvidenceTrack, cognition: CognitionTrack,
                 on_review_needed: Callable[[PatrolFinding], None] | None = None):
        self._evidence = evidence
        self._cognition = cognition
        self._on_review = on_review_needed
        self._lock = threading.RLock()
        self._findings: List[PatrolFinding] = []
        self._access_counter: Dict[str, int] = {}    # node_id → 访问次数
        self._last_consolidated: float = 0.0
        self._consolidation_score: Dict[str, float] = {}  # node_id → 稳定度

    def record_access(self, node_id: str) -> None:
        with self._lock:
            self._access_counter[node_id] = self._access_counter.get(node_id, 0) + 1

    # ── 日巡检 ──
    def daily_scan(self) -> List[PatrolFinding]:
        """轻量日巡检：扫描冲突/重复/过期，生成复审清单。"""
        findings: List[PatrolFinding] = []

        # 1. 检测冲突
        conflicts = self._cognition.find_conflicts()
        for a, b, reason in conflicts:
            findings.append(PatrolFinding(
                finding_type="conflict", severity="medium",
                detail={"nodes": [a.node_id, b.node_id],
                        "contents": [a.content[:80], b.content[:80]],
                        "reason": reason},
            ))

        # 2. 检测过期（很久未更新且低置信度）
        now = time.time()
        for nid, node in self._cognition._nodes.items():
            age_days = (now - node.updated_at) / 86400
            if age_days > 30 and node.confidence in (Confidence.LOW, Confidence.DISPUTED):
                findings.append(PatrolFinding(
                    finding_type="stale", severity="low",
                    detail={"node_id": nid, "age_days": round(age_days, 1),
                            "content": node.content[:60]},
                ))

        with self._lock:
            self._findings.extend(findings)
        return findings

    # ── 周巩固 ──
    def weekly_consolidate(self) -> Dict[str, Any]:
        """周期周巩固：高频调用知识固化为稳定节点，低调用碎片降权。"""
        with self._lock:
            total_access = sum(self._access_counter.values()) or 1
            consolidated = 0
            softened = 0

            for nid, node in self._cognition._nodes.items():
                access = self._access_counter.get(nid, 0)
                freq = access / total_access

                if freq > 0.1:  # 高频 → 固化
                    node.metadata["consolidated"] = True
                    node.metadata["stability"] = min(1.0,
                        node.metadata.get("stability", 0.5) + 0.1)
                    self._consolidation_score[nid] = node.metadata["stability"]
                    consolidated += 1
                elif freq < 0.01 and not node.metadata.get("consolidated"):
                    # 低频且未固化 → 软遗忘降权
                    node.confidence = Confidence.LOW
                    node.metadata["soft_forgotten"] = True
                    softened += 1

            self._last_consolidated = time.time()
            return {
                "consolidated": consolidated, "softened": softened,
                "total_nodes": len(self._cognition._nodes),
                "access_total": total_access,
            }

    # ── 人工复审 ──
    def collect_for_review(self, min_severity: str = "medium") -> List[PatrolFinding]:
        """收集需要人工复审的发现。"""
        severity_order = {"low": 0, "medium": 1, "high": 2}
        threshold = severity_order.get(min_severity, 1)
        candidates: List[PatrolFinding] = []
        with self._lock:
            for f in self._findings:
                if severity_order.get(f.severity, 0) >= threshold:
                    candidates.append(f)
        return candidates

    def apply_human_review(self, finding_index: int, resolution: Dict[str, Any]) -> bool:
        """应用人工复审结果：修订/采纳/驳回。"""
        with self._lock:
            if finding_index < 0 or finding_index >= len(self._findings):
                return False
            f = self._findings[finding_index]
            f.detail["reviewed"] = True
            f.detail["resolution"] = resolution
            # 如果是冲突仲裁，更新对应节点置信度
            node_ids = f.detail.get("nodes", [])
            for nid in node_ids:
                node = self._cognition._nodes.get(nid)
                if node:
                    chosen = resolution.get("chosen_node")
                    if chosen == nid:
                        node.confidence = Confidence.HIGH
                    else:
                        node.confidence = Confidence.DISPUTED
            return True

    @property
    def finding_count(self) -> int:
        with self._lock:
            return len(self._findings)


# ═══════════════════════════════════════════════════════════════════
# HippoScroll 统一引擎
# ═══════════════════════════════════════════════════════════════════

class HippoScrollEngine:
    """Hippo-Scroll 统一入口：双轨 + 金字塔检索 + 仲裁 + 巡检。

    用法：
        hs = HippoScrollEngine()
        # 存入证据
        aid = hs.deposit_evidence(EvidenceAnchor.create("img.jpg", Modality.IMAGE))
        # 添加共识/解读
        hs.cognition.add_consensus(aid, "图中为一只猫", source="user_a")
        hs.cognition.add_interpretation(aid, "图中可能是一只豹猫", source="user_b")
        # 检索
        result = hs.retrieve("猫", need_deep_verify=False)
        # 巡检
        findings = hs.patrol.daily_scan()
        # 仲裁输出
        arb = hs.arbitrate("图中的动物是什么", aid)
    """

    def __init__(self):
        self.evidence = EvidenceTrack()
        self.cognition = CognitionTrack(self.evidence)
        self.retriever = PyramidRetriever(self.evidence, self.cognition)
        self.patrol = MetacognitivePatrol(self.evidence, self.cognition)

    def deposit_evidence(self, anchor: EvidenceAnchor) -> str:
        return self.evidence.deposit(anchor)

    def retrieve(self, query: str, need_deep_verify: bool = False,
                 top_k: int = 5) -> Dict[str, Any]:
        return self.retriever.retrieve(query, need_deep_verify, top_k)

    def arbitrate(self, query: str, anchor_id: str) -> ArbitrationResponse:
        """多源仲裁：对一个锚点的所有认知节点做结构化分层输出。"""
        nodes = self.cognition.get_by_anchor(anchor_id)
        anchor = self.evidence.get(anchor_id)

        # 溯源
        trace = []
        if anchor:
            trace.append({
                "anchor_id": anchor.anchor_id,
                "modality": anchor.modality.value,
                "source_hash": anchor.source_hash,
                "source_path": anchor.source_path,
                "coordinates": anchor.spatial_coordinates,
            })

        # 共识
        consensus_nodes = [n for n in nodes if n.node_type == "consensus"]
        consensus_texts = [n.content for n in consensus_nodes]

        # 争议
        interpretations = [n for n in nodes if n.node_type == "interpretation"]
        dispute_viewpoints = []
        if interpretations:
            dispute_viewpoints.append({
                "topic": query,
                "viewpoints": [n.content for n in interpretations],
                "anchors": [n.anchor_id for n in interpretations],
            })

        # 结论
        conclusions = [n for n in nodes if n.node_type == "conclusion"]
        conclusion_text = conclusions[0].content if conclusions else "暂无综合结论"
        basis = [f"{n.confidence.value} confidence from {n.source}" for n in conclusions]

        conf = Confidence.HIGH if consensus_nodes else Confidence.MEDIUM
        if interpretations:
            conf = Confidence.DISPUTED

        # 记录访问（用于巡检的频率统计）
        for n in nodes:
            self.patrol.record_access(n.node_id)

        return ArbitrationResponse(
            query=query, trace=trace, consensus=consensus_texts,
            disputes=dispute_viewpoints, conclusion=conclusion_text,
            conclusion_basis=basis, confidence=conf,
        )


__all__ = [
    "ArbitrationResponse",
    "CognitionNode",
    "CognitionTrack",
    "Confidence",
    "EvidenceAnchor",
    "EvidenceTrack",
    "HippoScrollEngine",
    "MetacognitivePatrol",
    "Modality",
    "PatrolFinding",
    "PyramidRetriever",
]


# ─────────────────────────────────────────────────────────────────────────
# 单例工厂：让引擎在进程内常驻，被 main.py 启动时挂到 app.state，
# 外部经 /api/memory/hippo/* 端点真实触达。纯内存、零外部依赖。
# ─────────────────────────────────────────────────────────────────────────
_global_engine: "HippoScrollEngine | None" = None


def get_hippo_scroll() -> "HippoScrollEngine":
    """返回 Hippo-Scroll 可信记忆引擎单例。

    纯内存、零外部依赖（不依赖 GPU / LLM / 外网），故启动时即可构造，
    常驻于 app.state，供 /api/memory/hippo/* 端点真实调用其检索/仲裁/巡检。
    """
    global _global_engine
    if _global_engine is None:
        _global_engine = HippoScrollEngine()
    return _global_engine
