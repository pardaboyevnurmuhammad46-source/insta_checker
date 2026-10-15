import urllib.parse
from datetime import timedelta
import requests
from django.conf import settings
from django.utils import timezone
from .models import InstagramUser, UniqueLink


class InstagramOAuthError(Exception):
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
        expires_in = long_token_data.get('expires_in', 5184000)  # default 60 kun
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
