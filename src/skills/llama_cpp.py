"""
Llama.cpp 技能模块 - Windows原生推理引擎

Llama.cpp 是一个高性能的 LLM 推理引擎，提供最快的 CPU 推理速度。
通过 llama-server.exe 提供 API 接口，可与 Ollama 协同工作。

核心特性:
- 极致性能: 最快的 CPU 推理速度
- Windows原生: 无需编译，预编译包直接使用
- GGUF格式: 支持 Qwen、Llama、DeepSeek 等主流模型
- API服务: 通过 llama-server.exe 提供 HTTP API
- 内存友好: 8GB内存可运行 Qwen2.5-1.5B/Qwen2.5-3B

推荐模型(8GB内存):
- Qwen2.5-1.5B-Instruct-GGUF (Q4_K_M) ~1GB - 最快响应
- Qwen2.5-3B-Instruct-GGUF (Q4_K_M) ~2GB - 更强能力
- Llama-3.2-3B-Instruct-GGUF (Q4_K_M) ~2GB - 英文更强

架构整合:
用户输入 → Hermes → DeerFlow → Ollama API → Llama.cpp → 本地硬件
"""

import os
import logging
import uuid
import time
import subprocess
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base import Skill

logger = logging.getLogger(__name__)

from utils.config import config

LLAMA_CPP_PATH = config.LLAMA_CPP_PATH or str(Path(config.BASE_DIR) / "external" / "llama.cpp")
LLAMA_MODELS_PATH = os.path.join(LLAMA_CPP_PATH, "models")
LLAMA_SERVER_PORT = 8080

LLAMA_MODELS = {
    "qwen2.5-0.5b": {
        "name": "Qwen2.5-0.5B-Instruct",
        "size": "~400MB",
        "description": "最快响应，适合轻量任务",
        "recommended": False,
        "context_window": 2048,
        "tier": "LOW",
        "ollama_model": "qwen2.5:0.5b",
    },
    "qwen2.5-1.5b": {
        "name": "Qwen2.5-1.5B-Instruct",
        "size": "~1GB",
        "description": "平衡性能，推荐使用",
        "recommended": True,
        "context_window": 2048,
        "tier": "MEDIUM",
        "ollama_model": "qwen2.5:1.5b",
    },
    "qwen2.5-3b": {
        "name": "Qwen2.5-3B-Instruct",
        "size": "~2GB",
        "description": "更强能力，适合复杂任务",
        "recommended": False,
        "context_window": 2048,
        "tier": "HIGH",
        "ollama_model": "qwen2.5:3b",
    },
    "llama3.2-1b": {
        "name": "Llama-3.2-1B-Instruct",
        "size": "~1.3GB",
        "description": "英文更强，中文能力不如Qwen",
        "recommended": False,
        "context_window": 2048,
        "tier": "LOW",
        "ollama_model": "llama3.2:1b",
    },
}


class LlamaCppSkill(Skill):
    """
    Llama.cpp 推理引擎技能
    
    提供本地大模型推理能力，通过 llama-server.exe 提供 HTTP API。
    支持 GGUF 格式的量化模型，8GB内存可流畅运行。
    """
    
    NAME = "llama_cpp"
    DESCRIPTION = "Llama.cpp 推理引擎 — Windows原生，最快CPU推理，支持GGUF量化模型，8GB内存最优解"
    VERSION = "1.0.0"
    AUTHOR = "Llama.cpp Community"
    LICENSE = "MIT"
    CATEGORY = "ai"
    TAGS = ["llama.cpp", "llama", "gguf", "inference", "local", "cpu"]
    CAPABILITIES = [
        "chat",
        "text_generation",
        "embeddings",
        "model_management",
        "local_inference",
        "api_server",
    ]
    
    def __init__(self):
        super().__init__()
        self._llama_cpp_available = False
        self._server_running = False
        self._server_process = None
        self._api_base_url = f"http://localhost:{LLAMA_SERVER_PORT}"
        self._enhanced_mode = True
        self._current_model = None
        self._current_tier = None
        self._fallback_tiers = ["HIGH", "MEDIUM", "LOW"]
        self._check_llama_cpp()
    
    def _check_llama_cpp(self):
        """检查 Llama.cpp 是否可用"""
        try:
            if os.path.exists(LLAMA_CPP_PATH):
                server_path = os.path.join(LLAMA_CPP_PATH, "llama-server.exe")
                if os.path.exists(server_path):
                    self._llama_cpp_available = True
                    logger.info("Llama.cpp 可用")
                
                os.makedirs(LLAMA_MODELS_PATH, exist_ok=True)
        except Exception as e:
            logger.warning("Llama.cpp 检查失败: %s", e)
    
    def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行 Llama.cpp 操作
        
        Args:
            context: 执行上下文
                - action: 操作类型 (chat, generate, embeddings, start_server, stop_server, list_models)
                - prompt: 提示文本
                - model: 模型名称
                - max_tokens: 最大生成token数
                - temperature: 温度参数
        
        Returns:
            Dict: 执行结果
        """
        action = context.get("action", "chat")
        
        task_id = str(uuid.uuid4())[:8]
        
        if self._enhanced_mode and self._llama_cpp_available:
            result = self._execute_enhanced(action, context)
        else:
            result = self._execute_fallback(action, context)
        
        return {
            "success": result.get("success", False),
            "task_id": task_id,
            "action": action,
            "result": result.get("result"),
            "error": result.get("error"),
            "mode": "enhanced" if self._enhanced_mode and self._llama_cpp_available else "fallback",
            "llama_cpp_available": self._llama_cpp_available,
            "server_running": self._server_running,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_enhanced(self, action: str, context: Dict) -> Dict[str, Any]:
        """增强模式执行 — 使用 Llama.cpp"""
        try:
            if action == "start_server":
                return self._start_server(context)
            
            elif action == "stop_server":
                return self._stop_server()
            
            elif action == "list_models":
                return self._list_models()
            
            elif action == "chat":
                return self._chat(context)
            
            elif action == "generate":
                return self._generate(context)
            
            elif action == "embeddings":
                return self._embeddings(context)
            
            return {"success": False, "error": f"操作 {action} 未实现"}
            
        except Exception as e:
            logger.error(f"Llama.cpp 执行失败: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
    
    def _start_server(self, context: Dict) -> Dict[str, Any]:
        """启动 Llama.cpp 服务器，带熔断机制"""
        if self._server_running:
            return {"success": True, "result": {"message": "服务器已在运行"}}
        
        preferred_model = context.get("model", "qwen2.5-1.5b")
        
        fallback_results = []
        
        for tier in self._fallback_tiers:
            model_name = self._find_model_by_tier(tier)
            if not model_name:
                continue
            
            model_info = LLAMA_MODELS.get(model_name)
            model_file = self._find_model_file(model_name)
            
            if not model_file:
                continue
            
            result = self._try_start_with_model(model_name, model_info, model_file, context)
            
            if result.get("success"):
                self._current_model = model_name
                self._current_tier = tier
                result["result"]["fallback_tier"] = tier
                
                if tier != "HIGH":
                    result["result"]["fallback_reason"] = f"降级到 {tier} 模型"
                
                return result
            
            fallback_results.append({
                "tier": tier,
                "model": model_name,
                "error": result.get("error"),
            })
        
        return {
            "success": False,
            "error": "所有模型启动失败，熔断机制已触发",
            "fallback_attempts": fallback_results,
            "alternatives": self._get_ollama_alternatives(),
        }
    
    def _find_model_by_tier(self, tier: str) -> Optional[str]:
        """根据优先级找到可用模型"""
        for model_name, info in LLAMA_MODELS.items():
            if info.get("tier") == tier:
                return model_name
        return None
    
    def _find_model_file(self, model_name: str) -> Optional[str]:
        """查找模型文件"""
        try:
            if not os.path.exists(LLAMA_MODELS_PATH):
                return None
            
            for f in os.listdir(LLAMA_MODELS_PATH):
                if model_name.lower() in f.lower() and f.endswith(".gguf"):
                    return f
            
            model_file = self._extract_from_ollama(model_name)
            if model_file:
                return model_file
            
            return None
        except Exception:
            return None
    
    def _extract_from_ollama(self, model_name: str) -> Optional[str]:
        """从 Ollama 提取 GGUF 模型"""
        model_info = LLAMA_MODELS.get(model_name)
        if not model_info:
            return None
        
        ollama_model = model_info.get("ollama_model")
        if not ollama_model:
            return None
        
        try:
            import subprocess as sp
            
            result = sp.run(
                ["ollama", "show", ollama_model, "--path"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode == 0:
                ollama_path = result.stdout.strip()
                gguf_path = os.path.join(ollama_path, "gguf/model-f16.gguf")
                
                if os.path.exists(gguf_path):
                    dest_path = os.path.join(LLAMA_MODELS_PATH, f"{model_name}-q4_k_m.gguf")
                    os.makedirs(LLAMA_MODELS_PATH, exist_ok=True)
                    
                    if not os.path.exists(dest_path):
                        import shutil
                        shutil.copy2(gguf_path, dest_path)
                        logger.info(f"从 Ollama 复制模型: {gguf_path} -> {dest_path}")
                    
                    return f"{model_name}-q4_k_m.gguf"
            
            return None
        except Exception as e:
            logger.warning(f"从 Ollama 提取模型失败 {model_name}: {e}")
            return None
    
    def _try_start_with_model(self, model_name: str, model_info: Dict, model_file: str, context: Dict) -> Dict[str, Any]:
        """尝试用指定模型启动服务器"""
        try:
            model_path = os.path.join(LLAMA_MODELS_PATH, model_file)
            context_window = context.get("context_window", model_info.get("context_window", 2048))
            num_threads = context.get("num_threads", 4)
            
            cmd = [
                os.path.join(LLAMA_CPP_PATH, "llama-server.exe"),
                "-m", model_path,
                "-c", str(context_window),
                "--host", "0.0.0.0",
                "--port", str(LLAMA_SERVER_PORT),
                "-t", str(num_threads),
                "-ngl", "0",
            ]
            
            logger.info(f"尝试启动 Llama.cpp [{model_info.get('tier')}]: {model_name}")
            
            self._server_process = subprocess.Popen(
                cmd,
                cwd=LLAMA_CPP_PATH,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            
            time.sleep(8)
            
            try:
                resp = requests.get(f"{self._api_base_url}/health", timeout=5)
                if resp.status_code == 200:
                    self._server_running = True
                    return {
                        "success": True,
                        "result": {
                            "message": "Llama.cpp 服务器启动成功",
                            "model": model_name,
                            "model_name": model_info.get("name"),
                            "tier": model_info.get("tier"),
                            "size": model_info.get("size"),
                            "context_window": context_window,
                            "port": LLAMA_SERVER_PORT,
                        },
                    }
            except requests.ConnectionError as e:
                logger.debug("Llama.cpp 服务器尚未就绪，重试中: %s", e)
            
            self._server_process.terminate()
            self._server_process.wait(timeout=5)
            
            return {"success": False, "error": "服务器启动超时"}
            
        except Exception as e:
            return {"success": False, "error": f"启动失败: {e}"}
    
    def _get_ollama_alternatives(self) -> List[Dict[str, str]]:
        """获取 Ollama 可用模型作为备选"""
        alternatives = []
        try:
            import subprocess as sp
            
            result = sp.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        alternatives.append({
                            "model": parts[0],
                            "size": parts[2],
                            "note": "可用的 Ollama 模型",
                        })
        except Exception as e:
            logger.warning("获取 Ollama 模型列表失败: %s", e)

        return alternatives

    def _stop_server(self) -> Dict[str, Any]:
        """停止 Llama.cpp 服务器"""
        if not self._server_running:
            return {"success": True, "result": {"message": "服务器未运行"}}
        
        try:
            self._server_process.terminate()
            self._server_process.wait(timeout=5)
            self._server_running = False
            return {"success": True, "result": {"message": "服务器已停止"}}
        except Exception as e:
            return {"success": False, "error": f"停止失败: {e}"}
    
    def _list_models(self) -> Dict[str, Any]:
        """列出可用模型"""
        models = []
        if os.path.exists(LLAMA_MODELS_PATH):
            for f in os.listdir(LLAMA_MODELS_PATH):
                if f.endswith(".gguf"):
                    size = os.path.getsize(os.path.join(LLAMA_MODELS_PATH, f)) / (1024 * 1024)
                    models.append({
                        "name": f,
                        "size_mb": round(size, 1),
                    })
        
        return {
            "success": True,
            "result": {
                "available_models": models,
                "supported_models": LLAMA_MODELS,
                "models_path": LLAMA_MODELS_PATH,
            },
        }
    
    def _chat(self, context: Dict) -> Dict[str, Any]:
        """聊天对话"""
        if not self._server_running:
            return {"success": False, "error": "服务器未运行，请先启动"}
        
        prompt = context.get("prompt", "")
        max_tokens = context.get("max_tokens", 200)
        temperature = context.get("temperature", 0.7)
        
        if not prompt:
            return {"success": False, "error": "请提供提示文本"}
        
        try:
            resp = requests.post(
                f"{self._api_base_url}/v1/chat/completions",
                json={
                    "model": "local",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            
            return {
                "success": True,
                "result": {
                    "response": content,
                    "prompt": prompt,
                },
            }
        
        except requests.ConnectionError:
            return {"success": False, "error": "无法连接服务器"}
        except Exception as e:
            return {"success": False, "error": f"请求失败: {e}"}
    
    def _generate(self, context: Dict) -> Dict[str, Any]:
        """文本生成"""
        if not self._server_running:
            return {"success": False, "error": "服务器未运行，请先启动"}
        
        prompt = context.get("prompt", "")
        max_tokens = context.get("max_tokens", 500)
        temperature = context.get("temperature", 0.7)
        
        if not prompt:
            return {"success": False, "error": "请提供提示文本"}
        
        try:
            resp = requests.post(
                f"{self._api_base_url}/v1/completions",
                json={
                    "model": "local",
                    "prompt": prompt,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": False,
                },
                timeout=120,
            )
            resp.raise_for_status()
            
            data = resp.json()
            content = data["choices"][0]["text"]
            
            return {
                "success": True,
                "result": {
                    "response": content,
                    "prompt": prompt,
                },
            }
        
        except Exception as e:
            return {"success": False, "error": f"请求失败: {e}"}
    
    def _embeddings(self, context: Dict) -> Dict[str, Any]:
        """获取向量嵌入"""
        if not self._server_running:
            return {"success": False, "error": "服务器未运行，请先启动"}
        
        text = context.get("text", "")
        
        if not text:
            return {"success": False, "error": "请提供文本"}
        
        try:
            resp = requests.post(
                f"{self._api_base_url}/v1/embeddings",
                json={
                    "model": "local",
                    "input": text,
                },
                timeout=60,
            )
            resp.raise_for_status()
            
            data = resp.json()
            embedding = data["data"][0]["embedding"]
            
            return {
                "success": True,
                "result": {
                    "embedding": embedding,
                    "text": text,
                    "dimensions": len(embedding),
                },
            }
        
        except Exception as e:
            return {"success": False, "error": f"请求失败: {e}"}
    
    def _execute_fallback(self, action: str, context: Dict) -> Dict[str, Any]:
        """降级模式执行"""
        try:
            if action == "start_server":
                return {
                    "success": True,
                    "result": {
                        "mode": "fallback",
                        "message": "Llama.cpp 未安装，使用模拟模式",
                        "instructions": self._get_install_instructions(),
                    },
                }
            
            elif action == "list_models":
                return {
                    "success": True,
                    "result": {
                        "mode": "fallback",
                        "supported_models": LLAMA_MODELS,
                        "instructions": self._get_install_instructions(),
                    },
                }
            
            elif action in ["chat", "generate"]:
                prompt = context.get("prompt", "")
                return {
                    "success": True,
                    "result": {
                        "mode": "fallback",
                        "prompt": prompt,
                        "response": "[模拟响应] 基于本地模型生成的回复（需要安装 Llama.cpp）",
                        "instructions": self._get_install_instructions(),
                    },
                }
            
            return {"success": False, "error": f"操作 {action} 在降级模式下不可用"}
            
        except Exception as e:
            logger.error(f"降级模式执行失败: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_install_instructions(self) -> List[str]:
        """获取安装说明"""
        return [
            "1. 下载 Llama.cpp Windows 预编译包",
            f"2. 解压到 {LLAMA_CPP_PATH}",
            f"3. 下载 GGUF 模型到 {LLAMA_MODELS_PATH}\\",
            "4. 启动: .\\llama-server.exe -m models\\xxx.gguf -c 2048 --host 0.0.0.0 --port 8080",
        ]
    
    def _get_model_download_instructions(self, model_name: str) -> List[str]:
        """获取模型下载说明"""
        urls = {
            "qwen2.5-1.5b": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF",
            "qwen2.5-3b": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF",
            "llama-3.2-3b": "https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct-GGUF",
            "deepseek-chat": "https://huggingface.co/deepseek-ai/DeepSeek-Chat-GGUF",
        }
        
        url = urls.get(model_name, "https://huggingface.co/models?search=gguf")
        
        return [
            f"1. 下载模型: {url}",
            "2. 选择 Q4_K_M 量化版本（8GB内存最优）",
            f"3. 下载 .gguf 文件到 {LLAMA_MODELS_PATH}",
        ]
    
    def is_available(self) -> bool:
        """检查 Llama.cpp 是否可用"""
        return self._llama_cpp_available


def get_llama_cpp_skill() -> LlamaCppSkill:
    """获取或创建 Llama.cpp 技能实例"""
    return LlamaCppSkill()


def register_llama_cpp_skill(registry=None):
    """注册 Llama.cpp 技能到技能注册表"""
    if registry is None:
        from .base import SkillRegistry
        registry = SkillRegistry()
    
    skill = LlamaCppSkill()
    registry.register(skill)
    logger.info("Llama.cpp 技能已注册")
    return skill