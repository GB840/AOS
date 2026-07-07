import logging
import json
import base64
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

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

from utils.config import config


class ASREngine:
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
            logger.info("百度ASR access_token获取成功")
        except Exception as e:
            logger.warning(f"百度ASR初始化失败: {e}")

    def recognize_baidu(self, audio_bytes: bytes, format: str = "wav") -> Dict[str, Any]:
        if not REQUESTS_AVAILABLE:
            return {"success": False, "error": "requests库未安装"}
        if not self.baidu_access_token:
            self._init_baidu_token()
            if not self.baidu_access_token:
                return {"success": False, "error": "百度API密钥未配置"}

        url = f"{config.BAIDU_BASE_URL}/rpc/2.0/audio/v1/asr"
        params = {
            "access_token": self.baidu_access_token,
            "format": format,
            "rate": 16000,
            "channel": 1,
            "cuid": "aos-client",
            "len": len(audio_bytes),
            "speech": base64.b64encode(audio_bytes).decode(),
        }

        try:
            response = requests.post(url, json=params, timeout=30)
            result = response.json()
            if result.get("err_no") == 0:
                return {
                    "success": True,
                    "text": "".join(result.get("result", [])),
                    "provider": "baidu",
                }
            else:
                return {"success": False, "error": result.get("err_msg", "识别失败")}
        except Exception as e:
            logger.error(f"百度ASR调用失败: {e}")
            return {"success": False, "error": str(e)}

    def recognize_xfyun(self, audio_bytes: bytes) -> Dict[str, Any]:
        if not WEBSOCKET_AVAILABLE:
            return {"success": False, "error": "websocket-client库未安装"}
        if not config.XFYUN_APP_ID or not config.XFYUN_API_KEY or not config.XFYUN_API_SECRET:
            return {"success": False, "error": "讯飞API密钥未配置"}

        import hashlib
        import hmac
        from datetime import datetime
        from urllib.parse import urlparse, urlencode
        import queue

        result_queue = queue.Queue()
        answer = {"content": ""}

        app_id = config.XFYUN_APP_ID
        api_key = config.XFYUN_API_KEY
        api_secret = config.XFYUN_API_SECRET

        host = "iat-api.xf-yun.com"
        iat_url = f"wss://{host}/v2/iat"

        parsed = urlparse(iat_url)
        date = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")
        signature_origin = f"host: {host}\ndate: {date}\nGET {parsed.path} HTTP/1.1"
        signature_sha = hmac.new(api_secret.encode(), signature_origin.encode(), digestmod=hashlib.sha256).digest()
        signature = base64.b64encode(signature_sha).decode()
        authorization_origin = f'api_key="{api_key}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature}"'
        authorization = base64.b64encode(authorization_origin.encode()).decode()

        ws_url = f"{iat_url}?{urlencode({'authorization': authorization, 'date': date, 'host': host})}"

        def on_message(ws, message):
            data = json.loads(message)
            code = data.get("header", {}).get("code")
            if code != 0:
                result_queue.put(Exception(f"讯飞ASR错误: {data}"))
                return
            payload = data.get("payload", {})
            if payload.get("result"):
                result = payload["result"]
                if result.get("ws"):
                    for ws_item in result["ws"]:
                        for cw in ws_item["cw"]:
                            answer["content"] += cw.get("w", "")
            if data.get("header", {}).get("status") == 2:
                result_queue.put(answer["content"])
                ws.close()

        def on_error(ws, error):
            result_queue.put(Exception(f"讯飞WebSocket错误: {error}"))

        def on_open(ws):
            def run():
                data = {
                    "header": {"app_id": app_id, "status": 0},
                    "parameter": {
                        "iat": {
                            "language": "zh_cn",
                            "domain": "general",
                            "accent": "mandarin",
                            "sample_rate": 16000,
                            "format": "wav",
                            "bit_rate": 16,
                        },
                        "result": {
                            "encoding": "utf8",
                            "compress": "raw",
                            "format": "json",
                        },
                    },
                    "payload": {"audio": base64.b64encode(audio_bytes).decode()},
                }
                ws.send(json.dumps(data))

            import threading
            threading.Thread(target=run, daemon=True).start()

        ws = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error, on_open=on_open)
        ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
        ws_thread.start()

        try:
            result = result_queue.get(timeout=30)
            if isinstance(result, Exception):
                raise result
            return {"success": True, "text": result, "provider": "xfyun"}
        except queue.Empty:
            return {"success": False, "error": "讯飞ASR超时"}

    def recognize(self, audio_bytes: bytes, format: str = "wav") -> Dict[str, Any]:
        if config.XFYUN_ENABLED and config.XFYUN_API_KEY:
            result = self.recognize_xfyun(audio_bytes)
            if result["success"]:
                return result

        if config.BAIDU_ENABLED and config.BAIDU_API_KEY:
            result = self.recognize_baidu(audio_bytes, format)
            if result["success"]:
                return result

        return {"success": False, "error": "没有可用的语音识别服务"}