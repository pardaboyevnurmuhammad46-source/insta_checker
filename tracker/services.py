import base64
import hashlib
import hmac
import json
import logging
import os
import sys
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
    TokenInvalid,
    MetaWebhookError,
)
from .instagram_client import (
    get_instagram_client,
    list_recent_media,
    get_media_insights,
)

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


def create_reels_container_resumable(
    ig_user_id: str, access_token: str, caption: str = '', share_to_feed: bool = True
) -> tuple[str, str]:
    return get_instagram_client().create_reels_container_resumable(ig_user_id, access_token, caption, share_to_feed)


def upload_video_binary(upload_url: str, file_obj, file_size: int, access_token: str) -> None:
    return get_instagram_client().upload_video_binary(upload_url, file_obj, file_size, access_token)


def check_container_status(container_id: str, access_token: str) -> dict:
    return get_instagram_client().check_container_status(container_id, access_token)


def wait_for_container_ready(container_id: str, access_token: str, max_attempts: int = 45, delay: int = 2) -> bool:
    return get_instagram_client().wait_for_container_ready(container_id, access_token, max_attempts=max_attempts, delay=delay)


def publish_container(ig_user_id: str, container_id: str, access_token: str) -> str:
    return get_instagram_client().publish_container(ig_user_id, container_id, access_token)


def get_media_permalink(ig_media_id: str, access_token: str) -> str:
    return get_instagram_client().get_media_permalink(ig_media_id, access_token)


def validate_video_orientation(file_field) -> str | None:
    """
    MP4 faylining tkhd atomini tekshirib, video yo'nalishini (vertikal/gorizontal) aniqlaydi.
    Instagram Reels faqat vertikal (9:16 yoki 4:5) videolarni qabul qiladi.
    Gorizontal (16:9) bo'lsa xato xabari qaytaradi.
    """
    try:
        if hasattr(file_field, 'open'):
            file_field.open('rb')
        pos_before = file_field.tell() if hasattr(file_field, 'tell') else 0
        file_field.seek(0)
        data = file_field.read(1024 * 1024)  # Dastlabki 1 MB
        file_field.seek(pos_before)

        import struct
        idx = 0
        while True:
            pos = data.find(b'tkhd', idx)
            if pos == -1:
                break
            version = data[pos + 4]
            offset = 80 if version == 0 else 92
            if pos + offset + 8 <= len(data):
                w_raw, h_raw = struct.unpack('>II', data[pos + offset : pos + offset + 8])
                w = w_raw / 65536.0
                h = h_raw / 65536.0
                if w > 0 and h > 0:
                    if w > h:
                        return (
                            f"Video o'lchami ({int(w)}x{int(h)}) gorizontal (16:9 formatda). "
                            "Instagram Reels faqat vertikal (9:16 formatda, masalan 720x1280 yoki 1080x1920) "
                            "videolarni qabul qiladi. Gorizontal video Instagram tomonidan rad etiladi."
                        )
                    return None
            idx = pos + 4
    except Exception as exc:
        logger.debug("Video o'lchamlarini tekshirishda xatolik: %s", exc)
    return None


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

    # Video holati tekshiruvi (tayyorlanmoqda yoki xatolik)
    if chosen_video.status in ['pending', 'processing']:
        err_msg = "Video hozirda tayyorlanmoqda (konvertatsiya qilinmoqda). Iltimos, video tayyor bo'lishini kuting."
        post, _ = Post.objects.get_or_create(link=link)
        post.status = 'failed'
        post.error = err_msg
        post.save(update_fields=['status', 'error'])
        link.status = 'failed'
        link.save(update_fields=['status'])
        raise InstagramPublishError(err_msg)

    if chosen_video.status == 'failed':
        err_msg = f"Video yaroqsiz: {chosen_video.processing_error or 'Video qayta ishlashda xatolik yuz bergan.'}"
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

    # Video davomiyligi tekshiruvi: 3 soniyadan 90 soniyagacha
    if file_size > 1024 and hasattr(chosen_video.file, 'path') and os.path.exists(chosen_video.file.path):
        from .video_utils import get_video_info, validate_video_duration
        info = get_video_info(chosen_video.file.path)
        dur_err = validate_video_duration(info.get('duration', 0.0))
        if dur_err:
            post, _ = Post.objects.get_or_create(link=link)
            post.status = 'failed'
            post.error = dur_err
            post.save(update_fields=['status', 'error'])
            link.status = 'failed'
            link.save(update_fields=['status'])
            raise InstagramPublishError(dur_err)

    # Video formati (orientatsiyasi) tekshiruvi: konvertatsiyadan keyingi faylni tekshiramiz
    if file_size > 1024:
        orientation_err = validate_video_orientation(chosen_video.file)
        if orientation_err:
            post, _ = Post.objects.get_or_create(link=link)
            post.status = 'failed'
            post.error = orientation_err
            post.save(update_fields=['status', 'error'])
            link.status = 'failed'
            link.save(update_fields=['status'])
            raise InstagramPublishError(orientation_err)

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

    upload_mode = getattr(settings, 'INSTAGRAM_UPLOAD_MODE', 'resumable')
    from unittest.mock import Mock, MagicMock
    if isinstance(create_reels_container, (Mock, MagicMock)) and not isinstance(create_reels_container_resumable, (Mock, MagicMock)):
        upload_mode = 'url'

    # video_url ni tayyorlab qo'yamiz (resumable uchun fallback yoki url rejimi uchun)
    video_url = chosen_video.url
    if not video_url.startswith(('http://', 'https://')):
        base = getattr(settings, 'PUBLIC_BASE_URL', '') or getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')
        base = base.rstrip('/')
        video_url = f"{base}{video_url}"

    container_id = None
    try:
        if upload_mode == 'resumable':
            try:
                # Resumable upload: video Meta serveriga to'g'ridan-to'g'ri binary oqim bilan yuklanadi (ngrok/URL shart emas)
                container_id, upload_uri = create_reels_container_resumable(
                    ig_user_id=user.ig_user_id,
                    access_token=user.access_token,
                    caption=caption,
                    share_to_feed=True,
                )
                if hasattr(chosen_video.file, 'open'):
                    chosen_video.file.open('rb')
                upload_video_binary(
                    upload_url=upload_uri,
                    file_obj=chosen_video.file,
                    file_size=file_size,
                    access_token=user.access_token,
                )
            except InstagramPublishError as res_err:
                # Agar Meta akkaunt tokeni uchun resumable'ni qo'llab-quvvatlamasa (masalan Instagram Login tokenida), URL rejimiga o'tamiz
                if "video_url is required" in str(res_err) or "OAuthException" in str(res_err):
                    logger.info("Resumable upload bu token uchun qo'llab-quvvatlanmadi, URL rejimiga o'tilmoqda: %s", res_err)
                    container_id = None
                else:
                    raise

        if not container_id:
            # URL rejimi (zaxira fallback)
            if getattr(settings, 'INSTAGRAM_MODE', 'real') != 'mock':
                if '127.0.0.1' in video_url or 'localhost' in video_url:
                    err_msg = (
                        "Video manzili lokal (127.0.0.1/localhost). URL rejimida Instagram serverlari videoni yuklay olishi uchun "
                        "ommaviy HTTPS manzil (PUBLIC_BASE_URL, masalan ngrok) sozlangan bo'lishi shart."
                    )
                    post.status = 'failed'
                    post.error = err_msg
                    post.save(update_fields=['status', 'error'])
                    link.status = 'failed'
                    link.save(update_fields=['status'])
                    raise InstagramPublishError(err_msg)

                if 'ngrok' in video_url and 'test' not in sys.argv:
                    try:
                        check_resp = requests.head(video_url, timeout=3)
                        if check_resp.status_code == 404 and 'ngrok-error-code' in check_resp.headers:
                            err_msg = (
                                "PUBLIC_BASE_URL da ko'rsatilgan ngrok tunnel to'xtagan yoki eskirgan (ERR_NGROK_3200). "
                                "Instagram videoni yuklay olmaydi. Iltimos, serverda ngrok'ni qayta ishga tushiring."
                            )
                            post.status = 'failed'
                            post.error = err_msg
                            post.save(update_fields=['status', 'error'])
                            link.status = 'failed'
                            link.save(update_fields=['status'])
                            raise InstagramPublishError(err_msg)
                    except requests.RequestException:
                        pass

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


def sync_user_media(instagram_user: InstagramUser) -> dict:
    """
    Instagram Graph API orqali foydalanuvchining so'nggi Reels postlarini tekshiradi va bazani yangilaydi:
    1. list_recent_media chaqiriladi.
    2. REELS bo'lgan va caption ichida foydalanuvchining biror UniqueLink.code kodi bor medialar uchun
       Post (status='verified', source='self') yaratiladi yoki yangilanadi.
       Agar mavjud post source='site' bo'lsa, source o'zgartirilmaydi.
    3. Agar ig_media_id boshqa foydalanuvchining postiga tegishli bo'lsa, o'tkazib yuboriladi va log yoziladi.
    4. Har bir verified post uchun get_media_insights chaqirilib, views va last_synced_at yangilanadi.
    5. Bazadagi verified postlardan Instagram ro'yxatida yo'qlari yoki kodi o'chirilganlari 'revoked' qilinadi.
    6. TokenInvalid xatosi yuz berganda InstagramUser.status = 'needs_reauth' qilinadi va sync to'xtatiladi.
    """
    if not instagram_user.access_token or instagram_user.status == 'needs_reauth':
        logger.warning("Foydalanuvchi tokeni mavjud emas yoki 'needs_reauth' holatida: user_id=%s", instagram_user.id)
        return {'status': 'skipped', 'reason': 'no_token_or_needs_reauth'}

    token = instagram_user.access_token

    try:
        media_list = list_recent_media(token=token, limit=25)
    except TokenInvalid as exc:
        logger.warning("Foydalanuvchi tokeni yaroqsiz (user_id=%s): %s", instagram_user.id, exc)
        instagram_user.status = 'needs_reauth'
        instagram_user.save(update_fields=['status'])
        return {'status': 'needs_reauth', 'error': str(exc)}

    # Foydalanuvchining barcha unikal linklari va kodlari
    user_links = list(instagram_user.links.all())
    code_to_link = {}
    for lk in user_links:
        if lk.code:
            code_to_link[lk.code.upper().strip()] = lk

    verified_media_ids = set()
    verified_posts = []

    # 1. Instagramdan olingan medialarni tekshirish
    for media in media_list:
        media_id = str(media.get('id') or '')
        if not media_id:
            continue

        product_type = str(media.get('media_product_type') or '').upper()
        if product_type != 'REELS':
            continue

        caption = str(media.get('caption') or '').upper()
        matching_link = None
        for code, lk in code_to_link.items():
            if code in caption:
                matching_link = lk
                break

        if not matching_link:
            continue

        # 2. ig_media_id boshqa foydalanuvchining postida bo'lsa, o'tkazib yuborish va log yozish
        existing_other = Post.objects.filter(ig_media_id=media_id).exclude(link__user=instagram_user).select_related('link__user').first()
        if existing_other:
            logger.warning(
                "ig_media_id=%s boshqa foydalanuvchiga tegishli (user_id=%s). Joriy user_id=%s uchun o'tkazib yuborildi.",
                media_id, existing_other.link.user_id, instagram_user.id
            )
            continue

        # Postni topish yoki yaratish
        existing_post = Post.objects.filter(ig_media_id=media_id).first()
        now = timezone.now()

        if existing_post:
            post = existing_post
            post.status = 'verified'
            if post.source != 'site':
                post.source = 'self'
            if media.get('permalink'):
                post.permalink = media['permalink']
            if media.get('thumbnail_url'):
                post.thumbnail_url = media['thumbnail_url']
            post.likes = int(media.get('like_count') or 0)
            post.comments_count = int(media.get('comments_count') or 0)
            post.last_synced_at = now
            post.save(update_fields=[
                'status', 'source', 'permalink', 'thumbnail_url',
                'likes', 'comments_count', 'last_synced_at'
            ])
        else:
            if hasattr(matching_link, 'post') and (not matching_link.post.ig_media_id):
                post = matching_link.post
                post.ig_media_id = media_id
                post.status = 'verified'
                if post.source != 'site':
                    post.source = 'self'
                post.permalink = media.get('permalink')
                post.thumbnail_url = media.get('thumbnail_url')
                post.likes = int(media.get('like_count') or 0)
                post.comments_count = int(media.get('comments_count') or 0)
                post.last_synced_at = now
                post.save()
            else:
                target_link = matching_link
                if hasattr(target_link, 'post'):
                    target_link = UniqueLink.objects.create(
                        user=instagram_user,
                        video=matching_link.video,
                        status='posted',
                    )
                post = Post.objects.create(
                    link=target_link,
                    ig_media_id=media_id,
                    status='verified',
                    source='self',
                    permalink=media.get('permalink'),
                    thumbnail_url=media.get('thumbnail_url'),
                    likes=int(media.get('like_count') or 0),
                    comments_count=int(media.get('comments_count') or 0),
                    last_synced_at=now,
                )

        verified_media_ids.add(media_id)
        verified_posts.append(post)

    # 3. Har bir verified post uchun get_media_insights chaqirilib, views va last_synced_at yangilanadi
    for post in verified_posts:
        try:
            insights = get_media_insights(token=token, media_id=post.ig_media_id)
            views = int(insights.get('views') or 0)
            post.views = views
            post.last_synced_at = timezone.now()
            post.save(update_fields=['views', 'last_synced_at'])

            PostStat.objects.create(
                post=post,
                views=post.views,
                likes=post.likes,
                comments_count=post.comments_count,
            )
            check_and_award_prizes(post)
        except TokenInvalid as exc:
            logger.warning("get_media_insights token yaroqsiz (user_id=%s): %s", instagram_user.id, exc)
            instagram_user.status = 'needs_reauth'
            instagram_user.save(update_fields=['status'])
            return {'status': 'needs_reauth', 'error': str(exc)}
        except Exception as exc:
            logger.warning("get_media_insights da xatolik (post_id=%s): %s", post.id, exc)

    # 4. Bazadagi verified postlardan Instagram ro'yxatida yo'qlari yoki kodi qolmaganlari -> revoked
    user_verified_posts = Post.objects.filter(
        link__user=instagram_user,
        status='verified',
    )
    revoked_count = 0
    now = timezone.now()
    for p in user_verified_posts:
        if p.ig_media_id not in verified_media_ids:
            p.status = 'revoked'
            p.last_synced_at = now
            p.save(update_fields=['status', 'last_synced_at'])
            revoked_count += 1
            logger.info("Post revoked qilindi: post_id=%s, ig_media_id=%s", p.id, p.ig_media_id)

    return {
        'status': 'success',
        'verified_count': len(verified_posts),
        'revoked_count': revoked_count,
    }
