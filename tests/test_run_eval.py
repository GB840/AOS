"""运行评测器（UniClawBench 思路）的单测：用真实 run 夹具 + 一个构造的假成功样本。"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from run_eval import score_run, risk_score  # noqa: E402

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIX, name), "r", encoding="utf-8") as f:
        return json.load(f)


def test_real_runs_score_healthy():
    for name in ("run_baidu_channel_access.json", "run_anysearch_memory.json"):
        run = _load(name)
        sc = score_run(run)
        # 核心两步成功，完整性 >= 0.66
        assert sc["completeness"] >= 0.66
        # 失败步都有诚实 error，风险低
        assert sc["risk"] <= 0.2
        # planner 产出多步带标签计划，主动性满
        assert sc["proactivity"] == 1.0


def test_fake_success_flagged_high_risk():
    fake = {
        "plan": "1. [web.search] x",
        "execution": {
            "trace": [
                {"capability": "web.search", "ok": True, "out": {}},  # 假成功
            ]
        },
    }
    assert risk_score(fake) >= 0.8
