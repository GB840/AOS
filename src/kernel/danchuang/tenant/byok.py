"""BYOK（Bring Your Own Key）模型供应商管理。

让用户自助填入自己在国内主流大模型供应商的 API Key（端点预置在
provider_presets.yaml），密钥经 Fernet 对称加密后落库（tenants.db 的
tenant_provider_keys 表），严格按 tenant_id 隔离。推理时按租户默认供应商
解密并注入 AOS 已有的 LiteLLM 平面（OpenAI 兼容透传），不重新发明路由。

这是管道层（inference plane），不是前沿能力。
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .tenant_manager import TenantManager
from utils.keystore import encrypt_secret, decrypt_secret
from core.fabric.adapters.litellm_adapter import LiteLLMAdapter, InvokeRequest
from core.fabric.capability import Capability

logger = logging.getLogger(__name__)

_PRESETS_PATH = Path(__file__).resolve().parent / "provider_presets.yaml"


def _base_dir() -> Path:
    # byok.py at <root>/src/kernel/danchuang/tenant/byok.py
    return Path(__file__).resolve().parents[4]


def _app_env() -> str:
    return os.environ.get("AOS_ENV", os.environ.get("APP_ENV", "development"))


class ByokStore:
    """租户 BYOK 密钥的存储 + 解析 + 测试。"""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.tm = TenantManager(db_path)
        self._presets = self._load_presets()

    # —— 预设表 ——
    def _load_presets(self) -> Dict[str, Any]:
        try:
            with open(_PRESETS_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return {p["id"]: p for p in data.get("providers", [])}
        except (OSError, yaml.YAMLError) as e:
            logger.error("加载 provider_presets.yaml 失败: %s", e)
            return {}

    def list_presets(self) -> List[Dict[str, Any]]:
        return list(self._presets.values())

    def get_preset(self, provider_id: str) -> Optional[Dict[str, Any]]:
        return self._presets.get(provider_id)

    # —— 存储（加密 + 租户隔离）——
    def save(
        self,
        tenant_id: str,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        is_default: bool = False,
    ) -> Dict[str, Any]:
        preset = self.get_preset(provider)
        if not preset:
            return {"ok": False, "error": f"未知供应商: {provider}"}
        base = api_base or preset.get("base_url", "")
        model = model or (preset["models"][0]["id"] if preset.get("models") else "")
        if not model:
            return {"ok": False, "error": "该供应商无可选模型"}
        cipher = encrypt_secret(api_key, base_dir=_base_dir(), app_env=_app_env())
        key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
        self.tm.save_provider_key(tenant_id, provider, model, base, cipher, key_hash, is_default)
        return {"ok": True, "provider": provider, "model": model, "is_default": is_default}

    def list_keys(self, tenant_id: str) -> List[Dict[str, Any]]:
        return self.tm.list_provider_keys(tenant_id)

    def delete(self, tenant_id: str, provider: str) -> bool:
        return self.tm.delete_provider_key(tenant_id, provider)

    def set_default(self, tenant_id: str, provider: str) -> bool:
        return self.tm.set_default_provider(tenant_id, provider)

    # —— 测试（用真实 Key 调一次供应商）——
    def test_provider(
        self,
        provider: str,
        api_key: str,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> Dict[str, Any]:
        preset = self.get_preset(provider)
        if not preset:
            return {"ok": False, "error": f"未知供应商: {provider}"}
        base = api_base or preset.get("base_url", "")
        model = model or (preset["models"][0]["id"] if preset.get("models") else None)
        if not model:
            return {"ok": False, "error": "无可用模型"}
        payload = {
            "model": model,
            "api_base": base,
            "api_key": api_key,
            "opts": {"custom_llm_provider": "openai"},
        }
        try:
            res = LiteLLMAdapter().invoke(InvokeRequest(Capability.LLM_GATEWAY, payload=payload))
            return {"ok": res.ok, "model": model, "error": res.error}
        except Exception as e:  # 导入/网络等异常
            return {"ok": False, "error": str(e)}

    # —— 解析为 LiteLLM 推理负载（供 autopilot / chat 注入）——
    def resolve_tenant_payload(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        row = self.tm.get_default_provider_key(tenant_id)
        if not row:
            return None
        try:
            key = decrypt_secret(row["key_cipher"], base_dir=_base_dir(), app_env=_app_env())
        except Exception as e:
            logger.error("BYOK 解密失败 tenant=%s: %s", tenant_id, e)
            return None
        return {
            "model": row["model"],
            "api_base": row["api_base"],
            "api_key": key,
            "opts": {"custom_llm_provider": "openai"},
        }

    def chat(
        self,
        tenant_id: str,
        prompt: str,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        """用本租户配置的模型供应商直接对话（端到端闭环验证点）。"""
        if provider:
            row = self.tm.get_provider_key(tenant_id, provider)
            if not row:
                return {"ok": False, "error": f"未保存供应商: {provider}"}
            try:
                key = decrypt_secret(row["key_cipher"], base_dir=_base_dir(), app_env=_app_env())
            except Exception as e:
                return {"ok": False, "error": f"解密失败: {e}"}
            payload: Dict[str, Any] = {
                "model": row["model"],
                "api_base": row["api_base"],
                "api_key": key,
                "opts": {"custom_llm_provider": "openai"},
            }
        else:
            payload = self.resolve_tenant_payload(tenant_id)
            if not payload:
                return {"ok": False, "error": "未配置默认模型供应商，请先保存并设为默认"}
            payload = dict(payload)

        payload["messages"] = [{"role": "user", "content": prompt}]
        try:
            res = LiteLLMAdapter().invoke(InvokeRequest(Capability.LLM_GATEWAY, payload=payload))
            return {
                "ok": res.ok,
                "content": res.data.get("content") if res.ok else None,
                "model": payload["model"],
                "error": res.error,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
