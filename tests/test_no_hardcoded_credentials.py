"""守门：禁止在源码硬编码真实 IMA Client ID（开源合规）

2026-08-09 复查发现 src/skills/ima.py 曾把真实 Client ID 写死为 DEFAULT_CLIENT_ID 默认值，
环境变量未配置时回退到真实值——属凭据泄露。本测试锁定该回归，且自身不嵌入任何真实凭据。
"""
import os

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def test_ima_module_no_hardcoded_default_client_id():
    src = _read(os.path.join("src", "skills", "ima.py"))
    # 真实 Client ID 曾硬编码为 DEFAULT_CLIENT_ID 默认值，已移除；源码不得再定义该符号
    assert "DEFAULT_CLIENT_ID" not in src, \
        "ima.py 不得再定义 DEFAULT_CLIENT_ID（避免硬编码真实 Client ID）"
    # 凭证必须仅从环境变量读取
    assert 'os.environ.get("IMA_OPENAPI_CLIENTID"' in src, \
        "ima.py 应从环境变量 IMA_OPENAPI_CLIENTID 读取 Client ID"


def test_ima_agent_comment_no_misleading_default_phrase():
    src = _read(os.path.join("src", "subagents", "ima_agent.py"))
    # 旧注释曾误导「Client ID 已有默认值」，已修正为提示从 .env 配置
    assert "Client ID 已有默认值" not in src
