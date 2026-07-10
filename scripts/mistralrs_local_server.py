#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mistralrs_local_server.py —— 用 mistralrs Python SDK (Runner) 把本地模型包成
OpenAI 兼容端点 (/v1/chat/completions, /v1/models)。

这就是 mistralrs 引擎本体（与 `mistralrs serve` 同一引擎），只是因为沙箱无法
下载 CLI 二进制，改用已安装的 Python SDK 直接起等效服务。
三种模型分别起独立进程 (各占一个端口)，AOS 路由器按任务类型选端口。

用法:
  python scripts/mistralrs_local_server.py \
      --port 1235 --kind plain \
      --model-path "D:/models/Qwen2.5-Coder-3B-Instruct" --isq Q4K \
      --model-name qwen2.5-coder-3b

  python scripts/mistralrs_local_server.py \
      --port 1234 --kind gguf \
      --model-path "C:/Users/Administrator/MiniCPM5-1B-GGUF" \
      --gguf-file MiniCPM5-1B-Q4_K_M.gguf --model-name minicpm5-1b
"""
import argparse
import json
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import mistralrs
from mistralrs import Runner, Which, ChatCompletionRequest


def build_runner(args):
    if args.kind == "gguf":
        which = Which.GGUF(
            tok_model_id=args.model_path,
            quantized_model_id=args.model_path,
            quantized_filename=args.gguf_file,
        )
        in_situ = None
    else:  # plain (safetensors)
        which = Which.Plain(model_id=args.model_path)
        in_situ = args.isq
    print(f"[load] building Runner for {args.model_name} (kind={args.kind}, isq={in_situ}) ...", flush=True)
    runner = Runner(which=which, in_situ_quant=in_situ)
    print(f"[load] {args.model_name} ready on :{args.port}", flush=True)
    return runner


def to_openai(response, model_name):
    # response: mistralrs ChatCompletionResponse-like 对象
    content = ""
    try:
        content = response.choices[0].message.content or ""
    except Exception:
        content = str(response)
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex[:12],
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


class Handler(BaseHTTPRequestHandler):
    runner = None
    model_name = None

    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/") in ("/v1/models", "/models"):
            self._send(200, {"object": "list", "data": [{"id": Handler.model_name, "object": "model"}]})
        elif self.path.rstrip("/") in ("/", "/health", "/v1/health"):
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception as e:
            self._send(400, {"error": f"bad json: {e}"})
            return

        if self.path.rstrip("/") in ("/v1/chat/completions", "/chat/completions"):
            messages = payload.get("messages", [])
            req = ChatCompletionRequest(
                model=payload.get("model", Handler.model_name),
                messages=messages,
                temperature=payload.get("temperature", 0.7),
                max_tokens=payload.get("max_tokens", 2048),
                top_p=payload.get("top_p"),
                stream=False,
            )
            try:
                resp = Handler.runner.send_chat_completion_request(req)
                self._send(200, to_openai(resp, Handler.model_name))
            except Exception as e:
                self._send(500, {"error": str(e)})
            return

        self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass  # 静默


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--kind", choices=["plain", "gguf"], required=True)
    ap.add_argument("--model-path", required=True)
    ap.add_argument("--gguf-file", default=None)
    ap.add_argument("--isq", default=None, help="ISQ 量化等级, 如 Q4K (plain 用)")
    ap.add_argument("--model-name", default="local-model")
    args = ap.parse_args()

    Handler.runner = build_runner(args)
    Handler.model_name = args.model_name

    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"[serve] OpenAI-compatible API on http://localhost:{args.port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
