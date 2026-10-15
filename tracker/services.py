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
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest

logger = logging.getLogger(__name__)


# class InstagramOAuthError(Exception):
#     pass
# class InstagramNetworkError(InstagramOAuthError):
#     pass
# class InstagramPublishError(Exception):
#     pass
# class InstagramMetricsError(Exception):
#     def __init__(self, message: str, is_deleted: bool = False, is_auth_error: bool = False):
#         super().__init__(message)
#         self.is_deleted = is_deleted
#         self.is_auth_error = is_auth_error

class InstagramBaseError(Exception):
    pass


class InstagramNetworkError(InstagramBaseError):
    pass


class InstagramOAuthError(InstagramBaseError):
    pass


class InstagramOAuthNetworkError(InstagramOAuthError, InstagramNetworkError):
    pass


class InstagramPublishError(InstagramBaseError):
    pass


class InstagramPublishNetworkError(InstagramPublishError, InstagramNetworkError):
    pass


class InstagramMetricsError(InstagramBaseError):
    def __init__(self, message: str, is_deleted: bool = False, is_auth_error: bool = False):
        super().__init__(message)
        self.is_deleted = is_deleted
        self.is_auth_error = is_auth_error


class InstagramMetricsNetworkError(InstagramMetricsError, InstagramNetworkError):
    pass


class MetaWebhookError(Exception):
    pass


# ==========================================
# 1. Instagram OAuth & Token boshqaruvi
# ==========================================

def build_instagram_auth_url(token: str) -> str:
    base_url = "https://www.instagram.com/oauth/authorize"
    params = {
        'client_id': settings.INSTAGRAM_APP_ID,
        'redirect_uri': settings.INSTAGRAM_REDIRECT_URI,
        'scope': settings.INSTAGRAM_SCOPE,
        'response_type': 'code',
        'state': str(token),
    }
    return f"{base_url}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str) -> dict:
    cleaned_code = code.split('#_')[0]
    token_url = "https://api.instagram.com/oauth/access_token"
    payload = {
        'client_id': settings.INSTAGRAM_APP_ID,
        'client_secret': settings.INSTAGRAM_APP_SECRET,
        'grant_type': 'authorization_code',
        'redirect_uri': settings.INSTAGRAM_REDIRECT_URI,
        'code': cleaned_code,
    }

    try:
        response = requests.post(token_url, data=payload, timeout=15)
    except requests.RequestException as exc:
        raise InstagramNetworkError(f"Instagram serveriga ulanishda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramOAuthError(f"Access token olishda xatolik: {response.text}")

    return response.json()


def get_long_lived_token(short_lived_token: str) -> dict:
    graph_url = "https://graph.instagram.com/access_token"
    params = {
        'grant_type': 'ig_exchange_token',
        'client_secret': settings.INSTAGRAM_APP_SECRET,
        'access_token': short_lived_token,
    }

    try:
        response = requests.get(graph_url, params=params, timeout=15)
    except requests.RequestException as exc:
        raise InstagramNetworkError(f"Long-lived token olishda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramOAuthError(f"Long-lived token olishda xatolik: {response.text}")

    return response.json()


def refresh_instagram_access_token(access_token: str) -> dict:
    """
    60 kunlik uzoq muddatli tokenni muddati tugashidan oldin yangilash (Graph API refresh_access_token).
    """
    url = "https://graph.instagram.com/refresh_access_token"
    params = {
        'grant_type': 'ig_refresh_token',
        'access_token': access_token,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        raise InstagramNetworkError(f"Token yangilashda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramOAuthError(f"Token yangilab bo'lmadi: {response.text}")

    return response.json()


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
    url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': access_token,
    }
    try:
        response = requests.post(url, data=payload, timeout=30)
    except requests.RequestException as exc:
        # raise InstagramPublishError(f"Reels container yaratishda tarmoq xatoligi: {exc}") from exc
        raise InstagramPublishNetworkError(f"Reels container yaratishda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramPublishError(f"Reels container yaratib bo'lmadi: {response.text}")

    container_id = response.json().get('id')
    if not container_id:
        raise InstagramPublishError("Container ID olinmadi.")
    return str(container_id)


def check_container_status(container_id: str, access_token: str) -> dict:
    url = f"https://graph.instagram.com/v21.0/{container_id}"
    params = {
        'fields': 'status_code,status',
        'access_token': access_token,
    }
    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        # raise InstagramPublishError(f"Container holatini tekshirishda xatolik: {exc}") from exc
        raise InstagramPublishNetworkError(f"Container holatini tekshirishda xatolik: {exc}") from exc

    if response.status_code != 200:
        raise InstagramPublishError(f"Container holatini olib bo'lmadi: {response.text}")

    return response.json()


def wait_for_container_ready(container_id: str, access_token: str, max_attempts: int = 12, delay: int = 5) -> bool:
    for _ in range(max_attempts):
        status_data = check_container_status(container_id, access_token)
        status_code = status_data.get('status_code')
        if status_code == 'FINISHED':
            return True
        elif status_code in ('ERROR', 'EXPIRED'):
            raise InstagramPublishError(f"Reels yuklash xatoligi: {status_data}")
        time.sleep(delay)

    # raise InstagramPublishError("Reels videosini qayta ishlash vaqti tugadi (timeout).")
    raise InstagramPublishNetworkError("Reels videosini qayta ishlash vaqti tugadi (timeout).")


def publish_container(ig_user_id: str, container_id: str, access_token: str) -> str:
    url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media_publish"
    payload = {
        'creation_id': container_id,
        'access_token': access_token,
    }
    try:
        response = requests.post(url, data=payload, timeout=30)
    except requests.RequestException as exc:
        # raise InstagramPublishError(f"Reels'ni publish qilishda tarmoq xatoligi: {exc}") from exc
        raise InstagramPublishNetworkError(f"Reels'ni publish qilishda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramPublishError(f"Reels publish qilinmadi: {response.text}")

    media_id = response.json().get('id')
    if not media_id:
        raise InstagramPublishError("Nashr etilgan media ID olinmadi.")
    return str(media_id)


def get_media_permalink(ig_media_id: str, access_token: str) -> str:
    url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
    params = {
        'fields': 'permalink',
        'access_token': access_token,
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get('permalink') or f"https://www.instagram.com/reel/{ig_media_id}/"
    except requests.RequestException:
        pass
    return f"https://www.instagram.com/reel/{ig_media_id}/"


def publish_reels_for_link(link_id: int, caption: str = '') -> Post:
    try:
        link = UniqueLink.objects.select_related('user').get(id=link_id)
    except UniqueLink.DoesNotExist as exc:
        raise InstagramPublishError(f"UniqueLink topilmadi: id={link_id}") from exc

    user = link.user
    if user.status != 'connected' or not user.access_token or not user.ig_user_id:
        raise InstagramPublishError("Foydalanuvchi Instagram akkauntini ulamagan yoki token yo'q.")

    if not link.video:
        raise InstagramPublishError("Joylash uchun video fayl mavjud emas.")

    post, _ = Post.objects.get_or_create(link=link)
    # Idempotentlik: agar post allaqachon published bo'lsa (masalan Celery retry paytida), qayta joylamaymiz
    if post.status == 'published' and post.ig_media_id:
        logger.info("Post allaqachon muvaffaqiyatli nashr etilgan (link_id=%s, media_id=%s)", link_id, post.ig_media_id)
        return post

    post.status = 'publishing'
    post.save(update_fields=['status'])

    video_url = link.video.url
    if not video_url.startswith(('http://', 'https://')):
        base = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
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
        post.error = str(exc)
        post.save(update_fields=['status', 'error'])

        link.status = 'failed'
        link.save(update_fields=['status'])
        raise


# ==========================================
# 3. Adaptiv jadval va Metrikalarni tekshirish
# ==========================================

def calculate_next_check(post: Post, now=None) -> timezone.datetime | None:
    """
    Post yoshiga qarab keyingi tekshirish vaqtini adaptiv hisoblaydi:
    - 0 .. 24 soat: har 15 daqiqada
    - 1 .. 3 kun: har 1 soatda
    - 3 .. 7 kun: har 4 soatda
    - 7 .. 14 kun: har 12 soatda
    - 14 kundan so'ng (shu jumladan 30+ kunda ham post saqlanganini tekshirish uchun): kuniga 1 marta (24 soat)
    """
    if post.status != 'published' or not post.posted_at:
        return None

    if now is None:
        now = timezone.now()

    age = now - post.posted_at
    if age < timedelta(0):
        return now + timedelta(minutes=15)

    if age < timedelta(hours=24):
        return now + timedelta(minutes=15)
    elif age < timedelta(days=3):
        return now + timedelta(hours=1)
    elif age < timedelta(days=7):
        return now + timedelta(hours=4)
    elif age < timedelta(days=14):
        return now + timedelta(hours=12)
    else:
        return now + timedelta(days=1)


def fetch_post_metrics_from_instagram(ig_media_id: str, access_token: str) -> dict:
    """
    Instagram Graph API orqali media metrikalarini (likes, comments, views) oladi.
    """
    media_url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
    params = {
        'fields': 'like_count,comments_count,media_type',
        'access_token': access_token,
    }

    try:
        response = requests.get(media_url, params=params, timeout=15)
    except requests.RequestException as exc:
        # raise InstagramMetricsError(f"Media ma'lumotlarini olishda tarmoq xatoligi: {exc}") from exc
        raise InstagramMetricsNetworkError(f"Media ma'lumotlarini olishda tarmoq xatoligi: {exc}") from exc

    if response.status_code == 404:
        raise InstagramMetricsError(f"Media topilmadi (o'chirilgan bo'lishi mumkin): {response.text}", is_deleted=True)

    if response.status_code != 200:
        is_auth_error = False
        is_deleted = False
        try:
            err_data = response.json().get('error', {})
            err_code = err_data.get('code')
            if err_code == 190:
                is_auth_error = True
            elif err_code == 100 and err_data.get('error_subcode') == 33:
                is_deleted = True
        except Exception:
            pass

        raise InstagramMetricsError(
            f"Media metrikalarini olib bo'lmadi: {response.text}",
            is_deleted=is_deleted,
            is_auth_error=is_auth_error,
        )

    data = response.json()
    likes = data.get('like_count', 0)
    comments = data.get('comments_count', 0)

    # Reels Insights: views yoki plays ni olish
    views = 0
    insights_url = f"https://graph.instagram.com/v21.0/{ig_media_id}/insights"
    for metric_name in ('views', 'plays'):
        try:
            ins_resp = requests.get(
                insights_url,
                params={'metric': metric_name, 'access_token': access_token},
                timeout=15,
            )
            if ins_resp.status_code == 200:
                ins_data = ins_resp.json().get('data', [])
                for item in ins_data:
                    if item.get('name') == metric_name:
                        values = item.get('values', [])
                        if values and isinstance(values, list):
                            views = values[0].get('value', 0)
                        elif 'total_value' in item:
                            views = item.get('total_value', {}).get('value', 0)
                        break
                if views > 0:
                    break
        except requests.RequestException:
            pass

    return {
        'likes': int(likes or 0),
        'comments_count': int(comments or 0),
        'views': int(views or 0),
    }


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
        metrics = fetch_post_metrics_from_instagram(post.ig_media_id, user.access_token)
        post.likes = metrics['likes']
        post.comments_count = metrics['comments_count']
        if metrics['views'] > 0 or post.views == 0:
            post.views = metrics['views']

        post.last_checked_at = timezone.now()
        post.next_check_at = calculate_next_check(post)
        post.error = None
        post.save(update_fields=['likes', 'comments_count', 'views', 'last_checked_at', 'next_check_at', 'error'])

        # Sovrin berish logikasi
        check_and_award_prizes(post)
        return post

    except InstagramMetricsError as exc:
        if exc.is_deleted:
            post.status = 'deleted'
            post.next_check_at = None
            post.error = "Instagram'dan post o'chirilgan."
            post.save(update_fields=['status', 'next_check_at', 'error'])
        elif exc.is_auth_error:
            user.status = 'needs_reauth'
            user.save(update_fields=['status'])
            post.error = "Instagram tokeni yaroqsiz (needs_reauth)."
            post.next_check_at = None
            post.save(update_fields=['error', 'next_check_at'])
        else:
            post.error = str(exc)
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
    # --- Eski tozalash kodi (komentga olindi):
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
