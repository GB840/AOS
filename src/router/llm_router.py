import json
import logging
from enum import Enum
from typing import List, Dict, Optional, Any

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

try:
    import websocket
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False
    websocket = None

import threading
import queue

from utils.config import config

logger = logging.getLogger(__name__)


class TaskType(Enum):
    CODING = "coding"
    HIGH_CONCURRENCY = "high_concurrency"
    LONG_CONTEXT = "long_context"
    VOICE = "voice"
    EXPERIMENT = "experiment"
    GENERAL = "general"


class ModelProvider(Enum):
    ZHIPU = "zhipu"
    SILICONFLOW = "siliconflow"
    BAIDU = "baidu"
    XFYUN = "xfyun"
    OLLAMA = "ollama"


class LLMRouter:
    def __init__(self):
        self.providers: Dict[ModelProvider, Dict[str, Any]] = {}
        self.clients: Dict[ModelProvider, Any] = {}
        self.baidu_access_token: Optional[str] = None
        self._init_providers()

    def _init_providers(self):
        if config.ZHIPU_ENABLED and config.ZHIPU_API_KEY and not config.ZHIPU_API_KEY.startswith("your_"):
            if OPENAI_AVAILABLE:
                try:
                    self.providers[ModelProvider.ZHIPU] = {
                        "name": "智谱GLM-4-Flash",
                        "model": config.ZHIPU_MODEL,
                        "enabled": True,
                        "available": True,
                    }
                    self.clients[ModelProvider.ZHIPU] = OpenAI(
                        api_key=config.ZHIPU_API_KEY,
                        base_url=config.ZHIPU_BASE_URL,
                    )
                except Exception as e:
                    logger.warning(f"智谱初始化失败: {e}")
            else:
                logger.warning("openai库未安装，智谱GLM不可用")

        if config.SILICONFLOW_ENABLED and config.SILICONFLOW_API_KEY and not config.SILICONFLOW_API_KEY.startswith("your_"):
            if OPENAI_AVAILABLE:
                try:
                    self.providers[ModelProvider.SILICONFLOW] = {
                        "name": "硅基流动",
                        "model": config.SILICONFLOW_MODEL,
                        "enabled": True,
                        "available": True,
                    }
                    self.clients[ModelProvider.SILICONFLOW] = OpenAI(
                        api_key=config.SILICONFLOW_API_KEY,
                        base_url=config.SILICONFLOW_BASE_URL,
                    )
                except Exception as e:
                    logger.warning(f"硅基流动初始化失败: {e}")
            else:
                logger.warning("openai库未安装，硅基流动不可用")

        if config.BAIDU_ENABLED and config.BAIDU_API_KEY and not config.BAIDU_API_KEY.startswith("your_"):
            if REQUESTS_AVAILABLE:
                try:
                    self.providers[ModelProvider.BAIDU] = {
                        "name": "百度ERNIE",
                        "model": config.BAIDU_MODEL,
                        "enabled": True,
                        "available": True,
                    }
                    self._refresh_baidu_token()
                except Exception as e:
                    logger.warning(f"百度ERNIE初始化失败: {e}")
            else:
                logger.warning("requests库未安装，百度ERNIE不可用")

        if config.XFYUN_ENABLED and config.XFYUN_API_KEY and not config.XFYUN_API_KEY.startswith("your_"):
            if WEBSOCKET_AVAILABLE:
                try:
                    self.providers[ModelProvider.XFYUN] = {
                        "name": "讯飞星火",
                        "model": config.XFYUN_MODEL,
                        "enabled": True,
                        "available": True,
                    }
                except Exception as e:
                    logger.warning(f"讯飞星火初始化失败: {e}")
            else:
                logger.warning("websocket-client库未安装，讯飞星火不可用")

        if config.OLLAMA_ENABLED:
            if OPENAI_AVAILABLE:
                try:
                    self.providers[ModelProvider.OLLAMA] = {
                        "name": "Ollama本地",
                        "model": config.OLLAMA_MODEL,
                        "enabled": True,
                        "available": True,
                    }
                    self.clients[ModelProvider.OLLAMA] = OpenAI(
                        base_url=f"{config.OLLAMA_BASE_URL}/v1",
                        api_key="ollama",
                    )
                except Exception as e:
                    logger.warning(f"Ollama初始化失败: {e}")
            else:
                logger.warning("openai库未安装，Ollama不可用")

        if not self.providers:
            logger.warning("没有可用的LLM提供商，请安装相应依赖或配置API密钥")
        else:
            logger.info(f"已初始化 {len(self.providers)} 个LLM提供商")

    def _refresh_baidu_token(self):
        if not REQUESTS_AVAILABLE:
            return
        try:
            if config.BAIDU_API_KEY.startswith("bce-v3/"):
                self.baidu_access_token = config.BAIDU_API_KEY
                logger.info("百度API使用新格式密钥，直接使用Bearer认证")
            else:
                url = f"{config.BAIDU_BASE_URL}/oauth/2.0/token"
                params = {
                    "grant_type": "client_credentials",
                    "client_id": config.BAIDU_API_KEY,
                    "client_secret": config.BAIDU_SECRET_KEY,
                }
                response = requests.post(url, params=params, timeout=10)
                result = response.json()
                self.baidu_access_token = result.get("access_token")
                logger.info("百度access_token刷新成功")
        except Exception as e:
            logger.warning(f"百度access_token刷新失败: {e}")
            if ModelProvider.BAIDU in self.providers:
                self.providers[ModelProvider.BAIDU]["available"] = False

    def _get_provider_priority(self, task_type: TaskType) -> List[ModelProvider]:
        priority_map = {
            TaskType.CODING: [config.ROUTER_CODING_PRIMARY, config.ROUTER_FALLBACK],
            TaskType.HIGH_CONCURRENCY: [config.ROUTER_HIGH_CONCURRENCY_PRIMARY, config.ROUTER_FALLBACK],
            TaskType.LONG_CONTEXT: [config.ROUTER_LONG_CONTEXT_PRIMARY, config.ROUTER_FALLBACK],
            TaskType.VOICE: [config.ROUTER_VOICE_PRIMARY, config.ROUTER_FALLBACK],
            TaskType.EXPERIMENT: [config.ROUTER_EXPERIMENT_PRIMARY, config.ROUTER_FALLBACK],
            TaskType.GENERAL: [
                config.ROUTER_CODING_PRIMARY,
                config.ROUTER_HIGH_CONCURRENCY_PRIMARY,
                config.ROUTER_LONG_CONTEXT_PRIMARY,
                config.ROUTER_FALLBACK,
            ],
        }

        priority = []
        seen = set()
        for p in priority_map.get(task_type, priority_map[TaskType.GENERAL]):
            try:
                provider = ModelProvider(p)
            except ValueError:
                continue
            if provider not in seen and provider in self.providers:
                if self.providers[provider].get("available", False):
                    priority.append(provider)
                    seen.add(provider)

        if ModelProvider.OLLAMA not in seen and ModelProvider.OLLAMA in self.providers:
            priority.append(ModelProvider.OLLAMA)

        return priority

    def _call_zhipu(self, messages: List[Dict], **kwargs) -> str:
        if not OPENAI_AVAILABLE:
            raise Exception("openai库未安装")
        client = self.clients[ModelProvider.ZHIPU]
        model = self.providers[ModelProvider.ZHIPU]["model"]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
        return response.choices[0].message.content

    def _call_siliconflow(self, messages: List[Dict], **kwargs) -> str:
        if not OPENAI_AVAILABLE:
            raise Exception("openai库未安装")
        client = self.clients[ModelProvider.SILICONFLOW]
        model = self.providers[ModelProvider.SILICONFLOW]["model"]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
        return response.choices[0].message.content

    def _call_baidu(self, messages: List[Dict], **kwargs) -> str:
        if not REQUESTS_AVAILABLE:
            raise Exception("requests库未安装")
        if not self.baidu_access_token:
            self._refresh_baidu_token()
            if not self.baidu_access_token:
                raise Exception("百度access_token不可用")

        url = f"{config.BAIDU_BASE_URL}/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/{self.providers[ModelProvider.BAIDU]['model']}"
        data = {
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
        }
        
        if config.BAIDU_API_KEY.startswith("bce-v3/"):
            headers = {"Authorization": f"Bearer {self.baidu_access_token}"}
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            params = {"access_token": self.baidu_access_token}
            response = requests.post(url, params=params, json=data, timeout=30)
        
        result = response.json()
        if "error_code" in result:
            if result["error_code"] == 110:
                self._refresh_baidu_token()
                return self._call_baidu(messages, **kwargs)
            raise Exception(f"百度API错误: {result}")
        return result["result"]

    def _call_xfyun(self, messages: List[Dict], **kwargs) -> str:
        if not WEBSOCKET_AVAILABLE:
            raise Exception("websocket-client库未安装")
        import base64
        import hashlib
        import hmac
        from datetime import datetime
        from urllib.parse import urlparse, urlencode

        result_queue = queue.Queue()
        answer = {"content": ""}

        app_id = config.XFYUN_APP_ID
        api_key = config.XFYUN_API_KEY
        api_secret = config.XFYUN_API_SECRET

        model_domains = {
            "lite": "general",
            "v3": "generalv3",
            "v3.5": "generalv3.5",
        }
        domain = model_domains.get(config.XFYUN_MODEL, "general")

        host = "spark-api.xf-yun.com"
        spark_url = f"wss://{host}/v2.1/chat"

        parsed = urlparse(spark_url)
        date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {host}\ndate: {date}\nGET {parsed.path} HTTP/1.1"
        signature_sha = hmac.new(api_secret.encode(), signature_origin.encode(), digestmod=hashlib.sha256).digest()
        signature = base64.b64encode(signature_sha).decode()
        authorization_origin = f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        ws_url = f"{spark_url}?{urlencode({'authorization': authorization, 'date': date, 'host': host})}"

        def on_message(ws, message):
            data = json.loads(message)
            code = data.get("header", {}).get("code")
            if code != 0:
                result_queue.put(Exception(f"讯飞API错误: {data}"))
                return
            choices = data.get("payload", {}).get("choices", {}).get("text", [])
            for c in choices:
                answer["content"] += c.get("content", "")
            if data.get("header", {}).get("status") == 2:
                result_queue.put(answer["content"])
                ws.close()

        def on_error(ws, error):
            result_queue.put(Exception(f"讯飞WebSocket错误: {error}"))

        def on_open(ws):
            def run():
                data = {
                    "header": {"app_id": app_id},
                    "parameter": {
                        "chat": {
                            "domain": domain,
                            "temperature": kwargs.get("temperature", 0.7),
                            "max_tokens": kwargs.get("max_tokens", 2048),
                        }
                    },
                    "payload": {"message": {"text": messages}},
                }
                ws.send(json.dumps(data))

            threading.Thread(target=run, daemon=True).start()

        ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_open=on_open)
        ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
        ws_thread.start()

        try:
            result = result_queue.get(timeout=30)
            if isinstance(result, Exception):
                raise result
            return result
        except queue.Empty:
            raise Exception("讯飞API超时")

    def _call_ollama(self, messages: List[Dict], **kwargs) -> str:
        if not OPENAI_AVAILABLE:
            raise Exception("openai库未安装")
        client = self.clients[ModelProvider.OLLAMA]
        model = self.providers[ModelProvider.OLLAMA]["model"]
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 2048),
        )
        return response.choices[0].message.content

    def _call_provider(self, provider: ModelProvider, messages: List[Dict], **kwargs) -> str:
        call_map = {
            ModelProvider.ZHIPU: self._call_zhipu,
            ModelProvider.SILICONFLOW: self._call_siliconflow,
            ModelProvider.BAIDU: self._call_baidu,
            ModelProvider.XFYUN: self._call_xfyun,
            ModelProvider.OLLAMA: self._call_ollama,
        }

        handler = call_map.get(provider)
        if not handler:
            raise ValueError(f"未知的提供商: {provider}")

        provider_name = self.providers[provider]["name"]
        logger.info(f"使用 {provider_name} 处理请求")
        try:
            result = handler(messages, **kwargs)
            self.providers[provider]["available"] = True
            return result
        except Exception as e:
            logger.warning(f"{provider_name} 调用失败: {e}")
            self.providers[provider]["available"] = False
            raise

    def chat(self, messages: List[Dict], task_type: TaskType = TaskType.GENERAL, **kwargs) -> Dict[str, Any]:
        priority = self._get_provider_priority(task_type)
        if not priority:
            return {
                "content": "系统未配置任何可用的LLM提供商。请安装openai/requests/websocket-client等依赖，并在.env中配置API密钥，或启用Ollama本地模型。",
                "provider": "none",
                "model": "none",
                "task_type": task_type.value,
                "success": False,
            }

        last_error = None
        for provider in priority:
            try:
                content = self._call_provider(provider, messages, **kwargs)
                return {
                    "content": content,
                    "provider": self.providers[provider]["name"],
                    "model": self.providers[provider]["model"],
                    "task_type": task_type.value,
                    "success": True,
                }
            except Exception as e:
                last_error = e
                logger.warning(f"提供商 {provider.value} 不可用，尝试下一个")
                continue

        return {
            "content": f"所有模型均不可用，最后错误: {str(last_error)}",
            "provider": "none",
            "model": "none",
            "task_type": task_type.value,
            "success": False,
        }

    def get_available_providers(self) -> List[Dict[str, Any]]:
        result = []
        for provider, info in self.providers.items():
            result.append(
                {
                    "id": provider.value,
                    "name": info["name"],
                    "model": info["model"],
                    "enabled": info["enabled"],
                    "available": info.get("available", False),
                }
            )
        return result
