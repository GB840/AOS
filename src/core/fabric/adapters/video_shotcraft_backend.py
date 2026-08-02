"""video-shotcraft 接入 —— 真接开源（Apache-2.0），非自研等价。

项目：Vincentwei1021/video-shotcraft（GitHub，Apache-2.0，可商用，0 元商用）
定位：给 Agent 装的「电影感产品宣传片」skill，基于 Remotion（React）——
106 张镜头配方卡 + 161 段动效 + 36.2s Ink Press 成片模板。

接入方式（对齐 AOS 第一性「本地优先 / 不绑死 / 诚实降级」）：
- 重型依赖（Node + pnpm + Remotion）全部惰性探测：未装即用 shutil.which 检测，
  不装就不装，绝不用内存冒充「视频已生成」。
- 仓库已克隆在 vendor/video-shotcraft（opt-in 本地资产，不入 git）；
  也可 env AOS_VIDEO_SHOTCRAFT_REPO 指定，或 ensure_repo() 自行克隆。
- 真渲染 = 在 template/ 里 `pnpm install` + `npx remotion render`（重，③，主机跑）。
- available() 如实反映「仓库在 + node 在」才 True；否则 False。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import List, Optional

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))


def _repo_root() -> str:
    d = _THIS_DIR
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "vendor")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.getcwd()


class VideoShotcraft:
    """video-shotcraft skill 封装（opt-in，本地优先）。"""

    def __init__(self, repo_path: Optional[str] = None) -> None:
        self.repo_path = repo_path or os.environ.get("AOS_VIDEO_SHOTCRAFT_REPO")
        self._candidates = [
            self.repo_path,
            os.path.join(_repo_root(), "vendor", "video-shotcraft"),
            os.path.expanduser("~/.claude/skills/video-shotcraft"),
            os.path.expanduser("~/.codex/skills/video-shotcraft"),
        ]

    # ---- 可用性（如实）----
    def _repo_present(self) -> Optional[str]:
        for p in self._candidates:
            if p and os.path.isdir(p):
                return p
        return None

    def _node_present(self) -> bool:
        return bool(shutil.which("node")) and bool(shutil.which("npx"))

    @property
    def available(self) -> bool:
        return bool(self._repo_present()) and self._node_present()

    def health_detail(self) -> dict:
        repo = self._repo_present()
        return {
            "engine": "video-shotcraft",
            "license": "Apache-2.0",
            "repo": repo,
            "repo_present": repo is not None,
            "node_present": self._node_present(),
            "ready": self.available,
            "note": "已克隆开源仓库 + Node 运行时即可用；真渲染需 pnpm install + npx remotion render（重，主机跑）",
        }

    # ---- opt-in 克隆 ----
    def ensure_repo(self, url: str = "https://github.com/Vincentwei1021/video-shotcraft.git") -> str:
        existing = self._repo_present()
        if existing:
            return existing
        target = os.path.join(_repo_root(), "vendor", "video-shotcraft")
        subprocess.run(["git", "clone", "--depth", "1", url, target], check=True, timeout=300)
        self.repo_path = target
        return target

    # ---- 渲染命令构造（真实 Remotion 路径）----
    def build_render_command(
        self,
        output: str,
        template: str = "Ink Press",
        props: Optional[dict] = None,
    ) -> List[str]:
        """构造真实渲染命令：在仓库 template/ 目录用 Remotion 渲染成 MP4。

        要求：template/ 已 `pnpm install`（首次重，约数百 MB npm 依赖）。
        """
        repo = self._repo_present()
        if not repo:
            raise RuntimeError("video-shotcraft 仓库缺失：设 AOS_VIDEO_SHOTCRAFT_REPO 或 ensure_repo() 克隆")
        if not self._node_present():
            raise RuntimeError("未检测到 node/npx：请安装 Node.js（https://nodejs.org）")
        template_dir = os.path.join(repo, "template")
        if not os.path.isdir(template_dir):
            raise RuntimeError(f"模板目录不存在：{template_dir}")
        cmd = [
            "npx", "remotion", "render",
            template,
            "--output", output,
        ]
        if props:
            cmd += ["--props", json.dumps(props)]
        return cmd

    def render(self, output: str, template: str = "Ink Press", props: Optional[dict] = None) -> dict:
        """执行真实渲染（重 I/O + CPU）。返回 {'ok': bool, 'output': path}。"""
        cmd = self.build_render_command(output, template, props)
        proc = subprocess.run(
            cmd, cwd=os.path.join(self._repo_present(), "template"),
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            return {"ok": False, "error": proc.stderr.strip()[:400] or "remotion 非零退出"}
        return {"ok": True, "output": output, "engine": "video-shotcraft"}
