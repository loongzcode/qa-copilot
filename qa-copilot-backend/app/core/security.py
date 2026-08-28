from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any, Literal

import jwt
from cryptography.fernet import Fernet, MultiFernet
from pwdlib import PasswordHash

from app.core.config import settings

password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """使用 Argon2 算法保存密码，数据库中不存储明文。"""

    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    return password_hash.verify(password, hashed_password)


def create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    now: datetime = datetime.now(tz=UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")
    

def decode_token(token: str, expected_type: Literal["access", "refresh"]) -> dict[str, Any]:
    payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("令牌类型不正确")
    return payload


def create_access_token(subject: str) -> str:
    return create_token(
        subject,
        token_type="access",
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(subject: str) -> str:
    return create_token(
        subject,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
    )


@lru_cache
def _get_fernet() -> MultiFernet:
    """创建数据加密器；首个密钥负责加密，旧密钥仅用于轮换期解密。"""

    keys = [
        settings.data_encryption_key,
        *settings.data_encryption_previous_keys,
    ]
    return MultiFernet(
        [Fernet(key.get_secret_value().encode("utf-8")) for key in keys]
    )


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def rotate_secret(value: str) -> str:
    """使用当前主密钥重新加密由旧密钥生成的 Fernet 密文。"""

    if not value:
        return ""
    return _get_fernet().rotate(value.encode("utf-8")).decode("utf-8")


def mask_secret(value: str) -> str:
    """接口返回时只展示首尾少量字符，防止密钥泄露到浏览器。"""

    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:3]}****{value[-4:]}"
