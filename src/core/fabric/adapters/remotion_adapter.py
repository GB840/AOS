"""Remotion 质量视频渲染适配器（video.remotion）—— AOS 数据可视化视频能力。

Remotion 是用 React 编写视频的框架，适合产出带数据图表、数学/物理原理
动画、科技感短视频的高质量 MP4。本适配器是 AOS 与 Remotion CLI 之间的
薄胶水层：把 AOS 的 `video.remotion` 能力调用，翻译成
`npx remotion render <entry> <composition> --output=... --props=<json>`。

设计原则（对齐 AOS 九大理念）：
- 薄胶水：AOS 不重造视频引擎，只标准化「怎么调 Remotion」。
- 诚实降级（理念6）：Remotion CLI 未安装时 `health()=False`、
  `invoke()` 返回 `ok=False` 并说明原因，绝不谎报渲染成功。
- 不污染主流程：注册失败静默跳过（hub 已 try/except 包裹）。

能力契约（invoke payload）：
- project_dir:   Remotion 项目根目录（含 package.json + entry 文件），必填
- composition_id: 要渲染的 composition 名称（Remotion 的 <Composition id=...>），必填
- props:         传给 composition 的 props（dict，如 {data:[...], title:"..."}），可选
- entry_point:   entry 文件路径（默认 <project_dir>/src/index.tsx），可选
- output:        输出 mp4 路径（默认 data/workspaces/remotion/<task_id>.mp4），可选
- concurrency:   并发帧数（Remotion --concurrency），可选
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid

from core.fabric.adapter import BaseAgentAdapter, InvokeRequest, InvokeResult
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)

_OUTPUT_DIR = os.environ.get(
    "AOS_REMOTION_OUTPUT_DIR",
    os.path.join("data", "workspaces", "remotion"),
)


def _output_dir() -> str:
    os.makedirs(_OUTPUT_DIR, exist_ok=True)
    return _OUTPUT_DIR


class RemotionAdapter(BaseAgentAdapter):
    """Remotion 渲染适配器：把 video.remotion 调用翻译为 `npx remotion render`。

    Remotion CLI 通过 npx 调用；若 npx 不可用或项目未装 remotion，
    渲染会诚实失败（ok=False），由调用方降级处理。
    """

    @property
    def engine_id(self) -> str:
        return "remotion"

    def __init__(self, route_fn=None) -> None:
        self._route_fn = route_fn

    # ── 可注入的子类钩子：便于离线测试时替换 subprocess 调用 ──
    def _run_render(self, cmd: list, cwd: str, timeout: int) -> subprocess.CompletedProcess:
        """执行渲染命令。默认走真实 subprocess；测试可 monkeypatch。"""
        return subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
        )

    def advertise_capabilities(self) -> list:
        return ["video.remotion"]

    def tier(self) -> str:
        # 高质量渲染属云端/外挂工具一极（high）；本地零成本由 VideoMaker 兜底。
        return "high"

    def health(self) -> bool:
        """探测 npx 是否可用（Remotion 经 npx 调用）。

        注：npx 存在 ≠ 项目已装 remotion；真正的「能否渲染」在 invoke 时判定。
        这里只做轻量存在性探测，避免每次 health 都重跑重命令。
        """
        return shutil.which("npx") is not None or shutil.which("remotion") is not None

    def health_detail(self) -> dict:
        npx = shutil.which("npx")
        remotion = shutil.which("remotion")
        return {
            "engine_id": self.engine_id,
            "available": bool(npx or remotion),
            "npx_path": npx,
            "remotion_path": remotion,
            "note": "未检测到 Remotion CLI 时，渲染会诚实失败；请 npm i -g remotion 或在项目内 npx remotion。",
        }

    def invoke(self, req: InvokeRequest) -> InvokeResult:
        if not self.health():
            return InvokeResult(
                ok=False,
                error="Remotion CLI 不可用：未检测到 npx/remotion。请先安装（npm i -g remotion 或在项目内 npx remotion）。",
                engine_id=self.engine_id,
            )

        payload = req.payload or {}
        project_dir = (payload.get("project_dir") or "").strip()
        composition_id = (payload.get("composition_id") or "").strip()
        if not project_dir:
            return InvokeResult(ok=False, error="缺少 project_dir（Remotion 项目根目录）",
                                engine_id=self.engine_id)
        if not composition_id:
            return InvokeResult(ok=False, error="缺少 composition_id（要渲染的 composition 名称）",
                                engine_id=self.engine_id)
        if not os.path.isdir(project_dir):
            return InvokeResult(ok=False, error=f"project_dir 不存在: {project_dir}",
                                engine_id=self.engine_id)

        entry_point = payload.get("entry_point") or os.path.join(project_dir, "src", "index.tsx")
        if not os.path.isfile(entry_point):
            return InvokeResult(ok=False, error=f"entry_point 不存在: {entry_point}",
                                engine_id=self.engine_id)

        task_id = uuid.uuid4().hex[:8]
        output = payload.get("output") or os.path.join(_output_dir(),
                                                        f"remotion_{task_id}.mp4")
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)

        # 组装 props（Remotion 接受 JSON 字符串）
        props = payload.get("props") or {}
        props_arg = ""
        if props:
            props_arg = "--props=" + json.dumps(props, ensure_ascii=False)

        concurrency = payload.get("concurrency") or 4
        cmd = [
            "npx", "remotion", "render",
            entry_point,
            composition_id,
            "--output=" + output,
            f"--concurrency={concurrency}",
        ]
        if props_arg:
            cmd.append(props_arg)

        timeout = int(payload.get("timeout") or 600)
        try:
            proc = self._run_render(cmd, cwd=project_dir, timeout=timeout)
        except subprocess.TimeoutExpired:
            return InvokeResult(ok=False, error=f"渲染超时（>{timeout}s）",
                                engine_id=self.engine_id)
        except Exception as e:  # noqa: BLE001
            return InvokeResult(ok=False, error=f"渲染命令执行异常: {e}",
                                engine_id=self.engine_id)

        if proc.returncode != 0:
            stderr = (proc.stderr or "")[:2000]
            return InvokeResult(
                ok=False,
                error=f"Remotion 渲染失败（exit={proc.returncode}）: {stderr}",
                engine_id=self.engine_id,
            )

        if not os.path.isfile(output):
            return InvokeResult(
                ok=False,
                error="渲染命令退出码为 0 但输出文件未生成（可能的 Remotion 项目配置问题）",
                engine_id=self.engine_id,
            )

        dur = 0.0
        try:
            dur = round(os.path.getsize(output) / (1024 * 1024), 2)
        except Exception:  # noqa: BLE001
            pass
        return InvokeResult(
            ok=True,
            data={
                "output": os.path.abspath(output),
                "composition_id": composition_id,
                "project_dir": project_dir,
                "size_mb": dur,
                "props": props,
            },
            engine_id=self.engine_id,
        )
