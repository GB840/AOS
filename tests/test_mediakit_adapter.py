"""MediakitAdapter 单元测试（9 项，覆盖契约/健康门控/诚实降级/真实_cmd 钩子）。

遵循 img2threejs_adapter 的离线测试范式：用可注入的 `_run` 钩子模拟 subprocess，
并用 mock.patch 让 `shutil.which("npx")` 返回真路径，从而在不装 Node / 不引
火山 Key 的情况下验证适配器逻辑与诚实降级行为。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.fabric.adapters.mediakit_adapter import (  # noqa: E402
    MediakitAdapter,
    _enabled,
    _ENV_ENABLED,
)


class FakeCompleted:
    """模拟 subprocess.CompletedProcess。"""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestMediakitAdapter(unittest.TestCase):

    def _enabled_env(self):
        # 强制开启 opt-in（测试内），避免依赖主机环境
        return mock.patch.dict(os.environ, {_ENV_ENABLED: "1", "AOS_MEDIAKIT_MODE": "local"})

    def _with_npx(self):
        # 让 health 认为 npx 存在
        return mock.patch(
            "core.fabric.adapters.mediakit_adapter.shutil.which",
            lambda x: "C:/npx" if x == "npx" else None,
        )

    def _ok_run(self, stdout="mediakit ok"):
        def _fake(cmd, timeout, env):
            return FakeCompleted(0, stdout, "")
        return _fake

    # ── 1. 基础契约 ──
    def test_basic_contract(self):
        a = MediakitAdapter()
        self.assertEqual(a.engine_id, "mediakit")
        self.assertEqual(a.advertise_capabilities(), ["media.process"])
        self.assertEqual(a.tier(), "medium")

    # ── 2. 未开启 opt-in → health False ──
    def test_health_false_when_not_enabled(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_ENABLED, None)
            self.assertFalse(_enabled())
            self.assertFalse(MediakitAdapter().health())

    # ── 3. 已开启但无 npx → health False ──
    def test_health_false_when_no_npx(self):
        with self._enabled_env(), mock.patch(
            "core.fabric.adapters.mediakit_adapter.shutil.which", lambda x: None
        ):
            self.assertFalse(MediakitAdapter().health())

    # ── 4. 已开启 + npx 存在 → health True ──
    def test_health_true_when_enabled_and_npx(self):
        with self._enabled_env(), self._with_npx():
            self.assertTrue(MediakitAdapter().health())
            d = MediakitAdapter().health_detail()
            self.assertTrue(d["available"])
            self.assertTrue(d["enabled"])

    # ── 5. 未健康时 invoke 诚实拒绝 ──
    def test_invoke_rejected_when_unhealthy(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(_ENV_ENABLED, None)
            a = MediakitAdapter()
            res = a.invoke(_req({"action": "run", "command": ["video", "cut"]}))
            self.assertFalse(res.ok)
            self.assertIn("不可用", res.error)

    # ── 6. run 经真实 _run 钩子跑通 ──
    def test_invoke_run_via_hook(self):
        with self._enabled_env(), self._with_npx():
            a = MediakitAdapter()
            a._run = self._ok_run("cut done")
            res = a.invoke(_req({"action": "run", "command": ["video", "cut", "--input", "a.mp4"]}))
            self.assertTrue(res.ok, res.error)
            self.assertEqual(res.data["mode"], "local")
            self.assertIn("cut", res.data["command"])
            self.assertEqual(res.data["stdout"], "cut done")

    # ── 7. help 探测能力清单 ──
    def test_invoke_help_via_hook(self):
        with self._enabled_env(), self._with_npx():
            a = MediakitAdapter()
            a._run = self._ok_run("USAGE: mediakit-cli ...")
            res = a.invoke(_req({"action": "help"}))
            self.assertTrue(res.ok, res.error)
            self.assertEqual(res.data["action"], "help")

    # ── 8. 云端模式缺 Key → 诚实失败 ──
    def test_cloud_requires_key(self):
        clean = {k: "" for k in ("VOLCENGINE_API_KEY", "MEDIAKIT_API_KEY", "ARK_API_KEY")}
        with self._enabled_env(), self._with_npx(), mock.patch.dict(os.environ, clean, clear=False):
            for k in clean:
                os.environ.pop(k, None)
            a = MediakitAdapter()
            res = a.invoke(_req({"action": "run", "mode": "cloud", "command": ["video", "cut"]}))
            self.assertFalse(res.ok)
            self.assertIn("云端模式需火山 API Key", res.error)

    # ── 9. 未知 action / 缺 command 诚实拒绝 ──
    def test_unknown_action_and_missing_command(self):
        with self._enabled_env(), self._with_npx():
            a = MediakitAdapter()
            bad = a.invoke(_req({"action": "frobnicate"}))
            self.assertFalse(bad.ok)
            self.assertIn("不支持的 action", bad.error)
            nocmd = a.invoke(_req({"action": "run"}))
            self.assertFalse(nocmd.ok)
            self.assertIn("缺少 command", nocmd.error)


def _req(payload):
    class _R:
        def __init__(self, p):
            self.payload = p
    return _R(payload)


if __name__ == "__main__":
    unittest.main(verbosity=2)
