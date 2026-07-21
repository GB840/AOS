"""media.image/media.video 路由收圆回归测试（轻量，仅 import capability 模块）。

守护：agnes（外部不可达的云端多模态）已退出 media 路由，图/视频改由
comfyui（本地 HIGH 优先）+ media-gen（国产 MEDIUM 兜底）服务。
若有人误把 agnes 的媒体能力加回，本测试会变红，提醒「图/视频默认走国产/本地」。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from core.fabric import capability as cap


def test_agnes_no_longer_advertises_media():
    agnes = cap.ENGINE_CAPABILITY_MAP["agnes"]
    assert cap.Capability.MEDIA_IMAGE not in agnes
    assert cap.Capability.MEDIA_VIDEO not in agnes
    # agnes 仍应保留 LLM 网关能力（纯 LLM Gateway 定位）
    assert cap.Capability.LLM_GATEWAY in agnes


def test_media_gen_serves_media():
    mg = cap.ENGINE_CAPABILITY_MAP["media-gen"]
    assert cap.Capability.MEDIA_IMAGE in mg
    assert cap.Capability.MEDIA_VIDEO in mg


def test_comfyui_serves_media():
    comfy = cap.ENGINE_CAPABILITY_MAP["comfyui"]
    assert cap.Capability.MEDIA_IMAGE in comfy
    assert cap.Capability.MEDIA_VIDEO in comfy


def test_media_image_tiers_have_local_high_and_national_medium():
    tiers = cap.capability_tiers(cap.Capability.MEDIA_IMAGE)
    assert "high" in tiers      # comfyui 本地优先
    assert "medium" in tiers    # media-gen 国产兜底
