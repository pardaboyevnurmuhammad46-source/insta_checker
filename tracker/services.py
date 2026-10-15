import time
import urllib.parse
from datetime import timedelta
import requests
from django.conf import settings
from django.utils import timezone
from .models import InstagramUser, UniqueLink, Post


class InstagramOAuthError(Exception):
    pass


class InstagramPublishError(Exception):
    pass


def build_instagram_auth_url(token: str) -> str:
    base_url = "https://api.instagram.com/oauth/authorize"
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
        raise InstagramOAuthError(f"Instagram serveriga ulanishda xatolik: {exc}") from exc

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
        raise InstagramOAuthError(f"Long-lived token olishda tarmoq xatoligi: {exc}") from exc

    if response.status_code != 200:
        raise InstagramOAuthError(f"Long-lived token olishda xatolik: {response.text}")

    return response.json()


def complete_instagram_oauth(code: str, token: str) -> tuple[InstagramUser, UniqueLink]:
    try:
        link = UniqueLink.objects.select_related('user').get(token=token)
    except UniqueLink.DoesNotExist as exc:
        raise InstagramOAuthError("Bunday unikal link topilmadi.") from exc

    # 1. Kodni qisqa muddatli tokenga almashtirish
    token_data = exchange_code_for_token(code)
    short_lived_token = token_data.get('access_token')
    ig_user_id = str(token_data.get('user_id', ''))

    if not short_lived_token:
        raise InstagramOAuthError("Instagram javobida access_token mavjud emas.")

    # 2. 60 kunlik uzoq muddatli tokenga almashtirish
    try:
        long_token_data = get_long_lived_token(short_lived_token)
        final_token = long_token_data.get('access_token', short_lived_token)
        expires_in = long_token_data.get('expires_in', 5184000)
    except InstagramOAuthError:
        final_token = short_lived_token
        expires_in = 3600

    # 3. InstagramUser ma'lumotlarini yangilash
    user = link.user
    user.ig_user_id = ig_user_id or user.ig_user_id
    user.access_token = final_token
    user.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
    user.status = 'connected'
    user.save(update_fields=['ig_user_id', 'access_token', 'token_expires_at', 'status'])

    # 4. Link holatini belgilash
    if link.status == 'pending':
        link.status = 'opened'
        link.save(update_fields=['status'])

    return user, link


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
        raise InstagramPublishError(f"Reels container yaratishda tarmoq xatoligi: {exc}") from exc

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
        raise InstagramPublishError(f"Container holatini tekshirishda xatolik: {exc}") from exc

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

    raise InstagramPublishError("Reels videosini qayta ishlash vaqti tugadi (timeout).")


def publish_container(ig_user_id: str, container_id: str, access_token: str) -> str:
    url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media_publish"
    payload = {
        'creation_id': container_id,
        'access_token': access_token,
    }
    try:
        response = requests.post(url, data=payload, timeout=30)
    except requests.RequestException as exc:
        raise InstagramPublishError(f"Reels'ni publish qilishda tarmoq xatoligi: {exc}") from exc

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
        post.next_check_at = timezone.now() + timedelta(minutes=15)
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
