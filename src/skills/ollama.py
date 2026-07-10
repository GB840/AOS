"""
Ollama Skill Module - 本地大模型

Ollama 是一个运行本地大模型的工具，支持 Qwen、DeepSeek 等多种模型。
核心价值：全程本地、无Token费用，是架构中"本地推理大脑"的核心。

与 Llama.cpp 协同工作：
- Llama.cpp: 提供最快的 CPU 推理速度（Windows原生）
- Ollama: 提供统一的 API 网关，支持创建自定义 GGUF 模型
- 架构: 用户输入 → Hermes → DeerFlow → Ollama API → Llama.cpp → 本地硬件

技术特点:
- 支持多种模型：Qwen2.5、DeepSeek、Llama、Mistral等
- 一键拉取和运行模型
- 支持从 GGUF 文件创建自定义模型
- 提供 REST API 接口
- 8GB内存可运行7B模型，推荐1.5B/3B模型

部署方式:
- 下载安装：https://ollama.com/download
- 拉取模型：ollama pull qwen2.5:7b
- 运行模型：ollama run qwen2.5:7b
- 创建自定义模型：ollama create qwen2.5-1.5b -f Modelfile
"""

import logging
import uuid
import time
import requests
from typing import Dict, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

OLLAMA_MODELS = {
    "qwen2.5:7b": {"name": "Qwen2.5 7B", "description": "阿里通义千问，中文能力强", "size": "约4.5GB"},
    "qwen2.5:3b": {"name": "Qwen2.5 3B", "description": "轻量级，8GB内存友好", "size": "约2GB"},
    "qwen2.5:14b": {"name": "Qwen2.5 14B", "description": "更高性能", "size": "约8GB"},
    "deepseek-chat:latest": {"name": "DeepSeek Chat", "description": "深度求索，代码能力强", "size": "约7GB"},
    "llama3.3:70b": {"name": "Llama 3.3 70B", "description": "Meta旗舰模型", "size": "约39GB"},
    "llama3.3:8b": {"name": "Llama 3.3 8B", "description": "轻量级Llama", "size": "约4.5GB"},
    "mistral:latest": {"name": "Mistral", "description": "高效开源模型", "size": "约4GB"},
    "phi3:latest": {"name": "Phi-3", "description": "微软轻量级模型", "size": "约2GB"},
}

OLLAMA_FEATURES = {
    "chat": {"name": "聊天", "description": "与本地模型对话"},
    "generate": {"name": "生成", "description": "生成文本"},
    "list_models": {"name": "列出模型", "description": "列出已安装的模型"},
    "pull_model": {"name": "拉取模型", "description": "从Ollama Hub拉取模型"},
    "push_model": {"name": "推送模型", "description": "推送模型到Ollama Hub"},
    "delete_model": {"name": "删除模型", "description": "删除本地模型"},
    "create_model": {"name": "创建模型", "description": "创建自定义模型"},
    "show_model": {"name": "查看模型", "description": "查看模型详情"},
    "embeddings": {"name": "嵌入", "description": "生成文本嵌入"},
    "chat_with_params": {"name": "聊天(自定义参数)", "description": "带自定义推理参数的聊天"},
    "generate_with_params": {"name": "生成(自定义参数)", "description": "带自定义推理参数的文本生成"},
    "get_performance": {"name": "性能统计", "description": "获取模型推理性能数据"},
    "set_default_params": {"name": "设置默认参数", "description": "设置默认推理参数"},
}


class OllamaSkill(Skill):
    """
    Ollama 本地大模型技能
    
    提供本地大模型推理能力，支持聊天、生成、嵌入等功能。
    使用 Ollama REST API 与本地模型交互。
    """
    
    NAME = "ollama"
    DESCRIPTION = "Ollama 本地大模型 — 运行Qwen、DeepSeek等模型，全程本地、无Token费用，支持与Llama.cpp协同"
    VERSION = "1.0.0"
    AUTHOR = "Ollama Inc."
    LICENSE = "MIT"
    CATEGORY = "ai"
    TAGS = ["ollama", "local", "llm", "model", "inference", "llama.cpp", "gguf"]
    CAPABILITIES = ["chat", "text_generation", "embeddings", "model_management", "local_inference", "gguf_import"]
    
    def __init__(self):
        super().__init__()
        self._ollama_url = "http://localhost:11434"
        self._ollama_available = False
        self._default_model = "qwen2.5:7b"
        self._enhanced_mode = True
        
        self._default_params = {
            "temperature": 0.7,
            "context_window": 2048,
            "max_tokens": 512,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
        }
        
        self._performance_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_time_ms": 0,
            "avg_tokens_per_second": 0,
            "model_stats": {},
        }
        
        self._check_ollama()
    
    def _check_ollama(self):
        """检查 Ollama 是否可用"""
        try:
            response = requests.get(f"{self._ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                self._ollama_available = True
                logger.info("Ollama 可用")
            else:
                logger.warning("Ollama 服务未运行")
        except Exception:
            logger.warning("Ollama 不可用，请安装并启动: https://ollama.com/download")
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Ollama 任务
        
        Args:
            context: 执行上下文
                - action: 操作类型 (chat/generate/list_models/pull_model/push_model/delete_model/create_model/show_model/embeddings)
                - model: 模型名称（可选，默认qwen2.5:7b）
                - message: 消息内容（聊天时必填）
                - prompt: 提示词（生成时必填）
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "chat")
        model = context.get("model", self._default_model)
        
        if action not in OLLAMA_FEATURES:
            return {
                "success": False,
                "error": f"未知操作: {action}，可用操作: {list(OLLAMA_FEATURES.keys())}",
                "available_actions": OLLAMA_FEATURES,
            }
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode:
            result = self._execute_enhanced(action, model, context)
        else:
            result = self._execute_ollama(action, model, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "action_name": OLLAMA_FEATURES[action]["name"],
            "model": model,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode else "ollama",
            "ollama_available": self._ollama_available,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, model: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用 Ollama API 或降级方案"""
        try:
            if self._ollama_available:
                return self._execute_ollama(action, model, context)
            
            return self._execute_fallback(action, model, context)
        except Exception as e:
            logger.error(f"增强模式执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _execute_ollama(self, action: str, model: str, context: Dict) -> Dict[str, Any]:
        """使用 Ollama API 执行操作"""
        try:
            if action == "chat":
                message = context.get("message", context.get("input", ""))
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": message}],
                    "stream": False,
                }
                
                response = requests.post(f"{self._ollama_url}/api/chat", json=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "result": {
                            "response": data.get("message", {}).get("content", ""),
                            "model": model,
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "generate":
                prompt = context.get("prompt", context.get("input", ""))
                
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }
                
                response = requests.post(f"{self._ollama_url}/api/generate", json=payload, timeout=120)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "result": {
                            "response": data.get("response", ""),
                            "model": model,
                            "token_count": data.get("total_duration", 0),
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "list_models":
                response = requests.get(f"{self._ollama_url}/api/tags", timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "result": {
                            "models": data.get("models", []),
                            "count": len(data.get("models", [])),
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "pull_model":
                payload = {"name": model, "stream": False}
                
                response = requests.post(f"{self._ollama_url}/api/pull", json=payload, timeout=600)
                
                if response.status_code == 200:
                    return {"success": True, "result": {"message": f"模型 {model} 拉取成功"}}
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "delete_model":
                response = requests.delete(f"{self._ollama_url}/api/delete", json={"name": model}, timeout=10)
                
                if response.status_code == 200:
                    return {"success": True, "result": {"message": f"模型 {model} 删除成功"}}
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "show_model":
                response = requests.get(f"{self._ollama_url}/api/show", params={"name": model}, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    return {"success": True, "result": data}
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "embeddings":
                prompt = context.get("prompt", context.get("input", ""))
                
                payload = {"model": model, "prompt": prompt}
                
                response = requests.post(f"{self._ollama_url}/api/embeddings", json=payload, timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "result": {
                            "embedding": data.get("embedding", []),
                            "dimensions": len(data.get("embedding", [])),
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "create_model":
                name = context.get("name", model)
                modelfile = context.get("modelfile", "")
                
                payload = {"name": name, "modelfile": modelfile}
                
                response = requests.post(f"{self._ollama_url}/api/create", json=payload, timeout=300)
                
                if response.status_code == 200:
                    return {"success": True, "result": {"message": f"模型 {name} 创建成功"}}
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "push_model":
                payload = {"name": model, "stream": False}
                
                response = requests.post(f"{self._ollama_url}/api/push", json=payload, timeout=600)
                
                if response.status_code == 200:
                    return {"success": True, "result": {"message": f"模型 {model} 推送成功"}}
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "chat_with_params":
                message = context.get("message", context.get("input", ""))
                params = context.get("params", {})
                
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": message}],
                    "stream": False,
                }
                
                payload.update(self._merge_params(params))
                
                start_time = time.time()
                response = requests.post(f"{self._ollama_url}/api/chat", json=payload, timeout=120)
                end_time = time.time()
                
                if response.status_code == 200:
                    data = response.json()
                    response_content = data.get("message", {}).get("content", "")
                    self._update_performance(model, len(response_content), (end_time - start_time) * 1000)
                    
                    return {
                        "success": True,
                        "result": {
                            "response": response_content,
                            "model": model,
                            "params": payload,
                            "time_ms": round((end_time - start_time) * 1000, 2),
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "generate_with_params":
                prompt = context.get("prompt", context.get("input", ""))
                params = context.get("params", {})
                
                payload = {
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                }
                
                payload.update(self._merge_params(params))
                
                start_time = time.time()
                response = requests.post(f"{self._ollama_url}/api/generate", json=payload, timeout=120)
                end_time = time.time()
                
                if response.status_code == 200:
                    data = response.json()
                    response_content = data.get("response", "")
                    self._update_performance(model, len(response_content), (end_time - start_time) * 1000)
                    
                    return {
                        "success": True,
                        "result": {
                            "response": response_content,
                            "model": model,
                            "params": payload,
                            "time_ms": round((end_time - start_time) * 1000, 2),
                        },
                    }
                else:
                    return {"success": False, "error": f"Ollama返回错误: {response.status_code}"}
            
            elif action == "get_performance":
                return {
                    "success": True,
                    "result": self._performance_stats,
                }
            
            elif action == "set_default_params":
                params = context.get("params", {})
                for key in params:
                    if key in self._default_params:
                        self._default_params[key] = params[key]
                
                return {
                    "success": True,
                    "result": {
                        "message": "默认参数已更新",
                        "default_params": self._default_params,
                    },
                }
            
            else:
                return {"success": False, "error": f"未知操作: {action}"}
        
        except Exception as e:
            logger.error(f"Ollama API调用失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _execute_fallback(self, action: str, model: str, context: Dict) -> Dict[str, Any]:
        """降级执行 — 使用外部LLM"""
        try:
            if action == "chat" or action == "generate":
                from core import get_brain
                
                brain = get_brain()
                message = context.get("message", context.get("prompt", context.get("input", "")))
                
                result = brain.chat(message=message, session_id=f"ollama-fallback-{message[:20]}")
                
                return {
                    "success": True,
                    "result": {
                        "response": result.get("response", ""),
                        "model": model,
                        "mode": "fallback",
                    },
                }
            
            elif action == "list_models":
                return {
                    "success": True,
                    "result": {
                        "models": [],
                        "count": 0,
                        "message": "Ollama未运行，请启动Ollama服务",
                    },
                }
            
            elif action == "pull_model":
                return {
                    "success": False,
                    "error": "Ollama未运行，请先安装并启动Ollama",
                }
            
            else:
                return {"success": False, "error": f"降级模式不支持操作: {action}"}
        except Exception as e:
            logger.error(f"降级模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def list_models(self) -> Dict[str, Any]:
        """列出所有可用模型"""
        return OLLAMA_MODELS
    
    def list_features(self) -> Dict[str, Any]:
        """列出所有可用功能"""
        return OLLAMA_FEATURES
    
    def _merge_params(self, params: Dict) -> Dict:
        """合并用户参数与默认参数"""
        merged = {}
        for key in self._default_params:
            merged[key] = params.get(key, self._default_params[key])
        return merged

    def _update_performance(self, model: str, token_count: int, time_ms: float):
        """更新性能统计"""
        self._performance_stats["total_requests"] += 1
        self._performance_stats["total_tokens"] += token_count
        self._performance_stats["total_time_ms"] += time_ms
        
        if self._performance_stats["total_time_ms"] > 0:
            self._performance_stats["avg_tokens_per_second"] = round(
                self._performance_stats["total_tokens"] / 
                (self._performance_stats["total_time_ms"] / 1000),
                2
            )
        
        if model not in self._performance_stats["model_stats"]:
            self._performance_stats["model_stats"][model] = {
                "requests": 0,
                "tokens": 0,
                "time_ms": 0,
                "avg_tokens_per_second": 0,
            }
        
        self._performance_stats["model_stats"][model]["requests"] += 1
        self._performance_stats["model_stats"][model]["tokens"] += token_count
        self._performance_stats["model_stats"][model]["time_ms"] += time_ms
        
        if self._performance_stats["model_stats"][model]["time_ms"] > 0:
            self._performance_stats["model_stats"][model]["avg_tokens_per_second"] = round(
                self._performance_stats["model_stats"][model]["tokens"] / 
                (self._performance_stats["model_stats"][model]["time_ms"] / 1000),
                2
            )

    def get_default_params(self) -> Dict:
        """获取默认推理参数"""
        return self._default_params

    def is_ollama_available(self) -> bool:
        """检查 Ollama 是否可用"""
        return self._ollama_available


def get_ollama_skill() -> OllamaSkill:
    """获取或创建 Ollama 技能实例"""
    return OllamaSkill()


def register_ollama_skill(registry=None):
    """注册 Ollama 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = OllamaSkill()
    registry.register(skill)
    logger.info("Ollama 技能已注册")
    return skill