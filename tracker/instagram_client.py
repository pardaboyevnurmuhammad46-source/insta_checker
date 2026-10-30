from abc import ABC, abstractmethod
import json
import logging
import random
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
    mask_sensitive_data,
)
from .exceptions import (
    InstagramOAuthError,
    InstagramNetworkError,
    InstagramPublishError,
    InstagramPublishNetworkError,
    InstagramMetricsError,
    InstagramRateLimitError,
    InstagramMetricsNetworkError,
    TokenInvalid,
)
from .rate_limiter import rate_limiter

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
    def check_account_type(self, access_token: str, ig_user_id: str = 'me', account_id: int | None = None) -> str:
        """Akkaunt turini tekshiradi (BUSINESS, MEDIA_CREATOR, PERSONAL)."""
        pass

    @abstractmethod
    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '', account_id: int | None = None) -> str:
        """Reels media container yaratadi va container ID qaytaradi (URL usuli)."""
        pass

    @abstractmethod
    def create_reels_container_resumable(
        self, ig_user_id: str, access_token: str, caption: str = '', share_to_feed: bool = True, account_id: int | None = None
    ) -> tuple[str, str]:
        """Resumable upload uchun container yaratadi va (container_id, upload_uri) qaytaradi."""
        pass

    @abstractmethod
    def upload_video_binary(
        self, upload_url: str, file_obj, file_size: int, access_token: str, account_id: int | None = None
    ) -> None:
        """Video binary oqimini Meta rupload serveriga yuklaydi."""
        pass

    @abstractmethod
    def check_container_status(self, container_id: str, access_token: str, account_id: int | None = None) -> dict:
        """Container tayyorlik holatini tekshiradi."""
        pass

    @abstractmethod
    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 45, delay: int = 2, account_id: int | None = None) -> bool:
        """Container yuklanishi tugashini kutadi."""
        pass

    @abstractmethod
    def publish_container(self, ig_user_id: str, container_id: str, access_token: str, account_id: int | None = None) -> str:
        """Containerni Instagramga nashr qiladi va media ID qaytaradi."""
        pass

    @abstractmethod
    def get_media_permalink(self, ig_media_id: str, access_token: str, account_id: int | None = None) -> str:
        """Nashr qilingan postning permalink havolasini oladi."""
        pass

    @abstractmethod
    def get_content_publishing_limit(self, ig_user_id: str, access_token: str, account_id: int | None = None) -> dict:
        """Foydalanuvchining kontent nashr etish kvotasi ma'lumotlarini (quota_usage, config) oladi."""
        pass

    @abstractmethod
    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None, account_id: int | None = None) -> dict:
        """Post statistikasi (views, likes, comments) ni oladi."""
        pass

    @abstractmethod
    def list_recent_media(self, access_token: str, limit: int = 25, return_paging_info: bool = False, account_id: int | None = None) -> list[dict] | tuple[list[dict], bool]:
        """Oxirgi medialar ro'yxatini oladi (maksimum 4 sahifa)."""
        pass

    @abstractmethod
    def get_media_insights(self, access_token: str, media_id: str, account_id: int | None = None) -> dict:
        """Media statistikasi va tahlillarini oladi (views, reach, likes, comments, shares, saved)."""
        pass


class RealInstagramClient(InstagramClient):
    """
    Haqiqiy Instagram Graph API mijoz adapteri.
    """

    @property
    def _requests(self):
        import tracker.services as svc
        return getattr(svc, 'requests', requests)

    def _check_business_headers(self, response, account_id: str | int | None = None):
        """Response sarlavhasidagi X-Business-Use-Case-Usage ni o'qib rate limiterga uzatadi."""
        if response is not None and hasattr(response, 'headers') and response.headers:
            rate_limiter.parse_and_apply_business_usage(response.headers, account_id=account_id)

    def build_auth_url(self, state: str) -> str:
        base_url = "https://www.instagram.com/oauth/authorize"
        redirect_uri = getattr(settings, 'INSTAGRAM_REDIRECT_URI', '').strip()
        params = {
            'client_id': str(settings.INSTAGRAM_APP_ID).strip(),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': getattr(settings, 'INSTAGRAM_SCOPE', 'instagram_business_basic,instagram_business_content_publish,instagram_business_manage_insights,instagram_business_manage_comments'),
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
            raise InstagramOAuthError(f"Access token olishda xatolik: {mask_sensitive_data(response.text)}")

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
            raise InstagramOAuthError(f"Long-lived token olishda xatolik: {mask_sensitive_data(response.text)}")

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
            raise InstagramOAuthError(f"Token yangilab bo'lmadi: {mask_sensitive_data(response.text)}")

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

    def check_account_type(self, access_token: str, ig_user_id: str = 'me', account_id: int | None = None) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}"
        try:
            response = self._requests.get(url, params={'fields': 'account_type,username', 'access_token': access_token}, timeout=15)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramNetworkError(f"Akkaunt turini tekshirishda tarmoq xatosi: {exc}") from exc

        if response.status_code != 200:
            return 'BUSINESS'

        data = response.json()
        acc_type = data.get('account_type')
        if not acc_type:
            return 'BUSINESS'
        return str(acc_type).upper()

    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '', account_id: int | None = None) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media"
        payload = {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': caption,
            'access_token': access_token,
        }
        try:
            response = self._requests.post(url, data=payload, timeout=30)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Reels container yaratishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Reels container yaratib bo'lmadi: {response.text}")

        container_id = response.json().get('id')
        if not container_id:
            raise InstagramPublishError("Container ID olinmadi.")
        return str(container_id)

    def create_reels_container_resumable(
        self, ig_user_id: str, access_token: str, caption: str = '', share_to_feed: bool = True, account_id: int | None = None
    ) -> tuple[str, str]:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media"
        payload = {
            'media_type': 'REELS',
            'upload_type': 'resumable',
            'caption': caption,
            'share_to_feed': 'true' if share_to_feed else 'false',
            'access_token': access_token,
        }
        try:
            response = self._requests.post(url, data=payload, timeout=30)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Resumable container yaratishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Resumable container yaratib bo'lmadi: {response.text}")

        data = response.json()
        container_id = data.get('id')
        if not container_id:
            raise InstagramPublishError("Container ID olinmadi.")
        upload_uri = data.get('uri') or f"https://rupload.facebook.com/ig-api-upload/v21.0/{container_id}"
        return str(container_id), str(upload_uri)

    def upload_video_binary(
        self, upload_url: str, file_obj, file_size: int, access_token: str, account_id: int | None = None
    ) -> None:
        headers = {
            'Authorization': f'OAuth {access_token}',
            'offset': '0',
            'file_size': str(file_size),
        }
        try:
            if hasattr(file_obj, 'seek'):
                file_obj.seek(0)
            response = self._requests.post(upload_url, data=file_obj, headers=headers, timeout=120)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Videoni Meta serveriga yuklashda tarmoq xatoligi: {exc}") from exc

        if response.status_code not in (200, 201):
            raise InstagramPublishError(f"Video binary yuklanmadi ({response.status_code}): {response.text}")

    def check_container_status(self, container_id: str, access_token: str, account_id: int | None = None) -> dict:
        url = f"https://graph.instagram.com/v21.0/{container_id}"
        params = {
            'fields': 'status_code,status',
            'access_token': access_token,
        }
        try:
            response = self._requests.get(url, params=params, timeout=15)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Container holatini tekshirishda xatolik: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Container holatini olib bo'lmadi: {response.text}")

        return response.json()

    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 45, delay: int = 2, account_id: int | None = None) -> bool:
        delays = [2, 3, 5, 8, 10]
        total_waited = 0
        max_wait_seconds = max_attempts * delay
        attempt = 0
        while total_waited < max_wait_seconds:
            if account_id:
                allowed, retry_after, _ = rate_limiter.acquire(account_id=account_id)
                if not allowed:
                    time.sleep(min(retry_after, 5.0))

            status_data = self.check_container_status(container_id, access_token, account_id=account_id)
            status_code = status_data.get('status_code')
            if status_code == 'FINISHED':
                return True
            elif status_code in ('ERROR', 'EXPIRED'):
                err_hint = (
                    f"Reels yuklash xatoligi: {status_data}. "
                    "Mumkin bo'lgan sabablar: "
                    "1) Video Reels talablariga mos emas (vertikal 9:16 emas, masalan gorizontal 16:9 yoki davomiyligi 3-90 soniya oralig'ida emas); "
                    "2) Video yuklash jarayonida xatolik yuz berdi; "
                    "3) Akkauntning kunlik Reels joylash limiti tugagan."
                )
                raise InstagramPublishError(err_hint)

            cur_delay = delays[min(attempt, len(delays) - 1)]
            time.sleep(cur_delay)
            total_waited += cur_delay
            attempt += 1

        raise InstagramPublishNetworkError(f"Reels videosini qayta ishlash vaqti tugadi (maksimal {max_wait_seconds} soniya kutildi).")

    def publish_container(self, ig_user_id: str, container_id: str, access_token: str, account_id: int | None = None) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/media_publish"
        payload = {
            'creation_id': container_id,
            'access_token': access_token,
        }
        try:
            response = self._requests.post(url, data=payload, timeout=30)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Reels'ni publish qilishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Reels publish qilinmadi: {response.text}")

        media_id = response.json().get('id')
        if not media_id:
            raise InstagramPublishError("Nashr etilgan media ID olinmadi.")
        return str(media_id)

    def get_media_permalink(self, ig_media_id: str, access_token: str, account_id: int | None = None) -> str:
        url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
        params = {
            'fields': 'permalink',
            'access_token': access_token,
        }
        try:
            response = self._requests.get(url, params=params, timeout=15)
            self._check_business_headers(response, account_id=account_id)
            if response.status_code == 200:
                return response.json().get('permalink') or f"https://www.instagram.com/reel/{ig_media_id}/"
        except requests.RequestException:
            pass
        return f"https://www.instagram.com/reel/{ig_media_id}/"

    def get_content_publishing_limit(self, ig_user_id: str, access_token: str, account_id: int | None = None) -> dict:
        url = f"https://graph.instagram.com/v21.0/{ig_user_id}/content_publishing_limit"
        params = {
            'fields': 'quota_usage,config',
            'access_token': access_token,
        }
        try:
            response = self._requests.get(url, params=params, timeout=15)
            self._check_business_headers(response, account_id=account_id)
        except requests.RequestException as exc:
            raise InstagramPublishNetworkError(f"Publishing limit olishda tarmoq xatoligi: {exc}") from exc

        if response.status_code != 200:
            raise InstagramPublishError(f"Publishing limit olib bo'lmadi ({response.status_code}): {response.text}")

        default_quota = int(getattr(settings, 'MAX_POSTS_PER_USER_PER_DAY', 100))
        res_data = response.json()
        items = res_data.get('data', [])
        if items and isinstance(items, list):
            item = items[0]
            config = item.get('config', {})
            return {
                'quota_usage': int(item.get('quota_usage', 0)),
                'quota_total': int(config.get('quota_total') or default_quota),
                'quota_duration': int(config.get('quota_duration', 86400)),
            }
        return {
            'quota_usage': int(res_data.get('quota_usage', 0)),
            'quota_total': int(res_data.get('config', {}).get('quota_total') or default_quota),
            'quota_duration': int(res_data.get('config', {}).get('quota_duration', 86400)),
        }

    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None, account_id: int | None = None) -> dict:
        media_url = f"https://graph.instagram.com/v21.0/{ig_media_id}"
        params = {
            'fields': 'like_count,comments_count,media_type',
            'access_token': access_token,
        }

        try:
            response = self._requests.get(media_url, params=params, timeout=15)
            self._check_business_headers(response, account_id=account_id)
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

    def list_recent_media(self, access_token: str, limit: int = 25, return_paging_info: bool = False, account_id: int | None = None) -> list[dict] | tuple[list[dict], bool]:
        return list_recent_media(token=access_token, limit=limit, return_paging_info=return_paging_info)

    def get_media_insights(self, access_token: str, media_id: str, account_id: int | None = None) -> dict:
        return get_media_insights(token=access_token, media_id=media_id)


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

    def check_account_type(self, access_token: str, ig_user_id: str = 'me', account_id: int | None = None) -> str:
        return 'BUSINESS'

    def create_reels_container(self, ig_user_id: str, video_url: str, access_token: str, caption: str = '', account_id: int | None = None) -> str:
        container_id = f"dry_run_container_{uuid.uuid4().hex[:10]}"
        return container_id

    def create_reels_container_resumable(
        self, ig_user_id: str, access_token: str, caption: str = '', share_to_feed: bool = True, account_id: int | None = None
    ) -> tuple[str, str]:
        container_id = f"dry_run_container_{uuid.uuid4().hex[:10]}"
        return container_id, f"https://rupload.facebook.com/ig-api-upload/v21.0/{container_id}"

    def upload_video_binary(
        self, upload_url: str, file_obj, file_size: int, access_token: str, account_id: int | None = None
    ) -> None:
        return

    def check_container_status(self, container_id: str, access_token: str, account_id: int | None = None) -> dict:
        return {
            "status_code": "FINISHED",
            "id": container_id,
        }

    def wait_for_container_ready(self, container_id: str, access_token: str, max_attempts: int = 45, delay: int = 2, account_id: int | None = None) -> bool:
        # Pollingni tekshirish uchun ixtiyoriy sun'iy kechikish
        sim_delay = getattr(settings, 'DRY_RUN_PUBLISH_DELAY_SECONDS', 2.0)
        if sim_delay and sim_delay > 0:
            time.sleep(min(sim_delay, 0.1))
        return True

    def publish_container(self, ig_user_id: str, container_id: str, access_token: str, account_id: int | None = None) -> str:
        media_id = f"dry_run_media_{uuid.uuid4().hex[:10]}"
        return media_id

    def get_media_permalink(self, ig_media_id: str, access_token: str, account_id: int | None = None) -> str:
        return f"https://www.instagram.com/reel/{ig_media_id}/"

    def get_content_publishing_limit(self, ig_user_id: str, access_token: str, account_id: int | None = None) -> dict:
        self._apply_simulated_delay()
        r = get_redis_client()
        # Redis orqali simulyatsiya sozlamalarini tekshirish
        sim_err = r.get(f"dry_run:sim:user:{ig_user_id}:publishing_limit_error")
        if sim_err:
            raise InstagramPublishError(f"Simulyatsiya qilingan publishing limit xatoligi: {sim_err}")

        default_quota = int(getattr(settings, 'MAX_POSTS_PER_USER_PER_DAY', 100))
        sim_usage = r.get(f"dry_run:sim:user:{ig_user_id}:quota_usage")
        sim_total = r.get(f"dry_run:sim:user:{ig_user_id}:quota_total")
        quota_usage = int(sim_usage) if sim_usage is not None else 0
        quota_total = int(sim_total) if sim_total is not None else default_quota

        return {
            'quota_usage': quota_usage,
            'quota_total': quota_total,
            'quota_duration': 86400,
        }

    def _apply_simulated_delay(self):
        delay_min = float(getattr(settings, 'DRY_RUN_API_DELAY_MIN', 0.0))
        delay_max = float(getattr(settings, 'DRY_RUN_API_DELAY_MAX', 0.0))
        if delay_max > 0:
            delay = random.uniform(delay_min, delay_max)
            if delay > 0:
                time.sleep(delay)

    def fetch_post_metrics(self, ig_media_id: str, access_token: str, post_id: int | None = None, account_id: int | None = None) -> dict:
        self._apply_simulated_delay()
        r = get_redis_client()
        r.incr("dry_run:sim:counters:fetch_post_metrics")

        # 0. Simulyatsiya qilingan response headers tekshiruvi (InstagramUser.id yoki post_id)
        target_account_id = account_id or post_id
        if target_account_id is not None:
            sim_headers = r.get(f"dry_run:sim:acc:{target_account_id}:headers") or r.get(f"dry_run:sim:post:{target_account_id}:headers")
            if sim_headers:
                import json
                try:
                    h_dict = json.loads(sim_headers)
                    rate_limiter.parse_and_apply_business_usage(h_dict, account_id=target_account_id)
                except Exception:
                    pass

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

    def list_recent_media(self, access_token: str, limit: int = 25, return_paging_info: bool = False) -> list[dict] | tuple[list[dict], bool]:
        self._apply_simulated_delay()
        r = get_redis_client()
        r.incr("dry_run:sim:counters:list_recent_media")
        
        if access_token:
            tok_err = r.get(f"dry_run:sim:token:{access_token}:error")
            if tok_err and str(tok_err) == "token_invalid":
                record_instagram_error(InstagramErrorType.TOKEN_INVALID)
                raise TokenInvalid("Token yaroqsiz (simulyatsiya)", error_code=190, error_subcode=463)

        media_list = []
        try:
            cached_media_ids_raw = r.get(f"dry_run:sim:token_media:{access_token}")
            if cached_media_ids_raw:
                media_ids = json.loads(cached_media_ids_raw)
                for mid in media_ids:
                    media_list.append({
                        'id': mid,
                        'like_count': 35,
                        'comments_count': 5,
                        'media_type': 'VIDEO',
                        'media_product_type': 'REELS',
                        'permalink': f"https://www.instagram.com/reel/{mid}/",
                    })
            else:
                # Benchmark emas, boshqa testlar uchun DB zaxirasi
                from .models import Post, InstagramUser
                user = InstagramUser.objects.filter(access_token=access_token).first()
                if user:
                    posts = Post.objects.filter(link__user=user).exclude(status='deleted')
                    for p in posts:
                        err = r.get(f"dry_run:sim:post:{p.id}:error")
                        if err and str(err) == "media_not_found":
                            continue
                        media_list.append({
                            'id': p.ig_media_id,
                            'like_count': p.likes + 2,
                            'comments_count': p.comments_count + 1,
                            'media_type': 'VIDEO',
                            'media_product_type': 'REELS',
                            'permalink': f"https://www.instagram.com/reel/{p.ig_media_id}/",
                        })
        except Exception as exc:
            logger.error("Simulyatsiya list_recent_media xatoligi: %s", exc)
            pass

        if return_paging_info:
            return media_list, True
        return media_list

    def get_media_insights(self, access_token: str, media_id: str) -> dict:
        self._apply_simulated_delay()
        r = get_redis_client()
        r.incr("dry_run:sim:counters:get_media_insights")
        
        if access_token:
            tok_err = r.get(f"dry_run:sim:token:{access_token}:error")
            if tok_err and str(tok_err) == "token_invalid":
                record_instagram_error(InstagramErrorType.TOKEN_INVALID)
                raise TokenInvalid("Token yaroqsiz (simulyatsiya)", error_code=190, error_subcode=463)

        sim_views = 250
        try:
            from .models import Post
            post = Post.objects.filter(ig_media_id=media_id).first()
            if post:
                sim_views_key = r.get(f"dry_run:sim:post:{post.id}:views")
                if sim_views_key:
                    sim_views = int(sim_views_key)
                else:
                    sim_views = max(post.views + 50, 250)
        except Exception:
            pass

        return {
            'views': sim_views,
            'reach': int(sim_views * 0.8),
            'likes': max(1, sim_views // 10),
            'comments': max(0, sim_views // 50),
            'comments_count': max(0, sim_views // 50),
            'shares': 3,
            'saved': 2,
            'raw': {'data': []},
        }


def _check_instagram_response(response: requests.Response, operation: str = "api_request") -> dict:
    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code != 200 or (isinstance(data, dict) and 'error' in data and not data.get('data')):
        err_info = data.get('error', {}) if isinstance(data, dict) else {}
        err_message = err_info.get('message') or response.text or f"HTTP {response.status_code} xatoligi"
        err_code = err_info.get('code')
        err_subcode = err_info.get('error_subcode')

        try:
            if err_code is not None:
                err_code = int(err_code)
        except (ValueError, TypeError):
            pass

        try:
            if err_subcode is not None:
                err_subcode = int(err_subcode)
        except (ValueError, TypeError):
            pass

        if err_code == 190 or str(err_code) == '190' or response.status_code == 401:
            record_instagram_error(InstagramErrorType.TOKEN_INVALID)
            log_instagram_error(
                InstagramErrorType.TOKEN_INVALID,
                f"[{operation}] Instagram token yaroqsiz (code 190): {err_message}",
                code=err_code,
                subcode=err_subcode,
            )
            raise TokenInvalid(
                message=f"Instagram access token yaroqsiz (code 190): {err_message}",
                error_code=190,
                error_subcode=err_subcode,
                status_code=response.status_code,
            )

        error_type = classify_instagram_error(response=response)
        record_instagram_error(error_type)
        log_instagram_error(
            error_type,
            f"[{operation}] Instagram API xatosi: {err_message}",
            code=err_code,
            subcode=err_subcode,
        )

        if error_type == InstagramErrorType.RATE_LIMIT:
            raise InstagramRateLimitError(
                f"Instagram rate limit ({operation}): {err_message}",
                status_code=response.status_code,
                error_code=err_code,
                error_subcode=err_subcode,
            )
        elif error_type == InstagramErrorType.SERVER_ERROR:
            raise InstagramMetricsNetworkError(
                f"Instagram server xatosi ({operation}): {err_message}",
                error_type=error_type,
                status_code=response.status_code,
                error_code=err_code,
                error_subcode=err_subcode,
            )
        else:
            raise InstagramMetricsError(
                f"Instagram API xatosi ({operation}, HTTP {response.status_code}): {err_message}",
                error_type=error_type,
                status_code=response.status_code,
                error_code=err_code,
                error_subcode=err_subcode,
            )

    return data


def list_recent_media(token: str, limit: int = 25, return_paging_info: bool = False) -> list[dict] | tuple[list[dict], bool]:
    """
    Foydalanuvchining so'nggi medialarini (Reels/postlar) oladi.
    GET https://graph.instagram.com/me/media?fields=id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url
    paging.next bo'yicha maksimum 4 sahifagacha o'qiydi.
    Xato kodi 190 bo'lsa TokenInvalid xatosi ko'tariladi.
    """
    if not token:
        raise TokenInvalid("Access token kiritilmagan", error_code=190)

    url = "https://graph.instagram.com/me/media"
    params = {
        'fields': 'id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count,thumbnail_url',
        'limit': int(limit),
        'access_token': token,
    }

    all_media: list[dict] = []
    current_url = url
    current_params = params
    max_pages = 4
    pages_fetched = 0
    pagination_completed = True

    while current_url and pages_fetched < max_pages:
        try:
            response = requests.get(
                current_url,
                params=current_params if pages_fetched == 0 else None,
                timeout=15,
            )
        except requests.RequestException as exc:
            record_instagram_error(InstagramErrorType.SERVER_ERROR)
            log_instagram_error(InstagramErrorType.SERVER_ERROR, f"list_recent_media tarmoq xatosi: {exc}")
            raise InstagramNetworkError(f"list_recent_media tarmoq xatosi: {exc}") from exc

        data = _check_instagram_response(response, operation="list_recent_media")
        items = data.get('data', [])
        if isinstance(items, list):
            all_media.extend(items)
        pages_fetched += 1

        paging = data.get('paging', {})
        next_url = paging.get('next') if isinstance(paging, dict) else None
        if not next_url:
            pagination_completed = True
            break
        current_url = next_url
        current_params = None
    else:
        if current_url:
            pagination_completed = False

    if return_paging_info:
        return all_media, pagination_completed
    return all_media


def get_media_insights(token: str, media_id: str) -> dict:
    """
    Berilgan media uchun ko'rishlar, reach, likes, izohlar, shares va saved metrikalarini oladi.
    GET https://graph.instagram.com/{media_id}/insights?metric=views,reach,likes,comments,shares,saved
    Metrik nomlari rasmiy Meta hujjatiga mos. Xato kodi 190 bo'lsa TokenInvalid ko'tariladi.
    """
    if not token:
        raise TokenInvalid("Access token kiritilmagan", error_code=190)
    if not media_id:
        raise ValueError("media_id kiritilishi shart")

    url = f"https://graph.instagram.com/{media_id}/insights"
    params = {
        'metric': 'views,reach,likes,comments,shares,saved',
        'access_token': token,
    }

    try:
        response = requests.get(url, params=params, timeout=15)
    except requests.RequestException as exc:
        record_instagram_error(InstagramErrorType.SERVER_ERROR)
        log_instagram_error(InstagramErrorType.SERVER_ERROR, f"get_media_insights tarmoq xatosi: {exc}")
        raise InstagramNetworkError(f"get_media_insights tarmoq xatosi: {exc}") from exc

    data = _check_instagram_response(response, operation="get_media_insights")

    metrics = {
        'views': 0,
        'reach': 0,
        'likes': 0,
        'comments': 0,
        'comments_count': 0,
        'shares': 0,
        'saved': 0,
    }

    raw_items = data.get('data', [])
    if isinstance(raw_items, list):
        for item in raw_items:
            name = item.get('name')
            val = 0
            if 'values' in item and isinstance(item['values'], list) and len(item['values']) > 0:
                val = item['values'][0].get('value', 0)
            elif 'total_value' in item and isinstance(item['total_value'], dict):
                val = item['total_value'].get('value', 0)
            elif 'value' in item:
                val = item.get('value', 0)

            try:
                val = int(val or 0)
            except (ValueError, TypeError):
                val = 0

            if name:
                metrics[name] = val
                if name == 'comments':
                    metrics['comments_count'] = val

    metrics['raw'] = data
    return metrics


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
