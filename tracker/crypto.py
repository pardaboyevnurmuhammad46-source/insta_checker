import base64
import hashlib
import os
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken

_fernet_cache = {}


def get_fernet_key() -> bytes:
    key = getattr(settings, 'TOKEN_ENCRYPTION_KEY', None) or os.environ.get('TOKEN_ENCRYPTION_KEY')
    if not key:
        raise ValueError("TOKEN_ENCRYPTION_KEY sozlamasi yoki muhit o'zgaruvchisi topilmadi.")
    if isinstance(key, str):
        key = key.strip().encode('utf-8')

    try:
        Fernet(key)
        return key
    except Exception:
        # Agar kalit to'g'ridan-to'g'ri 32-baytli base64 Fernet kalit bo'lmasa,
        # uni SHA-256 orqali deterministik 32 baytli URL-safe base64 kalitga aylantiramiz
        return base64.urlsafe_b64encode(hashlib.sha256(key).digest())


def get_fernet() -> Fernet:
    key = get_fernet_key()
    if key not in _fernet_cache:
        _fernet_cache[key] = Fernet(key)
    return _fernet_cache[key]


def is_fernet_encrypted(value: str) -> bool:
    """
    Berilgan matn Fernet orqali shifrlanganligini tekshiradi.
    """
    if not value or not isinstance(value, str):
        return False
    if not value.startswith('gAAAAA'):
        return False
    try:
        f = get_fernet()
        f.decrypt(value.encode('utf-8'))
        return True
    except Exception:
        return False


def encrypt_token(token: str | None) -> str | None:
    """
    Instagram access tokenni Fernet bilan shifrlaydi.
    Agar allaqachon shifrlangan bo'lsa yoki bo'sh bo'lsa, o'zgarishsiz qaytaradi (idempotent).
    """
    if not token:
        return token
    if is_fernet_encrypted(token):
        return token
    f = get_fernet()
    return f.encrypt(str(token).encode('utf-8')).decode('utf-8')


def decrypt_token(encrypted_token: str | None) -> str | None:
    """
    Fernet bilan shifrlangan tokenni asliga qaytaradi (decrypt).
    Agar shifrlanmagan bo'lsa yoki bo'sh bo'lsa, ma'lumot yo'qolmasligi uchun o'z holicha qaytaradi.
    """
    if not encrypted_token:
        return encrypted_token
    if not isinstance(encrypted_token, str) or not encrypted_token.startswith('gAAAAA'):
        return encrypted_token
    f = get_fernet()
    try:
        return f.decrypt(encrypted_token.encode('utf-8')).decode('utf-8')
    except (InvalidToken, Exception):
        # Ma'lumot yo'qolmasligi uchun xato bersa ham asl qiymatni qaytaramiz
        return encrypted_token
