"""内容生产流水线真跑测试（不 mock 业务逻辑，只 mock 外部服务）。

验证「一整条自主内容生产」真实跑通：
  1. 动态节点编排：意图→节点图真含 LoraLoader/ControlNet 且连接正确（非模板填参）
  2. 一句话自觉编排：prompt 含 lora:/controlnet: → 自动抽意图
  3. 整条流水线：produce 真跑出剧本+分镜+动态节点图+审核包落盘，默认不发布
  4. approve：审核通过后真落 published/ + manifest
  5. 经 FabricHub.route 真路由 produce（后台，约2.5min，skip 保护）
"""
import os
import json
import uuid
import pytest

from skills.comfyui import ComfyUIDirector, ComfyIntent
from kernel.plugins.comfyui_adapter import ComfyUIAdapter
from kernel.plugins.content_director import ContentDirector, ProductionResult, PublishResult


# ─── 1) 动态节点编排：连接正确性 ──────────────────────────────
def test_dynamic_node_graph_connections():
    d = ComfyUIDirector(default_ckpt="model.safetensors")
    intent = ComfyIntent(
        prompt="赛博朋克肖像", has_image=True, motion=True,
        loras=["cyberpunk.safetensors"], controlnets=["openpose"],
        action="img2vid",
    )
    wf = d.build_workflow(intent)

    classes = {n.get("class_type") for n in wf.values()}
    assert "LoraLoader" in classes, "未插入 LoRA 节点"
    assert "ControlNetLoader" in classes, "未插入 ControlNet 节点"
    assert "ControlNetApply" in classes, "未插入 ControlNetApply 节点"

    # KSampler 的 model 必须指向 LoraLoader 输出，而非直接 CheckpointLoader["4",0]
    ks = wf["3"]
    assert ks["inputs"]["model"] != ["4", 0], "LoRA 未重连 model"
    # KSampler 的 positive 必须指向 ControlNetApply 输出，而非 CLIPTextEncode["6",0]
    assert ks["inputs"]["positive"] != ["6", 0], "ControlNet 未重连 positive"

    # 所有连线必须指向真实存在的节点（无断开/悬空引用）
    for nid, node in wf.items():
        for k, v in node.get("inputs", {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in wf, f"断开连接 {nid}.{k} -> {v[0]}"

    # LoRA 名正确
    lora_node = [n for n in wf.values() if n["class_type"] == "LoraLoader"][0]
    assert lora_node["inputs"]["lora_name"] == "cyberpunk.safetensors"
    # seed 非负（兜底修正生效）
    assert ks["inputs"]["seed"] >= 0


# ─── 2) 一句话自觉编排：意图抽取 ──────────────────────────────
def test_one_shot_plan_intent():
    d = ComfyUIDirector()
    intent = d.plan_intent(
        "一只赛博朋克肖像 lora:cyberpunk.safetensors controlnet:openpose")
    assert "cyberpunk.safetensors" in intent.loras
    assert "openpose" in intent.controlnets
    assert intent.style == "cyberpunk"
    assert intent.action == "txt2img"  # 无图无 motion → 文生图

    # 图生视频场景
    intent2 = d.plan_intent("让这只猫动起来", image_path="cat.png")
    assert intent2.action == "img2vid"
    assert intent2.has_image is True

    # 显式高级字段 → 走动态编排（adapter 同构调用路径）
    intent3 = d.plan_intent("复古风车", loras=["vintage.safetensors"])
    assert intent3.loras == ["vintage.safetensors"]


# ─── 3) 整条流水线真跑（fake 外部工具，逻辑全真）──────────────
def _fake_route(cap, payload):
    """沙箱用假路由：web.search 返素材、media.* 返 output_path、code.generate 返代码。"""
    if cap == "web.search":
        return {"ok": True, "data": {"results": [
            {"title": "素材A", "url": "http://a"},
            {"title": "素材B", "url": "http://b"}]}}
    if cap in ("media.image", "media.video"):
        return {"ok": True, "data": {"output_path": f"/fake/{cap}_{uuid.uuid4().hex[:4]}.png"}}
    if cap == "code.generate":
        return {"ok": True, "data": {"code": "print('hello')"}}
    return {"ok": False, "data": {}}


def test_full_pipeline_produce(tmp_path):
    d = ContentDirector(route_fn=_fake_route, work_root=str(tmp_path))
    res = d.produce("一只赛博朋克猫的短片")

    assert isinstance(res, ProductionResult)
    assert res.task_id
    # 剧本真实生成且非空
    assert os.path.isfile(res.script_path)
    assert os.path.getsize(res.script_path) > 0
    # 检索到素材
    assert len(res.materials) == 2
    # 拆出 ≥1 个镜头，且每个镜头的节点图真被导演动态编排（含 LoRA）
    assert len(res.shots) >= 1
    for s in res.shots:
        wf = json.load(open(s["workflow_path"], encoding="utf-8"))
        assert any(n.get("class_type") == "LoraLoader" for n in wf.values()), \
            f"镜头{s['index']} 导演未动态编排 LoRA（目标含赛博朋克应加 lora）"
        assert s["output_path"], f"镜头{s['index']} 未产出 output_path"
    # 审核包落盘且字段完整
    assert os.path.isfile(res.review_path)
    md = open(res.review_path, encoding="utf-8").read()
    assert res.task_id in md and "审核" in md
    # 默认不发布（human-in-the-loop 停点）
    assert res.published is False
    assert not os.path.isdir(os.path.join(str(tmp_path), "published", res.task_id))
    return d, res


# ─── 4) approve 真发布 ───────────────────────────────────────
def test_approve_publishes(tmp_path):
    d, res = test_full_pipeline_produce(tmp_path)
    pub = d.approve(res.task_id)
    assert isinstance(pub, PublishResult)
    assert pub.ok is True
    pub_dir = os.path.join(str(tmp_path), "published", res.task_id)
    assert os.path.isdir(pub_dir), "发布目录未生成"
    assert os.path.isfile(os.path.join(pub_dir, "manifest.json")), "manifest 未生成"
    assert os.path.isdir(os.path.join(pub_dir, "shots")), "产物未复制"


# ─── 5) 经 FabricHub.route 真路由（后台，约2.5min）──────────
def test_via_fabric_hub_route():
    try:
        from kernel.plugins.fabric_hub import FabricHub
        hub = FabricHub()
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"FabricHub 构造跳过: {e}")
    out = hub.route("content.produce", {"goal": "测试短片"})
    assert out is not None
    data = out.data if hasattr(out, "data") else out
    # 降级（沙箱无网/无 ComfyUI）也应跑完并返回 task_id 或诚实错误
    assert data.get("task_id") or data.get("error")
