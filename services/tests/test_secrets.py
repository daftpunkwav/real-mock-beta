"""``app.core.secrets`` 单元测试。

覆盖：

- AES-256-GCM 加解密往返；
- 旧明文格式向后兼容（无前缀）；
- 旧 ``enc:v1:`` 密文显式抛 ``LegacySecretFormatError``；
- 篡改密文/tag/salt/nonce 任何字段都应被 AEAD 拒收；
- 空值/None 边界；
- 同明文两次加密密文不同（salt + nonce 随机）。
"""

from __future__ import annotations

import base64

import pytest

from shared.core.secrets import (
    LegacySecretFormatError,
    _reset_cache,
    decrypt_secret,
    encrypt_secret,
)


@pytest.fixture(autouse=True)
def _stable_master_key(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """用临时固定 master + 隔离 keyfile 避免污染全局 ``data/.secret.key``。"""
    import base64 as _b64

    monkeypatch.setenv("SECRET_KEY", _b64.b64encode(b"a" * 32).decode())
    # 用临时目录覆盖默认 keyfile
    monkeypatch.setattr(
        "shared.core.secrets._SHARED_DATA", tmp_path
    )
    monkeypatch.setattr(
        "shared.core.secrets._DEFAULT_KEYFILE", tmp_path / ".secret.key"
    )
    _reset_cache()
    yield
    _reset_cache()


class TestEncryptDecrypt:
    def test_roundtrip(self) -> None:
        plain = "sk-1234567890abcdef"
        enc = encrypt_secret(plain)
        assert enc is not None
        assert enc.startswith("enc:v2:")
        assert enc != plain
        assert decrypt_secret(enc) == plain

    def test_encrypt_idempotent(self) -> None:
        """已加密的字符串二次调用直接返回，不重复包裹。"""
        plain = "hello"
        enc = encrypt_secret(plain)
        assert encrypt_secret(enc) == enc

    def test_decrypt_legacy_plaintext(self) -> None:
        """未带 ``enc:v2:`` 前缀的旧明文直接返回,保证迁移期兼容。"""
        legacy = "legacy-plain-key"
        assert decrypt_secret(legacy) == legacy

    def test_decrypt_legacy_v1_raises(self) -> None:
        """``enc:v1:`` 旧密文应显式抛 ``LegacySecretFormatError``。"""
        with pytest.raises(LegacySecretFormatError):
            decrypt_secret(
                "enc:v1:" + base64.b64encode(b"x" * 16).decode() +
                ":" + base64.b64encode(b"y" * 32).decode() +
                ":" + base64.b64encode(b"z").decode()
            )

    def test_decrypt_empty_and_none(self) -> None:
        assert decrypt_secret(None) is None
        assert decrypt_secret("") == ""
        assert encrypt_secret(None) is None
        assert encrypt_secret("") == ""

    def test_tampered_cipher_rejected(self) -> None:
        """AEAD 篡改密文应抛异常。"""
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        ct = parts[5]
        # 翻转首字符（保持 base64 合法）
        parts[5] = ("B" if ct[0] != "B" else "C") + ct[1:]
        tampered = ":".join(parts)
        with pytest.raises(ValueError, match="AES-GCM 解密或认证失败"):
            decrypt_secret(tampered)

    def test_tampered_tag_rejected(self) -> None:
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        tag = parts[4]
        parts[4] = ("Z" if tag[0] != "Z" else "Y") + tag[1:]
        tampered = ":".join(parts)
        with pytest.raises(ValueError, match="AES-GCM 解密或认证失败"):
            decrypt_secret(tampered)

    def test_tampered_salt_rejected(self) -> None:
        enc = encrypt_secret("top-secret")
        assert enc is not None and enc.startswith("enc:v2:")
        parts = enc.split(":")
        assert len(parts) == 6
        salt = parts[2]
        parts[2] = ("Z" if salt[0] != "Z" else "Y") + salt[1:]
        tampered = ":".join(parts)
        # salt 改变 → 派生 key 不同 → GCM 解密必失败（也可视为加密不可逆）
        with pytest.raises((ValueError, Exception)):
            decrypt_secret(tampered)

    def test_wrong_format_raises(self) -> None:
        with pytest.raises(ValueError, match="加密串格式错误"):
            decrypt_secret("enc:v2:only:four")

    def test_random_salt_and_nonce(self) -> None:
        """同一明文两次加密应得到不同密文（salt + nonce 随机）。"""
        a = encrypt_secret("same")
        b = encrypt_secret("same")
        assert a != b
        # 但都能解回原文
        assert decrypt_secret(a) == decrypt_secret(b) == "same"

    def test_unicode_roundtrip(self) -> None:
        plain = "你好世界 🔑 résumé"
        assert decrypt_secret(encrypt_secret(plain)) == plain
