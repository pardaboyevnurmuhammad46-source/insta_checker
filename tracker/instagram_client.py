from abc import ABC, abstractmethod
import json
import logging
import time
import urllib.parse
import uuid
import requests
from django.conf import settings
from .instagram_errors import (
    InstagramErrorType,
    classify_instagram_error,
    log_instagram_error,
    record_instagram_error,
    get_redis_client,
)
from .exceptions import (
    InstagramOAuthError,
    InstagramNetworkError,
    InstagramPublishError,
    InstagramPublishNetworkError,
    InstagramMetricsError,
    InstagramRateLimitError,
    InstagramMetricsNetworkError,
)

logger = logging.getLogger(__name__)

REQUIRED_PERMISSIONS = {
    'instagram_business_content_publish',
    'instagram_business_manage_insights',
    'instagram_business_manage_comments',
}


class InstagramClient(ABC):
    """
    Instagram Graph API bilan ishlash uchun umumiy mijoz interfeysi.
    Haqiqiy (RealInstagramClient) va test/simulyatsiya (DryRunInstagramClient)
    bitta interfeys orqali ishlaydi.
    """

    @abstractmethod
    def build_auth_url(self, state: str) -> str:
        """OAuth avtorizatsiya URL manzilini yaratadi."""
        pass

    @abstractmethod
    def exchange_code_for_token(self, code: str) -> dict:
        """Avtorizatsiya kodini short-lived tokenga almashtiradi."""
        pass

    @abstractmethod
    def get_long_lived_token(self, short_lived_token: str) -> dict:
        """Short-lived tokenni 60 kunlik long-lived tokenga almashtiradi."""
        pass

    @abstractmethod
    def refresh_access_token(self, access_token: str) -> dict:
        """Uzoq muddatli tokenni muddati tugashidan oldin yangilaydi."""
        pass

    @abstractmethod
    def verify_token_permissions(self, access_token: str) -> tuple[bool, list[str]]:
        """Tokenning kerakli ruxsatnomalarga ega ekanligini tekshiradi."""
        pass

    @abstractmethod
    def check_account_type(self, access_token: str, ig_user_id: str = 'me') -> str:
        """Akkaunt turini tekshiradi (BUSINESS, MEDIA_CREATOR, PERSONAL)."""
        pass

    @abstractmethod
    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '') -> str:
        """Reels media container yaratadi va container ID qaytaradi."""
        pass

    @abstractmethod
    def check_container_status(self, container_id: str, access_token: str) -> dict:
        """Container tayyorlik holatini tekshiradi."""
        pass

    @abstractmethod
    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 12, delay: int = 5) -> bool:
        """Container yuklanishi tugashini kutadi."""
        pass

    @abstractmethod
    def publish_container(self, ig_user_id: str, container_id: str, access_token: str) -> str:
        """Containerni Instagramga nashr qiladi va media ID qaytaradi."""
        pass

    @abstractmethod
    def get_media_permalink(self, ig_media_id: str, access_token: str) -> str:
        """Nashr qilingan postning permalink havolasini oladi."""
        pass

    @abstractmethod
    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None) -> dict:
        """Post statistikasi (views, likes, comments) ni oladi."""
        pass


class RealInstagramClient(InstagramClient):
    """
    Haqiqiy Instagram Graph API mijoz adapteri.
    """

    @property
    def _requests(self):
        import tracker.services as svc
        return getattr(svc, 'requests', requests)

    def build_auth_url(self, state: str) -> str:
        base_url = "https://www.instagram.com/oauth/authorize"
        params = {
            'client_id': settings.INSTAGRAM_APP_ID,
            'redirect_uri': settings.INSTAGRAM_REDIRECT_URI,
            'scope': settings.INSTAGRAM_SCOPE,
            'response_type': 'code',
            'state': str(state),
        }
        return f"{base_url}?{urllib.parse.urlencode(params)}"

    def exchange_code_for_token(self, code: str) -> dict:
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
            response = self._requests.post(token_url, data=payload, timeout=15)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Instagram serveriga ulanishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramOAuthError(f"Access token olishda xatolik: {response.text}")

        return response.json()

    def get_long_lived_token(self, short_lived_token: str) -> dict:
        graph_url = "https://graph.instagram.com/access_token"
        params = {
            'grant_type': 'ig_exchange_token',
            'client_secret': settings.INSTAGRAM_APP_SECRET,
            'access_token': short_lived_token,
        }

        try:
            response = self._requests.get(graph_url, params=params, timeout=15)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Long-lived token olishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramOAuthError(f"Long-lived token olishda xatolik: {response.text}")

        return response.json()

    def refresh_access_token(self, access_token: str) -> dict:
        url = "https://graph.instagram.com/refresh_access_token"
        params = {
            'grant_type': 'ig_refresh_token',
            'access_token': access_token,
        }

        try:
            response = self._requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Token yangilashda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramOAuthError(f"Token yangilab bo'lmadi: {response.text}")

        return response.json()

    def verify_token_permissions(self, access_token: str) -> tuple[bool, list[str]]:
        url = "https://graph.instagram.com/me/permissions"
        try:
            response = self._requests.get(url, params={'access_token': access_token}, timeout=15)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Ruxsatlarni tekshirishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            return True, []

        data = response.json().get('data')
        if data is None:
            return True, []

        granted = {
            item.get('permission') for item in data
            if item.get('status') == 'granted'
        }
        missing = [perm for perm in REQUIRED_PERMISSIONS if perm not in granted]
        return (len(missing) == 0, missing)

    def check_account_type(self, access_token: str, ig_user_id: str = 'me') -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}"
        try:
            response = self._requests.get(url, params={'fields': 'account_type,username', 'access_token': access_token}, timeout=15)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Akkaunt turini tekshirishda tarmoq xatosi: {exc}") from exc

        if response.status_code != 200:
            return 'BUSINESS'

        data = response.json()
        acc_type = data.get('account_type')
        if not acc_type:
            return 'BUSINESS'
        return str(acc_type).upper()

    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '') -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media"
        payload = {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': caption,
            'access_token': access_token,
        }
        try:
            response = self._requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Reels container yaratishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Reels container yaratib bo'lmadi: {response.text}")

        container_id = response.json().get('id')
        if not container_id:
            raise InstagramPublishError("Container ID olinmadi.")
        return str(container_id)

    def check_container_status(self, container_id: str, access_token: str) -> dict:
        url = f"https://graph.instagram.com/v21.0/{container_id}"
        params = {
            'fields': 'status_code,status',
            'access_token': access_token,
        }
        try:
            response = self._requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Container holatini tekshirishda xatolik: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Container holatini olib bo'lmadi: {response.text}")

        return response.json()

    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 12, delay: int = 5) -> bool:
        for _ in range(max_attempts):
            status_data = self.check_container_status(container_id, access_token)
            status_code = status_data.get('status_code')
            if status_code == 'FINISHED':
                return True
            elif status_code in ('ERROR', 'EXPIRED'):
                raise InstagramPublishError(f"Reels yuklash xatoligi: {status_data}")
            time.sleep(delay)

        raise InstagramPublishNetworkError("Reels videosini qayta ishlash vaqti tugadi (timeout).")

    def publish_container(self, ig_user_id: str, container_id: str, access_token: str) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media_publish"
        payload = {
            'creation_id': container_id,
            'access_token': access_token,
        }
        try:
            response = self._requests.post(url, data=payload, timeout=30)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Reels'ni publish qilishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Reels publish qilinmadi: {response.text}")

        media_id = response.json().get('id')
        if not media_id:
            raise InstagramPublishError("Nashr etilgan media ID olinmadi.")
        return str(media_id)

    def get_media_permalink(self, ig_media_id: str, access_token: str) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
        params = {
            'fields': 'permalink',
            'access_token': access_token,
        }
        try:
            response = self._requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get('permalink') or f"https://www.instagram.com/reel/{ig_media_id}/"
        except requests.RequestException:
            pass
        return f"https://www.instagram.com/reel/{ig_media_id}/"

    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None) -> dict:
        media_url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
        params = {
            'fields': 'like_count,comments_count,media_type',
            'access_token': access_token,
        }

        try:
            response = self._requests.get(media_url, params=params, timeout=15)
        except requests.RequestException as exc:
            record_instagram_error(InstagramErrorType.SERVER_ERROR)
            log_instagram_error(
                InstagramErrorType.SERVER_ERROR,
                f"Media ma'lumotlarini olishda tarmoq xatoligi: {exc}",
            )
            raise InstagramMetricsNetworkError(f"Media ma'lumotlarini olishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            error_type = classify_instagram_error(response=response)
            err_code = None
            err_subcode = None
            try:
                body = response.json()
                if isinstance(body, dict):
                    err_data = body.get('error')
                    if isinstance(err_data, dict):
                        raw_c = err_data.get('code')
                        if isinstance(raw_c, (int, str)) and str(raw_c).lstrip('-').isdigit():
                            err_code = int(raw_c)
                        raw_sc = err_data.get('error_subcode')
                        if isinstance(raw_sc, (int, str)) and str(raw_sc).lstrip('-').isdigit():
                            err_subcode = int(raw_sc)
            except Exception:
                pass

            record_instagram_error(error_type)
            log_instagram_error(
                error_type,
                response.text,
                code=err_code,
                subcode=err_subcode,
            )

            if error_type == InstagramErrorType.RATE_LIMIT:
                raise InstagramRateLimitError(
                    f"Instagram rate limit cheklovi: {response.text}",
                    status_code=response.status_code,
                    error_code=err_code,
                    error_subcode=err_subcode,
                )
            elif error_type == InstagramErrorType.SERVER_ERROR:
                raise InstagramMetricsNetworkError(
                    f"Instagram server xatoligi: {response.text}",
                    error_type=error_type,
                    status_code=response.status_code,
                    error_code=err_code,
                    error_subcode=err_subcode,
                )
            else:
                raise InstagramMetricsError(
                    f"Media metrikalarini olib bo'lmadi: {response.text}",
                    error_type=error_type,
                    status_code=response.status_code,
                    error_code=err_code,
                    error_subcode=err_subcode,
                )

        data = response.json()
        likes = data.get('like_count', 0)
        comments = data.get('comments_count', 0)

        views = 0
        insights_url = f"https://graph.instagram.com/v21.0/{ig_media_id}/insights"
        for metric_name in ('views', 'plays'):
            try:
                ins_resp = self._requests.get(
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


class DryRunInstagramClient(InstagramClient):
    """
    DRY_RUN va simulyatsiya mijoz adapteri.
    Instagram API ga hech qanday haqiqiy so'rov yubormaydi.
    Redis'dagi simulyatsiya holatini o'qiydi va shunga mos sun'iy javob beradi.
    """

    def build_auth_url(self, state: str) -> str:
        site_url = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        return f"{site_url}/oauth/callback/?code=dry_run&state={state}"

    def exchange_code_for_token(self, code: str) -> dict:
        mock_user_id = "dry_run_user_9999"
        mock_token = f"dry_run_short_token_{uuid.uuid4().hex[:12]}"
        return {
            "access_token": mock_token,
            "user_id": mock_user_id,
        }

    def get_long_lived_token(self, short_lived_token: str) -> dict:
        return {
            "access_token": f"dry_run_long_token_{uuid.uuid4().hex[:16]}",
            "expires_in": 5184000,  # 60 kun
        }

    def refresh_access_token(self, access_token: str) -> dict:
        return {
            "access_token": f"dry_run_refreshed_token_{uuid.uuid4().hex[:16]}",
            "expires_in": 5184000,
        }

    def verify_token_permissions(self, access_token: str) -> tuple[bool, list[str]]:
        return True, []

    def check_account_type(self, access_token: str, ig_user_id: str = 'me') -> str:
        return 'BUSINESS'

    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '') -> str:
        container_id = f"dry_run_container_{uuid.uuid4().hex[:10]}"
        return container_id

    def check_container_status(self, container_id: str, access_token: str) -> dict:
        return {
            "status_code": "FINISHED",
            "id": container_id,
        }

    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 12, delay: int = 5) -> bool:
        # Pollingni tekshirish uchun ixtiyoriy sun'iy kechikish
        sim_delay = getattr(settings, 'DRY_RUN_PUBLISH_DELAY_SECONDS', 2.0)
        if sim_delay and sim_delay > 0:
            time.sleep(sim_delay)
        return True

    def publish_container(self, ig_user_id: str, container_id: str, access_token: str) -> str:
        media_id = f"dry_run_media_{uuid.uuid4().hex[:10]}"
        return media_id

    def get_media_permalink(self, ig_media_id: str, access_token: str) -> str:
        return f"https://www.instagram.com/reel/{ig_media_id}/"

    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None) -> dict:
        r = get_redis_client()

        # 1. Post darajasidagi simulyatsiya qilingan xatoliklar
        if post_id is not None:
            post_err = r.get(f"dry_run:sim:post:{post_id}:error")
            if post_err:
                post_err_str = str(post_err)
                if post_err_str == "media_not_found":
                    record_instagram_error(InstagramErrorType.MEDIA_NOT_FOUND)
                    raise InstagramMetricsError(
                        "Media topilmadi yoki o'chirilgan (simulyatsiya)",
                        error_type=InstagramErrorType.MEDIA_NOT_FOUND,
                        status_code=400,
                        error_code=100,
                        error_subcode=33,
                    )
                elif post_err_str == "network_error":
                    record_instagram_error(InstagramErrorType.SERVER_ERROR)
                    raise InstagramMetricsNetworkError(
                        "Tarmoq nosozligi (simulyatsiya)",
                        error_type=InstagramErrorType.SERVER_ERROR,
                        status_code=503,
                        error_code=2,
                    )
                elif post_err_str == "rate_limit":
                    record_instagram_error(InstagramErrorType.RATE_LIMIT)
                    raise InstagramRateLimitError(
                        "Instagram rate limit cheklovi (simulyatsiya)",
                        status_code=429,
                        error_code=4,
                    )

        # 2. Token / User darajasidagi simulyatsiya qilingan xatoliklar
        if access_token:
            tok_err = r.get(f"dry_run:sim:token:{access_token}:error")
            if tok_err and str(tok_err) == "token_invalid":
                record_instagram_error(InstagramErrorType.TOKEN_INVALID)
                raise InstagramMetricsError(
                    "Token yaroqsiz (simulyatsiya)",
                    error_type=InstagramErrorType.TOKEN_INVALID,
                    status_code=400,
                    error_code=190,
                    error_subcode=463,
                )

        # 3. Post darajasidagi simulyatsiya qilingan ko'rishlar
        if post_id is not None:
            sim_views = r.get(f"dry_run:sim:post:{post_id}:views")
            if sim_views:
                try:
                    views_int = int(sim_views)
                    likes = max(1, views_int // 10)
                    comments = max(0, views_int // 50)
                    return {
                        "views": views_int,
                        "likes": likes,
                        "comments_count": comments,
                    }
                except (ValueError, TypeError):
                    pass

        # Standart sun'iy metrikalar
        return {
            "views": 250,
            "likes": 25,
            "comments_count": 5,
        }


def get_instagram_client() -> InstagramClient:
    """
    Sozlamaga qarab RealInstagramClient yoki DryRunInstagramClient qaytaradi.
    Tizim bo'ylab mijoz faqat bitta joyda aniqlanadi.
    Faqat INSTAGRAM_MODE='mock' yoki INSTAGRAM_DRY_RUN=True bo'lganda soxta klient ishlatiladi.
    Real rejimda (default: INSTAGRAM_MODE='real') soxta klient hech qachon ishlatilmaydi.
    """
    if getattr(settings, 'INSTAGRAM_MODE', 'real') == 'mock' or getattr(settings, 'INSTAGRAM_DRY_RUN', False):
        return DryRunInstagramClient()
    return RealInstagramClient()
