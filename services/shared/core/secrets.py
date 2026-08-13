"""API Key 等敏感字段的 at-rest 加密（AES-256-GCM，依赖 cryptography）。

设计目标：

- 用 **AES-256-GCM** 提供认证加密（AEAD），每次密文随机 salt 与 nonce；
- 输出格式 ``enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>`` 便于版本演进；
- 旧 ``enc:v1:`` 密文显式抛 :class:`LegacySecretFormatError`，引导用户在 Settings
  页面重新保存 Key——避免静默迁移导致密钥握手错误诊断困难；
- 密钥来源：环境变量 ``SECRET_KEY``（base64 或明文字符串），
  缺省在 ``data/.secret.key`` 持久化随机 32 字节密钥。

.. note::

    本模块依赖 ``cryptography``（>= 42.0）；加密层是真正的认证加密
    （GCM），不再使用 XOR 流。``requirements.txt`` 必须包含 cryptography。
"""

from __future__ import annotations

import base64
import logging
import os
import secrets as _secrets
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.config import SHARED_ROOT  # 单一真源：master key 与 DB 同目录

logger = logging.getLogger(__name__)

# v1 = 旧 XOR + HMAC；v2 = AES-256-GCM
_VERSION_V1 = "enc:v1"
_VERSION_V2 = "enc:v2"

_SALT_BYTES = 16
_NONCE_BYTES = 12  # GCM 标准 nonce 长度
_TAG_BYTES = 16
_KEY_BYTES = 32
_KDF_ITERATIONS = 200_000

# master key 与 DB / uploads 同目录：services/shared/data/.secret.key
_SHARED_DATA = SHARED_ROOT / "data"
_DEFAULT_KEYFILE = _SHARED_DATA / ".secret.key"

_MASTER_SALT = b"app-master-v2"

# 最低 master key 强度：明文 ≥16 字符，或 base64 解码后 ≥16 字节
_MIN_MASTER_KEY_BYTES = 16


def validate_master_key_env() -> str:
    """校验 ``SECRET_KEY`` 强度，返回 ``"ok"`` | ``"missing"`` | ``"too_short"``。

    纯函数：不读取/生成任何 keyfile，不触发 :func:`_master_bytes` 缓存，
    供启动门禁与运行时防线复用。
    """
    raw = os.environ.get("SECRET_KEY")
    if not raw:
        return "missing"
    try:
        decoded = base64.b64decode(raw, validate=True)
    except Exception:
        decoded = b""
    if len(decoded) >= _MIN_MASTER_KEY_BYTES or len(raw) >= _MIN_MASTER_KEY_BYTES:
        return "ok"
    return "too_short"


class LegacySecretFormatError(ValueError):
    """旧版加密格式无法解密，请重新保存 API Key。"""


def _derive_key(master: bytes, salt: bytes) -> bytes:
    """从 master + 每密文 salt 派生 32 字节 AES 密钥。"""
    import hashlib

    return hashlib.pbkdf2_hmac(
        "sha256", master, salt, _KDF_ITERATIONS, dklen=_KEY_BYTES
    )


def _load_secret_bytes() -> bytes:
    """返回原始 master 密钥（≥32 字节）。

    密钥强度（≥16 字节）由 :func:`validate_master_key_env` 校验，
    ``main.py`` 的启动门禁在 ``env=prod`` 下强制；此处不重复拒绝，
    以免破坏 dev 场景下既有短密钥部署。
    """
    raw = os.environ.get("SECRET_KEY")
    if raw:
        # 既支持 base64 编码，也支持明文字符串（自动规范化）
        try:
            decoded = base64.b64decode(raw, validate=True)
            if len(decoded) >= 16:
                return decoded.ljust(_KEY_BYTES, b"0")[:_KEY_BYTES]
        except Exception:
            pass
        return _derive_key(raw.encode("utf-8"), _MASTER_SALT)

    # 持久化 fallback
    _SHARED_DATA.mkdir(parents=True, exist_ok=True)
    if _DEFAULT_KEYFILE.exists():
        try:
            return base64.b64decode(_DEFAULT_KEYFILE.read_text().strip())
        except Exception:
            pass

    fresh = _secrets.token_bytes(_KEY_BYTES)
    _DEFAULT_KEYFILE.write_text(base64.b64encode(fresh).decode())
    try:
        os.chmod(_DEFAULT_KEYFILE, 0o600)
    except OSError:
        pass
    logger.warning(
        "未检测到 SECRET_KEY，已生成一次性密钥: %s；生产环境请显式提供环境变量",
        _DEFAULT_KEYFILE,
    )
    return fresh


@lru_cache
def _master_bytes() -> bytes:
    """缓存 master 密钥，避免每次加解密都重新解析 env / 文件。"""
    return _load_secret_bytes()


def _reset_cache() -> None:
    """仅供测试使用：清空缓存后下一次 encrypt/decrypt 会重新加载 master。"""
    _master_bytes.cache_clear()


def _aesgcm() -> "AESGCM":
    return AESGCM(_master_bytes())


def encrypt_secret(plaintext: str | None) -> str | None:
    """加密字符串；``None`` / 空值原样返回。"""
    if not plaintext:
        return plaintext
    if plaintext.startswith(f"{_VERSION_V2}:"):
        return plaintext  # 已加密
    salt = os.urandom(_SALT_BYTES)
    nonce = os.urandom(_NONCE_BYTES)
    master = _master_bytes()
    key = _derive_key(master, salt)
    cipher_with_tag = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    # GCM 输出 = ciphertext || tag；拆分后写入格式
    if len(cipher_with_tag) < _TAG_BYTES:
        raise ValueError("AES-GCM 输出长度异常")
    ct = cipher_with_tag[:-_TAG_BYTES]
    tag = cipher_with_tag[-_TAG_BYTES:]
    return (
        f"{_VERSION_V2}:"
        f"{base64.b64encode(salt).decode()}:"
        f"{base64.b64encode(nonce).decode()}:"
        f"{base64.b64encode(tag).decode()}:"
        f"{base64.b64encode(ct).decode()}"
    )


def decrypt_secret(value: str | None) -> str | None:
    """解密；解密失败抛出 :class:`ValueError` 或 :class:`LegacySecretFormatError`。"""
    if not value:
        return value
    if value.startswith(f"{_VERSION_V1}:"):
        # 旧格式无法向后兼容解密——避免静默迁移误判密钥错误。
        raise LegacySecretFormatError(
            "检测到旧版 (enc:v1) 加密 API Key，请到「设置」页面重新保存。"
        )
    if not value.startswith(f"{_VERSION_V2}:"):
        # 未加密明文：迁移期或开发环境兼容。
        return value
    parts = value.split(":", 5)
    if len(parts) != 6:
        raise ValueError("加密串格式错误")
    _, _, salt_b64, nonce_b64, tag_b64, ct_b64 = parts
    try:
        salt = base64.b64decode(salt_b64)
        nonce = base64.b64decode(nonce_b64)
        tag = base64.b64decode(tag_b64)
        ct = base64.b64decode(ct_b64)
    except Exception as exc:
        raise ValueError("加密串 base64 解析失败") from exc
    master = _master_bytes()
    key = _derive_key(master, salt)
    try:
        plain_bytes = AESGCM(key).decrypt(nonce, ct + tag, None)
    except Exception as exc:
        raise ValueError("AES-GCM 解密或认证失败：密钥可能已变更或数据被篡改") from exc
    return plain_bytes.decode("utf-8")


__all__ = [
    "LegacySecretFormatError",
    "encrypt_secret",
    "decrypt_secret",
    "validate_master_key_env",
    "_reset_cache",
    "_master_bytes",
    "_VERSION_V2",
]
