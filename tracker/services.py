import base64
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
import uuid
from datetime import timedelta
import requests
from django.conf import settings
from django.utils import timezone
# from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest, get_video_for_user, PostStat, Notification
from .rate_limiter import rate_limiter
from .instagram_errors import (
    InstagramErrorType,
    classify_instagram_error,
    log_instagram_error,
    mask_sensitive_data,
    record_instagram_error,
)
from .exceptions import (
    InstagramBaseError,
    InstagramNetworkError,
    InstagramOAuthError,
    InstagramOAuthNetworkError,
    InstagramPublishError,
    InstagramPublishNetworkError,
    InstagramMetricsError,
    InstagramRateLimitError,
    InstagramMetricsNetworkError,
    MetaWebhookError,
)
from .instagram_client import get_instagram_client

logger = logging.getLogger(__name__)


# ==========================================
# 1. Instagram OAuth & Token boshqaruvi
# ==========================================

def build_instagram_auth_url(token: str) -> str:
    return get_instagram_client().build_auth_url(token)


def exchange_code_for_token(code: str) -> dict:
    return get_instagram_client().exchange_code_for_token(code)


def get_long_lived_token(short_lived_token: str) -> dict:
    return get_instagram_client().get_long_lived_token(short_lived_token)


def refresh_instagram_access_token(access_token: str) -> dict:
    return get_instagram_client().refresh_access_token(access_token)


def refresh_user_token(user: InstagramUser) -> bool:
    """
    InstagramUser uchun tokenni yangilaydi va saqlaydi.
    Tarmoq xatosi bo'lsa status o'zgarmaydi.
    Faqat token bekor qilingan (OAuth xatosi) bo'lsa, 'needs_reauth' holatiga o'tkazadi.
    """
    if not user.access_token:
        return False

    try:
        data = refresh_instagram_access_token(user.access_token)
        new_token = data.get('access_token')
        expires_in = data.get('expires_in', 5184000)
        if new_token:
            user.access_token = new_token
        user.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
        user.status = 'connected'
        user.save(update_fields=['access_token', 'token_expires_at', 'status'])
        logger.info("InstagramUser token yangilandi: user_id=%s", user.id)
        return True
    except InstagramNetworkError as exc:
        logger.warning("Foydalanuvchi tokenini yangilashda tarmoq xatosi (user_id=%s): %s", user.id, exc)
        return False
    except InstagramOAuthError as exc:
        logger.warning("Foydalanuvchi tokenini yangilab bo'lmadi (user_id=%s): %s", user.id, exc)
        user.status = 'needs_reauth'
        user.save(update_fields=['status'])
        return False


REQUIRED_PERMISSIONS = {
    'instagram_business_content_publish',
    'instagram_business_manage_insights',
    'instagram_business_manage_comments',
}


def verify_token_permissions(access_token: str) -> tuple[bool, list[str]]:
    return get_instagram_client().verify_token_permissions(access_token)


def check_instagram_account_type(access_token: str, ig_user_id: str = 'me') -> str:
    return get_instagram_client().check_account_type(access_token, ig_user_id)


def complete_instagram_oauth(code: str, token: str) -> tuple[InstagramUser, UniqueLink]:
    try:
        link = UniqueLink.objects.select_related('user').get(token=token)
    except UniqueLink.DoesNotExist as exc:
        raise InstagramOAuthError("Bunday unikal link topilmadi.") from exc

    token_data = exchange_code_for_token(code)
    short_lived_token = token_data.get('access_token')
    ig_user_id = str(token_data.get('user_id', ''))

    if not short_lived_token:
        raise InstagramOAuthError("Instagram javobida access_token mavjud emas.")

    try:
        long_token_data = get_long_lived_token(short_lived_token)
        final_token = long_token_data.get('access_token', short_lived_token)
        expires_in = long_token_data.get('expires_in', 5184000)
    except InstagramOAuthError:
        final_token = short_lived_token
        expires_in = 3600

    # Token ruxsatlarini tekshirish
    has_perms, missing = verify_token_permissions(final_token)
    if not has_perms:
        link.user.status = 'needs_reauth'
        link.user.save(update_fields=['status'])
        raise InstagramOAuthError(
            f"Instagram ruxsatlari to'liq berilmagan ({', '.join(missing)} yetishmayapti). "
            "Iltimos, qayta ulaning va barcha ruxsatlarga (publish, insights, comments) rozilik bering."
        )

    # Akkaunt turini tekshirish (faqat Business/Creator akkauntlar qo'llab-quvvatlanadi)
    acc_type = check_instagram_account_type(final_token, ig_user_id or 'me')
    if acc_type == 'PERSONAL':
        link.user.status = 'needs_reauth'
        link.user.save(update_fields=['status'])
        raise InstagramOAuthError(
            "Sizning Instagram akkauntingiz shaxsiy (Personal). "
            "Reels avtomatik joylash faqat Professional (Business yoki Creator) akkauntlar uchun amal qiladi. "
            "Iltimos, Instagram hisobingizni Professional akkauntga o'tkazing."
        )

    user = link.user
    user.ig_user_id = ig_user_id or user.ig_user_id
    user.access_token = final_token
    user.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    user.status = 'connected'
    user.save(update_fields=['ig_user_id', 'access_token', 'token_expires_at', 'status'])

    if link.status == 'pending':
        link.status = 'opened'
        link.save(update_fields=['status'])

    return user, link


# ==========================================
# 2. Instagram Reels joylash (Publishing)
# ==========================================

def create_reels_container(ig_user_id: str, video_url: str, access_token: str, caption: str = '') -> str:
    return get_instagram_client().create_reels_container(ig_user_id, video_url, access_token, caption)


def check_container_status(container_id: str, access_token: str) -> dict:
    return get_instagram_client().check_container_status(container_id, access_token)


def wait_for_container_ready(container_id: str, access_token: str, max_attempts: int = 12, delay: int = 5) -> bool:
    return get_instagram_client().wait_for_container_ready(container_id, access_token, max_attempts=max_attempts, delay=delay)


def publish_container(ig_user_id: str, container_id: str, access_token: str) -> str:
    return get_instagram_client().publish_container(ig_user_id, container_id, access_token)


def get_media_permalink(ig_media_id: str, access_token: str) -> str:
    return get_instagram_client().get_media_permalink(ig_media_id, access_token)


def publish_reels_for_link(link_id: int, caption: str = '') -> Post:
    try:
        link = UniqueLink.objects.select_related('user').get(id=link_id)
    except UniqueLink.DoesNotExist as exc:
        raise InstagramPublishError(f"UniqueLink topilmadi: id={link_id}") from exc

    user = link.user
    if user.status != 'connected' or not user.access_token or not user.ig_user_id:
        raise InstagramPublishError("Foydalanuvchi Instagram akkauntini ulamagan yoki token yo'q.")

    # Akkaunt turini tekshirish (shaxsiy akkauntlarga Reels joylab bo'lmaydi)
    acc_type = check_instagram_account_type(user.access_token, user.ig_user_id)
    if acc_type == 'PERSONAL':
        err_msg = "Sizning Instagram akkauntingiz shaxsiy (Personal). Reels avtomatik joylash faqat Professional (Business yoki Creator) akkauntlar uchun amal qiladi."
        post, _ = Post.objects.get_or_create(link=link)
        post.status = 'failed'
        post.error = err_msg
        post.save(update_fields=['status', 'error'])
        link.status = 'failed'
        link.save(update_fields=['status'])
        raise InstagramPublishError(err_msg)

    # 1-bosqichdagi video tanlash qoidasi orqali videoni aniqlash
    chosen_video = link.video or get_video_for_user(user)
    if not chosen_video:
        err_msg = "Joylash uchun video fayl mavjud emas. Linkka video biriktirilmagan va tizimda faol umumiy (default) video ham yo'q."
        post, _ = Post.objects.get_or_create(link=link)
        post.status = 'failed'
        post.error = err_msg
        post.save(update_fields=['status', 'error'])
        link.status = 'failed'
        link.save(update_fields=['status'])
        raise InstagramPublishError(err_msg)

    # Video faylining mavjudligi va hajm tekshiruvi (dummy 4-10 baytli fayllar uchun)
    try:
        file_size = chosen_video.file.size if chosen_video.file else 0
    except Exception:
        file_size = 0

    if not chosen_video.file or file_size == 0:
        err_msg = f"Joylash uchun video fayli topilmadi yoki bo'sh ({chosen_video.title})."
        post, _ = Post.objects.get_or_create(link=link)
        post.status = 'failed'
        post.error = err_msg
        post.save(update_fields=['status', 'error'])
        link.status = 'failed'
        link.save(update_fields=['status'])
        raise InstagramPublishError(err_msg)

    if link.video != chosen_video:
        link.video = chosen_video
        link.save(update_fields=['video'])

    post, _ = Post.objects.get_or_create(link=link)
    # Idempotentlik: agar post allaqachon published bo'lsa (masalan Celery retry paytida), qayta joylamaymiz
    if post.status == 'published' and post.ig_media_id:
        logger.info("Post allaqachon muvaffaqiyatli nashr etilgan (link_id=%s, media_id=%s)", link_id, post.ig_media_id)
        return post

    post.status = 'publishing'
    post.save(update_fields=['status'])

    # video_url ommaviy tashqi URL bo'lishi shart (Instagram serveri yuklashi uchun)
    video_url = chosen_video.url
    if not video_url.startswith(('http://', 'https://')):
        base = getattr(settings, 'PUBLIC_BASE_URL', '') or getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        base = base.rstrip('/')
        video_url = f"{base}{video_url}"

    try:
        container_id = create_reels_container(
            ig_user_id=user.ig_user_id,
            video_url=video_url,
            access_token=user.access_token,
            caption=caption,
        )

        wait_for_container_ready(container_id, user.access_token)

        ig_media_id = publish_container(user.ig_user_id, container_id, user.access_token)

        permalink = get_media_permalink(ig_media_id, user.access_token)

        post.ig_media_id = ig_media_id
        post.permalink = permalink
        post.status = 'published'
        post.posted_at = timezone.now()
        post.next_check_at = calculate_next_check(post)
        post.error = None
        post.save(update_fields=['ig_media_id', 'permalink', 'status', 'posted_at', 'next_check_at', 'error'])

        link.status = 'posted'
        link.save(update_fields=['status'])

        return post
    except Exception as exc:
        post.status = 'failed'
        clean_err = str(exc)
        if "access_token" in clean_err:
            clean_err = "Instagram API autentifikatsiya xatoligi yuz berdi."
        post.error = clean_err[:500]
        post.save(update_fields=['status', 'error'])
        link.status = 'failed'
        link.save(update_fields=['status'])
        raise
    # except Exception as exc:
    #     post.status = 'failed'
    #     post.error = str(exc)
    #     post.save(update_fields=['status', 'error'])
    #     link.status = 'failed'
    #     link.save(update_fields=['status'])
    #     raise


# ==========================================
# 3. Adaptiv jadval va Metrikalarni tekshirish
# ==========================================

def calculate_next_check(post: Post, now=None) -> timezone.datetime | None:
    """
    Post yoshiga va prizga yaqinligiga qarab keyingi tekshirish vaqtini adaptiv hisoblaydi:
    - 0 .. 6 soat: har 15 daqiqada
    - 6 .. 24 soat: har 1 soatda
    - 1 .. 3 kun: har 3 soatda
    - 3 .. 30 kun: har 24 soatda
    - 30 kundan keyin: haftada 1 marta (7 kun)
    Agar views kutilayotgan prizning 80% iga yetgan bo'lsa -> har 15 daqiqada.
    """
    if post.status != 'published' or not post.posted_at:
        return None

    if now is None:
        now = timezone.now()

    # Prizga yaqinlikni tekshirish
    milestones = get_configured_milestones()
    awarded_milestones = list(post.prizes.values_list('milestone', flat=True))
    next_milestone = None
    for m in sorted(milestones):
        if m not in awarded_milestones:
            next_milestone = m
            break

    if next_milestone and post.views >= (next_milestone * 0.8):
        return now + timedelta(minutes=15)

    age = now - post.posted_at
    if age < timedelta(hours=6):
        return now + timedelta(minutes=15)
    elif age < timedelta(hours=24):
        return now + timedelta(hours=1)
    elif age < timedelta(days=3):
        return now + timedelta(hours=3)
    elif age < timedelta(days=30):
        return now + timedelta(days=1)
    else:
        return now + timedelta(days=7)


def fetch_post_metrics_from_instagram(ig_media_id: str, access_token: str, post_id: int | None = None) -> dict:
    """
    Instagram Graph API orqali media metrikalarini (likes, comments, views) oladi.
    Haqiqiy yoki DRY_RUN rejimiga qarab tegishli mijoz adapteridan foydalanadi.
    """
    return get_instagram_client().fetch_post_metrics(ig_media_id, access_token, post_id=post_id)


def update_post_metrics(post: Post) -> Post:
    """
    Post statistikasini Instagram'dan tortib oladi, bazani yangilaydi va sovrinlarni tekshiradi.
    """
    user = post.link.user
    if not user.access_token or user.status != 'connected':
        post.error = "Foydalanuvchi akkaunti ulanmagan yoki token mavjud emas."
        post.next_check_at = None
        post.save(update_fields=['error', 'next_check_at'])
        return post

    try:
        metrics = fetch_post_metrics_from_instagram(post.ig_media_id, user.access_token, post_id=post.id)
        post.likes = metrics['likes']
        post.comments_count = metrics['comments_count']
        if metrics['views'] > 0 or post.views == 0:
            post.views = metrics['views']

        post.last_checked_at = timezone.now()
        post.next_check_at = calculate_next_check(post)
        post.error = None
        post.save(update_fields=['likes', 'comments_count', 'views', 'last_checked_at', 'next_check_at', 'error'])

        # Tarix (PostStat) yozish
        PostStat.objects.create(
            post=post,
            views=post.views,
            likes=post.likes,
            comments_count=post.comments_count,
        )

        # Sovrin berish logikasi
        check_and_award_prizes(post)
        return post

    except InstagramMetricsError as exc:
        error_type = getattr(exc, 'error_type', None)

        # (d) Rate limit / throttle holati
        if isinstance(exc, InstagramRateLimitError) or error_type == InstagramErrorType.RATE_LIMIT:
            # 4-talab: Instagram rate limit xatosi kelsa, umumiy cheklagich vaqtincha pasaytirilsin
            # (masalan 1 daqiqaga yarimiga), postlar o'chirilgan yoki xato deb belgilanmasin.
            rate_limiter.trigger_backoff(duration_seconds=60)
            logger.warning(
                "Instagram rate limit xatosi (post_id=%s): umumiy tezlik 60s ga 50%% ga pasaytirildi. Post holati saqlandi.",
                post.id,
            )
            # Post o'chirilgan yoki xato deb belgilanmasin: status va error o'zgartirilmaydi!
            post.next_check_at = timezone.now() + timedelta(minutes=1)
            post.save(update_fields=['next_check_at'])
            return post

        # (e) Tarmoq yoki server xatoligi
        if isinstance(exc, InstagramNetworkError) or error_type == InstagramErrorType.SERVER_ERROR:
            raise

        # (a) Media topilmadi / o'chirilgan
        if exc.is_deleted or error_type == InstagramErrorType.MEDIA_NOT_FOUND:
            post.status = 'deleted'
            post.next_check_at = None
            post.deleted_detected_at = timezone.now()
            post.error = "Instagram'dan post o'chirilgan."
            post.save(update_fields=['status', 'next_check_at', 'deleted_detected_at', 'error'])

        # (c) Ruxsat yetishmaydi
        elif error_type == InstagramErrorType.PERMISSION_DENIED:
            user.status = 'needs_reauth'
            user.save(update_fields=['status'])
            post.error = "Instagram ruxsati (permission) yetishmaydi."
            post.next_check_at = None
            post.save(update_fields=['error', 'next_check_at'])

        # (b) Token yaroqsiz / bekor qilingan
        elif error_type == InstagramErrorType.TOKEN_INVALID or exc.is_auth_error:
            user.status = 'needs_reauth'
            user.save(update_fields=['status'])
            post.error = "Instagram tokeni yaroqsiz (needs_reauth)."
            post.next_check_at = None
            post.save(update_fields=['error', 'next_check_at'])

        # (f) Boshqa xatolar
        else:
            post.error = mask_sensitive_data(str(exc))
            post.next_check_at = timezone.now() + timedelta(minutes=30)
            post.save(update_fields=['error', 'next_check_at'])

        return post


# ==========================================
# 4. Sovrinlar (Prize) berish logikasi
# ==========================================

DEFAULT_PRIZE_MILESTONES = [500, 1000, 5000, 10000, 50000, 100000]


def get_configured_milestones() -> list[int]:
    raw = getattr(settings, 'PRIZE_MILESTONES', None)
    if not raw:
        return DEFAULT_PRIZE_MILESTONES
    if isinstance(raw, (list, tuple)):
        return [int(x) for x in raw]
    if isinstance(raw, str):
        return [int(x.strip()) for x in raw.split(',') if x.strip().isdigit()]
    return DEFAULT_PRIZE_MILESTONES


def check_and_award_prizes(post: Post) -> list[Prize]:
    """
    Post ko'rishlar soni (views) marralarga (milestones) yetganida Prize yozuvini yaratadi.
    """
    milestones = get_configured_milestones()
    awarded = []
    for milestone in sorted(milestones):
        if post.views >= milestone:
            prize, created = Prize.objects.get_or_create(
                post=post,
                milestone=milestone,
                defaults={'sent_at': timezone.now()},
            )
            if created:
                awarded.append(prize)
                logger.info("Yangi sovrin berildi: post_id=%s, milestone=%s", post.id, milestone)
    return awarded


# ==========================================
# 5. Meta Deauthorize & Data Deletion
# ==========================================

def parse_signed_request(signed_request: str, app_secret: str) -> dict:
    """
    Meta signed_request parametrini tahlil qiladi va imzosini tekshiradi (HMAC-SHA256).
    """
    if not signed_request or '.' not in signed_request:
        raise MetaWebhookError("Noto'g'ri signed_request formati.")

    try:
        encoded_sig, payload = signed_request.split('.', 1)
        sig_padding = '=' * (-len(encoded_sig) % 4)
        sig = base64.urlsafe_b64decode(encoded_sig + sig_padding)

        payload_padding = '=' * (-len(payload) % 4)
        data_json = base64.urlsafe_b64decode(payload + payload_padding).decode('utf-8')
        data = json.loads(data_json)
    except Exception as exc:
        raise MetaWebhookError(f"signed_request dekodlashda xatolik: {exc}") from exc

    if not app_secret:
        raise MetaWebhookError("INSTAGRAM_APP_SECRET sozlanmagan.")

    expected_sig = hmac.new(
        app_secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).digest()

    if not hmac.compare_digest(sig, expected_sig):
        raise MetaWebhookError("Imzo mos kelmadi (invalid signature).")

    return data


def handle_deauthorize_request(user_id: str) -> int:
    """
    Foydalanuvchi ilovadan ruxsatni bekor qilganda chaqiriladi.
    Statusni 'needs_reauth' qiladi va tokenni tozalaydi.
    """
    updated_count = InstagramUser.objects.filter(ig_user_id=str(user_id)).update(
        status='needs_reauth',
        access_token=None,
    )
    logger.info("Foydalanuvchi deautorizatsiya qilindi: ig_user_id=%s, soni=%s", user_id, updated_count)
    return updated_count


def handle_data_deletion_request(user_id: str) -> tuple[str, str]:
    """
    Meta Data Deletion Request callback mantiqi.
    Qaytaradi: (tracking_url, confirmation_code)
    """
    confirmation_code = uuid.uuid4().hex
    users = InstagramUser.objects.filter(ig_user_id=str(user_id))
    # for user in users:
    #     user.status = 'needs_reauth'
    #     user.access_token = None
    #     user.name = f"Deleted User {user.id}"
    #     user.save(update_fields=['status', 'access_token', 'name'])

    for user in users:
        user.status = 'needs_reauth'
        user.access_token = None
        user.token_expires_at = None
        user.ig_user_id = None
        user.name = f"Deleted User {user.id}"
        user.save(update_fields=['status', 'access_token', 'token_expires_at', 'ig_user_id', 'name'])

    DataDeletionRequest.objects.create(
        confirmation_code=confirmation_code,
        user_id=str(user_id),
        status='completed',
        details="Foydalanuvchi shaxsiy ma'lumotlari Meta so'rovi bo'yicha tozalandi.",
    )

    site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
    status_url = f"{site_url}/oauth/data-deletion/status/{confirmation_code}/"
    logger.info("Data deletion yakunlandi: ig_user_id=%s, code=%s", user_id, confirmation_code)
    return status_url, confirmation_code
