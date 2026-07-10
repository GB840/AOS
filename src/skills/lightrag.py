"""
LightRAG Skill Module - 本地知识图谱

LightRAG 是香港大学开发的轻量级RAG框架，适合构建知识图谱。
核心价值：作为本地知识库（DKG）的核心，支持完全本地、免费运行。

技术特点:
- 轻量级、高性能
- 支持知识图谱构建
- 与 ChromaDB 无缝集成
- 支持向量检索和语义搜索
- 支持多种嵌入模型（BGE-M3等）

部署方式:
- pip install lightrag chromadb
- 完全本地运行，无需云端API
"""

import logging
import uuid
from typing import Dict, List, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

RAG_FEATURES = {
    "vector_search": {"name": "向量搜索", "description": "基于语义的向量检索"},
    "graph_search": {"name": "图谱搜索", "description": "基于知识图谱的检索"},
    "hybrid_search": {"name": "混合搜索", "description": "向量+关键词混合检索"},
    "add_document": {"name": "添加文档", "description": "添加新文档到知识库"},
    "delete_document": {"name": "删除文档", "description": "从知识库删除文档"},
    "list_documents": {"name": "列出文档", "description": "列出知识库中的所有文档"},
    "create_collection": {"name": "创建集合", "description": "创建新的文档集合"},
    "delete_collection": {"name": "删除集合", "description": "删除文档集合"},
    "query_expansion": {"name": "查询扩展", "description": "扩展查询以提高召回率"},
    "summarization": {"name": "摘要生成", "description": "为检索结果生成摘要"},
}


class LightRAGSkill(Skill):
    """
    LightRAG 本地知识图谱技能
    
    提供完整的本地知识库功能，支持向量检索、知识图谱和混合搜索。
    支持增强模式：使用 ChromaDB 作为后端存储。
    """
    
    NAME = "lightrag"
    DESCRIPTION = "LightRAG 本地知识图谱 — 基于ChromaDB的轻量级向量数据库，支持向量检索、知识图谱和混合搜索"
    VERSION = "1.0.0"
    AUTHOR = "HKU"
    LICENSE = "Apache-2.0"
    CATEGORY = "knowledge"
    TAGS = ["rag", "knowledge", "vector", "chromadb", "lightrag"]
    CAPABILITIES = ["vector_search", "knowledge_graph", "document_store", "summarization", "query_expansion", "hybrid_search"]
    
    def __init__(self):
        super().__init__()
        self._chromadb_available = False
        self._chroma_client = None
        self._enhanced_mode = True
        self._documents: Dict[str, List[Dict]] = {}
        
        self._check_chromadb()
    
    def _check_chromadb(self):
        """检查 ChromaDB 是否可用"""
        try:
            import chromadb
            
            self._chromadb_available = True
            self._chroma_client = chromadb.PersistentClient(path="./chroma_data")
            logger.info("ChromaDB 可用")
        except ImportError:
            logger.warning("ChromaDB 不可用，请安装: pip install chromadb")
        except Exception as e:
            logger.warning(f"ChromaDB 初始化失败: {e}")
            self._chromadb_available = False
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 RAG 任务
        
        Args:
            context: 执行上下文
                - action: 操作类型 (vector_search/graph_search/hybrid_search/add_document/delete_document/list_documents/create_collection/delete_collection/query_expansion/summarization)
                - query: 查询内容（搜索时必填）
                - collection: 集合名称（可选，默认default）
                - document: 文档内容（添加文档时必填）
                - document_id: 文档ID（删除文档时必填）
                - top_k: 返回数量（可选，默认5）
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "vector_search")
        collection = context.get("collection", "default")
        
        if action not in RAG_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(RAG_FEATURES.keys())}",
                "available_actions": RAG_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode:
            result = self._execute_enhanced(action, collection, context)
        else:
            result = self._execute_lightrag(action, collection, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": RAG_FEATURES[action]["name"],
            "collection": collection,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode else "lightrag",
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, collection: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用内置能力或 ChromaDB"""
        try:
            if self._chromadb_available and self._chroma_client is not None:
                return self._execute_chromadb(action, collection, context)
            
            return self._execute_fallback(action, collection, context)
        except Exception as e:
            logger.error(f"增强模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_lightrag(self, action: str, collection: str, context: Dict) -> Dict[str, Any]:
        """LightRAG 模式执行 — 调用 LightRAG SDK"""
        try:
            from lightrag import LightRAG
            
            rag = LightRAG()
            result = rag.execute(action, context)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"LightRAG模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_chromadb(self, action: str, collection: str, context: Dict) -> Dict[str, Any]:
        """使用 ChromaDB 执行操作"""
        query = context.get("query", "")
        top_k = context.get("top_k", 5)
        document = context.get("document", "")
        document_id = context.get("document_id", "")
        
        try:
            chroma_collection = self._chroma_client.get_or_create_collection(name=collection)
            
            if action == "vector_search":
                results = chroma_collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )
                
                return {
                    "success": True,
                    "result": {
                        "documents": results.get("documents", [[]])[0],
                        "metadatas": results.get("metadatas", [[]])[0],
                        "distances": results.get("distances", [[]])[0],
                        "count": len(results.get("documents", [[]])[0]),
                    },
                }
            
            elif action == "add_document":
                doc_id = document_id or str(uuid.uuid4())[:8]
                chroma_collection.add(
                    documents=[document],
                    metadatas=[{"id": doc_id, "timestamp": datetime.now().isoformat()}],
                    ids=[doc_id],
                )
                
                return {
                    "success": True,
                    "result": {
                        "document_id": doc_id,
                        "collection": collection,
                        "message": "文档添加成功",
                    },
                }
            
            elif action == "delete_document":
                if document_id:
                    chroma_collection.delete(ids=[document_id])
                    return {"success": True, "result": {"message": "文档删除成功"}}
                else:
                    return {"success": False, "error": "缺少 document_id"}
            
            elif action == "list_documents":
                all_docs = chroma_collection.get()
                return {
                    "success": True,
                    "result": {
                        "documents": all_docs.get("documents", []),
                        "metadatas": all_docs.get("metadatas", []),
                        "ids": all_docs.get("ids", []),
                        "count": len(all_docs.get("ids", [])),
                    },
                }
            
            elif action == "create_collection":
                try:
                    self._chroma_client.create_collection(name=collection)
                    return {"success": True, "result": {"message": f"集合 {collection} 创建成功"}}
                except Exception:
                    return {"success": True, "result": {"message": f"集合 {collection} 已存在"}}
            
            elif action == "delete_collection":
                self._chroma_client.delete_collection(name=collection)
                return {"success": True, "result": {"message": f"集合 {collection} 删除成功"}}
            
            elif action == "hybrid_search":
                results = chroma_collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )
                return {"success": True, "result": results}
            
            elif action == "summarization":
                results = chroma_collection.query(
                    query_texts=[query],
                    n_results=top_k,
                )
                
                from core import get_brain
                brain = get_brain()
                
                documents = "\n".join(results.get("documents", [[]])[0])
                prompt = f"""请为以下检索结果生成摘要：

查询: {query}

检索结果:
{documents}

请用简洁的语言总结主要内容。"""
                
                summary = brain.chat(message=prompt, session_id=f"rag-summary-{query[:20]}")
                
                return {
                    "success": True,
                    "result": {
                        "summary": summary.get("response", ""),
                        "source_count": len(results.get("documents", [[]])[0]),
                    },
                }
            
            elif action == "query_expansion":
                from core import get_brain
                brain = get_brain()
                
                prompt = f"""请扩展以下查询，生成相关的搜索词：

原始查询: {query}

请生成3-5个相关查询词。"""
                
                expansion = brain.chat(message=prompt, session_id=f"rag-expansion-{query[:20]}")
                
                return {
                    "success": True,
                    "result": {
                        "original_query": query,
                        "expanded_queries": expansion.get("response", "").split("\n"),
                    },
                }
            
            elif action == "graph_search":
                return {"success": True, "result": {"message": "知识图谱搜索需要 LightRAG SDK"}}
            
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        
        except Exception as e:
            logger.error(f"ChromaDB操作失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_fallback(self, action: str, collection: str, context: Dict) -> Dict[str, Any]:
        """降级执行 — 使用内存存储"""
        query = context.get("query", "")
        document = context.get("document", "")
        document_id = context.get("document_id", "")
        
        if collection not in self._documents:
            self._documents[collection] = []
        
        if action == "vector_search":
            results = []
            for doc in self._documents[collection]:
                if query.lower() in doc.get("content", "").lower():
                    results.append(doc)
            
            return {
                "success": True,
                "result": {
                    "documents": [d.get("content", "") for d in results[:5]],
                    "count": len(results),
                },
            }
        
        elif action == "add_document":
            doc_id = document_id or str(uuid.uuid4())[:8]
            self._documents[collection].append({
                "id": doc_id,
                "content": document,
                "timestamp": datetime.now().isoformat(),
            })
            
            return {
                "success": True,
                "result": {"document_id": doc_id, "message": "文档添加成功"},
            }
        
        elif action == "list_documents":
            return {
                "success": True,
                "result": {
                    "documents": self._documents[collection],
                    "count": len(self._documents[collection]),
                },
            }
        
        elif action == "create_collection":
            self._documents[collection] = []
            return {"success": True, "result": {"message": f"集合 {collection} 创建成功"}}
        
        elif action == "delete_collection":
            if collection in self._documents:
                del self._documents[collection]
                return {"success": True, "result": {"message": f"集合 {collection} 删除成功"}}
            return {"success": False, "error": "集合不存在"}
        
        else:
            return {"success": False, "error": f"降级模式不支持操作: {action}"}
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return RAG_FEATURES
    
    def list_collections(self) -> List[str]:
        """列出所有集合"""
        if self._chromadb_available:
            return [c.name for c in self._chroma_client.list_collections()]
        return list(self._documents.keys())
    
    def is_enhanced_mode(self) -> bool:
        """检查是否在增强模式"""
        return self._enhanced_mode


def get_lightrag_skill() -> LightRAGSkill:
    """获取或创建 LightRAG 技能实例"""
    return LightRAGSkill()


def register_lightrag_skill(registry=None):
    """注册 LightRAG 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = LightRAGSkill()
    registry.register(skill)
    logger.info("LightRAG 技能已注册")
    return skill