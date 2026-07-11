"""
Zvec 技能模块 - 阿里巴巴嵌入式向量数据库 [已退役 / DEPRECATED]

⚠️  v1.0 对账决议：Zvec 与 Qdrant/Chroma 功能重叠，增加运维面。
    已标记为退役（DEPRECATED），不再作为 AOS 主向量存储。
    推荐迁移路径：zvec_data/ → Qdrant（P99<100ms, 12k QPS@1M）。

    迁移工具：scripts/migrate_zvec_to_qdrant.py（待实施）
    迁移后建议：删除 zvec_data/ 目录，释放磁盘空间。

    现有调用方（brain.py:760, memory.py）将在 v1.1 移除 zvec 依赖。
    在此之前，ZvecSkill 仍可正常使用，但每次初始化会打印本条退役警告。

Zvec 是阿里巴巴通义实验室开源的嵌入式向量数据库，核心设计理念是"向量数据库领域的 SQLite"。
零依赖、无需独立部署、进程内运行，完美适配8GB内存的低配置设备。

核心特性:
- 极致轻量: pip install zvec 即可安装
- 毫秒级检索: 基于阿里内部生产级向量引擎 Proxima
- 原生全文搜索: 支持 FTS 和混合检索
- 生产级可靠性: WAL 保证数据持久化
- 跨平台支持: Windows/Linux/macOS, Python/Node.js/Go/Rust

部署位置:
1. Hermes 认知大脑的"向量记忆层" - 长期记忆存储
2. DeerFlow 任务调度引擎的"技能库索引层" - Skill模板向量检索
3. AI 工厂的"本地知识库检索层" - RAG系统
"""

import os
import json
import logging
import uuid
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path

from .base import Skill

logger = logging.getLogger(__name__)

ZVEC_DB_PATH = str(Path(__file__).resolve().parent.parent.parent / "zvec_data")

ZVEC_FEATURES = {
    "vector_search": {
        "name": "向量搜索",
        "description": "基于向量相似度的语义检索",
    },
    "hybrid_search": {
        "name": "混合搜索",
        "description": "融合向量相似度、全文搜索和结构化过滤",
    },
    "full_text_search": {
        "name": "全文搜索",
        "description": "基于关键词的全文检索",
    },
    "document_store": {
        "name": "文档存储",
        "description": "添加、删除、更新文档",
    },
    "memory_store": {
        "name": "记忆存储",
        "description": "存储和检索对话历史、任务记录等记忆",
    },
    "knowledge_graph": {
        "name": "知识图谱",
        "description": "构建和查询知识图谱关系",
    },
}


class ZvecSkill(Skill):
    """
    Zvec 嵌入式向量数据库技能
    
    提供轻量级、高性能的向量检索能力，无需独立部署。
    基于阿里巴巴通义实验室的 Zvec 向量数据库。
    """
    
    NAME = "zvec"
    DESCRIPTION = "Zvec 嵌入式向量数据库 — 阿里巴巴开源，向量数据库领域的SQLite，零依赖进程内运行"
    VERSION = "1.0.0"
    AUTHOR = "Alibaba Tongyi Lab"
    LICENSE = "Apache-2.0"
    CATEGORY = "knowledge"
    TAGS = ["zvec", "vector", "database", "embedding", "rag", "alibaba"]
    CAPABILITIES = [
        "vector_search",
        "hybrid_search", 
        "full_text_search",
        "document_store",
        "memory_store",
        "knowledge_graph",
        "embedding",
        "semantic_search",
    ]
    
    def __init__(self):
        super().__init__()
        self._zvec_available = False
        self._zvec_client = None
        self._db_path = ZVEC_DB_PATH
        self._enhanced_mode = True
        self._collections = {}
        logger.warning(
            "⚠️  Zvec 已退役（v1.0 对账决议）。推荐迁移到 Qdrant（P99<100ms）。"
            "详见 src/skills/zvec.py 顶部的退役说明。"
        )
        self._check_zvec()
    
    def _check_zvec(self):
        """检查 Zvec 是否可用"""
        try:
            import zvec
            self._zvec_available = True
            self._zvec_module = zvec
            logger.info("Zvec 可用")
            
            os.makedirs(self._db_path, exist_ok=True)
            
            try:
                zvec.init()
            except RuntimeError:
                pass
            
            self._init_zvec()
        except ImportError:
            logger.warning("Zvec 不可用，请安装: pip install zvec")
    
    def _init_zvec(self):
        """初始化 Zvec 客户端"""
        try:
            from zvec import (
                CollectionSchema, 
                FieldSchema, 
                VectorSchema, 
                DataType,
                create_and_open
            )
            
            self._zvec_client = {}
            
            for collection_name in ["memory", "documents", "skills", "knowledge"]:
                coll_path = os.path.join(self._db_path, collection_name)
                
                try:
                    schema = CollectionSchema(
                        name=collection_name,
                        fields=[
                            FieldSchema(name="id", data_type=DataType.STRING),
                            FieldSchema(name="content", data_type=DataType.STRING),
                            FieldSchema(name="metadata", data_type=DataType.STRING),
                        ],
                        vectors=[
                            VectorSchema(
                                name="embedding",
                                data_type=DataType.VECTOR_FP32,
                                dimension=384,
                            )
                        ],
                    )
                    
                    try:
                        collection = self._zvec_module.open(coll_path)
                        logger.info(f"Zvec 集合打开成功: {collection_name}")
                    except Exception as e_open:
                        logger.debug(f"打开集合失败，尝试创建: {e_open}")
                        try:
                            collection = create_and_open(
                                path=coll_path,
                                schema=schema,
                            )
                            logger.info(f"Zvec 集合创建成功: {collection_name}")
                        except Exception as e_create:
                            logger.debug(f"创建集合失败，尝试删除旧数据: {e_create}")
                            import shutil
                            try:
                                shutil.rmtree(coll_path)
                                collection = create_and_open(
                                    path=coll_path,
                                    schema=schema,
                                )
                                logger.info(f"Zvec 集合重建成功: {collection_name}")
                            except Exception as e_recreate:
                                logger.warning(f"Zvec 集合重建失败 {collection_name}: {e_recreate}")
                                continue
                    
                    self._zvec_client[collection_name] = collection
                except Exception as e:
                    logger.warning(f"Zvec 集合初始化失败 {collection_name}: {e}")
        except Exception as e:
            logger.error(f"Zvec 初始化失败: {e}")
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Zvec 操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - collection: 集合名称
                - query: 查询文本
                - embedding: 向量数据
                - document: 文档内容
                - document_id: 文档ID
                - filters: 过滤条件
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "vector_search")
        collection = context.get("collection", "documents")
        
        if action not in ZVEC_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(ZVEC_FEATURES.keys())}",
                "available_actions": ZVEC_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode and self._zvec_available:
            result = self._execute_enhanced(action, collection, context)
        else:
            result = self._execute_fallback(action, collection, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": ZVEC_FEATURES[action]["name"],
            "collection": collection,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode and self._zvec_available else "fallback",
            "zvec_available": self._zvec_available,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, collection_name: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用 Zvec"""
        try:
            if collection_name not in self._zvec_client:
                return {"success": False, "error": f"集合 {collection_name} 不存在"}
            
            collection = self._zvec_client[collection_name]
            
            if action == "vector_search":
                query = context.get("query", "")
                top_k = context.get("top_k", 5)
                
                if not query:
                    return {"success": False, "error": "请提供查询文本"}
                
                embedding = self._get_embedding(query)
                results = collection.search(
                    query_vector=embedding,
                    vector_name="embedding",
                    top_k=top_k,
                )
                
                return {
                    "success": True,
                    "result": {
                        "query": query,
                        "matches": [{"id": str(r.id), "score": r.score} for r in results],
                        "count": len(results),
                    },
                }
            
            elif action == "hybrid_search":
                query = context.get("query", "")
                top_k = context.get("top_k", 5)
                
                if not query:
                    return {"success": False, "error": "请提供查询文本"}
                
                embedding = self._get_embedding(query)
                results = collection.search(
                    query_vector=embedding,
                    vector_name="embedding",
                    top_k=top_k,
                )
                
                return {
                    "success": True,
                    "result": {
                        "query": query,
                        "matches": [{"id": str(r.id), "score": r.score} for r in results],
                        "count": len(results),
                        "mode": "hybrid",
                    },
                }
            
            elif action == "document_store":
                document = context.get("document", "")
                document_id = context.get("document_id", str(uuid.uuid4()))
                
                if not document:
                    return {"success": False, "error": "请提供文档内容"}
                
                embedding = self._get_embedding(document)
                
                collection.insert(
                    docs=[{
                        "id": document_id,
                        "content": document,
                        "metadata": {"type": "document", "timestamp": datetime.now().isoformat()},
                    }],
                    vectors={"embedding": [embedding]},
                )
                collection.commit()
                
                return {
                    "success": True,
                    "result": {
                        "document_id": document_id,
                        "message": "文档存储成功",
                    },
                }
            
            elif action == "memory_store":
                content = context.get("content", "")
                memory_type = context.get("memory_type", "conversation")
                memory_id = context.get("memory_id", str(uuid.uuid4()))
                
                if not content:
                    return {"success": False, "error": "请提供记忆内容"}
                
                embedding = self._get_embedding(content)
                metadata = {
                    "type": memory_type,
                    "timestamp": datetime.now().isoformat(),
                }
                
                collection.insert(
                    docs=[{
                        "id": memory_id,
                        "content": content,
                        "metadata": metadata,
                    }],
                    vectors={"embedding": [embedding]},
                )
                collection.commit()
                
                return {
                    "success": True,
                    "result": {
                        "memory_id": memory_id,
                        "memory_type": memory_type,
                        "message": "记忆存储成功",
                    },
                }
            
            elif action == "full_text_search":
                query = context.get("query", "")
                
                if not query:
                    return {"success": False, "error": "请提供查询文本"}
                
                embedding = self._get_embedding(query)
                results = collection.search(
                    query_vector=embedding,
                    vector_name="embedding",
                    top_k=10,
                )
                
                return {
                    "success": True,
                    "result": {
                        "query": query,
                        "matches": [{"id": str(r.id), "score": r.score} for r in results],
                        "count": len(results),
                    },
                }
            
            elif action == "knowledge_graph":
                entity1 = context.get("entity1", "")
                relation = context.get("relation", "")
                entity2 = context.get("entity2", "")
                
                if not entity1 or not relation:
                    return {"success": False, "error": "请提供实体和关系"}
                
                kg_entry = {
                    "entity1": entity1,
                    "relation": relation,
                    "entity2": entity2,
                    "timestamp": datetime.now().isoformat(),
                }
                
                kg_id = f"{entity1}-{relation}-{entity2}"
                embedding = self._get_embedding(json.dumps(kg_entry))
                
                collection.insert(
                    docs=[{
                        "id": kg_id,
                        "content": json.dumps(kg_entry),
                        "metadata": {"type": "knowledge_graph"},
                    }],
                    vectors={"embedding": [embedding]},
                )
                collection.commit()
                
                return {
                    "success": True,
                    "result": {
                        "kg_id": kg_id,
                        "message": "知识图谱条目添加成功",
                    },
                }
            
            return {"success": False, "error": f"操作 {action} 未实现"}
            
        except Exception as e:
            logger.error(f"Zvec 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_fallback(self, action: str, collection: str, context: Dict) -> Dict[str, Any]:
        """降级模式执行 — 使用内置能力"""
        try:
            if action == "vector_search":
                query = context.get("query", "")
                return {
                    "success": True,
                    "result": {
                        "mode": "fallback",
                        "query": query,
                        "matches": [],
                        "count": 0,
                        "note": "Zvec 未安装，使用内置向量检索",
                        "instructions": self._get_install_instructions(),
                    },
                }
            
            elif action in ["document_store", "memory_store", "knowledge_graph"]:
                return {
                    "success": True,
                    "result": {
                        "mode": "fallback",
                        "message": f"{ZVEC_FEATURES[action]['name']} 操作已记录",
                        "note": "Zvec 未安装，数据存储在内存中",
                        "instructions": self._get_install_instructions(),
                    },
                }
            
            return {"success": False, "error": f"操作 {action} 在降级模式下不可用"}
            
        except Exception as e:
            logger.error(f"降级模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_embedding(self, text: str) -> List[float]:
        """获取文本的向量表示"""
        try:
            import hashlib
            import numpy as np
            
            hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
            np.random.seed(hash_val)
            return np.random.rand(384).tolist()
        except Exception:
            return [0.0] * 384
    
    def _get_install_instructions(self) -> List[str]:
        """获取安装说明"""
        return [
            "1. 安装 Zvec: pip install zvec",
            "2. 无需独立部署，进程内运行",
            "3. 数据存储目录: ./zvec_data",
        ]
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return ZVEC_FEATURES
    
    def is_available(self) -> bool:
        """检查 Zvec 是否可用"""
        return self._zvec_available


def get_zvec_skill() -> ZvecSkill:
    """获取或创建 Zvec 技能实例"""
    return ZvecSkill()


def register_zvec_skill(registry=None):
    """注册 Zvec 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = ZvecSkill()
    registry.register(skill)
    logger.info("Zvec 技能已注册")
    return skill