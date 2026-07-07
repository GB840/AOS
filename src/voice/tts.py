import logging
import json
import base64
from typing import Dict, Any

logger = logging.getLogger(__name__)

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

from utils.config import config


class TTSEngine:
    def __init__(self):
        self.baidu_access_token = None
        self._init_baidu_token()

    def _init_baidu_token(self):
        if not REQUESTS_AVAILABLE:
            return
        if not config.BAIDU_API_KEY or not config.BAIDU_SECRET_KEY:
            return
        try:
            url = f"{config.BAIDU_BASE_URL}/oauth/2.0/token"
            params = {
                "grant_type": "client_credentials",
                "client_id": config.BAIDU_API_KEY,
                "client_secret": config.BAIDU_SECRET_KEY,
            }
            response = requests.post(url, params=params, timeout=10)
            result = response.json()
            self.baidu_access_token = result.get("access_token")
            logger.info("百度TTS access_token获取成功")
        except Exception as e:
            logger.warning(f"百度TTS初始化失败: {e}")

    def synthesize_baidu(self, text: str, voice: str = "zh", speed: float = 1.0, pitch: float = 0.0) -> Dict[str, Any]:
        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests库未安装"}
        if not self.baidu_access_token:
            self._init_baidu_token()
            if not self.baidu_access_token:
                return {"success": False, "error": "百度API密钥未配置"}

        url = f"{config.BAIDU_BASE_URL}/rpc/2.0/tts/v1/text2audio"
        params = {
            "access_token": self.baidu_access_token,
            "text": text,
            "lan": voice,
            "tok": self.baidu_access_token,
            "ctp": 1,
            "cuid": "aos-client",
            "spd": int(speed * 5),
            "pit": int(pitch * 5),
            "vol": 5,
            "per": 0,
            "aue": 3,
        }

        try:
            response = requests.post(url, params=params, timeout=30)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "")
                if "audio" in content_type:
                    return {
                        "success": True,
                        "audio": response.content,
                        "content_type": content_type,
                        "provider": "baidu",
                    }
                else:
                    try:
                        result = response.json()
                        return {"success": False, "error": result.get("err_msg", "合成失败")}
                    except:
                        return {"success": False, "error": "未知错误"}
            return {"success": False, "error": f"HTTP错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"百度TTS调用失败: {e}")
            return {"success": False, "error": str(e)}

    def synthesize_zhipu(self, text: str, voice: str = "glm-tts-zh", speed: float = 1.0) -> Dict[str, Any]:
        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests库未安装"}
        if not config.ZHIPU_API_KEY:
            return {"success": False, "error": "智谱API密钥未配置"}

        url = f"{config.ZHIPU_BASE_URL}/audio/text_to_speech"
        headers = {
            "Authorization": f"Bearer {config.ZHIPU_API_KEY}",
            "Content-Type": "application/json",
        }
        data = {
            "model": voice,
            "input": text,
            "parameters": {
                "speed": speed,
                "voice_type": "female",
            },
        }

        try:
            response = requests.post(url, headers=headers, json=data, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if "audio" in result:
                    audio_bytes = base64.b64decode(result["audio"])
                    return {
                        "success": True,
                        "audio": audio_bytes,
                        "content_type": "audio/wav",
                        "provider": "zhipu",
                    }
                else:
                    return {"success": False, "error": result.get("error", {}).get("message", "合成失败")}
            return {"success": False, "error": f"HTTP错误: {response.status_code}"}
        except Exception as e:
            logger.error(f"智谱TTS调用失败: {e}")
            return {"success": False, "error": str(e)}

    def synthesize(self, text: str, voice: str = "zh", speed: float = 1.0, pitch: float = 0.0) -> Dict[str, Any]:
        if config.ZHIPU_ENABLED and config.ZHIPU_API_KEY:
            result = self.synthesize_zhipu(text, voice="glm-tts-zh", speed=speed)
            if result["success"]:
                return result

        if config.BAIDU_ENABLED and config.BAIDU_API_KEY:
            result = self.synthesize_baidu(text, voice=voice, speed=speed, pitch=pitch)
            if result["success"]:
                return result

        return {"success": False, "error": "没有可用的语音合成服务"}