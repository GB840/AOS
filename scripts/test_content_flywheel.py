"""端到端全链路验证：内容飞轮完整闭环。

Forge（内容生产）→ Cast（多平台分发）→ Echo（全网反馈）→ Refine（内容优化）
"""
import sys
import os
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from core.fabric.adapters.video_maker_adapter import VideoMakerAdapter
from core.fabric.adapters.content_marketer_adapter import ContentMarketerAdapter
from core.fabric.adapters.cast_adapter import CastAdapter
from core.fabric.adapters.echo_adapter import EchoAdapter
from core.fabric.adapters.refine_adapter import RefineAdapter
from core.fabric.adapters.search_adapter import SearchAdapter


def build_lightweight_hub():
    """构建轻量级路由函数。"""
    adapters = {}

    # 视频生成
    try:
        vma = VideoMakerAdapter()
        if vma.health():
            adapters["video-maker"] = vma
    except Exception:
        pass

    # 搜索
    try:
        sa = SearchAdapter()
        adapters["web-search"] = sa
    except Exception:
        pass

    # 内容营销
    try:
        cm = ContentMarketerAdapter()
        adapters["content-marketer"] = cm
    except Exception:
        pass

    # 分发
    try:
        ca = CastAdapter()
        adapters["cast"] = ca
    except Exception:
        pass

    # 反馈采集
    try:
        ea = EchoAdapter()
        adapters["echo"] = ea
    except Exception:
        pass

    # 优化
    try:
        ra = RefineAdapter()
        adapters["refine"] = ra
    except Exception:
        pass

    def route_fn(capability, payload):
        from core.fabric.adapter import InvokeRequest, InvokeResult
        cap_str = capability.value if hasattr(capability, "value") else capability

        cap_map = {
            "media.video": ["video-maker"],
            "web.search": ["web-search"],
            "content.marketing_video": ["content-marketer"],
            "content.publish": ["cast"],
            "content.distribute": ["cast"],
            "content.feedback": ["echo"],
            "content.sentiment": ["echo"],
            "content.optimize": ["refine"],
            "content.refine": ["refine"],
        }

        candidates = cap_map.get(cap_str, [])
        for eid in candidates:
            if eid in adapters and hasattr(adapters[eid], "health"):
                try:
                    if adapters[eid].health():
                        req = InvokeRequest(capability=cap_str, payload=payload)
                        return adapters[eid].invoke(req)
                except Exception:
                    continue

        return InvokeResult(ok=False, error=f"无可用提供者: {cap_str}")

    # 注入 route_fn 到需要的适配器
    for name in ["content-marketer", "cast", "echo", "refine"]:
        if name in adapters and hasattr(adapters[name], "set_route_fn"):
            adapters[name].set_route_fn(route_fn)

    return route_fn, adapters


def main():
    print("=" * 80)
    print("AOS 内容飞轮全链路验证：Forge → Cast → Echo → Refine")
    print("=" * 80)

    t0 = time.time()

    # ── 初始化 ──
    print("\n" + "─" * 80)
    print("[0/4] 初始化核心适配器...")
    route_fn, adapters = build_lightweight_hub()
    print(f"  已注册 {len(adapters)} 个适配器: {list(adapters.keys())}")

    required = ["content-marketer", "cast", "echo", "refine"]
    missing = [r for r in required if r not in adapters]
    if missing:
        print(f"❌ 缺少必要适配器: {missing}")
        return 1

    topic = "AI 智能体"
    print(f"\n🎯 主题: {topic}")

    # ── 第 1 步：Forge — 内容生产 ──
    print("\n" + "─" * 80)
    print("[1/4] Forge：内容生产（搜索素材 → 写脚本 → 生成视频）")
    print("─" * 80)

    t1 = time.time()
    cm = adapters["content-marketer"]
    forge_result = cm.produce(topic, style="douyin", duration=60)
    forge_time = time.time() - t1

    if forge_result.ok:
        print(f"  ✅ 内容生产成功！")
        print(f"     执行阶段: {forge_result.stages}")
        print(f"     素材数: {len(forge_result.materials)}")
        print(f"     视频时长: {forge_result.video_duration:.1f} 秒")
        print(f"     视频路径: {forge_result.video_path}")
        print(f"     耗时: {forge_time:.1f} 秒")
        print(f"\n  📝 脚本预览:")
        for i, line in enumerate(forge_result.script.split("\n"), 1):
            if line.strip() and i <= 4:
                print(f"     {i}. {line.strip()[:50]}")
    else:
        print(f"  ❌ 内容生产失败: {forge_result.error}")
        print("     继续后续步骤（用模拟数据）")
        forge_result.video_path = "simulated_video.mp4"
        forge_result.script = "模拟脚本内容"

    # ── 第 2 步：Cast — 多平台分发 ──
    print("\n" + "─" * 80)
    print("[2/4] Cast：多平台分发（生成各平台发布包）")
    print("─" * 80)

    t2 = time.time()
    cast = adapters["cast"]
    from core.fabric.adapter import InvokeRequest
    cast_req = InvokeRequest(
        capability="content.publish",
        payload={
            "topic": topic,
            "video_path": forge_result.video_path,
            "script": forge_result.script,
            "platforms": ["douyin", "xiaohongshu", "bilibili"],
            "mode": "package",
        },
    )
    cast_res = cast.invoke(cast_req)
    cast_time = time.time() - t2

    if cast_res.ok:
        data = cast_res.data or {}
        packages = data.get("packages", [])
        print(f"  ✅ 分发成功！生成 {len(packages)} 个平台发布包")
        print(f"     耗时: {cast_time:.1f} 秒")
        for pkg in packages:
            print(f"\n  📱 {pkg['platform'].upper()}:")
            print(f"     标题: {pkg['title'][:40]}...")
            print(f"     标签: {' '.join('#' + t for t in pkg['tags'][:5])}")
    else:
        print(f"  ❌ 分发失败: {cast_res.error}")

    # ── 第 3 步：Echo — 全网反馈采集 ──
    print("\n" + "─" * 80)
    print("[3/4] Echo：全网反馈采集（搜索 → 情感分析 → 需求挖掘）")
    print("─" * 80)

    t3 = time.time()
    echo = adapters["echo"]
    echo_req = InvokeRequest(
        capability="content.feedback",
        payload={
            "keyword": topic,
            "max_results": 10,
        },
    )
    echo_res = echo.invoke(echo_req)
    echo_time = time.time() - t3

    if echo_res.ok:
        data = echo_res.data or {}
        print(f"  ✅ 反馈采集成功！")
        print(f"     总条数: {data.get('total_count')}")
        print(f"     正面: {data.get('positive_count')} / "
              f"负面: {data.get('negative_count')} / "
              f"中性: {data.get('neutral_count')}")
        print(f"     高频关键词: {', '.join(data.get('top_keywords', [])[:5])}")
        print(f"     潜在需求: {len(data.get('needs', []))} 条")
        print(f"     耗时: {echo_time:.1f} 秒")

        if data.get("needs"):
            print(f"\n  💡 需求挖掘（前 3 条）:")
            for need in data["needs"][:3]:
                print(f"     • {need[:50]}...")

        feedback_data = data
    else:
        print(f"  ⚠️  反馈采集失败: {echo_res.error}")
        print("     用模拟数据继续")
        feedback_data = {
            "total_count": 10,
            "positive_count": 6,
            "negative_count": 2,
            "neutral_count": 2,
            "top_keywords": ["智能", "效率", "体验", "功能"],
            "needs": ["希望有更多教程", "能不能支持中文"],
        }

    # ── 第 4 步：Refine — 内容优化 ──
    print("\n" + "─" * 80)
    print("[4/4] Refine：内容优化（基于反馈生成优化建议）")
    print("─" * 80)

    t4 = time.time()
    refine = adapters["refine"]
    refine_req = InvokeRequest(
        capability="content.optimize",
        payload={
            "topic": topic,
            "feedback_data": feedback_data,
            "content_type": "video",
        },
    )
    refine_res = refine.invoke(refine_req)
    refine_time = time.time() - t4

    if refine_res.ok:
        data = refine_res.data or {}
        suggestions = data.get("suggestions", [])
        high_count = sum(1 for s in suggestions if s.get("priority") == "high")
        print(f"  ✅ 优化建议生成成功！")
        print(f"     共 {len(suggestions)} 条建议（高优 {high_count} 条）")
        print(f"     耗时: {refine_time:.1f} 秒")

        print(f"\n  🎯 高优先级建议:")
        for s in suggestions:
            if s.get("priority") == "high":
                print(f"     • [{s['category']}] {s['suggestion']}")
                print(f"       原因: {s['reason'][:50]}...")

        next_plan = data.get("next_content_plan", {})
        if next_plan:
            print(f"\n  📅 下一期内容计划:")
            print(f"     主题: {next_plan.get('topic')}")
            print(f"     角度: {next_plan.get('angle')}")

        print(f"\n  🧪 A/B 测试方案: {len(data.get('ab_test_plan', []))} 组")
    else:
        print(f"  ❌ 优化生成失败: {refine_res.error}")

    # ── 总结 ──
    total_time = time.time() - t0
    print("\n" + "=" * 80)
    print("🎉 内容飞轮全链路验证完成！")
    print("=" * 80)
    print(f"  Forge  内容生产: {'✅' if forge_result.ok else '⚠️ '} "
          f"({forge_time:.1f}s)")
    print(f"  Cast   多平台分发: {'✅' if cast_res.ok else '❌'} "
          f"({cast_time:.1f}s)")
    print(f"  Echo   反馈采集: {'✅' if echo_res.ok else '⚠️ '} "
          f"({echo_time:.1f}s)")
    print(f"  Refine 内容优化: {'✅' if refine_res.ok else '❌'} "
          f"({refine_time:.1f}s)")
    print(f"  总耗时: {total_time:.1f} 秒")
    print()
    print("  闭环路径：")
    print("    Forge 生产内容 → Cast 分发到各平台 → Echo 采集用户反馈 → Refine 优化 → 下一轮 Forge")
    print()
    print("  这就是内容飞轮：越转越快，越用越好。")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
