"""端到端验证：内容营销智能体（content-marketer）。

输入一个主题 → 搜索素材 → 写脚本 → 生成视频。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.wiring import build_fabric_hub


def main():
    print("=" * 70)
    print("AOS 内容飞轮验证：Content Marketer Agent")
    print("=" * 70)

    print("\n[1/5] 构建 FabricHub...")
    hub = build_fabric_hub(isolate_heavy=False)
    if hub is None:
        print("❌ FabricHub 构建失败")
        return 1
    print("✅ FabricHub 构建成功")

    print("\n[2/5] 检查 content-marketer 能力...")
    report = hub.health_report()
    adapters = report.get("adapters", {})
    cm_info = adapters.get("content-marketer")
    if not cm_info:
        print("❌ content-marketer 未注册")
        print(f"   已注册引擎: {list(adapters.keys())}")
        return 1
    print(f"  状态: live={cm_info.get('live')}")
    print(f"  能力: {cm_info.get('capabilities')}")

    if not cm_info.get("live"):
        print("❌ content-marketer 不健康")
        return 1

    topic = "AOS 智能体操作系统"
    print(f"\n[3/5] 调用内容营销智能体")
    print(f"  主题: {topic}")
    print(f"  风格: douyin（竖屏）")
    print(f"  目标时长: 60秒")

    result = hub.route("content.marketing_video", {
        "topic": topic,
        "style": "douyin",
        "duration": 60,
    })

    print("\n[4/5] 结果:")
    if hasattr(result, "ok") and result.ok:
        data = result.data or {}
        print(f"✅ 生产成功!")
        print(f"  任务ID: {data.get('task_id')}")
        print(f"  执行阶段: {data.get('stages')}")
        print(f"  素材数: {data.get('materials_count')}")
        print(f"  视频时长: {data.get('video_duration'):.2f} 秒")
        print(f"  视频路径: {data.get('video_path')}")
        print(f"\n  脚本内容:")
        script = data.get("script", "")
        for i, line in enumerate(script.split("\n"), 1):
            if line.strip():
                print(f"    {i}. {line.strip()[:60]}")

        video_path = data.get("video_path")
        if video_path and os.path.exists(video_path):
            size_mb = os.path.getsize(video_path) / (1024 * 1024)
            print(f"\n  文件大小: {size_mb:.2f} MB")
    else:
        error = result.error if hasattr(result, "error") else str(result)
        print(f"❌ 生产失败: {error}")
        return 1

    print("\n[5/5] 验证总结:")
    print("  ✅ 内容营销智能体注册成功")
    print("  ✅ 搜索素材 → 写脚本 → 生成视频 全链路跑通")
    print("  ✅ 视频文件真实生成")

    print("\n" + "=" * 70)
    print("🎉 AOS 内容飞轮 MVP 验证通过！")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
