"""全链路验证：内容飞轮 + LLM 深度分析。

Forge → Cast → Echo(+LLM) → Refine(+LLM) → ContentFlywheel 自动循环
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
from core.fabric.utils.ollama_utils import llm_available, vlm_available, list_models


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

    # 注入 route_fn
    for name in ["content-marketer", "cast", "echo", "refine"]:
        if name in adapters and hasattr(adapters[name], "set_route_fn"):
            adapters[name].set_route_fn(route_fn)

    return route_fn, adapters


def main():
    t0 = time.time()
    print("=" * 80)
    print("AOS 内容飞轮全链路验证（含 LLM 深度分析）")
    print("=" * 80)

    # 检查本地模型
    print("\n[环境检查]")
    print(f"  LLM 可用: {llm_available()}")
    print(f"  VLM 可用: {vlm_available()}")
    models = list_models()
    if models:
        print(f"  本地模型数: {len(models)}")
        for m in models[:6]:
            size_gb = m.get("size", 0) / (1024**3)
            print(f"    - {m.get('name')} ({size_gb:.1f} GB)")

    print("\n[初始化]")
    route_fn, adapters = build_lightweight_hub()
    print(f"  已注册 {len(adapters)} 个适配器: {list(adapters.keys())}")

    topic = "AI 智能体"
    print(f"\n🎯 主题: {topic}")

    # ── 第 1 步：Forge 内容生产 ──
    print("\n" + "─" * 80)
    print("[1/4] Forge：内容生产")
    print("─" * 80)
    t1 = time.time()
    cm = adapters["content-marketer"]
    forge_result = cm.produce(topic, style="douyin", duration=60)
    forge_time = time.time() - t1

    if forge_result.ok:
        print(f"  ✅ 成功 ({forge_time:.1f}s)")
        print(f"     阶段: {forge_result.stages}")
        print(f"     素材: {len(forge_result.materials)} 条")
        print(f"     视频: {forge_result.video_duration:.1f}s / {forge_result.video_path[:50]}...")
    else:
        print(f"  ❌ 失败: {forge_result.error}")
        forge_result.video_path = ""
        forge_result.script = "测试脚本"

    # ── 第 2 步：Cast 多平台分发 ──
    print("\n" + "─" * 80)
    print("[2/4] Cast：多平台分发")
    print("─" * 80)
    t2 = time.time()
    from core.fabric.adapter import InvokeRequest
    cast_req = InvokeRequest(
        capability="content.publish",
        payload={
            "topic": topic,
            "video_path": forge_result.video_path,
            "script": forge_result.script,
            "platforms": ["douyin", "xiaohongshu", "bilibili"],
        },
    )
    cast_res = adapters["cast"].invoke(cast_req)
    cast_time = time.time() - t2

    if cast_res.ok:
        data = cast_res.data or {}
        packages = data.get("packages", [])
        print(f"  ✅ 成功 ({cast_time:.1f}s)")
        print(f"     生成 {len(packages)} 个平台发布包")
        for pkg in packages:
            print(f"     - {pkg['platform']}: {pkg['title'][:30]}...")
    else:
        print(f"  ❌ 失败: {cast_res.error}")

    # ── 第 3 步：Echo 反馈采集 + LLM 深度分析 ──
    print("\n" + "─" * 80)
    print("[3/4] Echo：全网反馈采集 + LLM 深度分析")
    print("─" * 80)
    t3 = time.time()
    echo_req = InvokeRequest(
        capability="content.feedback",
        payload={
            "keyword": topic,
            "max_results": 15,
            "deep_analysis": True,
            "use_llm": True,
        },
    )
    echo_res = adapters["echo"].invoke(echo_req)
    echo_time = time.time() - t3

    if echo_res.ok:
        data = echo_res.data or {}
        print(f"  ✅ 成功 ({echo_time:.1f}s)")
        print(f"     反馈数: {data.get('total_count')}")
        print(f"     情感: +{data.get('positive_count')} / "
              f"-{data.get('negative_count')} / "
              f"~{data.get('neutral_count')}")
        print(f"     关键词: {', '.join(data.get('top_keywords', [])[:5])}")
        print(f"     需求: {len(data.get('needs', []))} 条")

        # 打印 LLM 深度分析摘要
        summary = data.get("summary", "")
        if "LLM 深度分析" in summary:
            print(f"\n  🧠 LLM 深度分析:")
            lines = summary.split("\n")
            for line in lines[:8]:
                if line.strip():
                    print(f"     {line[:60]}")
    else:
        print(f"  ❌ 失败: {echo_res.error}")

    # ── 第 4 步：Refine 内容优化 + LLM 深度优化 ──
    print("\n" + "─" * 80)
    print("[4/4] Refine：内容优化 + LLM 深度优化")
    print("─" * 80)
    t4 = time.time()
    feedback_data = echo_res.data if echo_res.ok else {}
    refine_req = InvokeRequest(
        capability="content.optimize",
        payload={
            "topic": topic,
            "feedback_data": feedback_data,
            "content_type": "video",
            "use_llm": True,
        },
    )
    refine_res = adapters["refine"].invoke(refine_req)
    refine_time = time.time() - t4

    if refine_res.ok:
        data = refine_res.data or {}
        suggestions = data.get("suggestions", [])
        high_count = sum(1 for s in suggestions if s.get("priority") == "high")
        print(f"  ✅ 成功 ({refine_time:.1f}s)")
        print(f"     建议数: {len(suggestions)} (高优 {high_count} 条)")

        # 下一期计划
        next_plan = data.get("next_content_plan", {})
        if next_plan:
            print(f"\n  📅 下一期内容计划:")
            print(f"     主题: {next_plan.get('topic')}")
            print(f"     角度: {next_plan.get('angle')}")

        # LLM 分析
        if next_plan.get("llm_analysis"):
            print(f"\n  🧠 LLM 深度优化建议:")
            analysis = next_plan["llm_analysis"]
            lines = analysis.split("\n")
            for line in lines[:6]:
                if line.strip():
                    print(f"     {line[:60]}")
    else:
        print(f"  ❌ 失败: {refine_res.error}")

    # ── 总结 ──
    total_time = time.time() - t0
    print("\n" + "=" * 80)
    print("🎉 内容飞轮全链路（含 LLM）验证完成！")
    print("=" * 80)
    print(f"  Forge  内容生产:   {'✅' if forge_result.ok else '❌'} ({forge_time:.1f}s)")
    print(f"  Cast   多平台分发: {'✅' if cast_res.ok else '❌'} ({cast_time:.1f}s)")
    print(f"  Echo   反馈采集:   {'✅' if echo_res.ok else '❌'} ({echo_time:.1f}s)")
    print(f"  Refine 内容优化:   {'✅' if refine_res.ok else '❌'} ({refine_time:.1f}s)")
    print(f"  总耗时: {total_time:.1f} 秒")
    print()
    print("  本地模型能力:")
    print(f"    LLM (qwen2.5-coder:7b): {'可用' if llm_available() else '不可用'}")
    print(f"    VLM (minicpm-v):       {'可用' if vlm_available() else '不可用'}")
    print()
    print("  闭环路径：")
    print("    Forge → Cast → Echo(+LLM) → Refine(+LLM) → 下一轮 Forge")
    print("=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
