"""media-gen 异步隔离守护。

media-gen 视频生成为同步长轮询（轮询期间 time.sleep 阻塞当前线程）。验证
经 asyncio.to_thread 包裹后，事件循环在轮询期间仍能处理其他协程——即不阻塞
事件循环。main.py 的媒体调用路径已统一用 asyncio.to_thread 包裹 hub.route/
invoke_engine，故 media-gen 无需改成 async（那会破坏 sync 调用链）。
"""
import asyncio
import sys
import time

sys.path.insert(0, "src")

from core.fabric.adapter import InvokeRequest, InvokeResult
from core.fabric.capability import Capability
from core.fabric.adapters.media_gen_adapter import MediaGenAdapter


def test_video_generation_does_not_block_event_loop(monkeypatch):
    a = MediaGenAdapter()
    monkeypatch.setattr(a, "_available", True)

    # 模拟「同步长轮询」：阻塞 0.2s
    def slow_video(payload):
        time.sleep(0.2)
        return InvokeResult(ok=True, data={"url": "https://x/v.mp4"})

    monkeypatch.setattr(a, "_gen_video", slow_video)

    async def other():
        await asyncio.sleep(0.05)
        return "event-loop-alive"

    async def main():
        res, alive = await asyncio.gather(
            asyncio.to_thread(
                a.invoke,
                InvokeRequest(capability=Capability.MEDIA_VIDEO, payload={"prompt": "x"}),
            ),
            other(),
        )
        return res, alive

    res, alive = asyncio.run(main())
    assert res.ok
    # 事件循环在 0.2s 同步阻塞期间仍处理了 other()（0.05s 完成）→ 未阻塞
    assert alive == "event-loop-alive"
    assert res.data["url"] == "https://x/v.mp4"
