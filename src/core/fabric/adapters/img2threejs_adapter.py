"""img2threejs 适配器 —— AOS fabric 的 media.3d.reconstruct 平面。

把参考图里的物体用**代码**重建为程序化 Three.js 模型（reconstruction-by-code，
不是照片测量/网格提取/下载素材包）。上游工具 img2threejs（Apache-2.0）vendored 于
`third_party/img2threejs/`，是「纯 Python 3.10+ stdlib 脚本 + agent 视觉判断」的
分阶段雕刻管线：intake（探测/校验/细节清单）→ spec（质量契约/组件层级）→
build（逐 pass 生成 Three.js）→ review（divine_eye 零 token 多信号评分做质量门）。

诚实边界（对齐宪法 §0.7.1 三层区分，绝不吹牛）：
- 本适配器只承诺**脚本层能确定性一次调用**的能力：
  · probe    —— 读图技术属性（尺寸/格式，stage1_intake/probe_image.py）
  · score    —— 渲染图↔参考图评分/质量门（stage4_review/divine_eye.py，零 token）
  · pipeline —— 返回四阶段脚本路径 + SKILL 指引（供上层 agent 驱动，默认动作）
- **完整重建**（读图理解 + 写 Three.js 代码 + 视觉复核决策）是多轮 agent 循环，
  依赖 host 的视觉能力与 LLM，**不是** adapter 一次 invoke 能做到的。所以 pipeline
  动作只给「怎么驱动」的真实指引，绝不谎报「一句话/一张图直接出 3D」。

设计原则：
- 零服务端重依赖：脚本纯 stdlib，本地零成本 → tier=high（本地优先）。
- 诚实降级（理念6）：vendored 源码缺失或 python 不可用时 health()=False、
  invoke 返回 ok=False 说明原因；注册失败静默跳过（hub 已 try/except 包裹）。

能力契约（invoke payload）：
- action:  "probe" | "score" | "pipeline"（默认 "pipeline"）
  · probe  需 image（参考图路径）
  · score  需 reference（参考图路径）+ render（渲染截图路径）
  · pipeline 可选 name / complexity，返回管线脚本路径 + 驱动指引
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)


def _default_root() -> Path:
    """vendored img2threejs 根目录（third_party/img2threejs）。

    本文件路径：src/core/fabric/adapters/img2threejs_adapter.py
    parents[4] == 仓库根 → /third_party/img2threejs。可用 AOS_IMG2THREEJS_ROOT 覆盖。
    """
    override = os.environ.get("AOS_IMG2THREEJS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "third_party" / "img2threejs"


class Img2ThreejsAdapter(BaseAgentAdapter):
    """图片→程序化 Three.js 重建适配器（media.3d.reconstruct）。

    只暴露脚本层确定性能力；完整重建的视觉判断由上层 agent（产品研发岗 loop /
    host agent）按 pipeline 指引驱动。
    """

    def __init__(self, root: str | os.PathLike | None = None) -> None:
        self._root = Path(root) if root else _default_root()
        self._forge = self._root / "forge"
        logger.info("Img2ThreejsAdapter: root=%s (exists=%s)",
                    self._root, self._forge.is_dir())

    @property
    def engine_id(self) -> str:
        return "img2threejs"

    def advertise_capabilities(self) -> list:
        return [Capability.MEDIA_3D_RECONSTRUCT]

    def tier(self) -> str:
        return "high"  # 本地纯 stdlib，零成本 / 零依赖 / 最强隐私

    def supported_protocols(self) -> list[str]:
        return []

    def health(self) -> bool:
        """脚本目录存在且关键脚本齐全即视为可用（纯 stdlib，无需装依赖）。"""
        try:
            return (
                self._forge.is_dir()
                and (self._forge / "stage1_intake" / "probe_image.py").is_file()
                and (self._forge / "stage4_review" / "divine_eye.py").is_file()
            )
        except Exception:  # noqa: BLE001
            return False

    def health_detail(self) -> dict:
        return {
            "engine_id": self.engine_id,
            "available": self.health(),
            "root": str(self._root),
            "forge_dir": str(self._forge),
            "note": ("vendored img2threejs (Apache-2.0)；脚本纯 Python stdlib，"
                     "零第三方依赖。缺失则重建能力诚实不可用。"),
        }

    # ── 可注入钩子：便于离线测试替换真实 subprocess ──
    def _run(self, cmd: list, timeout: int) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self.health():
            return InvokeResult(
                ok=False,
                error=(f"img2threejs 不可用：未找到 vendored 脚本（{self._forge}）。"
                       "请确认 third_party/img2threejs 存在，或设 AOS_IMG2THREEJS_ROOT。"),
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        action = (payload.get("action") or "pipeline").strip().lower()

        if action == "probe":
            return self._probe(payload)
        if action == "score":
            return self._score(payload)
        if action == "pipeline":
            return self._pipeline(payload)
        return InvokeResult(
            ok=False,
            error=f"未知 action='{action}'（支持 probe / score / pipeline）",
            engine_id=self.engine_id,
        )

    # ── probe：读图技术属性（确定性，零 token）──
    def _probe(self, payload: dict) -> InvokeResult:
        image = (payload.get("image") or payload.get("reference") or "").strip()
        if not image:
            return InvokeResult(ok=False, error="probe 需要 image（参考图路径）",
                                engine_id=self.engine_id)
        if not os.path.isfile(image):
            return InvokeResult(ok=False, error=f"图片不存在: {image}",
                                engine_id=self.engine_id)
        script = self._forge / "stage1_intake" / "probe_image.py"
        cmd = [sys.executable, str(script), image]
        try:
            proc = self._run(cmd, timeout=int(payload.get("timeout") or 60))
        except subprocess.TimeoutExpired:
            return InvokeResult(ok=False, error="probe 超时", engine_id=self.engine_id)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"probe 执行异常: {e}",
                                engine_id=self.engine_id)
        if proc.returncode != 0:
            return InvokeResult(ok=False,
                                error=f"probe 失败: {(proc.stderr or '')[:800]}",
                                engine_id=self.engine_id)
        data = _parse_json(proc.stdout)
        return InvokeResult(ok=True, data={
            "action": "probe",
            "image": image,
            "result": data if data is not None else (proc.stdout or "").strip(),
            "engine": "img2threejs",
        }, engine_id=self.engine_id)

    # ── score：渲染↔参考图 divine_eye 评分（确定性质量门，零 token）──
    def _score(self, payload: dict) -> InvokeResult:
        reference = (payload.get("reference") or "").strip()
        render = (payload.get("render") or "").strip()
        if not reference or not render:
            return InvokeResult(ok=False,
                                error="score 需要 reference 与 render 两个图片路径",
                                engine_id=self.engine_id)
        for label, p in (("reference", reference), ("render", render)):
            if not os.path.isfile(p):
                return InvokeResult(ok=False, error=f"{label} 不存在: {p}",
                                    engine_id=self.engine_id)
        script = self._forge / "stage4_review" / "divine_eye.py"
        cmd = [sys.executable, str(script),
               "--reference", reference, "--render", render, "--json"]
        try:
            proc = self._run(cmd, timeout=int(payload.get("timeout") or 120))
        except subprocess.TimeoutExpired:
            return InvokeResult(ok=False, error="score 超时", engine_id=self.engine_id)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"score 执行异常: {e}",
                                engine_id=self.engine_id)
        if proc.returncode != 0:
            return InvokeResult(ok=False,
                                error=f"divine_eye 评分失败: {(proc.stderr or '')[:800]}",
                                engine_id=self.engine_id)
        data = _parse_json(proc.stdout)
        return InvokeResult(ok=True, data={
            "action": "score",
            "reference": reference,
            "render": render,
            "verdict": data if data is not None else (proc.stdout or "").strip(),
            "engine": "img2threejs",
            "note": "divine_eye 零 token 多信号评分（IoU/SSIM/对称/边缘等），确定性质量门。",
        }, engine_id=self.engine_id)

    # ── pipeline：返回四阶段脚本路径 + 驱动指引（诚实，不谎报一次出 3D）──
    def _pipeline(self, payload: dict) -> InvokeResult:
        name = (payload.get("name") or "object").strip()
        complexity = (payload.get("complexity") or "moderate").strip()
        f = self._forge
        stages = {
            "stage1_intake": {
                "probe_image": str(f / "stage1_intake" / "probe_image.py"),
                "build_detail_inventory": str(f / "stage1_intake" / "build_detail_inventory.py"),
                "check_reference_admission": str(f / "stage1_intake" / "check_reference_admission.py"),
            },
            "stage2_spec": {
                "new_pre_spec_assessment": str(f / "stage2_spec" / "new_pre_spec_assessment.py"),
                "new_sculpt_spec": str(f / "stage2_spec" / "new_sculpt_spec.py"),
                "validate_sculpt_spec": str(f / "stage2_spec" / "validate_sculpt_spec.py"),
            },
            "stage3_build": {
                "generate_threejs_factory": str(f / "stage3_build" / "generate_threejs_factory.py"),
                "orchestrate_passes": str(f / "stage3_build" / "orchestrate_passes.py"),
            },
            "stage4_review": {
                "divine_eye": str(f / "stage4_review" / "divine_eye.py"),
                "correction_loop": str(f / "stage4_review" / "correction_loop.py"),
                "vlm_gate": str(f / "stage4_review" / "vlm_gate.py"),
            },
        }
        return InvokeResult(ok=True, data={
            "action": "pipeline",
            "name": name,
            "complexity": complexity,
            "skill_doc": str(self._root / "SKILL.md"),
            "grimoire_dir": str(self._root / "grimoire"),
            "stages": stages,
            "engine": "img2threejs",
            "driver": "agent",
            "honest_note": (
                "img2threejs 是 agent 驱动的多阶段管线：脚本负责确定性质量门控（探测/评分/"
                "校验），视觉判断（读图理解、写 Three.js 代码、渲染复核）需上层 agent（产品"
                "研发岗 loop 或 host agent，具备图像理解 + LLM）逐 pass 驱动。本 adapter 不"
                "谎报一次 invoke 出成品；请按 SKILL.md 顺序：intake→spec→build→review，每"
                "个 pass 用 divine_eye score 复核，identity 特征错误即打回该 pass。"
            ),
        }, engine_id=self.engine_id)


def _parse_json(text: str):
    """尽力把脚本 stdout 解析成 JSON；失败返回 None（由调用方回退原文）。"""
    if not text:
        return None
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        # 有些脚本可能在 JSON 前后带日志行，尝试截取首个 { 到末个 }
        try:
            start = text.index("{")
            end = text.rindex("}")
            return json.loads(text[start:end + 1])
        except Exception:  # noqa: BLE001
            return None
