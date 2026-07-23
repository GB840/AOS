"""密钥与敏感凭据的安全管理。

取代此前散落在 config/security 中的弱默认口令与 HS256 对称密钥：

- JWT 升级为非对称 **RS256**：私钥签名 / 公钥验签，杜绝"已知对称密钥离线伪造令牌"。
- 开发环境缺失敏感凭据时，自动生成强随机值并持久化到 ``.secrets/``（已被 .gitignore 排除）。
- 生产环境缺失敏感凭据时 **果断 fail-fast**，禁止弱默认悄悄上线。

解析优先级（JWT 密钥）：
  1. 环境变量 ``AOS_JWT_PRIVATE_KEY`` / ``AOS_JWT_PUBLIC_KEY``（PEM 字符串）
  2. 文件 ``<BASE_DIR>/.secrets/jwt/{private,public}.pem``
  3. 开发环境：自动生成 RSA 2048 并持久化
  4. 生产环境：缺失即抛 ``RuntimeError``（fail-fast）
"""
from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

JWT_PRIV_ENV = "AOS_JWT_PRIVATE_KEY"
JWT_PUB_ENV = "AOS_JWT_PUBLIC_KEY"
JWT_DIRNAME = "jwt"
PRIV_FILENAME = "private.pem"
PUB_FILENAME = "public.pem"


def _secrets_dir(base_dir: Path) -> Path:
    return Path(base_dir) / ".secrets"


def write_secret_file(path: Path, content: str) -> None:
    """以 0o600 权限写入敏感文件，父目录按需创建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
    finally:
        pass
    try:
        os.chmod(path, 0o600)
    except OSError:
        # Windows 上 chmod 权限语义有限，忽略即可（文件已最小化创建）
        pass


def generate_strong_password(length: int = 24) -> str:
    """生成 URL-safe 强随机口令（用于自动生成的数据库/网关管理员口令）。"""
    return secrets.token_urlsafe(length)


def _load_pem(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _generate_rsa_keypair() -> tuple[str, str]:
    """生成 RSA 2048 密钥对，返回 (private_pem, public_pem)。"""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    pub_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return priv_pem, pub_pem


def load_jwt_keys(
    base_dir: Path, app_env: str, *, force_generate: bool = False
) -> tuple[str, str]:
    """返回 (private_pem, public_pem)。

    详见模块 docstring 的解析优先级。生产环境缺失密钥时抛 ``RuntimeError``。
    """
    base_dir = Path(base_dir)

    # 1) 环境变量优先（容器 / K8s Secret 场景）
    env_priv = os.environ.get(JWT_PRIV_ENV)
    env_pub = os.environ.get(JWT_PUB_ENV)
    if env_priv and env_pub:
        return env_priv.strip(), env_pub.strip()

    # 2) 文件回退
    sec_dir = _secrets_dir(base_dir) / JWT_DIRNAME
    priv_path = sec_dir / PRIV_FILENAME
    pub_path = sec_dir / PUB_FILENAME
    file_priv = _load_pem(priv_path)
    file_pub = _load_pem(pub_path)
    if file_priv and file_pub:
        return file_priv, file_pub

    # 3) 生成（仅开发环境或显式 force_generate）
    if force_generate or app_env != "production":
        priv_pem, pub_pem = _generate_rsa_keypair()
        write_secret_file(priv_path, priv_pem)
        write_secret_file(pub_path, pub_pem)
        logger.warning(
            "⚠️ 已自动生成 RSA JWT 密钥对并持久化到 %s（开发环境）。"
            "生产环境请改用环境变量或挂载密钥，勿依赖自动生成。",
            sec_dir,
        )
        return priv_pem, pub_pem

    # 4) 生产环境缺失 -> fail-fast
    raise RuntimeError(
        "生产环境缺少 JWT 非对称密钥：请设置环境变量 "
        f"{JWT_PRIV_ENV}/{JWT_PUB_ENV}，或在 {sec_dir} 放置 {PRIV_FILENAME}/{PUB_FILENAME}。"
    )


# ═══════════════════════════════════════════════════════
#  BYOK 对称加密（Fernet）
#  用于加密租户自有的模型供应商 API Key，落库 tenant_provider_keys。
#  主密钥解析优先级：
#    1. 环境变量 AOS_BYOK_MASTER_KEY（PEM 字符串 / 任意口令）
#    2. 文件 <BASE_DIR>/.secrets/byok/byok.key（Fernet 原始密钥）
#    3. 开发环境：自动生成 Fernet 密钥并持久化
#    4. 生产环境：缺失即 fail-fast
# ═══════════════════════════════════════════════════════

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

BYOK_MASTER_ENV = "AOS_BYOK_MASTER_KEY"
BYOK_DIRNAME = "byok"
BYOK_FILENAME = "byok.key"

_master_fernet = None


def _byok_key_path(base_dir: Path) -> Path:
    return Path(base_dir) / ".secrets" / BYOK_DIRNAME / BYOK_FILENAME


def _is_raw_fernet_key(value: str) -> bool:
    """判断字符串是否已是合法 Fernet 密钥（url-safe base64，解码后 32 字节）。"""
    try:
        return len(base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))) == 32
    except Exception:
        return False


def _derive_fernet(passphrase: str) -> Fernet:
    """从任意口令派生 Fernet 密钥（HKDF-SHA256）。"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"aos-byok",
        info=b"aos-byok-master",
    )
    return Fernet(base64.urlsafe_b64encode(hkdf.derive(passphrase.encode("utf-8"))))


def _app_env() -> str:
    return os.environ.get("AOS_ENV", os.environ.get("APP_ENV", "development"))


def _default_base() -> Path:
    # keystore.py at <root>/src/utils/keystore.py
    return Path(__file__).resolve().parents[2]


def load_fernet_master(
    base_dir: Path | None = None,
    app_env: str | None = None,
    *,
    force_generate: bool = False,
) -> Fernet:
    """返回（并缓存）BYOK 主密钥 Fernet 实例。"""
    global _master_fernet
    if _master_fernet is not None:
        return _master_fernet

    base_dir = Path(base_dir) if base_dir else _default_base()
    app_env = app_env or _app_env()

    # 1) 环境变量（最优先，适合容器 / K8s Secret）
    env_key = os.environ.get(BYOK_MASTER_ENV)
    if env_key:
        _master_fernet = Fernet(env_key) if _is_raw_fernet_key(env_key) else _derive_fernet(env_key)
        return _master_fernet

    # 2) 文件回退
    path = _byok_key_path(base_dir)
    if path.is_file():
        raw = _load_pem(path)
        if raw:
            _master_fernet = Fernet(raw) if _is_raw_fernet_key(raw) else _derive_fernet(raw)
            return _master_fernet

    # 3) 生成（仅开发环境或显式 force_generate）
    if force_generate or app_env != "production":
        key = Fernet.generate_key()
        write_secret_file(path, key.decode("utf-8"))
        _master_fernet = Fernet(key)
        logger.warning(
            "⚠️ 已自动生成 BYOK 主密钥并持久化到 %s（开发环境）。"
            "生产环境请设置环境变量 %s，勿依赖自动生成。",
            path,
            BYOK_MASTER_ENV,
        )
        return _master_fernet

    # 4) 生产环境缺失 -> fail-fast
    raise RuntimeError(
        f"生产环境缺少 BYOK 主密钥：请设置环境变量 {BYOK_MASTER_ENV}，"
        f"或在 {path} 放置密钥文件。"
    )


def encrypt_secret(
    plaintext: str,
    *,
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> str:
    """加密明文密钥，返回可落库的密文字符串。"""
    f = load_fernet_master(base_dir, app_env)
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(
    ciphertext: str,
    *,
    base_dir: Path | None = None,
    app_env: str | None = None,
) -> str:
    """解密密文，返回明文密钥。"""
    f = load_fernet_master(base_dir, app_env)
    return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
