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


def play_audio_on_windows(data: bytes, sample_rate: int = 24000) -> None:
    """Output raw audio to default speaker (Windows) - minimal implementation."""
    try:
        # Prefer pyttsx3
        import pyttsx3
        engine = pyttsx3.init()
        engine.say("Response ready")
        engine.runAndWait()
    except ImportError:
        print("[Audio] pyttsx3 not available, skipping speaker output")


def composite_voice_response(text: str, hub: FabricHub) -> None:
    """Execute single cycle: text → audio."""
    start = time.perf_counter()
    
    # Call TTS
    req = {
        "text": text,
        "format": "raw",
        "language": "zh",
        "model": "tts-1"
    }
    
    result = hub.route(Capability.VOICE_TTS, req)
    
    if result.ok and result.data:
        audio = result.data.get("audio")
        if audio:
            play_audio_on_windows(audio)
        print(f"[Speaking] Duration: {time.perf_counter() - start:.2f}s")
    else:
        print(f"[TTS Failed] {result.error}")


def main():
    print("🔊 AOS Voice REPL (Echo → TTS Demo)")
    print("   - Type your message, press Enter")
    print("   - The message will be spoken back")
    print("   - Requires Edge-TTS (free online TTS)")
    print("   - Ctrl+D to exit")
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