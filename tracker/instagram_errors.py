from enum import Enum
import json
import logging
import re
import time
import redis
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class InstagramErrorType(str, Enum):
    """
    Instagram Graph API xatolik turlari (BOSQICH 10 talabi bo'yicha).
    """
    MEDIA_NOT_FOUND = "media_not_found"      # (a) media yo'q/o'chirilgan
    TOKEN_INVALID = "token_invalid"          # (b) token yaroqsiz/bekor qilingan
    PERMISSION_DENIED = "permission_denied"  # (c) ruxsat (permission) yetishmaydi
    RATE_LIMIT = "rate_limit"                # (d) Instagram rate limit/throttle
    SERVER_ERROR = "server_error"            # (e) vaqtinchalik server xatosi
    OTHER = "other"                          # (f) boshqa


# ==============================================================================
# Meta Graph API Rasmiy Xatoliklar Jadvali
# Manba: developers.facebook.com/docs/graph-api/guides/error-handling
#        developers.facebook.com/docs/graph-api/overview/rate-limiting
# ==============================================================================
META_ERROR_CATALOG = [
    {
        "type": InstagramErrorType.RATE_LIMIT,
        "name": "Instagram Rate Limit / Throttle",
        "codes": {4, 17, 32, 341, 613},
        "subcodes": {1996, 2446079},
        "code_subcodes": {
            (17, 2446079),  # Ads/API rate limit
            (613, 1996),    # Custom rate limit: inconsistent behavior
        },
        "http_statuses": {429},
        "description": "Instagram so'rovlar limiti oshdi (app, user, page yoki custom throttle)",
    },
    {
        "type": InstagramErrorType.TOKEN_INVALID,
        "name": "Token Invalid / Expired / Revoked",
        "codes": {102, 190},
        "subcodes": {458, 459, 460, 463, 464, 467, 490, 491, 492},
        "code_subcodes": {
            (190, 458),     # App uninstalled
            (190, 459),     # User checkpointed
            (190, 460),     # Password changed
            (190, 463),     # Token expired
            (190, 464),     # Unconfirmed user
            (190, 467),     # Invalid access token
            (190, 490),     # Invalid user session
            (190, 491),     # Invalid user session
            (190, 492),     # Invalid user session
        },
        "http_statuses": {401},
        "description": "Foydalanuvchi tokeni muddati o'tgan, bekor qilingan yoki sessiya yaroqsiz",
    },
    {
        "type": InstagramErrorType.MEDIA_NOT_FOUND,
        "name": "Media Missing / Deleted",
        "codes": {24, -2},
        "code_subcodes": {
            (100, 33),      # Unsupported get request. Object does not exist / deleted
            (24, 2207006),  # Media Not Found / The requested resource does not exist
            (-2, 2207020),  # Media has expired
        },
        "http_statuses": {404},
        "description": "Media obyekti topilmadi yoki o'chirilgan (Code 100 / Subcode 33 yoki HTTP 404)",
    },
    {
        "type": InstagramErrorType.PERMISSION_DENIED,
        "name": "Permission Denied",
        "codes": {3, 10},
        "code_ranges": [(200, 299)],
        "http_statuses": {403},
        "description": "Ilova yoki token kerakli ruxsatnomalarga (permissions) ega emas",
    },
    {
        "type": InstagramErrorType.SERVER_ERROR,
        "name": "Temporary Server Error",
        "codes": {1, 2},
        "code_subcodes": set(),
        "http_statuses": {500, 502, 503, 504},
        "description": "Meta serverlarida texnik uzilish yoki vaqtinchalik xatolik",
    },
]


def classify_instagram_error(
    response: requests.Response | None = None,
    status_code: int | None = None,
    error_code: int | None = None,
    error_subcode: int | None = None,
    error_message: str | None = None,
    exception: Exception | None = None,
) -> InstagramErrorType:
    """
    Instagram Graph API xatosini tahlil qiladi va 6 ta turdan biriga ajratadi:
    (a) media_not_found
    (b) token_invalid
    (c) permission_denied
    (d) rate_limit
    (e) server_error
    (f) other

    Meta hujjatlari (code va error_subcode) asosida ishlaydi.
    """
    # 1. Tarmoq xatoliklari va istisnolar
    if exception is not None:
        if isinstance(exception, (requests.RequestException, TimeoutError, ConnectionError)):
            return InstagramErrorType.SERVER_ERROR

    # 2. Response obyekti berilgan bo'lsa, status va JSON ma'lumotlarini ajratib olamiz
    if response is not None:
        if status_code is None:
            status_code = response.status_code
        try:
            body = response.json()
            if isinstance(body, dict):
                err = body.get('error')
                if isinstance(err, dict):
                    if error_code is None and 'code' in err:
                        raw_c = err.get('code')
                        if isinstance(raw_c, (int, str)) and str(raw_c).lstrip('-').isdigit():
                            error_code = int(raw_c)
                    if error_subcode is None and 'error_subcode' in err:
                        raw_sc = err.get('error_subcode')
                        if isinstance(raw_sc, (int, str)) and str(raw_sc).lstrip('-').isdigit():
                            error_subcode = int(raw_sc)
                    if error_message is None and 'message' in err:
                        raw_msg = err.get('message')
                        if isinstance(raw_msg, str):
                            error_message = raw_msg
        except Exception:
            pass

    # 3. Aniq (code, subcode) juftligini tekshirish (eng yuqori aniqlik)
    if error_code is not None and error_subcode is not None:
        pair = (error_code, error_subcode)
        for rule in META_ERROR_CATALOG:
            if pair in rule.get('code_subcodes', set()):
                return rule['type']

    # 4. Error subcode bo'yicha tekshirish (masalan 190 subkodlari: 463, 467, 458 ...)
    if error_subcode is not None:
        for rule in META_ERROR_CATALOG:
            if error_subcode in rule.get('subcodes', set()):
                return rule['type']

    # 5. Error code bo'yicha tekshirish
    if error_code is not None:
        # Rate limit kodlari: 4, 17, 32, 341, 613
        if error_code in {4, 17, 32, 341, 613}:
            return InstagramErrorType.RATE_LIMIT
        # Token yaroqsizlik kodlari: 190, 102
        if error_code in {190, 102}:
            return InstagramErrorType.TOKEN_INVALID
        # Server xatoliklari: 1, 2
        if error_code in {1, 2}:
            return InstagramErrorType.SERVER_ERROR
        # Permission kodlari: 10, 3 yoki 200..299 oralig'i
        if error_code in {3, 10} or (200 <= error_code <= 299):
            return InstagramErrorType.PERMISSION_DENIED
        # Media not found kodlari: 24, -2
        if error_code in {24, -2}:
            return InstagramErrorType.MEDIA_NOT_FOUND

    # 6. HTTP Status Code bo'yicha tekshirish
    if status_code is not None:
        if status_code == 429:
            return InstagramErrorType.RATE_LIMIT
        if status_code == 401:
            return InstagramErrorType.TOKEN_INVALID
        if status_code == 403:
            return InstagramErrorType.PERMISSION_DENIED
        if status_code in {500, 502, 503, 504}:
            return InstagramErrorType.SERVER_ERROR
        if status_code == 404:
            return InstagramErrorType.MEDIA_NOT_FOUND

    # 7. Xato matniga ko'ra qo'shimcha aniqlash (fallback)
    if error_message:
        msg_lower = error_message.lower()
        if "rate limit" in msg_lower or "too many calls" in msg_lower or "user request limit" in msg_lower:
            return InstagramErrorType.RATE_LIMIT
        if "unsupported get request" in msg_lower and "does not exist" in msg_lower:
            return InstagramErrorType.MEDIA_NOT_FOUND
        if "tried accessing nonexisting field" in msg_lower:
            return InstagramErrorType.MEDIA_NOT_FOUND
        if "access token" in msg_lower and ("invalid" in msg_lower or "expired" in msg_lower or "session" in msg_lower):
            return InstagramErrorType.TOKEN_INVALID
        if "permission" in msg_lower:
            return InstagramErrorType.PERMISSION_DENIED

    return InstagramErrorType.OTHER


# ==============================================================================
# Token va Maxfiy Ma'lumotlarni Maskalash (Masking)
# ==============================================================================
SENSITIVE_PATTERNS = [
    # access_token=... yoki token=...
    (re.compile(r'((?:access_token|client_secret|token|secret)\s*[:=]\s*["\']?)([^"\'&\s]+)(["\']?)', re.IGNORECASE), r'\1***\3'),
    # Bearer header tokenlari
    (re.compile(r'(Bearer\s+)([a-zA-Z0-9_\-\.]+)', re.IGNORECASE), r'\1***'),
    # Meta access token prefikslari (masalan EAAB..., IGQV..., IGAA...)
    (re.compile(r'\b(EAAB[a-zA-Z0-9_\-]{10,})\b'), r'EAAB***'),
    (re.compile(r'\b(IGQV[a-zA-Z0-9_\-]{10,})\b'), r'IGQV***'),
    (re.compile(r'\b(IGAA[a-zA-Z0-9_\-]{10,})\b'), r'IGAA***'),
    # Fernet encrypted tokenlar
    (re.compile(r'\b(gAAAAA[a-zA-Z0-9_\-]{20,})\b'), r'gAAAAA***'),
    # Dry run mock tokenlar
    (re.compile(r'\b(dry_run_[a-zA-Z0-9_\-]{8,})\b'), r'dry_run_***'),
]


def mask_sensitive_data(text: str) -> str:
    """
    Log va xato xabarlaridagi token va maxfiy ma'lumotlarni yashiradi.
    """
    if not text:
        return ""
    result = str(text)
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def log_instagram_error(
    error_type: InstagramErrorType,
    message: str,
    post_id: int | None = None,
    account_id: int | None = None,
    code: int | None = None,
    subcode: int | None = None,
):
    """
    Maskalangan qisqa xato logini yozadi.
    """
    masked_msg = mask_sensitive_data(message)
    details = []
    if post_id is not None:
        details.append(f"post_id={post_id}")
    if account_id is not None:
        details.append(f"account_id={account_id}")
    if code is not None:
        details.append(f"code={code}")
    if subcode is not None:
        details.append(f"subcode={subcode}")

    ctx = f" ({', '.join(details)})" if details else ""
    logger.warning("Instagram xatosi [%s]%s: %s", error_type.value, ctx, masked_msg)


# ==============================================================================
# Oxirgi 1 soat ichidagi xato turlari hisoblagichlari (Redis)
# ==============================================================================
def get_redis_client():
    url = getattr(
        settings,
        'REDIS_CACHE_URL',
        getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0'),
    )
    return redis.Redis.from_url(url, decode_responses=True)


def record_instagram_error(error_type: InstagramErrorType | str):
    """
    Xatolik yuz berganda uni joriy daqiqa chelagiga yozadi.
    Har bir daqiqa kalitining TTL muddati 3700 soniya (~61 daqiqa).
    """
    if isinstance(error_type, InstagramErrorType):
        err_key = error_type.value
    else:
        err_key = str(error_type)

    now_ts = int(time.time())
    minute_ts = now_ts // 60
    redis_key = f"{{ig_err}}:min:{minute_ts}"

    try:
        r = get_redis_client()
        pipe = r.pipeline()
        pipe.hincrby(redis_key, err_key, 1)
        pipe.expire(redis_key, 3700)
        pipe.execute()
    except Exception as exc:
        logger.error("Xatolik hisoblagichini Redis'ga yozishda muammo: %s", exc)


def get_instagram_errors_last_hour() -> dict[str, int]:
    """
    Oxirgi 1 soat (60 daqiqa) ichidagi barcha xato turlari sonini qaytaradi.
    """
    result = {t.value: 0 for t in InstagramErrorType}
    result["total"] = 0

    now_ts = int(time.time())
    current_minute = now_ts // 60

    try:
        r = get_redis_client()
        pipe = r.pipeline()
        for i in range(60):
            pipe.hgetall(f"{{ig_err}}:min:{current_minute - i}")
        buckets = pipe.execute()

        for bucket in buckets:
            if bucket and isinstance(bucket, dict):
                for err_type, count_str in bucket.items():
                    try:
                        cnt = int(count_str)
                    except (ValueError, TypeError):
                        cnt = 0
                    if err_type in result:
                        result[err_type] += cnt
                    else:
                        result[err_type] = cnt
                    result["total"] += cnt
    except Exception as exc:
        logger.error("Oxirgi 1 soatdagi xatolarni Redis'dan o'qishda muammo: %s", exc)

    return result


def reset_error_counters():
    """
    Xatolik hisoblagichlarini tozalash (testlar uchun).
    """
    try:
        r = get_redis_client()
        now_ts = int(time.time())
        current_minute = now_ts // 60
        keys = [f"{{ig_err}}:min:{current_minute - i}" for i in range(120)]
        r.delete(*keys)
    except Exception:
        pass
