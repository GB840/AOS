"""Agnes AI 真机调用演示（在主机上运行，需 AGNES_API_KEY）。

用法：
  cd D:\AOS
  $env:PYTHONPATH="D:/AOS/src"
  C:/Users/Administrator/AppData/Local/Programs/Python/Python314/python.exe scripts/agnes_demo.py --mode chat
  # --mode image   文生图
  # --mode video   文生视频（异步轮询，可能耗时数十秒）
  # --mode all     文本 + 图像
  # --prompt "..." 自定义提示词
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, "D:/AOS/src")

try:
    from dotenv import load_dotenv
    load_dotenv("D:/AOS/.env")
except Exception:
    pass

from core.fabric.adapters.agnes_adapter import AgnesAdapter


def main() -> int:
    ap = argparse.ArgumentParser(description="Agnes AI 多模态真机演示")
    ap.add_argument("--mode", choices=["chat", "image", "video", "all"], default="chat")
    ap.add_argument("--prompt", default="用一句话介绍什么是 Agent OS。")
    ap.add_argument("--model", default=None, help="覆盖默认模型（如 agnes-image-2.0-flash）")
    args = ap.parse_args()

    if not os.environ.get("AGNES_API_KEY"):
        print("ERROR: AGNES_API_KEY 未配置，请检查 D:/AOS/.env")
        return 2

    a = AgnesAdapter()

    if args.mode in ("chat", "all"):
        r = a.chat(args.prompt, model=args.model)
        print("\n[CHAT] " + (r.data.get("content", "") if r.ok else r.error))

    if args.mode in ("image", "all"):
        r = a.generate_image(args.prompt, model=args.model)
        print("\n[IMAGE] " + (json.dumps(r.data, ensure_ascii=False) if r.ok else r.error))

    if args.mode == "video":
        print("\n[VIDEO] 提交异步任务并轮询结果（最多 180s）...")
        r = a.generate_video(args.prompt, model=args.model)
        print("[VIDEO] " + (json.dumps(r.data, ensure_ascii=False) if r.ok else r.error))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
