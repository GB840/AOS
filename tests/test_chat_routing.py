"""chat_routing.select_chat_backends 纯函数单测（不依赖重型依赖，秒级）。

验证单基座第一性：默认 [fabric, kernel]；brain.py 仅 opt-in 兜底。
"""
import os
import pytest

from api.chat_routing import (
    select_chat_backends,
    BACKEND_FABRIC,
    BACKEND_KERNEL,
    BACKEND_BRAIN,
    BRAIN_DEPRECATION_MSG,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # 每个测试前清掉相关 env，保证默认行为可复现
    for k in ("AOS_CHAT_BACKEND", "AOS_BRAIN_FALLBACK"):
        monkeypatch.delenv(k, raising=False)
    yield


def test_default_chain_is_fabric_then_kernel():
    assert select_chat_backends() == [BACKEND_FABRIC, BACKEND_KERNEL]


def test_brain_fallback_appends_brain_at_end():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_BRAIN_FALLBACK", "1")
    try:
        assert select_chat_backends() == [BACKEND_FABRIC, BACKEND_KERNEL, BACKEND_BRAIN]
    finally:
        monkeypatch.undo()


def test_explicit_kernel_backend():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_CHAT_BACKEND", "kernel")
    try:
        assert select_chat_backends() == [BACKEND_KERNEL]
    finally:
        monkeypatch.undo()


def test_explicit_kernel_with_brain_fallback():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_CHAT_BACKEND", "kernel")
    monkeypatch.setenv("AOS_BRAIN_FALLBACK", "1")
    try:
        assert select_chat_backends() == [BACKEND_KERNEL, BACKEND_BRAIN]
    finally:
        monkeypatch.undo()


def test_explicit_brain_backend_is_legacy_only():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_CHAT_BACKEND", "brain")
    try:
        assert select_chat_backends() == [BACKEND_BRAIN]
    finally:
        monkeypatch.undo()


def test_case_insensitive_backend():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_CHAT_BACKEND", "FABRIC")
    try:
        assert select_chat_backends() == [BACKEND_FABRIC, BACKEND_KERNEL]
    finally:
        monkeypatch.undo()


def test_unknown_backend_falls_back_to_default():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("AOS_CHAT_BACKEND", "does-not-exist")
    try:
        assert select_chat_backends() == [BACKEND_FABRIC, BACKEND_KERNEL]
    finally:
        monkeypatch.undo()


def test_deprecation_msg_mentions_env_knobs():
    assert "AOS_BRAIN_FALLBACK" in BRAIN_DEPRECATION_MSG
    assert "AOS_CHAT_BACKEND" in BRAIN_DEPRECATION_MSG
    assert "FabricHub" in BRAIN_DEPRECATION_MSG
