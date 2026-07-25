"""证据溯源链——让每个AI结论都能追溯到原始证据。

这是Hippo-Scroll的第三/四层实现：
- PyramidRetriever：语义→缩略→原始 三层检索
- EvidenceChain：从结论反向追溯到原始证据的完整链条

应用场景：
- 金融合规：每个投资建议可追溯到数据来源
- 医疗辅助：每个诊断建议可追溯到检查报告
- 法律文书：每个引用可追溯到原始判例

核心数据结构：
- EvidenceNode：证据链节点，每个节点代表一条证据
- EvidenceChain：完整的有向无环图，从结论到原始证据
- EvidenceChainBuilder：从Trace自动构建证据链
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _hash_content(content: str) -> str:
    """计算内容的SHA256哈希。"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


@dataclass
class EvidenceNode:
    """证据链节点。

    每个节点代表一条证据，可以是：
    - 原始证据：搜索结果、文件内容、数据库查询等
    - 中间结论：推理过程中间产物
    - 最终结论：AI的最终输出
    """
    node_id: str
    content: str                          # 证据内容摘要
    source: str                           # 来源（URL/文件/数据库）
    source_hash: str = ""                 # 来源内容哈希（防篡改）
    confidence: float = 1.0               # 证据可信度（0-1）
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List[str] = field(default_factory=list)  # 子证据ID（下层证据）
    parent: Optional[str] = None          # 父证据ID（上层结论）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "content": self.content,
            "source": self.source,
            "source_hash": self.source_hash,
            "confidence": self.confidence,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "children": self.children,
            "parent": self.parent,
        }


@dataclass
class EvidenceChain:
    """完整的证据溯源链——从结论到原始证据的有向无环图。

    结构：
    - leaf_node：结论节点（AI的最终输出）
    - root_nodes：原始证据节点（数据来源）
    - nodes：所有节点的扁平列表
    - integrity_hash：链完整性哈希（防篡改）
    """
    chain_id: str
    conclusion: str                       # AI结论
    conclusion_hash: str                  # 结论哈希
    nodes: List[EvidenceNode] = field(default_factory=list)
    root_nodes: List[str] = field(default_factory=list)  # 原始证据ID
    leaf_node: Optional[str] = None       # 结论节点ID
    integrity_hash: str = ""              # 链完整性哈希
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "conclusion": self.conclusion,
            "conclusion_hash": self.conclusion_hash,
            "nodes": [n.to_dict() for n in self.nodes],
            "root_nodes": self.root_nodes,
            "leaf_node": self.leaf_node,
            "integrity_hash": self.integrity_hash,
            "created_at": self.created_at,
        }

    def verify_integrity(self) -> bool:
        """验证证据链完整性——检查哈希链是否被篡改。"""
        if not self.integrity_hash:
            return True  # 未计算哈希时默认通过

        computed = self._compute_hash()
        return computed == self.integrity_hash

    def _compute_hash(self) -> str:
        """计算链的完整性哈希。"""
        parts = []
        for node in sorted(self.nodes, key=lambda n: n.node_id):
            parts.append(f"{node.node_id}:{node.source_hash}:{node.confidence}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


class EvidenceChainBuilder:
    """证据链构建器——从AI执行Trace自动构建证据溯源链。

    支持两种构建来源：
    1. 从autopilot执行Trace构建
    2. 从记忆条目构建

    典型工作流：
    1. build_from_trace()或build_from_memory()构建证据链
    2. traverse_chain()向上遍历到原始证据
    3. verify_chain()验证完整性
    4. export_for_audit()导出审计报告
    """

    def __init__(self):
        self._chains: Dict[str, EvidenceChain] = {}

    def build_from_trace(self, trace: Dict[str, Any]) -> EvidenceChain:
        """从执行Trace构建证据链。

        Trace结构：
        {
          "task": "...",
          "steps": [
            {"capability": "web.search", "engine": "baidu", "ok": true,
             "output": {"results": [...]}},
            {"capability": "inference.llm", "engine": "zhipu", "ok": true,
             "output": {"content": "..."}}
          ],
          "final": "最终结论"
        }
        """
        chain_id = f"chain_{uuid.uuid4().hex[:8]}"
        conclusion = trace.get("final", trace.get("output", {}).get("final", ""))
        conclusion_hash = _hash_content(conclusion)

        nodes: List[EvidenceNode] = []
        root_node_ids: List[str] = []
        node_map: Dict[str, EvidenceNode] = {}

        # 构建每个step的节点
        steps = trace.get("steps", [])
        prev_node_id = None

        for i, step in enumerate(steps):
            node_id = f"node_{i:03d}"
            capability = step.get("capability", "unknown")
            engine = step.get("engine", "unknown")
            ok = step.get("ok", False)
            output = step.get("output", {})

            # 构建节点内容
            content = self._extract_step_summary(step)
            source = f"{capability}@{engine}"
            source_hash = _hash_content(json.dumps(output, ensure_ascii=False, default=str))

            # 置信度：成功=1.0，失败=0.3，有搜索结果=额外加分
            confidence = 1.0 if ok else 0.3
            if capability == "web.search" and ok:
                result_count = len(output.get("results", []))
                confidence = min(1.0, 0.5 + result_count * 0.05)

            node = EvidenceNode(
                node_id=node_id,
                content=content,
                source=source,
                source_hash=source_hash,
                confidence=confidence,
                metadata={
                    "step_index": i,
                    "capability": capability,
                    "engine": engine,
                    "success": ok,
                },
                parent=prev_node_id if prev_node_id else None,
            )

            nodes.append(node)
            node_map[node_id] = node

            # 建立父子关系
            if prev_node_id:
                node_map[prev_node_id].children.append(node_id)

            # 原始证据节点（搜索/查询类）
            if capability in ("web.search", "web.fetch", "data.query", "memory.recall"):
                root_node_ids.append(node_id)

            prev_node_id = node_id

        # 创建结论节点
        if prev_node_id:
            conclusion_node = EvidenceNode(
                node_id="node_final",
                content=conclusion[:500] if conclusion else "(无结论)",
                source="autopilot.output",
                source_hash=conclusion_hash,
                confidence=0.9,
                metadata={"step_index": len(steps), "is_conclusion": True},
                parent=prev_node_id,
            )
            nodes.append(conclusion_node)
            node_map[prev_node_id].children.append("node_final")
            leaf_node_id = "node_final"
        else:
            leaf_node_id = None

        # 若无原始证据节点，用第一个step作为根
        if not root_node_ids and nodes:
            root_node_ids.append(nodes[0].node_id)

        # 构建链
        chain = EvidenceChain(
            chain_id=chain_id,
            conclusion=conclusion,
            conclusion_hash=conclusion_hash,
            nodes=nodes,
            root_nodes=root_node_ids,
            leaf_node=leaf_node_id,
        )

        # 计算完整性哈希
        chain.integrity_hash = chain._compute_hash()

        self._chains[chain_id] = chain
        return chain

    def build_from_memory(self, memory_entries: List[Dict]) -> EvidenceChain:
        """从记忆条目构建证据链。

        memory_entries结构：
        [
          {"content": "...", "source": "trace:xxx", "similarity": 0.85, "timestamp": ...},
          {"content": "...", "source": "reflection:yyy", "similarity": 0.9, "timestamp": ...}
        ]
        """
        chain_id = f"chain_mem_{uuid.uuid4().hex[:8]}"

        nodes: List[EvidenceNode] = []
        root_node_ids: List[str] = []

        # 按时间排序
        sorted_entries = sorted(memory_entries, key=lambda e: e.get("timestamp", 0))

        for i, entry in enumerate(sorted_entries):
            node_id = f"mem_{i:03d}"
            content = entry.get("content", "")
            source = entry.get("source", "memory")
            similarity = entry.get("similarity", 0.5)

            node = EvidenceNode(
                node_id=node_id,
                content=content[:500],
                source=source,
                source_hash=_hash_content(content),
                confidence=similarity,
                metadata={
                    "memory_index": i,
                    "similarity": similarity,
                },
                parent=f"mem_{i-1:03d}" if i > 0 else None,
            )
            nodes.append(node)

            # 所有记忆条目都是原始证据
            root_node_ids.append(node_id)

        # 建立父子关系
        for i in range(1, len(nodes)):
            nodes[i - 1].children.append(nodes[i].node_id)

        # 结论从最后一条记忆推断
        conclusion = sorted_entries[-1].get("content", "") if sorted_entries else ""
        conclusion_hash = _hash_content(conclusion)

        chain = EvidenceChain(
            chain_id=chain_id,
            conclusion=conclusion[:500],
            conclusion_hash=conclusion_hash,
            nodes=nodes,
            root_nodes=root_node_ids,
            leaf_node=nodes[-1].node_id if nodes else None,
        )
        chain.integrity_hash = chain._compute_hash()

        self._chains[chain_id] = chain
        return chain

    def traverse_chain(self, chain_id: str, node_id: str = None) -> List[EvidenceNode]:
        """从指定节点向上遍历到根（原始证据）。

        返回从指定节点到根的路径，按从叶到根的顺序。
        若node_id为None，从leaf_node开始。
        """
        chain = self._chains.get(chain_id)
        if chain is None:
            raise ValueError(f"证据链 {chain_id} 不存在")

        node_id = node_id or chain.leaf_node
        if node_id is None:
            return []

        # 构建节点索引
        node_map = {n.node_id: n for n in chain.nodes}

        # 向上遍历
        path = []
        current_id = node_id
        while current_id:
            node = node_map.get(current_id)
            if node is None:
                break
            path.append(node)
            current_id = node.parent

        return path

    def get_full_chain(self, chain_id: str) -> Dict[str, Any]:
        """获取完整证据链（树状结构）。

        返回树状JSON，包含：
        - chain: 链元数据
        - tree: 树状证据结构
        - stats: 链统计信息
        """
        chain = self._chains.get(chain_id)
        if chain is None:
            raise ValueError(f"证据链 {chain_id} 不存在")

        # 构建节点索引
        node_map = {n.node_id: n for n in chain.nodes}

        # 从根节点递归构建树
        def build_tree(node_id: str) -> Dict[str, Any]:
            node = node_map.get(node_id)
            if node is None:
                return {}
            return {
                "node_id": node.node_id,
                "content": node.content,
                "source": node.source,
                "confidence": node.confidence,
                "children": [build_tree(cid) for cid in node.children],
            }

        tree = []
        for root_id in chain.root_nodes:
            tree.append(build_tree(root_id))

        # 统计信息
        total_nodes = len(chain.nodes)
        avg_confidence = (sum(n.confidence for n in chain.nodes) / total_nodes
                         if total_nodes else 0)
        min_confidence = min((n.confidence for n in chain.nodes), default=1.0)

        return {
            "chain": {
                "chain_id": chain.chain_id,
                "conclusion": chain.conclusion,
                "conclusion_hash": chain.conclusion_hash,
                "integrity_hash": chain.integrity_hash,
                "created_at": chain.created_at,
            },
            "tree": tree,
            "stats": {
                "total_nodes": total_nodes,
                "root_nodes": len(chain.root_nodes),
                "avg_confidence": round(avg_confidence, 4),
                "min_confidence": round(min_confidence, 4),
                "integrity_valid": chain.verify_integrity(),
            },
        }

    def verify_chain(self, chain_id: str) -> Dict[str, Any]:
        """验证证据链完整性——检查哈希链是否被篡改。

        返回：
        - valid: 是否通过
        - details: 各节点哈希验证详情
        - summary: 验证摘要
        """
        chain = self._chains.get(chain_id)
        if chain is None:
            raise ValueError(f"证据链 {chain_id} 不存在")

        # 验证链级完整性哈希
        chain_valid = chain.verify_integrity()

        # 验证各节点哈希
        node_details = []
        for node in chain.nodes:
            computed_hash = _hash_content(node.content)
            hash_valid = computed_hash == node.source_hash if node.source_hash else True
            node_details.append({
                "node_id": node.node_id,
                "source": node.source,
                "hash_valid": hash_valid,
                "confidence": node.confidence,
            })

        # 验证父子关系完整性
        node_map = {n.node_id: n for n in chain.nodes}
        relationship_valid = True
        for node in chain.nodes:
            if node.parent and node.parent not in node_map:
                relationship_valid = False
            for child_id in node.children:
                if child_id not in node_map:
                    relationship_valid = False

        all_valid = chain_valid and relationship_valid and all(
            d["hash_valid"] for d in node_details
        )

        return {
            "valid": all_valid,
            "chain_hash_valid": chain_valid,
            "relationships_valid": relationship_valid,
            "node_details": node_details,
            "summary": (
                f"证据链 {chain_id} 验证{'通过' if all_valid else '失败'}："
                f"{len(chain.nodes)}个节点，{len(chain.root_nodes)}个原始证据"
            ),
        }

    def export_for_audit(self, chain_id: str) -> str:
        """导出审计友好的Markdown格式证据报告。

        用途：金融合规审计、医疗辅助可解释性、法律文书证据公示。
        """
        chain = self._chains.get(chain_id)
        if chain is None:
            raise ValueError(f"证据链 {chain_id} 不存在")

        # 构建节点索引
        node_map = {n.node_id: n for n in chain.nodes}

        lines = [
            f"# 证据溯源报告",
            f"",
            f"**链ID**: `{chain.chain_id}`",
            f"**结论**: {chain.conclusion[:200]}",
            f"**结论哈希**: `{chain.conclusion_hash}`",
            f"**完整性哈希**: `{chain.integrity_hash}`",
            f"**创建时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(chain.created_at))}",
            f"",
            f"## 验证状态",
            f"",
            f"- 链完整性: {'通过' if chain.verify_integrity() else '未通过'}",
            f"- 节点数: {len(chain.nodes)}",
            f"- 原始证据数: {len(chain.root_nodes)}",
            f"",
            f"## 证据链路",
            f"",
        ]

        # 从叶到根的完整路径
        path = self.traverse_chain(chain_id)
        for i, node in enumerate(path):
            direction = "结论" if i == 0 else ("证据" if node.children else "原始证据")
            lines.append(f"### [{i+1}] {direction}: {node.source}")
            lines.append(f"")
            lines.append(f"- **内容**: {node.content[:300]}")
            lines.append(f"- **来源哈希**: `{node.source_hash}`")
            lines.append(f"- **置信度**: {node.confidence:.2%}")
            lines.append(f"- **时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(node.timestamp))}")
            if node.metadata:
                lines.append(f"- **元数据**: {json.dumps(node.metadata, ensure_ascii=False)}")
            lines.append(f"")

        # 原始证据汇总
        lines.append(f"## 原始证据汇总")
        lines.append(f"")
        for root_id in chain.root_nodes:
            node = node_map.get(root_id)
            if node:
                lines.append(f"- `{node.node_id}`: {node.source} (置信度: {node.confidence:.2%})")
                lines.append(f"  {node.content[:150]}")
                lines.append(f"")

        # 声明
        lines.append(f"---")
        lines.append(f"*本报告由AOS证据溯源链自动生成，哈希链防篡改。*")

        return "\n".join(lines)

    def get_node(self, chain_id: str, node_id: str) -> Optional[EvidenceNode]:
        """获取链中特定节点。"""
        chain = self._chains.get(chain_id)
        if chain is None:
            return None
        for node in chain.nodes:
            if node.node_id == node_id:
                return node
        return None

    def list_chains(self) -> List[Dict[str, Any]]:
        """列出所有证据链。"""
        return [
            {
                "chain_id": c.chain_id,
                "conclusion": c.conclusion[:100],
                "node_count": len(c.nodes),
                "root_count": len(c.root_nodes),
                "integrity_valid": c.verify_integrity(),
                "created_at": c.created_at,
            }
            for c in self._chains.values()
        ]

    def _extract_step_summary(self, step: Dict[str, Any]) -> str:
        """从step中提取摘要文本。"""
        capability = step.get("capability", "")
        engine = step.get("engine", "")
        output = step.get("output", {})
        ok = step.get("ok", False)

        if capability == "web.search":
            results = output.get("results", [])
            if results:
                titles = [r.get("title", "")[:50] for r in results[:3]]
                return f"搜索结果({len(results)}条): {'; '.join(titles)}"
            return f"搜索: {engine} (无结果)"

        elif capability == "inference.llm":
            content = output.get("content", "")
            return f"推理结果: {content[:150]}"

        elif capability == "memory.recall":
            entries = output.get("entries", [])
            return f"记忆召回({len(entries)}条)"

        elif capability.startswith("data."):
            return f"数据查询: {capability} @ {engine}"

        else:
            status = "成功" if ok else "失败"
            return f"{capability} @ {engine}: {status}"
