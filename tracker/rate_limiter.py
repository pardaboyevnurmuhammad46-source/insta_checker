import logging
import math
import time
import uuid
import redis
from django.conf import settings

logger = logging.getLogger(__name__)

# Redis Lua skript: Sliding Window log algoritmi asosida atomik cheklov
# KEYS[1]: Global sliding window kaliti ({ig_rate}:global)
# KEYS[2]: Instagram throttle / backoff bayrog'i ({ig_rate}:throttle_backoff)
# KEYS[3]: Akkaunt soniyalik cheklov kaliti ({ig_rate}:acc:{account_id}:sec) yoki bo'sh satr
# KEYS[4]: Akkaunt soatlik cheklov kaliti ({ig_rate}:acc:{account_id}:hour) yoki bo'sh satr
# ARGV[1]: Hozirgi vaqt (sekund, float)
# ARGV[2]: Global limit (sekundiga ruxsat etilgan so'rovlar soni)
# ARGV[3]: Akkaunt sekundiga limiti
# ARGV[4]: Akkaunt soatiga limiti
# ARGV[5]: Noyob so'rov identifikatori (uuid)
# ARGV[6]: Ushbu tranzaksiyadagi so'rovlar soni (requests_count)
SLIDING_WINDOW_LUA = """
local now = tonumber(ARGV[1])
local global_limit = tonumber(ARGV[2])
local account_sec_limit = tonumber(ARGV[3])
local account_hour_limit = tonumber(ARGV[4])
local unique_id = ARGV[5]
local requests_count = tonumber(ARGV[6]) or 1

-- 1. Instagram rate limit (backoff) mavjudligini tekshirish
local is_throttled = redis.call('EXISTS', KEYS[2])
if is_throttled == 1 then
    -- Agar Instagram'dan rate limit olingan bo'lsa, umumiy tezlik chegarasi yarmiga pasaytiriladi
    global_limit = math.max(1, math.floor(global_limit / 2))
end

-- 2. Global sliding window (1.0 soniya)
local global_window_start = now - 1.0
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', '(' .. global_window_start)
local global_count = redis.call('ZCARD', KEYS[1])
if global_count + requests_count > global_limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry_after = 1.0
    if oldest and #oldest >= 2 then
        retry_after = math.max(0.1, (tonumber(oldest[2]) + 1.0) - now)
    end
    return {0, tostring(retry_after), 'global_rate_limit'}
end

-- 3. Akkaunt soniyalik sliding window (1.0 soniya)
if KEYS[3] ~= '' and account_sec_limit > 0 then
    local acc_sec_start = now - 1.0
    redis.call('ZREMRANGEBYSCORE', KEYS[3], '-inf', '(' .. acc_sec_start)
    local acc_sec_count = redis.call('ZCARD', KEYS[3])
    if acc_sec_count + requests_count > account_sec_limit then
        local oldest = redis.call('ZRANGE', KEYS[3], 0, 0, 'WITHSCORES')
        local retry_after = 1.0
        if oldest and #oldest >= 2 then
            retry_after = math.max(0.1, (tonumber(oldest[2]) + 1.0) - now)
        end
        return {0, tostring(retry_after), 'account_sec_rate_limit'}
    end
end

-- 4. Akkaunt soatlik sliding window (3600.0 soniya)
if KEYS[4] ~= '' and account_hour_limit > 0 then
    local acc_hour_start = now - 3600.0
    redis.call('ZREMRANGEBYSCORE', KEYS[4], '-inf', '(' .. acc_hour_start)
    local acc_hour_count = redis.call('ZCARD', KEYS[4])
    if acc_hour_count + requests_count > account_hour_limit then
        local oldest = redis.call('ZRANGE', KEYS[4], 0, 0, 'WITHSCORES')
        local retry_after = 60.0
        if oldest and #oldest >= 2 then
            retry_after = math.max(1.0, (tonumber(oldest[2]) + 3600.0) - now)
        end
        return {0, tostring(retry_after), 'account_hour_rate_limit'}
    end
end

-- 5. Barcha chegaralardan muvaffaqiyatli o'tildi: barcha kalitlarga atomik yozish
for i=1, requests_count do
    local member_id = unique_id .. '_' .. tostring(i)
    redis.call('ZADD', KEYS[1], now, member_id)
    if KEYS[3] ~= '' and account_sec_limit > 0 then
        redis.call('ZADD', KEYS[3], now, member_id)
    end
    if KEYS[4] ~= '' and account_hour_limit > 0 then
        redis.call('ZADD', KEYS[4], now, member_id)
    end
end

redis.call('EXPIRE', KEYS[1], 2)
if KEYS[3] ~= '' and account_sec_limit > 0 then
    redis.call('EXPIRE', KEYS[3], 2)
end
if KEYS[4] ~= '' and account_hour_limit > 0 then
    redis.call('EXPIRE', KEYS[4], 3610)
end

return {1, '0', ''}
"""


class InstagramRateLimiter:
    """
    Barcha Celery worker'lar uchun Redis va Lua asosidagi umumiy tezlik cheklagich.
    - Global tezlik: settings.INSTAGRAM_API_RATE_LIMIT (standart: 50/s)
    - Akkaunt sekundiga: settings.INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_SEC (standart: 5/s)
    - Akkaunt soatiga: settings.INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR (standart: 200/h)
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._script = None

    def get_redis(self):
        if self._redis is None:
            url = getattr(
                settings,
                'REDIS_CACHE_URL',
                getattr(settings, 'CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0'),
            )
            self._redis = redis.Redis.from_url(url, decode_responses=True)
        return self._redis

    def _get_script(self):
        if self._script is None:
            r = self.get_redis()
            self._script = r.register_script(SLIDING_WINDOW_LUA)
        return self._script

    def acquire(self, account_id: str | int | None = None, requests_count: int = 1) -> tuple[bool, float, str]:
        """
        Instagram API ga so'rov yuborishdan oldin ruxsat so'raydi.
        Qaytaradi: (allowed, retry_after_seconds, reason)
        """
        global_limit = getattr(settings, 'INSTAGRAM_API_RATE_LIMIT', 50)
        account_sec_limit = getattr(settings, 'INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_SEC', 5)
        account_hour_limit = getattr(settings, 'INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR', 200)

        # Hash tags ishlatish orqali barcha kalitlar bitta Redis slotiga tushadi
        global_key = "{ig_rate}:global"
        throttle_key = "{ig_rate}:throttle_backoff"
        acc_sec_key = f"{{ig_rate}}:acc:{account_id}:sec" if account_id else ""
        acc_hour_key = f"{{ig_rate}}:acc:{account_id}:hour" if account_id else ""

        now = time.time()
        unique_id = f"{now}_{uuid.uuid4().hex[:8]}"

        try:
            script = self._get_script()
            result = script(
                keys=[global_key, throttle_key, acc_sec_key, acc_hour_key],
                args=[now, global_limit, account_sec_limit, account_hour_limit, unique_id, requests_count],
            )
            # result: [allowed_int, retry_after_str, reason_str]
            allowed = bool(result[0] == 1)
            retry_after = float(result[1])
            reason = str(result[2])
            return allowed, retry_after, reason
        except Exception as exc:
            logger.error("Rate limiter Redis xatoligi: %s. So'rovga xavfsizlik uchun ruxsat berildi.", exc)
            return True, 0.0, ""

    def trigger_backoff(self, duration_seconds: int = 60):
        """
        Instagram rate limit xatosi (4, 17, 32, 613 yoki 429) yuz berganda
        umumiy tezlikni belgilangan vaqt davomida yarmiga pasaytiradi.
        """
        try:
            r = self.get_redis()
            throttle_key = "{ig_rate}:throttle_backoff"
            r.set(throttle_key, "1", ex=duration_seconds)
            logger.warning(
                "Instagram rate limit aniqlandi: umumiy tezlik %d soniyaga 50%% ga pasaytirildi.",
                duration_seconds,
            )
        except Exception as exc:
            logger.error("Rate limiter backoff belgilashda xatolik: %s", exc)

    def is_throttled(self) -> bool:
        """Cheklagich hozir pasaytirilgan (backoff) rejimdami?"""
        try:
            r = self.get_redis()
            return bool(r.exists("{ig_rate}:throttle_backoff"))
        except Exception:
            return False

    def get_rate_limited_accounts_count(self) -> int:
        """
        Limitga yetgan (soatiga 200 tadan oshgan) faol akkauntlar sonini qaytaradi.
        """
        try:
            r = self.get_redis()
            account_hour_limit = getattr(settings, 'INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR', 200)
            now = time.time()
            count = 0
            for key in r.scan_iter(match="{ig_rate}:acc:*:hour"):
                r.zremrangebyscore(key, '-inf', f"({now - 3600.0}")
                if r.zcard(key) >= account_hour_limit:
                    count += 1
            return count
        except Exception as exc:
            logger.error("Limitga yetgan akkauntlarni hisoblashda xatolik: %s", exc)
            return 0

    def reset(self, account_id: str | int | None = None):
        """Kesh va hisoblagichlarni tozalash (asosan testlar uchun)."""
        try:
            r = self.get_redis()
            keys = ["{ig_rate}:global", "{ig_rate}:throttle_backoff"]
            if account_id:
                keys.extend([
                    f"{{ig_rate}}:acc:{account_id}:sec",
                    f"{{ig_rate}}:acc:{account_id}:hour",
                ])
            r.delete(*keys)
        except Exception:
            pass


rate_limiter = InstagramRateLimiter()
