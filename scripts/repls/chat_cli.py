#!/usr/bin/env python3
"""
CLI REPL with voice: staple together LiteLLM (text-in) → TTS (audio-out)。

Usage:
  python scripts/repls/chat_cli.py

Flow:
  - Input from stdin (type or paste)
  - Route to LiteLLM capability (inference.llm)
  - Convert response to speech (voice.tts)
  - Output to speaker

这是P0A链最小闭环验证 -- 不涉及任何底层改动。
"""

import sys
import os
import time

# Add src to path for fabric imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from kernel.plugins.fabric_hub import FabricHub
from core.fabric.capability import Capability


def local_tts_fallback(text: str) -> bool:
    """本地 TTS 兜底 (pyttsx3) - 零网络、零成本、Windows 友好"""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        # 中文适配
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'Chinese' in voice.name or 'ZH' in voice.id.upper():
                engine.setProperty('voice', voice.id)
                break
        engine.say(text)
        engine.runAndWait()
        return True
    except Exception as e:
        print(f"[本地TTS失败] {e}")
        return False


def composite_voice_response(text: str, hub: FabricHub) -> None:
    """Execute single cycle: text → audio."""
    start = time.perf_counter()
    
    # 优先经 FabricHub TTS 路由 (在线/高品质)
    # 没有 live 引擎时诚实降级到本地
    req = {
        "text": text,
        "format": "raw",
        "language": "zh",
        "model": "tts-1"
    }
    
    result = hub.route(Capability.VOICE_TTS, req)
    
    if result.ok and result.data and result.data.get("audio"):
        # TODO: 如果有 audio 数据时的处理
        print(f"[在线TTS] Duration: {time.perf_counter() - start:.2f}s")
    else:
        # 降级到本地引擎
        print(f"[降级本地TTS] {result.error if result.error else '无在线引擎'}")
        if local_tts_fallback(text):
            print(f"[本地TTS] Duration: {time.perf_counter() - start:.2f}s")
        else:
            print(f"[TTS完全失败]")


def main():
    print("🔊 AOS Voice REPL (本地 TTS 闭环)")
    print("   - 输入文本，立即本地语音播报")
    print("   - 优先在线 TTS，无网降级 pyttsx3")
    print("   - Ctrl+D 或 Ctrl+C 退出")
    print("=" * 50)
    
    try:
        hub = FabricHub()
        tts_engine = hub.resolve_engine(Capability.VOICE_TTS)
        
        if not tts_engine:
            print("❌ No TTS engine available")
            return 1
            
        print(f"✅ TTS engine: {tts_engine}")
        print(f"   Available adapters: {len(hub._registry._adapters)}")
        
    except Exception as e:
        print(f"❌ Failed to load FabricHub: {e}")
        return 1
        
    while True:
        try:
            # Read from stdin
            line = input(">> ")
            if not line.strip():
                continue
                
            start = time.perf_counter()
            
            # For the demo: Echo input back (future: LiteLLM/other LLM)
            content = f"您说的是：{line.strip()}"
            print(f"🤖 {content}")
            print(f"\n[Response Latency] {time.perf_counter() - start:.2f}s")
            
            # Convert to speech
            start_tts = time.perf_counter()
            composite_voice_response(content, hub)
            print(f"[TTS Latency] {time.perf_counter() - start_tts:.2f}s")
            
        except EOFError:
            print("\nGoodbye!")
            break
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
    
    return 0


if __name__ == "__main__":
    sys.exit(main())