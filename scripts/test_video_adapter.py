"""端到端验证：VideoMakerAdapter 集成测试。

直接通过 FabricHub 调用 media.video 能力生成一条短视频。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from kernel.wiring import build_fabric_hub


def main():
    print("=" * 60)
    print("AOS 内容飞轮验证：FabricHub → media.video")
    print("=" * 60)

    print("\n[1/4] 构建 FabricHub...")
    hub = build_fabric_hub(isolate_heavy=False)
    if hub is None:
        print("❌ FabricHub 构建失败")
        return 1

    print(f"✅ FabricHub 构建成功")

    print("\n[2/4] 检查 media.video 能力（health_report）...")
    report = hub.health_report()
    adapters = report.get("adapters", {})
    print(f"  总适配器数: {report.get('total')}")
    print(f"  live 适配器数: {report.get('live')}")
    
    reg_errors = report.get("registration_errors", {})
    if reg_errors:
        print(f"  注册错误数: {len(reg_errors)}")
        for name, err in reg_errors.items():
            print(f"    - {name}: {err[:100]}")
    
    video_engines = {eid: info for eid, info in adapters.items() 
                     if "media.video" in info.get("capabilities", [])}
    print(f"  video 适配器数: {len(video_engines)}")
    for eid, info in video_engines.items():
        print(f"    - {eid} (live={info.get('live')}, isolated={info.get('isolated')})")

    if not video_engines:
        print("❌ 没有可用的 media.video 提供者")
        return 1

    print("\n[3/4] 调用 media.video 生成视频（3段分镜）...")
    script = [
        {"text": "AOS，智能体时代的操作系统。"},
        {"text": "单内核，多芯粒，故障隔离，能力路由。"},
        {"text": "本地优先，零成本可跑，不绑定任何厂商。"},
    ]
    result = hub.route("media.video", {
        "script": script,
        "output_name": "aos_intro_test",
        "size": "1280x720",
    })

    print(f"\n[4/4] 结果:")
    if result.ok:
        data = result.data or {}
        print(f"✅ 生成成功!")
        print(f"  输出文件: {data.get('output')}")
        print(f"  时长: {data.get('duration'):.2f} 秒")
        print(f"  分镜数: {data.get('segments')}")
        print(f"  引擎: {data.get('engine')}")

        output_path = data.get("output")
        if output_path and os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"  文件大小: {size_mb:.2f} MB")
    else:
        print(f"❌ 生成失败: {result.error}")
        return 1

    print("\n" + "=" * 60)
    print("验证通过！")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
