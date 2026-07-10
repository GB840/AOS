"""
Cognee Skill Module - 知识图谱记忆层

集成真实的 cognee 开源项目 (https://github.com/topoteretes/cognee)
提供知识图谱记忆和推理能力。

核心价值:
- 知识图谱: 将信息转化为结构化知识图谱
- 长期记忆: 跨会话的持久化记忆存储
- 推理能力: 基于知识图谱的智能推理
- 关系发现: 自动发现实体间的关系

部署位置:
1. Hermes 认知大脑的"长期记忆存储后端"
2. DeerFlow 任务调度引擎的"知识推理Worker"
3. AI 工厂的"知识图谱中心"

支持的操作:
- add_knowledge: 添加知识到图谱
- search_knowledge: 搜索知识
- query_graph: 查询知识图谱
- discover_relations: 发现实体关系
- export_graph: 导出知识图谱
- get_stats: 获取统计信息
"""

import os
import json
import logging
import uuid
from typing import Dict, List, Any
from datetime import datetime
from pathlib import Path

from .base import Skill
from utils.config import config

logger = logging.getLogger(__name__)

try:
    import cognee
    from cognee.api.v1.search import SearchType
    COGNEE_AVAILABLE = True
    logger.info("✅ cognee 开源库已加载")
except ImportError:
    COGNEE_AVAILABLE = False
    logger.warning("⚠️ cognee 开源库未安装，使用模拟模式")

ENTITY_TYPES = {
    "person": {"name": "人物", "description": "个人或角色"},
    "organization": {"name": "组织", "description": "公司、机构、团队"},
    "concept": {"name": "概念", "description": "抽象概念或理念"},
    "technology": {"name": "技术", "description": "技术、框架、工具"},
    "project": {"name": "项目", "description": "项目或产品"},
    "document": {"name": "文档", "description": "文档或文件"},
    "location": {"name": "地点", "description": "地理位置"},
    "event": {"name": "事件", "description": "事件或活动"},
}

RELATION_TYPES = {
    "related_to": {"name": "相关", "description": "两个实体相关联"},
    "part_of": {"name": "属于", "description": "一个实体是另一个的一部分"},
    "uses": {"name": "使用", "description": "一个实体使用另一个"},
    "created_by": {"name": "创建", "description": "一个实体由另一个创建"},
    "contains": {"name": "包含", "description": "一个实体包含另一个"},
    "depends_on": {"name": "依赖", "description": "一个实体依赖另一个"},
    "similar_to": {"name": "相似", "description": "两个实体相似"},
    "opposite_of": {"name": "相反", "description": "两个实体相反"},
    "works_at": {"name": "工作于", "description": "人物在组织工作"},
    "developed_by": {"name": "开发", "description": "技术/项目由谁开发"},
}

COGNEE_FEATURES = {
    "add_knowledge": {
        "name": "添加知识",
        "description": "添加知识到知识图谱",
        "input": ["content", "entity_type", "tags", "metadata"],
        "output": {"entity_id", "success"},
    },
    "search_knowledge": {
        "name": "搜索知识",
        "description": "在知识图谱中搜索相关知识",
        "input": ["query", "entity_type", "limit"],
        "output": {"results", "count"},
    },
    "query_graph": {
        "name": "查询图谱",
        "description": "查询知识图谱中的实体和关系",
        "input": ["query", "entity_id"],
        "output": {"entities", "relations", "paths"},
    },
    "discover_relations": {
        "name": "发现关系",
        "description": "自动发现实体间的潜在关系",
        "input": ["entity_id", "depth"],
        "output": {"relations", "discoveries"},
    },
    "export_graph": {
        "name": "导出图谱",
        "description": "导出知识图谱为JSON格式",
        "input": ["format"],
        "output": {"graph", "node_count", "edge_count"},
    },
    "get_stats": {
        "name": "统计信息",
        "description": "获取知识图谱的统计信息",
        "input": [],
        "output": {"entity_count", "relation_count", "types"},
    },
    "list_entities": {
        "name": "列出实体",
        "description": "列出知识图谱中的所有实体",
        "input": ["entity_type", "limit"],
        "output": {"entities", "count"},
    },
    "delete_entity": {
        "name": "删除实体",
        "description": "删除指定实体及其相关关系",
        "input": ["entity_id"],
        "output": {"success", "deleted_relations"},
    },
}


class CogneeSkill(Skill):
    """
    Cognee 技能 - 知识图谱记忆层
    
    为Hermes的记忆层增加知识图谱能力，支持将对话、文档等转化为长期记忆。
    """
    
    NAME = "cognee"
    DESCRIPTION = "Cognee — 知识图谱记忆层，支持对话/文档转化为长期记忆，提供知识图谱推理能力"
    VERSION = "1.0.0"
    AUTHOR = "cognee"
    LICENSE = "MIT"
    CATEGORY = "memory"
    TAGS = ["cognee", "knowledge", "graph", "memory", "long_term", "reasoning"]
    CAPABILITIES = [
        "knowledge_graph",
        "long_term_memory",
        "relation_discovery",
        "reasoning",
        "entity_extraction",
        "graph_query",
    ]
    
    def __init__(self):
        super().__init__()
        self._entities = {}
        self._relations = []
        self._entity_types = ENTITY_TYPES
        self._relation_types = RELATION_TYPES
        self._graph_path = os.path.join(config.BASE_DIR, "cognee_graph")
        Path(self._graph_path).mkdir(parents=True, exist_ok=True)
        self._load_graph()
        
    def _load_graph(self):
        """加载已有的知识图谱"""
        graph_file = os.path.join(self._graph_path, "graph.json")
        if os.path.exists(graph_file):
            try:
                with open(graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._entities = data.get("entities", {})
                    self._relations = data.get("relations", [])
                logger.info(f"知识图谱已加载: {len(self._entities)} 个实体, {len(self._relations)} 个关系")
            except Exception as e:
                logger.warning(f"加载知识图谱失败: {e}")
    
    def _save_graph(self):
        """保存知识图谱"""
        graph_file = os.path.join(self._graph_path, "graph.json")
        data = {
            "entities": self._entities,
            "relations": self._relations,
            "saved_at": datetime.now().isoformat(),
        }
        with open(graph_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行Cognee操作
        
        Args:
            context: 执行上下文
                - action: 操作类型
                - content: 知识内容
                - entity_type: 实体类型
                - tags: 标签列表
                - metadata: 元数据
                - query: 搜索/查询语句
                - entity_id: 实体ID
                - limit: 返回数量限制
                - depth: 查询深度
                - format: 输出格式
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "search_knowledge")
        
        if action not in COGNEE_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(COGNEE_FEATURES.keys())}",
                "available_actions": COGNEE_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if COGNEE_AVAILABLE:
            result = self._execute_real_cognee(action, task_id, context)
        else:
            result = self._execute_action(action, task_id, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": COGNEE_FEATURES[action]["name"],
            "result": result.get("result"),
            "error": result.get("error"),
            "entity_count": len(self._entities),
            "relation_count": len(self._relations),
            "timestamp": datetime.now().isoformat(),
            "cognee_version": cognee.__version__ if COGNEE_AVAILABLE else "模拟模式",
        }
    
    def _execute_real_cognee(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """使用真实的cognee开源库执行操作"""
        try:
            if action == "add_knowledge":
                content = context.get("content", "")
                tags = context.get("tags", [])
                
                if not content:
                    return {"success": False, "error": "请提供知识内容"}
                
                cognee.add(content)
                cognee.cognify()
                
                return {
                    "success": True,
                    "result": {
                        "message": "知识已添加到cognee知识图谱",
                        "content_length": len(content),
                        "tags": tags,
                    },
                }
            
            elif action == "search_knowledge":
                query = context.get("query", "")
                limit = context.get("limit", 10)
                
                if not query:
                    return {"success": False, "error": "请提供搜索查询"}
                
                results = cognee.search(query, search_type=SearchType.SEMANTIC)
                
                formatted_results = []
                for i, result in enumerate(results[:limit]):
                    if hasattr(result, '__dict__'):
                        formatted_results.append({
                            "id": str(i),
                            "content": str(result)[:200],
                            "score": getattr(result, 'score', 0),
                        })
                    else:
                        formatted_results.append({
                            "id": str(i),
                            "content": str(result)[:200],
                        })
                
                return {
                    "success": True,
                    "result": {
                        "query": query,
                        "results": formatted_results,
                        "count": len(formatted_results),
                    },
                }
            
            elif action == "query_graph":
                query = context.get("query", "")
                
                try:
                    graph_data = cognee.visualize_graph()
                    return {
                        "success": True,
                        "result": {
                            "graph_available": True,
                            "message": "知识图谱查询成功",
                        },
                    }
                except Exception as e:
                    return {
                        "success": True,
                        "result": {
                            "graph_available": False,
                            "message": f"图谱可视化需要单独启动服务: {str(e)[:100]}",
                        },
                    }
            
            elif action == "get_stats":
                datasets = cognee.datasets.list_datasets()
                return {
                    "success": True,
                    "result": {
                        "dataset_count": len(datasets),
                        "cognee_version": cognee.__version__,
                        "message": "cognee知识图谱统计信息",
                    },
                }
            
            elif action == "list_entities":
                datasets = cognee.datasets.list_datasets()
                entities = []
                for i, dataset in enumerate(datasets[:20]):
                    entities.append({
                        "id": str(i),
                        "content": str(dataset),
                        "type": "dataset",
                        "type_name": "数据集",
                    })
                
                return {
                    "success": True,
                    "result": {
                        "entities": entities,
                        "count": len(entities),
                    },
                }
            
            elif action == "export_graph":
                export_result = cognee.export()
                return {
                    "success": True,
                    "result": {
                        "format": "cognee-native",
                        "export_data": str(export_result)[:500],
                    },
                }
            
            else:
                logger.warning(f"cognee库不支持操作: {action}，回退到模拟模式")
                return self._execute_action(action, task_id, context)
        
        except Exception as e:
            logger.error(f"cognee执行失败 {action}: {e}", exc_info=True)
            logger.info("回退到模拟模式")
            return self._execute_action(action, task_id, context)
    
    def _execute_action(self, action: str, task_id: str, context: Dict) -> Dict[str, Any]:
        """执行具体操作（模拟模式）"""
        try:
            if action == "add_knowledge":
                return self._add_knowledge(task_id, context)
            elif action == "search_knowledge":
                return self._search_knowledge(context)
            elif action == "query_graph":
                return self._query_graph(context)
            elif action == "discover_relations":
                return self._discover_relations(context)
            elif action == "export_graph":
                return self._export_graph(context)
            elif action == "get_stats":
                return self._get_stats(context)
            elif action == "list_entities":
                return self._list_entities(context)
            elif action == "delete_entity":
                return self._delete_entity(context)
            else:
                return {"success": False, "error": f"操作 {action} 未实现"}
        except Exception as e:
            logger.error(f"执行失败 {action}: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _extract_entities(self, content: str) -> List[Dict]:
        """从内容中提取实体"""
        entities = []
        
        keywords = {
            "person": ["工程师", "设计师", "经理", "研究员", "专家"],
            "organization": ["公司", "团队", "部门", "机构", "实验室"],
            "technology": ["框架", "工具", "库", "语言", "系统"],
            "project": ["项目", "产品", "应用", "平台"],
            "concept": ["概念", "理念", "理论", "模型"],
        }
        
        for entity_type, type_keywords in keywords.items():
            for keyword in type_keywords:
                if keyword in content:
                    entities.append({"type": entity_type, "keyword": keyword})
        
        return entities
    
    def _add_knowledge(self, task_id: str, context: Dict) -> Dict[str, Any]:
        """添加知识到知识图谱"""
        content = context.get("content", "")
        entity_type = context.get("entity_type", "concept")
        tags = context.get("tags", [])
        metadata = context.get("metadata", {})
        
        if not content:
            return {"success": False, "error": "请提供知识内容"}
        
        if entity_type not in self._entity_types:
            return {
                "success": False,
                "error": f"无效实体类型: {entity_type}，可用类型: {list(self._entity_types.keys())}",
            }
        
        entity_id = str(uuid.uuid4())[:8]
        
        entity = {
            "id": entity_id,
            "content": content,
            "type": entity_type,
            "type_name": self._entity_types[entity_type]["name"],
            "tags": tags,
            "metadata": metadata,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "related_entities": [],
        }
        
        self._entities[entity_id] = entity
        
        extracted_entities = self._extract_entities(content)
        for extracted in extracted_entities:
            related_id = f"ext-{str(uuid.uuid4())[:6]}"
            self._entities[related_id] = {
                "id": related_id,
                "content": extracted["keyword"],
                "type": extracted["type"],
                "type_name": self._entity_types.get(extracted["type"], {}).get("name", extracted["type"]),
                "tags": [],
                "metadata": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "related_entities": [],
            }
            self._relations.append({
                "id": str(uuid.uuid4())[:8],
                "source": entity_id,
                "target": related_id,
                "type": "related_to",
                "type_name": self._relation_types["related_to"]["name"],
                "confidence": 0.7,
                "created_at": datetime.now().isoformat(),
            })
        
        self._save_graph()
        
        return {
            "success": True,
            "result": {
                "entity_id": entity_id,
                "entity": entity,
                "extracted_entities": len(extracted_entities),
                "message": f"知识添加成功，创建了 {1 + len(extracted_entities)} 个实体",
            },
        }
    
    def _search_knowledge(self, context: Dict) -> Dict[str, Any]:
        """搜索知识"""
        query = context.get("query", "")
        entity_type = context.get("entity_type", "")
        limit = context.get("limit", 10)
        
        if not query:
            return {"success": False, "error": "请提供搜索查询"}
        
        results = []
        for entity_id, entity in self._entities.items():
            if entity_type and entity["type"] != entity_type:
                continue
            
            search_text = f"{entity['content']} {' '.join(entity['tags'])}"
            if query.lower() in search_text.lower():
                results.append({
                    "id": entity_id,
                    "content": entity["content"][:200] + "..." if len(entity["content"]) > 200 else entity["content"],
                    "type": entity["type"],
                    "type_name": entity["type_name"],
                    "tags": entity["tags"],
                    "created_at": entity["created_at"],
                })
        
        results = results[:limit]
        
        return {
            "success": True,
            "result": {
                "query": query,
                "results": results,
                "count": len(results),
                "entity_type": entity_type,
            },
        }
    
    def _query_graph(self, context: Dict) -> Dict[str, Any]:
        """查询知识图谱"""
        query = context.get("query", "")
        entity_id = context.get("entity_id", "")
        
        entities = []
        relations = []
        
        if entity_id:
            entity = self._entities.get(entity_id)
            if entity:
                entities.append(entity)
                
                for rel in self._relations:
                    if rel["source"] == entity_id or rel["target"] == entity_id:
                        relations.append(rel)
                        
                        other_id = rel["target"] if rel["source"] == entity_id else rel["source"]
                        other_entity = self._entities.get(other_id)
                        if other_entity and other_entity not in entities:
                            entities.append(other_entity)
        else:
            for entity_id, entity in self._entities.items():
                if query and query.lower() in entity["content"].lower():
                    entities.append(entity)
            
            for rel in self._relations:
                if rel["source"] in [e["id"] for e in entities] or rel["target"] in [e["id"] for e in entities]:
                    relations.append(rel)
        
        return {
            "success": True,
            "result": {
                "entities": entities[:20],
                "relations": relations[:30],
                "entity_count": len(entities),
                "relation_count": len(relations),
            },
        }
    
    def _discover_relations(self, context: Dict) -> Dict[str, Any]:
        """发现实体关系"""
        entity_id = context.get("entity_id", "")
        depth = context.get("depth", 2)
        
        if not entity_id:
            return {"success": False, "error": "请提供实体ID"}
        
        if entity_id not in self._entities:
            return {"success": False, "error": f"实体 {entity_id} 未找到"}
        
        discoveries = []
        visited = {entity_id}
        current_level = [entity_id]
        
        for _ in range(depth):
            next_level = []
            for source_id in current_level:
                for rel in self._relations:
                    if rel["source"] == source_id and rel["target"] not in visited:
                        visited.add(rel["target"])
                        next_level.append(rel["target"])
                        discoveries.append({
                            "relation": rel,
                            "target_entity": self._entities.get(rel["target"], {}),
                            "depth": _ + 1,
                        })
                    elif rel["target"] == source_id and rel["source"] not in visited:
                        visited.add(rel["source"])
                        next_level.append(rel["source"])
                        discoveries.append({
                            "relation": rel,
                            "target_entity": self._entities.get(rel["source"], {}),
                            "depth": _ + 1,
                        })
            current_level = next_level
        
        return {
            "success": True,
            "result": {
                "entity_id": entity_id,
                "entity": self._entities.get(entity_id),
                "discoveries": discoveries,
                "discovery_count": len(discoveries),
                "depth": depth,
            },
        }
    
    def _export_graph(self, context: Dict) -> Dict[str, Any]:
        """导出知识图谱"""
        format = context.get("format", "json")
        
        if format == "json":
            graph = {
                "entities": self._entities,
                "relations": self._relations,
                "entity_types": self._entity_types,
                "relation_types": self._relation_types,
                "exported_at": datetime.now().isoformat(),
            }
            
            return {
                "success": True,
                "result": {
                    "format": "json",
                    "graph": graph,
                    "node_count": len(self._entities),
                    "edge_count": len(self._relations),
                },
            }
        else:
            return {"success": False, "error": f"不支持的格式: {format}"}
    
    def _get_stats(self, context: Dict) -> Dict[str, Any]:
        """获取统计信息"""
        type_counts = {}
        for entity in self._entities.values():
            entity_type = entity["type"]
            type_counts[entity_type] = type_counts.get(entity_type, 0) + 1
        
        relation_type_counts = {}
        for rel in self._relations:
            rel_type = rel["type"]
            relation_type_counts[rel_type] = relation_type_counts.get(rel_type, 0) + 1
        
        return {
            "success": True,
            "result": {
                "entity_count": len(self._entities),
                "relation_count": len(self._relations),
                "entity_types": type_counts,
                "relation_types": relation_type_counts,
                "graph_path": self._graph_path,
            },
        }
    
    def _list_entities(self, context: Dict) -> Dict[str, Any]:
        """列出实体"""
        entity_type = context.get("entity_type", "")
        limit = context.get("limit", 20)
        
        entities = []
        for entity_id, entity in self._entities.items():
            if entity_type and entity["type"] != entity_type:
                continue
            entities.append({
                "id": entity_id,
                "content": entity["content"][:100] + "..." if len(entity["content"]) > 100 else entity["content"],
                "type": entity["type"],
                "type_name": entity["type_name"],
                "tags": entity["tags"],
                "created_at": entity["created_at"],
            })
        
        entities = entities[:limit]
        
        return {
            "success": True,
            "result": {
                "entities": entities,
                "count": len(entities),
                "total_entities": len(self._entities),
                "entity_type": entity_type,
            },
        }
    
    def _delete_entity(self, context: Dict) -> Dict[str, Any]:
        """删除实体"""
        entity_id = context.get("entity_id", "")
        
        if not entity_id:
            return {"success": False, "error": "请提供实体ID"}
        
        if entity_id not in self._entities:
            return {"success": False, "error": f"实体 {entity_id} 未找到"}
        
        deleted_relations = []
        self._relations = [
            rel for rel in self._relations
            if rel["source"] != entity_id and rel["target"] != entity_id
        ]
        
        del self._entities[entity_id]
        self._save_graph()
        
        return {
            "success": True,
            "result": {
                "entity_id": entity_id,
                "deleted_relations": len(deleted_relations),
                "message": "实体已删除",
            },
        }
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return COGNEE_FEATURES
    
    def get_entity_count(self) -> int:
        """获取实体数量"""
        return len(self._entities)
    
    def get_relation_count(self) -> int:
        """获取关系数量"""
        return len(self._relations)


def get_cognee_skill() -> CogneeSkill:
    """获取或创建 Cognee 技能实例"""
    return CogneeSkill()


def register_cognee_skill(registry=None):
    """注册 Cognee 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = CogneeSkill()
    registry.register(skill)
    logger.info("Cognee 技能已注册")
    return skill