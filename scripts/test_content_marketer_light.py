"""轻量级验证：ContentMarketerAdapter 直接测试。

不走完整 build_fabric_hub（太慢），直接实例化适配器并注入 route_fn。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.video_maker_adapter import VideoMakerAdapter
from core.fabric.adapters.content_marketer_adapter import ContentMarketerAdapter
from core.fabric.adapters.search_adapter import SearchAdapter
from core.fabric.adapters import LiteLLMAdapter


def build_lightweight_hub():
    """构建一个轻量级的路由函数，只注册需要的几个适配器。"""
    adapters = {}
    
    # 视频生成
    try:
        vma = VideoMakerAdapter()
        if vma.health():
            adapters["video-maker"] = vma
            print(f"  ✅ video-maker 注册成功")
    except Exception as e:
        print(f"  ⚠️ video-maker 注册失败: {e}")
    
    # 搜索
    try:
        sa = SearchAdapter()
        adapters["web-search"] = sa
        print(f"  ✅ web-search 注册成功")
    except Exception as e:
        print(f"  ⚠️ web-search 注册失败: {e}")
    
    # LLM
    try:
        from core.fabric.adapters.litellm_adapter import LiteLLMAdapter
        llm = LiteLLMAdapter()
        if llm.health():
            adapters["litellm"] = llm
            print(f"  ✅ litellm 注册成功")
        else:
            print(f"  ⚠️ litellm 不健康，降级使用模板")
    except Exception as e:
        print(f"  ⚠️ litellm 不可用: {e}")
    
    def route_fn(capability, payload):
        """简单的路由函数。"""
        cap_str = capability.value if hasattr(capability, "value") else capability
        
        # 按能力匹配
        cap_map = {
            "media.video": ["video-maker"],
            "web.search": ["web-search"],
            "inference.llm": ["litellm"],
        }
        
        candidates = cap_map.get(cap_str, [])
        for eid in candidates:
            if eid in adapters and adapters[eid].health():
                adapter = adapters[eid]
                from core.fabric.adapter import InvokeRequest
                req = InvokeRequest(capability=cap_str, payload=payload)
                return adapter.invoke(req)
        
        # 找不到就返回空
        from core.fabric.adapter import InvokeResult
        return InvokeResult(ok=False, error=f"无可用提供者: {cap_str}")
    
    return route_fn, adapters


def main():
    print("=" * 70)
    print("AOS 内容飞轮验证：Content Marketer（轻量模式）")
    print("=" * 70)

    print("\n[1/4] 注册核心适配器...")
    route_fn, adapters = build_lightweight_hub()
    print(f"  共注册 {len(adapters)} 个适配器")

    print("\n[2/4] 初始化 ContentMarketerAdapter...")
    cm = ContentMarketerAdapter(route_fn=route_fn)
    print(f"  health: {cm.health()}")
    print(f"  capabilities: {[c.value if hasattr(c, 'value') else str(c) for c in cm.advertise_capabilities()]}")

    if not cm.health():
        print("❌ ContentMarketer 不健康")
        return 1

    topic = "AOS 智能体操作系统"
    print(f"\n[3/4] 生产营销视频")
    print(f"  主题: {topic}")
    print(f"  风格: douyin（竖屏）")
    
    result = cm.produce(topic, style="douyin", duration=60)

    print("\n[4/4] 结果:")
    if result.ok:
        print(f"✅ 生产成功!")
        print(f"  任务ID: {result.task_id}")
        print(f"  执行阶段: {result.stages}")
        print(f"  素材数: {len(result.materials)}")
        print(f"  视频时长: {result.video_duration:.2f} 秒")
        print(f"  视频路径: {result.video_path}")
        print(f"\n  脚本内容:")
        for i, line in enumerate(result.script.split("\n"), 1):
            if line.strip():
                print(f"    {i}. {line.strip()[:60]}")

        if result.video_path and os.path.exists(result.video_path):
            size_mb = os.path.getsize(result.video_path) / (1024 * 1024)
            print(f"\n  文件大小: {size_mb:.2f} MB")
    else:
        print(f"❌ 生产失败: {result.error}")
        return 1

    print("\n" + "=" * 70)
    print("🎉 内容营销智能体 MVP 验证通过！")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
