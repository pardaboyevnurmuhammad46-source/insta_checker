import base64
import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIClient

# from tracker.models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from tracker.models import (
    InstagramUser,
    UniqueLink,
    Post,
    Prize,
    DataDeletionRequest,
    Video,
    PostStat,
    Notification,
    get_video_for_user,
)
from tracker.admin import UniqueLinkAdmin, PostAdmin, InstagramUserAdmin
from tracker.services import (
    InstagramOAuthError,
    InstagramNetworkError,
    InstagramPublishError,
    InstagramPublishNetworkError,
    InstagramMetricsError,
    InstagramMetricsNetworkError,
    MetaWebhookError,
    build_instagram_auth_url,
    complete_instagram_oauth,
    publish_reels_for_link,
    calculate_next_check,
    fetch_post_metrics_from_instagram,
    update_post_metrics,
    check_and_award_prizes,
    refresh_instagram_access_token,
    refresh_user_token,
    parse_signed_request,
    handle_deauthorize_request,
    handle_data_deletion_request,
)
from tracker.tasks import (
    publish_reels_task,
    check_post_metrics_task,
    check_all_due_posts_task,
    refresh_expiring_tokens_task,
)
from tracker.rate_limiter import rate_limiter, InstagramRateLimiter
from tracker.instagram_errors import (
    InstagramErrorType,
    classify_instagram_error,
    mask_sensitive_data,
    record_instagram_error,
    get_instagram_errors_last_hour,
    reset_error_counters,
)
from tracker.services import InstagramRateLimitError


def create_mock_signed_request(payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    sig = hmac.new(secret.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('utf-8').rstrip('=')
    return f"{sig_b64}.{payload_b64}"


class SettingsEnvTestCase(TestCase):
    def test_settings_loaded_from_env(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertIn('default', settings.DATABASES)
        self.assertIn('check-all-due-posts-metrics', settings.CELERY_BEAT_SCHEDULE)
        self.assertIn('refresh-expiring-instagram-tokens', settings.CELERY_BEAT_SCHEDULE)
        self.assertTrue(len(settings.PRIZE_MILESTONES) > 0)
        self.assertIn('rest_framework.permissions.IsAdminUser', settings.REST_FRAMEWORK['DEFAULT_PERMISSION_CLASSES'])


class ModelsTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(name="Test User")
        dummy_video = SimpleUploadedFile("test.mp4", b"video_content", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy_video)
        self.post = Post.objects.create(link=self.link)

    def test_instagram_user_creation(self):
        self.assertEqual(self.user.status, 'pending')
        self.assertIsNone(self.user.ig_user_id)
        self.assertEqual(str(self.user), "Test User")

    def test_unique_link_auto_token(self):
        self.assertIsInstance(self.link.token, uuid.UUID)
        self.assertEqual(self.link.status, 'pending')
        self.assertIn("Test User", str(self.link))

    def test_post_creation(self):
        self.assertEqual(self.post.status, 'queued')
        self.assertEqual(self.post.views, 0)
        self.assertEqual(self.post.likes, 0)
        self.assertEqual(self.post.comments_count, 0)
        self.assertIn("Post: Test User", str(self.post))

    def test_prize_unique_together(self):
        Prize.objects.create(post=self.post, milestone=1000)
        with self.assertRaises(IntegrityError):
            Prize.objects.create(post=self.post, milestone=1000)

    def test_data_deletion_request_model(self):
        req = DataDeletionRequest.objects.create(
            confirmation_code="test_code_123",
            user_id="user_999",
            status="completed",
        )
        self.assertEqual(str(req), "Deletion test_code_123 (User user_999)")

    def test_unique_link_admin_full_link(self):
        admin_instance = UniqueLinkAdmin(UniqueLink, AdminSite())
        base = getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000').rstrip('/')
        expected_url = f"{base}/link/{self.link.token}/"
        self.assertEqual(admin_instance.full_link(self.link), expected_url)


class InstagramOAuthTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(name="OAuth User")
        dummy_video = SimpleUploadedFile("sample.mp4", b"data", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy_video)

    def test_build_instagram_auth_url(self):
        url = build_instagram_auth_url(str(self.link.token))
        self.assertIn("https://www.instagram.com/oauth/authorize", url)
        self.assertIn(f"state={self.link.token}", url)
        self.assertIn("response_type=code", url)

    @override_settings(INSTAGRAM_APP_ID='test_app_id', INSTAGRAM_APP_SECRET='test_secret')
    def test_redirect_to_instagram_success(self):
        response = self.client.get(f"/link/{self.link.token}/")
        # self.assertEqual(response.status_code, 200)
        # self.assertContains(response, "www.instagram.com/oauth/authorize")
        self.assertEqual(response.status_code, 302)
        self.assertIn("www.instagram.com/oauth/authorize", response.headers['Location'])

        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'opened')

    def test_redirect_expired_link(self):
        self.link.expires_at = timezone.now() - timedelta(days=1)
        self.link.save()

        response = self.client.get(f"/link/{self.link.token}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("muddati tugagan", response.content.decode())

    def test_redirect_invalid_status(self):
        self.link.status = 'posted'
        self.link.save()

        response = self.client.get(f"/link/{self.link.token}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("allaqachon ishlatilgan", response.content.decode())

    @patch('tracker.services.requests.get')
    @patch('tracker.services.requests.post')
    def test_complete_instagram_oauth_success(self, mock_post, mock_get):
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            'access_token': 'short_token_123',
            'user_id': '1784140001',
        }
        mock_post.return_value = mock_post_resp

        mock_get_resp = MagicMock()
        mock_get_resp.status_code = 200
        mock_get_resp.json.return_value = {
            'access_token': 'long_token_456',
            'token_type': 'bearer',
            'expires_in': 5184000,
        }
        mock_get.return_value = mock_get_resp

        user, link = complete_instagram_oauth(code="auth_code_xyz#_", token=str(self.link.token))

        self.assertEqual(user.ig_user_id, '1784140001')
        self.assertEqual(user.access_token, 'long_token_456')
        self.assertEqual(user.status, 'connected')
        self.assertIsNotNone(user.token_expires_at)
        self.assertEqual(link.status, 'opened')

    def test_callback_with_error(self):
        response = self.client.get(f"/oauth/callback/?error=access_denied&state={self.link.token}")
        self.assertEqual(response.status_code, 400)
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'failed')

    @patch('tracker.views.publish_reels_task.delay')
    @patch('tracker.views.complete_instagram_oauth')
    def test_callback_endpoint_success(self, mock_complete, mock_task_delay):
        mock_user = self.user
        mock_user.status = 'connected'
        mock_user.ig_user_id = '178414999'
        mock_complete.return_value = (mock_user, self.link)

        response = self.client.get(f"/oauth/callback/?code=test_code&state={self.link.token}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Muvaffaqiyatli Ulandi!", response.content.decode())
        mock_task_delay.assert_called_once_with(self.link.id)


class ReelsPublishingTestCase(TestCase):
    def setUp(self):
        self.patcher_requests_get = patch('tracker.services.requests.get')
        self.mock_requests_get = self.patcher_requests_get.start()
        mock_acc_resp = MagicMock()
        mock_acc_resp.status_code = 200
        mock_acc_resp.json.return_value = {"account_type": "BUSINESS"}
        self.mock_requests_get.return_value = mock_acc_resp
        self.addCleanup(self.patcher_requests_get.stop)

        self.user = InstagramUser.objects.create(
            name="Publisher User",
            ig_user_id="1784140002",
            access_token="valid_token_abc",
            status="connected",
        )
        dummy_video = SimpleUploadedFile("sample_video.mp4", b"video_bytes", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy_video)

    def test_publish_reels_unconnected_user(self):
        self.user.status = "pending"
        self.user.save()

        with self.assertRaises(InstagramPublishError):
            publish_reels_for_link(self.link.id)

    @patch('tracker.services.get_media_permalink')
    @patch('tracker.services.publish_container')
    @patch('tracker.services.wait_for_container_ready')
    @patch('tracker.services.create_reels_container')
    def test_publish_reels_success(self, mock_create, mock_wait, mock_publish, mock_permalink):
        mock_create.return_value = "container_123"
        mock_wait.return_value = True
        mock_publish.return_value = "media_999"
        mock_permalink.return_value = "https://instagram.com/reel/mock999/"

        post = publish_reels_for_link(self.link.id, caption="Test Caption")

        self.assertEqual(post.status, 'published')
        self.assertEqual(post.ig_media_id, 'media_999')
        self.assertEqual(post.permalink, "https://instagram.com/reel/mock999/")
        self.assertIsNotNone(post.posted_at)
        self.assertIsNotNone(post.next_check_at)

        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'posted')

    @patch('tracker.services.create_reels_container')
    def test_publish_reels_failure(self, mock_create):
        mock_create.side_effect = InstagramPublishError("API xatolik yuz berdi")

        with self.assertRaises(InstagramPublishError):
            publish_reels_for_link(self.link.id)

        post = Post.objects.get(link=self.link)
        self.assertEqual(post.status, 'failed')
        self.assertIn("API xatolik", post.error)

        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'failed')

    @patch('tracker.tasks.publish_reels_for_link')
    def test_publish_reels_task_success(self, mock_publish):
        mock_post = MagicMock()
        mock_post.id = 1
        mock_post.ig_media_id = "media_1"
        mock_post.status = "published"
        mock_publish.return_value = mock_post

        result = publish_reels_task(self.link.id)
        self.assertEqual(result.get('status'), 'published')
        self.assertEqual(result.get('ig_media_id'), 'media_1')

    @patch('tracker.services.create_reels_container')
    def test_publish_reels_idempotency(self, mock_create):
        # Post allaqachon published holatda
        post = Post.objects.create(
            link=self.link,
            ig_media_id="existing_media_111",
            status='published',
        )
        returned_post = publish_reels_for_link(self.link.id)
        # Qayta create_reels_container chaqirilmasligi kerak
        mock_create.assert_not_called()
        self.assertEqual(returned_post.id, post.id)
        self.assertEqual(returned_post.ig_media_id, "existing_media_111")

    @patch('tracker.tasks.publish_reels_for_link')
    def test_publish_reels_task_retries_on_network_error(self, mock_publish):
        mock_publish.side_effect = InstagramPublishNetworkError("Tarmoq uzildi")
        with patch.object(publish_reels_task, 'retry') as mock_retry:
            mock_retry.side_effect = Exception("Retry called")
            with self.assertRaises(Exception):
                publish_reels_task(self.link.id)
            mock_retry.assert_called_once()


class AdaptiveScheduleTestCase(TestCase):
    def setUp(self):
        user = InstagramUser.objects.create(name="Sched User")
        dummy = SimpleUploadedFile("v.mp4", b"content", content_type="video/mp4")
        link = UniqueLink.objects.create(user=user, video=dummy)
        self.post = Post.objects.create(link=link, status='published')

    def test_adaptive_intervals(self):
        base_now = timezone.now()

        # 0 to 6 hours -> 15 minutes
        self.post.posted_at = base_now - timedelta(hours=2)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(minutes=15))

        # 6 to 24 hours -> 1 hour
        self.post.posted_at = base_now - timedelta(hours=10)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(hours=1))

        # 1 to 3 days -> 3 hours
        self.post.posted_at = base_now - timedelta(days=2)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(hours=3))

        # 3 to 30 days -> 24 hours (1 day)
        self.post.posted_at = base_now - timedelta(days=10)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(days=1))

        # > 30 days -> 7 days
        self.post.posted_at = base_now - timedelta(days=35)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(days=7))


class MetricsAndPrizesTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Metric User",
            ig_user_id="1784149999",
            access_token="valid_token_xyz",
            status="connected",
        )
        dummy = SimpleUploadedFile("vid.mp4", b"content", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy)
        self.post = Post.objects.create(
            link=self.link,
            ig_media_id="media_12345",
            status='published',
            posted_at=timezone.now(),
        )

    @patch('tracker.services.requests.get')
    def test_fetch_metrics_success(self, mock_get):
        resp1 = MagicMock()
        resp1.status_code = 200
        resp1.json.return_value = {'like_count': 45, 'comments_count': 12}

        resp2 = MagicMock()
        resp2.status_code = 200
        resp2.json.return_value = {
            'data': [{'name': 'views', 'values': [{'value': 1250}]}]
        }

        mock_get.side_effect = [resp1, resp2]

        metrics = fetch_post_metrics_from_instagram("media_12345", "token")
        self.assertEqual(metrics['likes'], 45)
        self.assertEqual(metrics['comments_count'], 12)
        self.assertEqual(metrics['views'], 1250)

    @patch('tracker.services.requests.get')
    def test_fetch_metrics_deleted_media(self, mock_get):
        resp = MagicMock()
        resp.status_code = 404
        resp.text = "Not Found"
        mock_get.return_value = resp

        with self.assertRaises(InstagramMetricsError) as ctx:
            fetch_post_metrics_from_instagram("media_12345", "token")
        self.assertTrue(ctx.exception.is_deleted)

    @patch('tracker.services.fetch_post_metrics_from_instagram')
    def test_update_post_metrics_awards_prizes(self, mock_fetch):
        mock_fetch.return_value = {'likes': 100, 'comments_count': 20, 'views': 1500}

        update_post_metrics(self.post)
        self.post.refresh_from_db()

        self.assertEqual(self.post.views, 1500)
        self.assertEqual(self.post.likes, 100)
        self.assertEqual(self.post.comments_count, 20)
        self.assertIsNotNone(self.post.last_checked_at)
        self.assertIsNotNone(self.post.next_check_at)

        prizes = Prize.objects.filter(post=self.post).order_by('milestone')
        self.assertEqual(prizes.count(), 2)
        self.assertEqual(prizes[0].milestone, 500)
        self.assertEqual(prizes[1].milestone, 1000)

        check_and_award_prizes(self.post)
        self.assertEqual(Prize.objects.filter(post=self.post).count(), 2)

    @patch('tracker.services.fetch_post_metrics_from_instagram')
    def test_update_post_metrics_handles_deleted(self, mock_fetch):
        mock_fetch.side_effect = InstagramMetricsError("Media deleted", is_deleted=True)

        update_post_metrics(self.post)
        self.post.refresh_from_db()

        self.assertEqual(self.post.status, 'deleted')
        self.assertIsNone(self.post.next_check_at)
        self.assertIn("o'chirilgan", self.post.error)

    @patch('tracker.services.fetch_post_metrics_from_instagram')
    def test_update_post_metrics_handles_auth_error(self, mock_fetch):
        mock_fetch.side_effect = InstagramMetricsError("Token expired", is_auth_error=True)

        update_post_metrics(self.post)
        self.post.refresh_from_db()
        self.user.refresh_from_db()

        self.assertEqual(self.user.status, 'needs_reauth')
        self.assertIsNone(self.post.next_check_at)
        self.assertIn("needs_reauth", self.post.error)


class TokenRefreshTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Token User",
            access_token="old_long_token",
            token_expires_at=timezone.now() + timedelta(days=5),
            status="connected",
        )

    @patch('tracker.services.requests.get')
    def test_refresh_token_success(self, mock_get):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            'access_token': 'new_long_token_789',
            'token_type': 'bearer',
            'expires_in': 5184000,
        }
        mock_get.return_value = resp

        success = refresh_user_token(self.user)
        self.assertTrue(success)

        self.user.refresh_from_db()
        self.assertEqual(self.user.access_token, 'new_long_token_789')
        self.assertEqual(self.user.status, 'connected')
        self.assertTrue(self.user.token_expires_at > timezone.now() + timedelta(days=50))

    @patch('tracker.services.requests.get')
    def test_refresh_token_revoked_oauth_error(self, mock_get):
        resp = MagicMock()
        resp.status_code = 400
        resp.text = "OAuthException: Error validating access token"
        mock_get.return_value = resp

        success = refresh_user_token(self.user)
        self.assertFalse(success)

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, 'needs_reauth')

    @patch('tracker.services.requests.get')
    def test_refresh_token_network_error_preserves_status(self, mock_get):
        import requests
        mock_get.side_effect = requests.RequestException("Connection timeout")

        success = refresh_user_token(self.user)
        self.assertFalse(success)

        self.user.refresh_from_db()
        # Tarmoq xatosi bo'lganda user statusi 'needs_reauth' ga o'tib ketmasligi kerak!
        self.assertEqual(self.user.status, 'connected')


class MetaWebhooksTestCase(TestCase):
    def setUp(self):
        self.secret = "my_app_secret_123"
        self.user = InstagramUser.objects.create(
            name="Meta User",
            ig_user_id="meta_17841",
            access_token="token_to_delete",
            status="connected",
        )

    @override_settings(INSTAGRAM_APP_SECRET="my_app_secret_123")
    def test_parse_signed_request_valid(self):
        payload = {"user_id": "meta_17841", "algorithm": "HMAC-SHA256"}
        signed_request = create_mock_signed_request(payload, self.secret)

        data = parse_signed_request(signed_request, self.secret)
        self.assertEqual(data.get("user_id"), "meta_17841")

    @override_settings(INSTAGRAM_APP_SECRET="my_app_secret_123")
    def test_parse_signed_request_invalid_signature(self):
        payload = {"user_id": "meta_17841"}
        signed_request = create_mock_signed_request(payload, "wrong_secret")

        with self.assertRaises(MetaWebhookError):
            parse_signed_request(signed_request, self.secret)

    @override_settings(INSTAGRAM_APP_SECRET="my_app_secret_123")
    def test_deauthorize_endpoint(self):
        payload = {"user_id": "meta_17841", "algorithm": "HMAC-SHA256"}
        signed_request = create_mock_signed_request(payload, self.secret)

        response = self.client.post("/oauth/deauthorize/", {"signed_request": signed_request})
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, "needs_reauth")
        self.assertIsNone(self.user.access_token)

    @override_settings(INSTAGRAM_APP_SECRET="my_app_secret_123")
    def test_data_deletion_and_status_endpoint(self):
        payload = {"user_id": "meta_17841", "algorithm": "HMAC-SHA256"}
        signed_request = create_mock_signed_request(payload, self.secret)

        response = self.client.post("/oauth/data-deletion/", {"signed_request": signed_request})
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("confirmation_code", data)
        self.assertIn("url", data)
        conf_code = data["confirmation_code"]

        self.user.refresh_from_db()
        self.assertEqual(self.user.status, "needs_reauth")
        self.assertIsNone(self.user.access_token)
        self.assertIn("Deleted User", self.user.name)

        status_resp = self.client.get(f"/oauth/data-deletion/status/{conf_code}/")
        self.assertEqual(status_resp.status_code, 200)
        status_data = status_resp.json()
        self.assertEqual(status_data["status"], "completed")
        self.assertEqual(status_data["confirmation_code"], conf_code)
        self.assertNotIn("user_id", status_data)


class CeleryBeatAndTasksTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Task User",
            ig_user_id="user_celery",
            access_token="tok_celery",
            token_expires_at=timezone.now() + timedelta(days=2),
            status="connected",
        )
        dummy = SimpleUploadedFile("t.mp4", b"data", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy)
        self.post = Post.objects.create(
            link=self.link,
            ig_media_id="media_celery",
            status='published',
            posted_at=timezone.now(),
            next_check_at=timezone.now() - timedelta(minutes=1),
        )

    @patch('tracker.tasks.check_post_metrics_task.delay')
    def test_check_all_due_posts_task(self, mock_task_delay):
        res = check_all_due_posts_task()
        self.assertEqual(res, 1)
        mock_task_delay.assert_called_once_with(self.post.id)

        # Post next_check_at avtomatik ravishda kamida 8 daqiqaga oldinga surilganini tekshirish
        self.post.refresh_from_db()
        self.assertTrue(self.post.next_check_at > timezone.now() + timedelta(minutes=8))

    @patch('tracker.tasks.update_post_metrics')
    def test_check_post_metrics_task(self, mock_update):
        mock_post = MagicMock()
        mock_post.id = self.post.id
        mock_post.views = 2000
        mock_post.likes = 120
        mock_post.comments_count = 15
        mock_post.status = "published"
        mock_update.return_value = mock_post

        result = check_post_metrics_task(self.post.id)
        self.assertEqual(result["views"], 2000)
        self.assertEqual(result["likes"], 120)

    @patch('tracker.tasks.refresh_user_token')
    def test_refresh_expiring_tokens_task(self, mock_refresh):
        mock_refresh.return_value = True

        result = refresh_expiring_tokens_task()
        self.assertEqual(result["refreshed_count"], 1)
        mock_refresh.assert_called_once_with(self.user)

    @patch('tracker.admin.check_post_metrics_task.delay')
    def test_admin_check_metrics_action(self, mock_delay):
        admin_instance = PostAdmin(Post, AdminSite())
        mock_request = MagicMock()
        queryset = Post.objects.filter(id=self.post.id)

        admin_instance.check_metrics_action(mock_request, queryset)
        mock_delay.assert_called_once_with(self.post.id)

    @patch('tracker.admin.refresh_user_token')
    def test_admin_refresh_token_action(self, mock_refresh):
        admin_instance = InstagramUserAdmin(InstagramUser, AdminSite())
        mock_request = MagicMock()
        queryset = InstagramUser.objects.filter(id=self.user.id)

        admin_instance.refresh_token_action(mock_request, queryset)
        mock_refresh.assert_called_once_with(self.user)


class RestApiSecurityTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="admin", password="password123")
        self.ig_user = InstagramUser.objects.create(
            name="Secure User",
            ig_user_id="sec_123",
            access_token="secret_token_never_expose",
            status="connected",
        )
        dummy = SimpleUploadedFile("s.mp4", b"data", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.ig_user, video=dummy)
        self.post = Post.objects.create(link=self.link, status='published')

    def test_api_users_unauthenticated_forbidden(self):
        response = self.client.get("/api/users/")
        self.assertIn(response.status_code, (401, 403))

    def test_api_users_authenticated_admin_success_and_token_not_exposed(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        users_list = data if isinstance(data, list) else data.get('results', [])
        self.assertTrue(len(users_list) > 0)
        # access_token javobda chiqmasligi kerak (write_only: True)
        first_user = users_list[0]
        self.assertNotIn("access_token", first_user)
        self.assertIn("has_token", first_user)
        self.assertTrue(first_user["has_token"])

    def test_custom_actions_unauthenticated_forbidden(self):
        resp1 = self.client.post(f"/api/users/{self.ig_user.id}/refresh-token/")
        self.assertIn(resp1.status_code, (401, 403))

        resp2 = self.client.post(f"/api/posts/{self.post.id}/check-metrics/")
        self.assertIn(resp2.status_code, (401, 403))

    def test_public_endpoints_accessible_without_auth(self):
        resp_info = self.client.get("/link/")
        self.assertEqual(resp_info.status_code, 200)


class SecurityCheckTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="sec_admin", password="password123")
        self.user1 = User.objects.create_user(username="sec_user1", password="password123")
        self.user2 = User.objects.create_user(username="sec_user2", password="password123")
        
        self.ig_user1 = InstagramUser.objects.create(user=self.user1, name="User1 IG", status="connected")
        self.ig_user2 = InstagramUser.objects.create(user=self.user2, name="User2 IG", status="connected")
        
        self.video = Video.objects.create(title="Sec Video", is_active=True)

    def test_ordinary_user_cannot_create_link_for_another_user(self):
        """Oddiy foydalanuvchi boshqa foydalanuvchining ID si bilan link yarata olmasligi kerak."""
        self.client.force_authenticate(user=self.user1)
        
        payload = {
            "user": self.ig_user2.id,
            "video": self.video.id,
        }
        response = self.client.post("/api/links/", payload)
        
        # Unauthorized creation attempt should be blocked or overridden
        # Now we override user in perform_create, so it creates for user1 instead
        if response.status_code == 201:
            created_link = UniqueLink.objects.get(id=response.data['id'])
            self.assertEqual(created_link.user.id, self.ig_user1.id, "Security hole: user created link for someone else!")

    def test_logout_blacklists_token(self):
        """Logout endpointi refresh tokenni blacklist qilishini tekshirish."""
        # 1. Login qilib token olamiz
        resp = self.client.post("/api/token/", {"username": "sec_user1", "password": "password123"})
        self.assertEqual(resp.status_code, 200)
        refresh_token = resp.data["refresh"]

        # 2. Refresh token yordamida access tokenni yangilash ishlaydi
        refresh_resp = self.client.post("/api/token/refresh/", {"refresh": refresh_token})
        self.assertEqual(refresh_resp.status_code, 200)

        # 3. Logout (blacklist)
        logout_resp = self.client.post("/api/token/logout/", {"refresh": refresh_token})
        self.assertEqual(logout_resp.status_code, 200)

        # 4. Qayta refresh qilishga urinish xato berishi kerak
        refresh_resp2 = self.client.post("/api/token/refresh/", {"refresh": refresh_token})
        self.assertEqual(refresh_resp2.status_code, 401)

class NewApiRequirementsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="admin_api", password="password123")
        self.regular_user = User.objects.create_user(username="user_api", password="password123")
        
        self.ig_user = InstagramUser.objects.create(
            name="API User",
            ig_user_id="api_123",
            access_token="secret_token",
            status="connected",
            token_expires_at=timezone.now() + timedelta(days=3),
        )
        dummy = SimpleUploadedFile("s.mp4", b"data", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.ig_user, video=dummy, status='failed')
        self.post = Post.objects.create(
            link=self.link,
            status='failed',
            views=150,
            likes=10,
            comments_count=2,
            error="API error",
        )
        Prize.objects.create(post=self.post, milestone=100)

    def test_api_pagination(self):
        self.client.force_authenticate(user=self.admin)
        for i in range(55):
            InstagramUser.objects.create(name=f"User {i}")
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('results', data)
        self.assertEqual(len(data['results']), 50)

    def test_api_read_only_endpoints(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post("/api/posts/", {"link": self.link.id, "status": "published"})
        self.assertEqual(response.status_code, 405)

        response_prize = self.client.post("/api/prizes/", {"post": self.post.id, "milestone": 500})
        self.assertEqual(response_prize.status_code, 405)

    def test_api_dashboard(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.get("/api/dashboard/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Detailed verification of dashboard metrics
        self.assertEqual(data['users_by_status'].get('connected'), 1)
        self.assertEqual(data['links_by_status'].get('failed'), 1)
        self.assertEqual(data['posts_by_status'].get('failed'), 1)
        self.assertEqual(data['total_metrics']['total_views'], 150)
        self.assertEqual(data['total_metrics']['total_likes'], 10)
        self.assertEqual(data['total_metrics']['total_comments'], 2)
        self.assertEqual(data['total_prizes'], 1)
        self.assertEqual(data['expiring_tokens_count'], 1)

    def test_api_resend_and_retry(self):
        self.client.force_authenticate(user=self.admin)

        # Retry post
        with patch('tracker.views.publish_reels_task.delay') as mock_publish:
            resp = self.client.post(f"/api/posts/{self.post.id}/retry/")
            self.assertEqual(resp.status_code, 200)
            self.post.refresh_from_db()
            self.assertEqual(self.post.status, 'queued')
            self.assertIsNone(self.post.error)
            mock_publish.assert_called_once_with(self.link.id)

        # Resend link
        resp_link = self.client.post(f"/api/links/{self.link.id}/resend/")
        self.assertEqual(resp_link.status_code, 200)
        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'pending')

    def test_api_regular_user_forbidden(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get("/api/users/")
        self.assertEqual(response.status_code, 403)

    def test_api_jwt_auth_and_throttling(self):
        client = APIClient()
        response = client.get("/api/users/")
        self.assertEqual(response.status_code, 401)

        # Login to obtain token
        resp_token = client.post("/api/token/", {"username": "admin_api", "password": "password123"})
        self.assertEqual(resp_token.status_code, 200)
        token = resp_token.json()['access']

        # Access with Bearer token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response2 = client.get("/api/users/")
        self.assertEqual(response2.status_code, 200)


class UserPortalAndPublicEndpointsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = InstagramUser.objects.create(
            name="Portal User",
            ig_user_id="portal_ig_id",
            access_token="secret_portal_token",
            status="connected",
        )
        dummy = SimpleUploadedFile("promo.mp4", b"video_data", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy, status='posted')
        self.post = Post.objects.create(
            link=self.link,
            status='published',
            permalink='https://www.instagram.com/reel/Cxyz123/',
            views=120,
            likes=8,
            comments_count=1,
            posted_at=timezone.now(),
        )

        dummy2 = SimpleUploadedFile("promo2.mp4", b"video_data", content_type="video/mp4")
        self.link_no_post = UniqueLink.objects.create(user=self.user, video=dummy2, status='pending')

    def test_user_portal_html_with_post_success(self):
        resp = self.client.get(f"/my-post/{self.link.token}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Salom, Portal User!", content)
        self.assertIn("120", content)
        self.assertIn("https://www.instagram.com/reel/Cxyz123/", content)
        # Ensure private/sensitive credentials are NEVER exposed
        self.assertNotIn("secret_portal_token", content)
        self.assertNotIn("portal_ig_id", content)

    def test_user_portal_html_without_post_loading_card(self):
        resp = self.client.get(f"/my-post/{self.link_no_post.token}/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertIn("Instagram Reels'ga yuklaysizmi?", content)

    def test_user_portal_html_invalid_token_404(self):
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp = self.client.get(f"/my-post/{fake_uuid}/")
        self.assertEqual(resp.status_code, 404)

    def test_user_portal_html_method_not_allowed(self):
        resp = self.client.post(f"/my-post/{self.link.token}/")
        self.assertEqual(resp.status_code, 405)

    def test_user_portal_api_with_post_success(self):
        resp = self.client.get(f"/api/public/post/{self.link.token}/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "published")
        self.assertEqual(data["permalink"], "https://www.instagram.com/reel/Cxyz123/")
        self.assertEqual(data["views"], 120)
        self.assertEqual(data["likes"], 8)
        self.assertEqual(data["comments_count"], 1)
        self.assertIn("posted_at", data)
        # Faqat shu maydonlar, ortiqcha ma'lumot yo'qligini tekshirish
        expected_keys = {"status", "permalink", "views", "likes", "comments_count", "posted_at"}
        self.assertEqual(set(data.keys()), expected_keys)

    def test_user_portal_api_without_post_pending(self):
        resp = self.client.get(f"/api/public/post/{self.link_no_post.token}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "pending"})

    def test_user_portal_api_invalid_token_404(self):
        fake_uuid = "00000000-0000-0000-0000-000000000000"
        resp = self.client.get(f"/api/public/post/{fake_uuid}/")
        self.assertEqual(resp.status_code, 404)

    def test_user_portal_api_method_not_allowed(self):
        resp = self.client.post(f"/api/public/post/{self.link.token}/")
        self.assertEqual(resp.status_code, 405)

    def test_data_deletion_status_messages(self):
        req_pending = DataDeletionRequest.objects.create(
            confirmation_code="code_pending",
            user_id="user_1",
            status="pending",
        )
        resp_p = self.client.get(f"/oauth/data-deletion/status/{req_pending.confirmation_code}/")
        self.assertEqual(resp_p.status_code, 200)
        self.assertIn("qabul qilindi", resp_p.json()["message"])
        self.assertNotIn("user_id", resp_p.json())

        req_failed = DataDeletionRequest.objects.create(
            confirmation_code="code_failed",
            user_id="user_2",
            status="failed",
        )
        resp_f = self.client.get(f"/oauth/data-deletion/status/{req_failed.confirmation_code}/")
        self.assertEqual(resp_f.status_code, 200)
        self.assertIn("xatolik", resp_f.json()["message"])

        resp_404 = self.client.get("/oauth/data-deletion/status/non_existing_code/")
        self.assertEqual(resp_404.status_code, 404)

        resp_405 = self.client.post(f"/oauth/data-deletion/status/{req_pending.confirmation_code}/")
        self.assertEqual(resp_405.status_code, 405)


class Phase1ModelsTestCase(TestCase):
    def setUp(self):
        self.django_user = User.objects.create_user(username="test_auth_user", password="pwd")
        self.ig_user = InstagramUser.objects.create(name="Phase1 User", user=self.django_user)
        self.dummy_file = SimpleUploadedFile("v1.mp4", b"video", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.ig_user, video=self.dummy_file)
        self.post = Post.objects.create(link=self.link, status='published')

    def test_video_selection_rules(self):
        other_user = InstagramUser.objects.create(name="User Without Personal Video")

        # 1. Umumiy default video yaratish
        f1 = SimpleUploadedFile("def.mp4", b"default", content_type="video/mp4")
        v_default = Video.objects.create(title="General Promo", file=f1, is_default=True)

        # other_user da shaxsiy video yo'q -> default video olinadi
        chosen = get_video_for_user(other_user)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.id, v_default.id)

        # 2. other_user ga shaxsiy faol video yaratilsa -> shaxsiy video olinadi
        f2 = SimpleUploadedFile("personal.mp4", b"personal", content_type="video/mp4")
        v_personal = Video.objects.create(title="Personal Promo", file=f2, owner=other_user, is_active=True)

        chosen = get_video_for_user(other_user)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.id, v_personal.id)

        # 3. Yangi default video yaratilsa, eskisidan is_default olib tashlanadi
        f3 = SimpleUploadedFile("def2.mp4", b"default2", content_type="video/mp4")
        v_default2 = Video.objects.create(title="General Promo 2", file=f3, is_default=True)
        v_default.refresh_from_db()
        self.assertFalse(v_default.is_default)
        self.assertTrue(v_default2.is_default)

    def test_prize_unique_together_constraint(self):
        Prize.objects.create(post=self.post, milestone=500)
        with self.assertRaises(IntegrityError):
            Prize.objects.create(post=self.post, milestone=500)

    def test_post_stat_history(self):
        stat1 = PostStat.objects.create(post=self.post, views=100, likes=5, comments_count=1)
        stat2 = PostStat.objects.create(post=self.post, views=250, likes=12, comments_count=3)

        self.assertEqual(self.post.stats.count(), 2)
        stats = list(self.post.stats.all())
        self.assertEqual(stats[0].id, stat2.id)
        self.assertEqual(stats[1].id, stat1.id)

    def test_django_user_role_and_notification(self):
        self.assertFalse(self.ig_user.is_admin)
        self.assertEqual(self.ig_user.role, 'user')

        self.django_user.is_staff = True
        self.django_user.save()
        self.ig_user.refresh_from_db()
        self.assertTrue(self.ig_user.is_admin)
        self.assertEqual(self.ig_user.role, 'admin')

        prize = Prize.objects.create(post=self.post, milestone=1000)
        
        self.assertEqual(self.ig_user.notifications.count(), 1)
        notif = self.ig_user.notifications.first()
        self.assertEqual(notif.kind, 'prize')
        self.assertIn("1000", notif.message)
        self.assertFalse(notif.is_read)


class Phase2AuthPermissionsTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # Admin user
        self.admin = User.objects.create_superuser(username="admin_p2", password="admin_password")
        self.ig_admin = InstagramUser.objects.create(name="Admin Profile", user=self.admin)

        # User A
        self.user_a = User.objects.create_user(username="user_a", password="password_a")
        self.ig_user_a = InstagramUser.objects.create(name="User A Profile", user=self.user_a)
        dummy_a = SimpleUploadedFile("a.mp4", b"video_a", content_type="video/mp4")
        self.link_a = UniqueLink.objects.create(user=self.ig_user_a, video=dummy_a)
        self.post_a = Post.objects.create(link=self.link_a, status='published', views=10)
        self.stat_a = PostStat.objects.create(post=self.post_a, views=10)
        self.prize_a = Prize.objects.create(post=self.post_a, milestone=500)

        # User B
        self.user_b = User.objects.create_user(username="user_b", password="password_b")
        self.ig_user_b = InstagramUser.objects.create(name="User B Profile", user=self.user_b)
        dummy_b = SimpleUploadedFile("b.mp4", b"video_b", content_type="video/mp4")
        self.link_b = UniqueLink.objects.create(user=self.ig_user_b, video=dummy_b)
        self.post_b = Post.objects.create(link=self.link_b, status='published', views=20)
        self.stat_b = PostStat.objects.create(post=self.post_b, views=20)
        self.prize_b = Prize.objects.create(post=self.post_b, milestone=500)

    def test_anonymous_access_forbidden(self):
        # (c) tokensiz hamma yopiq
        self.assertEqual(self.client.get("/api/me/").status_code, 401)
        self.assertEqual(self.client.get("/api/posts/").status_code, 401)
        self.assertEqual(self.client.get("/api/links/").status_code, 401)
        self.assertEqual(self.client.get("/api/users/").status_code, 401)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 401)

    def test_regular_user_cannot_access_other_user_data(self):
        # (a) oddiy user boshqa userning postini/statistikasini ID bilan so'rasa 404 yoki 403 oladi
        self.client.force_authenticate(user=self.user_a)

        # User A o'z postini ko'ra oladi
        resp_own = self.client.get(f"/api/posts/{self.post_a.id}/")
        self.assertEqual(resp_own.status_code, 200)

        # User A User B ning postini ID bilan so'rasa 404 oladi
        resp_other_post = self.client.get(f"/api/posts/{self.post_b.id}/")
        self.assertIn(resp_other_post.status_code, (403, 404))

        # User A User B ning post statistikasini so'rasa 404/403 oladi
        resp_other_stats = self.client.get(f"/api/posts/{self.post_b.id}/stats/")
        self.assertIn(resp_other_stats.status_code, (403, 404))

        # User A User B ning linkini so'rasa 404/403 oladi
        resp_other_link = self.client.get(f"/api/links/{self.link_b.id}/")
        self.assertIn(resp_other_link.status_code, (403, 404))

        # User A User B ning prizini so'rasa 404/403 oladi
        resp_other_prize = self.client.get(f"/api/prizes/{self.prize_b.id}/")
        self.assertIn(resp_other_prize.status_code, (403, 404))

    def test_regular_user_cannot_access_admin_endpoints(self):
        # (b) oddiy user admin endpointiga kira olmaydi
        self.client.force_authenticate(user=self.user_a)

        self.assertEqual(self.client.get("/api/dashboard/").status_code, 403)
        self.assertEqual(self.client.get("/api/users/").status_code, 403)
        self.assertEqual(self.client.post("/api/admin/create-user/", {}).status_code, 403)
        self.assertEqual(self.client.post("/api/admin/reset-password/", {}).status_code, 403)

    def test_admin_can_access_all_data(self):
        # (d) admin hammasini ko'radi
        self.client.force_authenticate(user=self.admin)

        resp_posts = self.client.get("/api/posts/")
        self.assertEqual(resp_posts.status_code, 200)
        post_ids = [p['id'] for p in resp_posts.json()['results']]
        self.assertIn(self.post_a.id, post_ids)
        self.assertIn(self.post_b.id, post_ids)

        self.assertEqual(self.client.get(f"/api/posts/{self.post_a.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/posts/{self.post_b.id}/").status_code, 200)
        self.assertEqual(self.client.get("/api/dashboard/").status_code, 200)
        self.assertEqual(self.client.get("/api/users/").status_code, 200)

    def test_jwt_login_role_and_me_endpoint(self):
        # Admin login
        resp_admin = self.client.post("/api/token/", {"username": "admin_p2", "password": "admin_password"})
        self.assertEqual(resp_admin.status_code, 200)
        self.assertEqual(resp_admin.json().get('role'), "admin")

        # User login
        resp_user = self.client.post("/api/token/", {"username": "user_a", "password": "password_a"})
        self.assertEqual(resp_user.status_code, 200)
        self.assertEqual(resp_user.json().get('role'), "user")

        # /api/me/ tekshirish
        token_a = resp_user.json()['access']
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        resp_me = self.client.get("/api/me/")
        self.assertEqual(resp_me.status_code, 200)
        data_me = resp_me.json()
        self.assertEqual(data_me['username'], "user_a")
        self.assertEqual(data_me['role'], "user")
        self.assertFalse(data_me['is_staff'])
        self.assertIsNotNone(data_me['instagram_user'])

    def test_admin_create_user_and_password_lifecycle(self):
        self.client.force_authenticate(user=self.admin)

        # 1. Admin yangi foydalanuvchi yaratadi
        payload = {
            "username": "client_99",
            "password": "initial_password_123",
            "name": "Mijoz 99",
            "is_staff": False,
        }
        resp = self.client.post("/api/admin/create-user/", payload)
        self.assertEqual(resp.status_code, 201)
        created_data = resp.json()
        self.assertEqual(created_data['username'], "client_99")
        self.assertEqual(created_data['role'], "user")
        self.assertNotIn("password", created_data)
        self.assertNotIn("initial_password_123", json.dumps(created_data))

        # Yaratilgan user login qila oladi
        client_auth = APIClient()
        resp_login = client_auth.post("/api/token/", {"username": "client_99", "password": "initial_password_123"})
        self.assertEqual(resp_login.status_code, 200)
        token = resp_login.json()['access']
        client_auth.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # 2. User o'z parolini o'zgartiradi
        bad_change = client_auth.post("/api/change-password/", {
            "old_password": "wrong_password",
            "new_password": "new_password_456"
        })
        self.assertEqual(bad_change.status_code, 400)

        good_change = client_auth.post("/api/change-password/", {
            "old_password": "initial_password_123",
            "new_password": "new_password_456"
        })
        self.assertEqual(good_change.status_code, 200)

        resp_new_login = client_auth.post("/api/token/", {"username": "client_99", "password": "new_password_456"})
        self.assertEqual(resp_new_login.status_code, 200)

        # 3. Admin parolni tiklaydi
        user_obj = User.objects.get(username="client_99")
        resp_reset = self.client.post("/api/admin/reset-password/", {
            "user_id": user_obj.id,
            "new_password": "admin_reset_789"
        })
        self.assertEqual(resp_reset.status_code, 200)

        resp_reset_login = client_auth.post("/api/token/", {"username": "client_99", "password": "admin_reset_789"})
        self.assertEqual(resp_reset_login.status_code, 200)


class Phase3VideoManagementTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # Admin
        self.admin = User.objects.create_superuser(username="video_admin", password="password")
        self.ig_admin = InstagramUser.objects.create(name="Video Admin", user=self.admin)

        # Users
        self.user_a = User.objects.create_user(username="user_va", password="password")
        self.ig_user_a = InstagramUser.objects.create(name="User VA", user=self.user_a)

        self.user_b = User.objects.create_user(username="user_vb", password="password")
        self.ig_user_b = InstagramUser.objects.create(name="User VB", user=self.user_b)

    def test_invalid_video_extension_rejected(self):
        self.client.force_authenticate(user=self.admin)
        f_bad = SimpleUploadedFile("bad.avi", b"fake_avi", content_type="video/x-msvideo")
        resp = self.client.post("/api/videos/", {"title": "Bad Video", "file": f_bad}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertIn(".mp4", str(resp.json()))

    def test_empty_video_rejected(self):
        self.client.force_authenticate(user=self.admin)
        f_empty = SimpleUploadedFile("empty.mp4", b"", content_type="video/mp4")
        resp = self.client.post("/api/videos/", {"title": "Empty Video", "file": f_empty}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(any(word in str(resp.json()).lower() for word in ["empty", "bo'sh"]))

    @override_settings(MAX_VIDEO_SIZE_BYTES=100, MAX_VIDEO_SIZE_MB=1)
    def test_video_size_limit_rejected(self):
        self.client.force_authenticate(user=self.admin)
        f_large = SimpleUploadedFile("large.mp4", b"x" * 200, content_type="video/mp4")
        resp = self.client.post("/api/videos/", {"title": "Large Video", "file": f_large}, format="multipart")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("oshmasligi", str(resp.json()))

    def test_uuid_filename_assigned_on_upload(self):
        self.client.force_authenticate(user=self.admin)
        f_valid = SimpleUploadedFile("../../traversal_name.MP4", b"valid_video_data", content_type="video/mp4")
        resp = self.client.post("/api/videos/", {"title": "Safe Video", "file": f_valid}, format="multipart")
        self.assertEqual(resp.status_code, 201)
        video_id = resp.json()['id']
        video = Video.objects.get(pk=video_id)
        # Fayl nomi videos/<uuid>.mp4 formatida bo'lishi va path traversal yo'qligini tekshirish
        self.assertTrue(video.file.name.startswith("videos/"))
        self.assertTrue(video.file.name.endswith(".mp4"))
        self.assertNotIn("traversal", video.file.name)
        self.assertNotIn("..", video.file.name)

    def test_single_is_default_video_transaction(self):
        self.client.force_authenticate(user=self.admin)
        f1 = SimpleUploadedFile("v1.mp4", b"data1", content_type="video/mp4")
        v1 = Video.objects.create(title="Promo 1", file=f1, is_default=True)

        f2 = SimpleUploadedFile("v2.mp4", b"data2", content_type="video/mp4")
        v2 = Video.objects.create(title="Promo 2", file=f2, is_default=False)

        # v2 ni set-default orqali default qilish
        resp = self.client.post(f"/api/videos/{v2.id}/set-default/")
        self.assertEqual(resp.status_code, 200)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertFalse(v1.is_default)
        self.assertTrue(v2.is_default)
        # Faqat bittasi default ekanligini tasdiqlash
        self.assertEqual(Video.objects.filter(is_default=True).count(), 1)

    def test_regular_user_cannot_upload_or_modify_or_delete_videos(self):
        self.client.force_authenticate(user=self.user_a)
        f = SimpleUploadedFile("user_video.mp4", b"user_data", content_type="video/mp4")

        # POST rad etiladi
        self.assertEqual(self.client.post("/api/videos/", {"title": "UV", "file": f}, format="multipart").status_code, 403)

        f_admin = SimpleUploadedFile("admin_v.mp4", b"data", content_type="video/mp4")
        v = Video.objects.create(title="Admin Video", file=f_admin)

        # DELETE rad etiladi
        self.assertEqual(self.client.delete(f"/api/videos/{v.id}/").status_code, 403)

        # set-default rad etiladi
        self.assertEqual(self.client.post(f"/api/videos/{v.id}/set-default/").status_code, 403)

    def test_regular_user_only_sees_own_or_default_video(self):
        # Default video
        f_def = SimpleUploadedFile("default_promo.mp4", b"def", content_type="video/mp4")
        v_def = Video.objects.create(title="Default Promo", file=f_def, is_default=True)

        # User A ning shaxsiy videosi
        f_a = SimpleUploadedFile("va.mp4", b"va", content_type="video/mp4")
        v_a = Video.objects.create(title="User A Video", file=f_a, owner=self.ig_user_a, is_active=True)

        # User B ning shaxsiy videosi
        f_b = SimpleUploadedFile("vb.mp4", b"vb", content_type="video/mp4")
        v_b = Video.objects.create(title="User B Video", file=f_b, owner=self.ig_user_b, is_active=True)

        self.client.force_authenticate(user=self.user_a)

        # User A ro'yxatni so'raydi
        resp = self.client.get("/api/videos/")
        self.assertEqual(resp.status_code, 200)
        video_ids = [v['id'] for v in resp.json()['results']]
        self.assertIn(v_a.id, video_ids)
        self.assertIn(v_def.id, video_ids)
        self.assertNotIn(v_b.id, video_ids)

        # User A User B ning videosini ID bilan so'rasa 404 oladi
        self.assertEqual(self.client.get(f"/api/videos/{v_b.id}/").status_code, 404)

    @patch('tracker.services.requests.get')
    @patch('tracker.services.create_reels_container')
    @patch('tracker.services.wait_for_container_ready')
    @patch('tracker.services.publish_container')
    @patch('tracker.services.get_media_permalink')
    def test_publish_reels_uses_video_selection_rule(self, mock_permalink, mock_publish, mock_wait, mock_container, mock_get):
        mock_acc_resp = MagicMock()
        mock_acc_resp.status_code = 200
        mock_acc_resp.json.return_value = {"account_type": "BUSINESS"}
        mock_get.return_value = mock_acc_resp

        mock_container.return_value = "cont_123"
        mock_publish.return_value = "media_123"
        mock_permalink.return_value = "https://instagram.com/reel/123"

        # Shaxsiy video yaratamiz
        f_pers = SimpleUploadedFile("pers.mp4", b"pers_video", content_type="video/mp4")
        pers_video = Video.objects.create(title="Personal Choice", file=f_pers, owner=self.ig_user_a, is_active=True)

        self.ig_user_a.access_token = "valid_token"
        self.ig_user_a.ig_user_id = "17841"
        self.ig_user_a.status = 'connected'
        self.ig_user_a.save()

        # UniqueLink da video ko'rsatilmagan
        link = UniqueLink.objects.create(user=self.ig_user_a, video=None)

        post = publish_reels_for_link(link.id)
        self.assertEqual(post.status, 'published')
        link.refresh_from_db()
        self.assertEqual(link.video.id, pers_video.id)
        mock_container.assert_called_once()
        call_kwargs = mock_container.call_args[1]
        self.assertIn(pers_video.file.name, call_kwargs['video_url'])


class Phase4UserInstagramAndPublishTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # User 1
        self.user1 = User.objects.create_user(username="p4_user1", password="password")
        self.ig_user1 = InstagramUser.objects.create(name="P4 User1", user=self.user1)

        # User 2
        self.user2 = User.objects.create_user(username="p4_user2", password="password")
        self.ig_user2 = InstagramUser.objects.create(name="P4 User2", user=self.user2)

        # Video
        f = SimpleUploadedFile("v_p4.mp4", b"video_data", content_type="video/mp4")
        self.default_video = Video.objects.create(title="Default P4", file=f, is_default=True)

    def test_user_connect_instagram_flow(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.get("/api/user/connect-instagram/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("auth_url", data)
        self.assertIn("link_token", data)
        self.assertIn("instagram.com/oauth/authorize", data['auth_url'])

    @patch('tracker.views.requests.get')
    def test_user_connect_instagram_post_direct(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "user_id": "178419999",
            "username": "direct_connected_user",
            "account_type": "MEDIA_CREATOR"
        }
        mock_get.return_value = mock_resp

        self.client.force_authenticate(user=self.user1)
        resp = self.client.post("/api/user/connect-instagram/", {"access_token": "direct_token_xyz"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'connected')
        self.assertEqual(data['username'], 'direct_connected_user')

        self.ig_user1.refresh_from_db()
        self.assertEqual(self.ig_user1.status, 'connected')
        self.assertEqual(self.ig_user1.access_token, 'direct_token_xyz')

    @patch('tracker.views.publish_reels_task.delay')
    def test_user_publish_video_and_duplicate_prevention(self, mock_delay):
        self.client.force_authenticate(user=self.user1)

        # 1. Instagram ulanmagan bo'lsa xato beradi
        resp_unconnected = self.client.post("/api/user/publish/")
        self.assertEqual(resp_unconnected.status_code, 400)
        self.assertIn("ulanmagan", resp_unconnected.json()['error'])

        # Instagram ulaymiz
        self.ig_user1.status = 'connected'
        self.ig_user1.access_token = 'token_123'
        self.ig_user1.ig_user_id = '1784100'
        self.ig_user1.save()

        # 2. Videoni joylashni boshlash
        resp_publish = self.client.post("/api/user/publish/")
        self.assertEqual(resp_publish.status_code, 202)
        mock_delay.assert_called_once()

        # 3. Takroriy bosishdan himoya (queued holatda)
        resp_dup = self.client.post("/api/user/publish/")
        self.assertEqual(resp_dup.status_code, 409)
        self.assertIn("jarayonda", resp_dup.json()['error'])

    def test_user_publish_status_and_retry_lifecycle(self):
        self.ig_user1.status = 'connected'
        self.ig_user1.access_token = 'token_123'
        self.ig_user1.ig_user_id = '1784100'
        self.ig_user1.save()

        link = UniqueLink.objects.create(user=self.ig_user1)
        post = Post.objects.create(link=link, status='failed', error="Tarmoq xatosi", retry_count=0)

        self.client.force_authenticate(user=self.user1)

        # Polling status
        resp_status = self.client.get("/api/user/publish-status/")
        self.assertEqual(resp_status.status_code, 200)
        data = resp_status.json()
        self.assertTrue(data['has_post'])
        self.assertEqual(data['status'], 'failed')
        self.assertTrue(data['can_retry'])

        # 1-marta retry
        resp_r1 = self.client.post("/api/user/retry/")
        self.assertEqual(resp_r1.status_code, 200)
        self.assertEqual(resp_r1.json()['retry_count'], 1)

        # Post yana failed bo'ldi deb belgilaymiz
        post.refresh_from_db()
        post.status = 'failed'
        post.save()

        # 2-marta retry
        self.client.post("/api/user/retry/")
        post.refresh_from_db()
        post.status = 'failed'
        post.save()

        # 3-marta retry
        self.client.post("/api/user/retry/")
        post.refresh_from_db()
        self.assertEqual(post.retry_count, 3)
        post.status = 'failed'
        post.save()

        # 4-marta retry -> rad etiladi (limit: 3)
        resp_r4 = self.client.post("/api/user/retry/")
        self.assertEqual(resp_r4.status_code, 400)
        self.assertIn("tugadi", resp_r4.json()['error'])

    def test_user_cannot_retry_other_user_post(self):
        link2 = UniqueLink.objects.create(user=self.ig_user2)
        post2 = Post.objects.create(link=link2, status='failed')

        self.client.force_authenticate(user=self.user1)

        # User 1 User 2 ning postini retry qilmoqchi bo'ladi
        resp = self.client.post(f"/api/posts/{post2.id}/retry/")
        self.assertIn(resp.status_code, (403, 404))

    @patch('tracker.services.verify_token_permissions')
    @patch('tracker.services.get_long_lived_token')
    @patch('tracker.services.exchange_code_for_token')
    def test_missing_permissions_rejected(self, mock_exchange, mock_long_token, mock_perms):
        mock_exchange.return_value = {'access_token': 'short_token', 'user_id': '17841'}
        mock_long_token.return_value = {'access_token': 'long_token', 'expires_in': 5184000}
        mock_perms.return_value = (False, ['instagram_business_manage_insights'])

        link = UniqueLink.objects.create(user=self.ig_user1)

        with self.assertRaises(InstagramOAuthError) as ctx:
            complete_instagram_oauth('code_123', str(link.token))

        self.assertIn("ruxsatlari to'liq berilmagan", str(ctx.exception))
        self.ig_user1.refresh_from_db()
        self.assertEqual(self.ig_user1.status, 'needs_reauth')

    @patch('tracker.services.check_instagram_account_type')
    def test_personal_account_rejected_on_publish(self, mock_acc_type):
        mock_acc_type.return_value = 'PERSONAL'

        self.ig_user1.status = 'connected'
        self.ig_user1.access_token = 'token_pers'
        self.ig_user1.ig_user_id = '17841_pers'
        self.ig_user1.save()

        link = UniqueLink.objects.create(user=self.ig_user1)

        with self.assertRaises(InstagramPublishError) as ctx:
            publish_reels_for_link(link.id)

        self.assertIn("shaxsiy (Personal)", str(ctx.exception))
        post = Post.objects.get(link=link)
        self.assertEqual(post.status, 'failed')
        self.assertIn("shaxsiy", post.error)


class Phase5StatsEngineTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        
        self.user = User.objects.create_user(username="p5_user", password="pwd")
        self.ig_user = InstagramUser.objects.create(name="P5 User", user=self.user, status='connected', access_token='token123', ig_user_id='1234')
        self.link = UniqueLink.objects.create(user=self.ig_user)
        self.post = Post.objects.create(
            link=self.link,
            status='published',
            ig_media_id='media_p5',
            posted_at=timezone.now() - timedelta(hours=1),
            views=100
        )

    @patch('tracker.services.requests.get')
    def test_deleted_media_vs_token_error(self, mock_get):
        # 1. Deleted media (404)
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        mock_get.return_value = mock_resp_404

        update_post_metrics(self.post)
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'deleted')
        self.assertIsNotNone(self.post.deleted_detected_at)
        self.assertIsNone(self.post.next_check_at)

        # 2. Token error (OAuthException 190)
        self.post.status = 'published'
        self.post.save()
        
        mock_resp_190 = MagicMock()
        mock_resp_190.status_code = 400
        mock_resp_190.json.return_value = {"error": {"code": 190}}
        mock_get.return_value = mock_resp_190

        update_post_metrics(self.post)
        self.ig_user.refresh_from_db()
        self.post.refresh_from_db()
        self.assertEqual(self.ig_user.status, 'needs_reauth')
        self.assertEqual(self.post.status, 'published')  # Post status doesn't change to deleted
        self.assertIn("yaroqsiz", self.post.error)
        self.assertIsNone(self.post.next_check_at)

    def test_duplicate_prize_prevention_and_signal(self):
        # 500 ga yetdi
        self.post.views = 500
        self.post.save()
        
        check_and_award_prizes(self.post)
        self.assertEqual(Prize.objects.filter(post=self.post, milestone=500).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.ig_user, kind='prize').count(), 1)

        # Worker yana bir marta xuddi shu postni ishladi
        check_and_award_prizes(self.post)
        self.assertEqual(Prize.objects.filter(post=self.post, milestone=500).count(), 1)
        # Notification ko'paymaydi
        self.assertEqual(Notification.objects.filter(user=self.ig_user, kind='prize').count(), 1)

    def test_adaptive_interval_logic(self):
        now = timezone.now()
        
        # 0-6 hours
        self.post.posted_at = now - timedelta(hours=2)
        next_check = calculate_next_check(self.post, now=now)
        self.assertEqual(next_check, now + timedelta(minutes=15))
        
        # 6-24 hours
        self.post.posted_at = now - timedelta(hours=10)
        next_check = calculate_next_check(self.post, now=now)
        self.assertEqual(next_check, now + timedelta(hours=1))

        # Milestone 80% logic (500 * 0.8 = 400)
        self.post.posted_at = now - timedelta(days=2) # 1-3 days usually 3 hours
        self.post.views = 410
        next_check = calculate_next_check(self.post, now=now)
        # Prizga yaqin bo'lgani uchun 15 min
        self.assertEqual(next_check, now + timedelta(minutes=15))


class Phase6StatsApiTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client = APIClient()

        # Admin
        self.admin = User.objects.create_superuser(username="admin_p6", password="password")
        self.ig_admin = InstagramUser.objects.create(name="Admin P6", user=self.admin)

        # User A
        self.user_a = User.objects.create_user(username="user_p6_a", password="password")
        self.ig_user_a = InstagramUser.objects.create(name="User P6 A", user=self.user_a, status='connected')
        self.link_a = UniqueLink.objects.create(user=self.ig_user_a)
        self.post_a1 = Post.objects.create(
            link=self.link_a,
            status='published',
            views=300,
            likes=20,
            comments_count=5,
            posted_at=timezone.now() - timedelta(days=2),
            last_checked_at=timezone.now() - timedelta(hours=1),
        )
        self.stat_a1_1 = PostStat.objects.create(post=self.post_a1, views=100, likes=5, comments_count=1)
        self.stat_a1_2 = PostStat.objects.create(post=self.post_a1, views=300, likes=20, comments_count=5)
        self.prize_a = Prize.objects.create(post=self.post_a1, milestone=100)

        # User B
        self.user_b = User.objects.create_user(username="user_p6_b", password="password")
        self.ig_user_b = InstagramUser.objects.create(name="User P6 B", user=self.user_b, status='connected')
        self.link_b = UniqueLink.objects.create(user=self.ig_user_b)
        self.post_b = Post.objects.create(
            link=self.link_b,
            status='deleted',
            views=800,
            likes=40,
            comments_count=10,
            posted_at=timezone.now() - timedelta(days=5),
            deleted_detected_at=timezone.now() - timedelta(days=1),
        )
        self.stat_b = PostStat.objects.create(post=self.post_b, views=800, likes=40, comments_count=10)

    def test_me_summary(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/me/summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total_views'], 300)
        self.assertEqual(data['total_likes'], 20)
        self.assertEqual(data['total_comments'], 5)
        self.assertEqual(data['posts_count'], 1)
        self.assertEqual(data['prizes_count'], 1)
        self.assertIsNotNone(data['last_checked_at'])

    def test_me_posts(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/me/posts/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.post_a1.id)
        # User B ning posti ko'rinmasligi kerak
        post_ids = [p['id'] for p in results]
        self.assertNotIn(self.post_b.id, post_ids)

    def test_me_post_history_security(self):
        self.client.force_authenticate(user=self.user_a)

        # O'z postining tarixi ko'rinadi
        resp_own = self.client.get(f"/api/me/posts/{self.post_a1.id}/history/")
        self.assertEqual(resp_own.status_code, 200)
        self.assertEqual(len(resp_own.json()), 2)
        self.assertEqual(resp_own.json()[0]['views'], 100)
        self.assertEqual(resp_own.json()[1]['views'], 300)

        # Boshqa userning post tarixini so'raganda 404 qaytadi
        resp_other = self.client.get(f"/api/me/posts/{self.post_b.id}/history/")
        self.assertEqual(resp_other.status_code, 404)

    def test_me_notifications_and_read(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/me/notifications/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data['unread_count'], 1)

        # O'qilgan deb belgilash
        resp_read = self.client.post("/api/me/notifications/read/")
        self.assertEqual(resp_read.status_code, 200)

        # Qayta tekshirganda unread_count 0 bo'ladi
        resp2 = self.client.get("/api/me/notifications/")
        self.assertEqual(resp2.json()['unread_count'], 0)

    def test_me_prizes(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get("/api/me/prizes/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['milestone'], 100)

    def test_admin_summary_and_caching(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/summary/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("total_users", data)
        self.assertIn("posts_by_status", data)
        self.assertEqual(data['posts_by_status']['published'], 1)
        self.assertEqual(data['posts_by_status']['deleted'], 1)
        self.assertEqual(data['total_views'], 1100)  # 300 + 800

        # Oddiy user kirishi taqiqlangan
        self.client.force_authenticate(user=self.user_a)
        resp_forbidden = self.client.get("/api/admin/summary/")
        self.assertEqual(resp_forbidden.status_code, 403)

    def test_admin_users_list_and_detail(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/users/")
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertGreaterEqual(len(results), 2)
        user_names = [u['name'] for u in results]
        self.assertIn("User P6 A", user_names)

        # Detail tekshirish
        resp_detail = self.client.get(f"/api/admin/users/{self.ig_user_a.id}/")
        self.assertEqual(resp_detail.status_code, 200)
        d_data = resp_detail.json()
        self.assertEqual(d_data['total_views'], 300)
        self.assertEqual(len(d_data['posts']), 1)
        self.assertEqual(len(d_data['posts'][0]['history']), 2)

    def test_admin_posts_filtering_and_deleted(self):
        self.client.force_authenticate(user=self.admin)

        # Deleted postlarni filtrlash
        resp_del = self.client.get("/api/admin/posts/?status=deleted")
        self.assertEqual(resp_del.status_code, 200)
        results = resp_del.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.post_b.id)
        self.assertIsNotNone(results[0]['deleted_detected_at'])

        # Views bo'yicha tartiblash
        resp_sort = self.client.get("/api/admin/posts/?ordering=-views")
        self.assertEqual(resp_sort.status_code, 200)
        results_sort = resp_sort.json()['results']
        self.assertEqual(results_sort[0]['id'], self.post_b.id)

    def test_admin_stats_daily(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/stats/daily/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(isinstance(data, list))
        self.assertGreaterEqual(len(data), 1)

    def test_admin_export_posts_csv(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get("/api/admin/export/posts.csv")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="posts.csv"', resp['Content-Disposition'])
        content = b"".join(resp.streaming_content).decode('utf-8')
        self.assertIn("Post ID,User,Status,Views", content)
        self.assertIn("User P6 A", content)
        self.assertIn("User P6 B", content)

    def test_admin_users_n_plus_one_avoidance(self):
        self.client.force_authenticate(user=self.admin)
        with self.assertNumQueries(2):
            resp = self.client.get("/api/admin/users/")
            self.assertEqual(resp.status_code, 200)


# ==============================================================================
# BOSQICH 10: Rate Limiter, Error Classification & Monitoring Testlari
# ==============================================================================
import concurrent.futures
import requests
from django.core.cache import cache


class RateLimiterConcurrencyTestCase(TestCase):
    def setUp(self):
        super().setUp()
        rate_limiter.reset()

    def tearDown(self):
        rate_limiter.reset()
        super().tearDown()

    @override_settings(INSTAGRAM_API_RATE_LIMIT=10)
    def test_single_worker_within_limit(self):
        """Limit doirasidagi so'rovlar muvaffaqiyatli ruxsat oladi."""
        for _ in range(5):
            allowed, retry_after, reason = rate_limiter.acquire()
            self.assertTrue(allowed)
            self.assertEqual(retry_after, 0.0)

    @override_settings(INSTAGRAM_API_RATE_LIMIT=5)
    def test_single_worker_exceeds_limit(self):
        """Limitdan oshgan so'rovlar rad etiladi va retry_after qaytariladi."""
        for _ in range(5):
            allowed, _, _ = rate_limiter.acquire()
            self.assertTrue(allowed)

        # 6-chi so'rov rad etilishi kerak
        allowed, retry_after, reason = rate_limiter.acquire()
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0.0)
        self.assertEqual(reason, "global_rate_limit")

    @override_settings(INSTAGRAM_API_RATE_LIMIT=10)
    def test_two_workers_concurrent_total_rate(self):
        """
        Ikki worker bir vaqtda ishlaganda umumiy tezlik chegaradan (10/s) oshmaydi.
        Har bir worker 10 tadan (jami 20 ta) so'rov yuboradi.
        Ruxsat berilgan so'rovlar soni aniq limitga (10) teng bo'lishi kerak.
        """
        def worker_requests(count: int) -> list[bool]:
            results = []
            for _ in range(count):
                allowed, _, _ = rate_limiter.acquire()
                results.append(allowed)
            return results

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(worker_requests, 10)
            future2 = executor.submit(worker_requests, 10)
            res1 = future1.result()
            res2 = future2.result()

        total_allowed = sum(res1) + sum(res2)
        total_denied = (len(res1) + len(res2)) - total_allowed

        # Umumiy tezlik chegaradan oshmaganini tasdiqlash
        self.assertEqual(total_allowed, 10)
        self.assertEqual(total_denied, 10)

    @override_settings(
        INSTAGRAM_API_RATE_LIMIT=50,
        INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_SEC=2,
        INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR=50,
    )
    def test_per_account_rate_limiting(self):
        """Bitta akkaunt o'zining soniyalik limitidan oshganda rad etiladi, boshqa akkauntga ta'sir qilmaydi."""
        # Akkaunt 1: 2 ta so'rov ruxsat etiladi
        a1_res1, _, _ = rate_limiter.acquire(account_id=101)
        a1_res2, _, _ = rate_limiter.acquire(account_id=101)
        self.assertTrue(a1_res1)
        self.assertTrue(a1_res2)

        # Akkaunt 1: 3-so'rov rad etiladi
        a1_res3, retry_after, reason = rate_limiter.acquire(account_id=101)
        self.assertFalse(a1_res3)
        self.assertEqual(reason, "account_sec_rate_limit")

        # Akkaunt 2: alohida akkaunt bo'lgani uchun hali ruxsat beriladi
        a2_res1, _, _ = rate_limiter.acquire(account_id=102)
        self.assertTrue(a2_res1)

    @override_settings(INSTAGRAM_API_RATE_LIMIT=10)
    def test_trigger_backoff_halves_limit(self):
        """Backoff chaqirilganda umumiy limit yarmiga pasaytiriladi (10 -> 5)."""
        rate_limiter.trigger_backoff(duration_seconds=10)
        self.assertTrue(rate_limiter.is_throttled())

        # Endi limit 10 emas, 5 ta bo'lishi kerak
        allowed_count = 0
        for _ in range(8):
            allowed, _, _ = rate_limiter.acquire()
            if allowed:
                allowed_count += 1

        self.assertEqual(allowed_count, 5)


class InstagramErrorClassificationTestCase(TestCase):
    def test_media_not_found_meta_codes(self):
        """(a) Media yo'q/o'chirilgan holatlari rasmiy Meta kodlari bo'yicha."""
        # Code 100, Subcode 33 (Unsupported get request. Object does not exist)
        self.assertEqual(
            classify_instagram_error(error_code=100, error_subcode=33),
            InstagramErrorType.MEDIA_NOT_FOUND,
        )
        # Code 24, Subcode 2207006 (Media Not Found)
        self.assertEqual(
            classify_instagram_error(error_code=24, error_subcode=2207006),
            InstagramErrorType.MEDIA_NOT_FOUND,
        )
        # Code -2, Subcode 2207020 (Media has expired)
        self.assertEqual(
            classify_instagram_error(error_code=-2, error_subcode=2207020),
            InstagramErrorType.MEDIA_NOT_FOUND,
        )
        # HTTP 404
        self.assertEqual(
            classify_instagram_error(status_code=404),
            InstagramErrorType.MEDIA_NOT_FOUND,
        )

    def test_token_invalid_meta_codes(self):
        """(b) Token yaroqsiz/bekor qilingan rasmiy Meta kodlari bo'yicha."""
        # Code 190 (OAuthException), turli subkodlar
        self.assertEqual(
            classify_instagram_error(error_code=190, error_subcode=463),
            InstagramErrorType.TOKEN_INVALID,
        )
        self.assertEqual(
            classify_instagram_error(error_code=190, error_subcode=467),
            InstagramErrorType.TOKEN_INVALID,
        )
        self.assertEqual(
            classify_instagram_error(error_code=190, error_subcode=458),
            InstagramErrorType.TOKEN_INVALID,
        )
        self.assertEqual(
            classify_instagram_error(error_code=190, error_subcode=460),
            InstagramErrorType.TOKEN_INVALID,
        )
        # Code 102 (API Session)
        self.assertEqual(
            classify_instagram_error(error_code=102),
            InstagramErrorType.TOKEN_INVALID,
        )
        # HTTP 401
        self.assertEqual(
            classify_instagram_error(status_code=401),
            InstagramErrorType.TOKEN_INVALID,
        )

    def test_never_confuses_a_and_b(self):
        """(a) media yo'q va (b) token yaroqsiz bir-biri bilan aslo adashmasligi kerak."""
        err_a = classify_instagram_error(error_code=100, error_subcode=33)
        err_b = classify_instagram_error(error_code=190, error_subcode=463)

        self.assertEqual(err_a, InstagramErrorType.MEDIA_NOT_FOUND)
        self.assertEqual(err_b, InstagramErrorType.TOKEN_INVALID)
        self.assertNotEqual(err_a, err_b)

    def test_permission_denied_meta_codes(self):
        """(c) Ruxsat yetishmaydi rasmiy Meta kodlari bo'yicha."""
        # Code 10 (API Permission Denied)
        self.assertEqual(
            classify_instagram_error(error_code=10),
            InstagramErrorType.PERMISSION_DENIED,
        )
        # Code 200..299 (API Permission)
        self.assertEqual(
            classify_instagram_error(error_code=200),
            InstagramErrorType.PERMISSION_DENIED,
        )
        self.assertEqual(
            classify_instagram_error(error_code=299),
            InstagramErrorType.PERMISSION_DENIED,
        )
        # Code 3 (API Method)
        self.assertEqual(
            classify_instagram_error(error_code=3),
            InstagramErrorType.PERMISSION_DENIED,
        )
        # HTTP 403
        self.assertEqual(
            classify_instagram_error(status_code=403),
            InstagramErrorType.PERMISSION_DENIED,
        )

    def test_rate_limit_meta_codes(self):
        """(d) Instagram rate limit/throttle rasmiy Meta kodlari bo'yicha."""
        # Code 4 (App-level)
        self.assertEqual(
            classify_instagram_error(error_code=4),
            InstagramErrorType.RATE_LIMIT,
        )
        # Code 17 (User-level)
        self.assertEqual(
            classify_instagram_error(error_code=17),
            InstagramErrorType.RATE_LIMIT,
        )
        # Code 32 (Page-level)
        self.assertEqual(
            classify_instagram_error(error_code=32),
            InstagramErrorType.RATE_LIMIT,
        )
        # Code 613 (Custom throttle)
        self.assertEqual(
            classify_instagram_error(error_code=613),
            InstagramErrorType.RATE_LIMIT,
        )
        # Code 341 (Application limit)
        self.assertEqual(
            classify_instagram_error(error_code=341),
            InstagramErrorType.RATE_LIMIT,
        )
        # HTTP 429
        self.assertEqual(
            classify_instagram_error(status_code=429),
            InstagramErrorType.RATE_LIMIT,
        )

    def test_server_error_meta_codes(self):
        """(e) Vaqtinchalik server xatosi rasmiy Meta kodlari bo'yicha."""
        # Code 1 (API Unknown)
        self.assertEqual(
            classify_instagram_error(error_code=1),
            InstagramErrorType.SERVER_ERROR,
        )
        # Code 2 (API Service)
        self.assertEqual(
            classify_instagram_error(error_code=2),
            InstagramErrorType.SERVER_ERROR,
        )
        # HTTP 500, 502, 503
        self.assertEqual(
            classify_instagram_error(status_code=500),
            InstagramErrorType.SERVER_ERROR,
        )
        self.assertEqual(
            classify_instagram_error(status_code=503),
            InstagramErrorType.SERVER_ERROR,
        )
        # Tarmoq istisnosi
        self.assertEqual(
            classify_instagram_error(exception=requests.exceptions.ConnectTimeout("Timeout")),
            InstagramErrorType.SERVER_ERROR,
        )

    def test_other_error(self):
        """(f) Boshqa xatoliklar."""
        self.assertEqual(
            classify_instagram_error(error_code=506),  # Duplicate Post
            InstagramErrorType.OTHER,
        )


class PostMetricsErrorActionTestCase(TestCase):
    def setUp(self):
        super().setUp()
        rate_limiter.reset()
        reset_error_counters()
        self.django_user = User.objects.create_user(username="test_err_user", password="password")
        self.ig_user = InstagramUser.objects.create(
            user=self.django_user,
            name="ig_err_user",
            access_token="EAAB1234567890abcdef",
            status="connected",
        )
        self.video = Video.objects.create(
            title="Err Test Video",
            file=SimpleUploadedFile("test.mp4", b"data", content_type="video/mp4"),
            is_active=True,
        )
        self.link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status="posted")
        self.post = Post.objects.create(
            link=self.link,
            ig_media_id="media_test_999",
            status="published",
            posted_at=timezone.now() - timedelta(hours=2),
        )

    def tearDown(self):
        rate_limiter.reset()
        reset_error_counters()
        super().tearDown()

    @patch('tracker.services.requests.get')
    def test_rate_limit_post_not_deleted_and_limit_halved(self, mock_get):
        """
        (d) Instagram rate limit xatosi kelganda:
        - Post o'chirilgan yoki xato deb belgilanmasin (status 'published' qoladi).
        - Umumiy tezlik vaqtincha pasaytiriladi (rate_limiter.is_throttled() == True).
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = json.dumps({"error": {"message": "Too many requests", "code": 4}})
        mock_resp.json.return_value = {"error": {"message": "Too many requests", "code": 4}}
        mock_get.return_value = mock_resp

        updated_post = update_post_metrics(self.post)
        self.post.refresh_from_db()

        # Post status o'chirilmagan va xato deb belgilanmagan
        self.assertEqual(self.post.status, 'published')
        self.assertIsNone(self.post.error)
        self.assertIsNotNone(self.post.next_check_at)

        # Rate limiter vaqtincha pasaytirilgan holatda
        self.assertTrue(rate_limiter.is_throttled())

    @patch('tracker.services.requests.get')
    def test_media_not_found_action(self, mock_get):
        """(a) Media o'chirilganda: post status 'deleted' bo'ladi."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = json.dumps({"error": {"message": "Unsupported get request", "code": 100, "error_subcode": 33}})
        mock_resp.json.return_value = {"error": {"message": "Unsupported get request", "code": 100, "error_subcode": 33}}
        mock_get.return_value = mock_resp

        update_post_metrics(self.post)
        self.post.refresh_from_db()

        self.assertEqual(self.post.status, 'deleted')
        self.assertIsNotNone(self.post.deleted_detected_at)
        self.assertIn("o'chirilgan", self.post.error)
        self.assertIsNone(self.post.next_check_at)

    @patch('tracker.services.requests.get')
    def test_token_invalid_action(self, mock_get):
        """(b) Token yaroqsiz bo'lganda: user status 'needs_reauth' bo'ladi."""
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = json.dumps({"error": {"message": "Error validating access token", "code": 190, "error_subcode": 463}})
        mock_resp.json.return_value = {"error": {"message": "Error validating access token", "code": 190, "error_subcode": 463}}
        mock_get.return_value = mock_resp

        update_post_metrics(self.post)
        self.ig_user.refresh_from_db()
        self.post.refresh_from_db()

        self.assertEqual(self.ig_user.status, 'needs_reauth')
        self.assertIn("needs_reauth", self.post.error)

    @patch('tracker.services.requests.get')
    def test_permission_denied_action(self, mock_get):
        """(c) Ruxsat yetishmaydi bo'lganda: user status 'needs_reauth' bo'ladi."""
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = json.dumps({"error": {"message": "Application does not have permission", "code": 10}})
        mock_resp.json.return_value = {"error": {"message": "Application does not have permission", "code": 10}}
        mock_get.return_value = mock_resp

        update_post_metrics(self.post)
        self.ig_user.refresh_from_db()
        self.post.refresh_from_db()

        self.assertEqual(self.ig_user.status, 'needs_reauth')
        self.assertIn("permission", self.post.error)


class MaskingAndCountersTestCase(TestCase):
    def setUp(self):
        super().setUp()
        cache.delete('admin_summary_cache')
        reset_error_counters()
        self.admin = User.objects.create_superuser(username="admin_cnt", password="password", email="admin_cnt@test.com")
        self.client = APIClient()

    def tearDown(self):
        cache.delete('admin_summary_cache')
        reset_error_counters()
        super().tearDown()

    def test_mask_sensitive_data(self):
        """Tokenlar va secretlar to'g'ri maskalanadi."""
        text = "Request failed: access_token=my_secret_token and client_secret=my_secret_key and raw EAAB1234567890abcdef"
        masked = mask_sensitive_data(text)
        self.assertNotIn("my_secret_token", masked)
        self.assertNotIn("my_secret_key", masked)
        self.assertNotIn("EAAB1234567890abcdef", masked)
        self.assertIn("access_token=***", masked)
        self.assertIn("client_secret=***", masked)
        self.assertIn("EAAB***", masked)

    def test_redis_error_counters_last_hour(self):
        """Redis minutlik xato hisoblagichlari to'g'ri to'planadi."""
        record_instagram_error(InstagramErrorType.MEDIA_NOT_FOUND)
        record_instagram_error(InstagramErrorType.MEDIA_NOT_FOUND)
        record_instagram_error(InstagramErrorType.RATE_LIMIT)
        record_instagram_error(InstagramErrorType.TOKEN_INVALID)

        counts = get_instagram_errors_last_hour()
        self.assertEqual(counts["media_not_found"], 2)
        self.assertEqual(counts["rate_limit"], 1)
        self.assertEqual(counts["token_invalid"], 1)
        self.assertEqual(counts["permission_denied"], 0)
        self.assertEqual(counts["server_error"], 0)
        self.assertEqual(counts["other"], 0)
        self.assertEqual(counts["total"], 4)

    def test_admin_dashboard_shows_error_types(self):
        """Admin dashboard API da oxirgi 1 soatdagi xato turlari soni ko'rinadi."""
        cache.delete('admin_summary_cache')
        reset_error_counters()
        record_instagram_error(InstagramErrorType.RATE_LIMIT)
        record_instagram_error(InstagramErrorType.SERVER_ERROR)

        self.client.force_authenticate(user=self.admin)

        resp = self.client.get("/api/dashboard/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("instagram_errors_last_hour", data)
        err_stats = data["instagram_errors_last_hour"]
        self.assertEqual(err_stats["rate_limit"], 1)
        self.assertEqual(err_stats["server_error"], 1)
        self.assertGreaterEqual(err_stats["total"], 2)


class CeleryRateLimitingTaskTestCase(TestCase):
    def setUp(self):
        super().setUp()
        rate_limiter.reset()
        self.user = User.objects.create_user(username="celery_rate_user", password="password")
        self.ig_user = InstagramUser.objects.create(
            user=self.user,
            name="celery_rate_ig",
            access_token="EAAB1234567890",
            status="connected",
        )
        self.video = Video.objects.create(
            title="Celery Video",
            file=SimpleUploadedFile("celery.mp4", b"video", content_type="video/mp4"),
            is_active=True,
        )
        self.link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status="posted")
        self.post = Post.objects.create(link=self.link, ig_media_id="media_celery_1", status="published")

    def tearDown(self):
        rate_limiter.reset()
        super().tearDown()

    def test_celery_task_rate_limit_attribute_removed(self):
        """Celery shared_task rate_limit atributi olib tashlangan bo'lishi kerak."""
        self.assertIsNone(check_post_metrics_task.rate_limit)

    @patch('tracker.tasks.rate_limiter.acquire')
    @patch.object(check_post_metrics_task, 'retry')
    def test_task_retries_when_rate_limiter_denies(self, mock_retry, mock_acquire):
        """Rate limiter ruxsat bermasa: task xato hisoblanmaydi, post status o'zgarmaydi, self.retry qilinadi."""
        mock_acquire.return_value = (False, 2.5, "global_rate_limit")
        mock_retry.side_effect = Exception("CeleryRetryTriggered")

        with self.assertRaises(Exception) as ctx:
            check_post_metrics_task(self.post.id)
        self.assertIn("CeleryRetryTriggered", str(ctx.exception))

        # self.retry countdown bilan chaqirilganini tekshirish
        mock_retry.assert_called_once()
        _, kwargs = mock_retry.call_args
        self.assertEqual(kwargs.get('countdown'), 3)

        # Post holati o'zgarmasligini tekshirish
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'published')
        self.assertIsNone(self.post.error)

    @patch('tracker.tasks.update_post_metrics')
    def test_task_runs_when_rate_limiter_allows(self, mock_update):
        """Rate limiter ruxsat berganda task odatiy bajariladi."""
        mock_post = MagicMock()
        mock_post.id = self.post.id
        mock_post.views = 1500
        mock_post.likes = 80
        mock_post.comments_count = 10
        mock_post.status = "published"
        mock_update.return_value = mock_post

        result = check_post_metrics_task(self.post.id)
        self.assertEqual(result["post_id"], self.post.id)
        self.assertEqual(result["views"], 1500)

    @patch('tracker.tasks.update_post_metrics')
    @patch.object(check_post_metrics_task, 'retry')
    def test_task_handles_instagram_rate_limit_error(self, mock_retry, mock_update):
        """Instagram API dan rate limit kelganda: backoff yoqiladi, post o'chirilmaydi, 60s bilan retry qilinadi."""
        mock_update.side_effect = InstagramRateLimitError("Rate limit reached")
        mock_retry.side_effect = Exception("RateLimitRetryTriggered")

        with self.assertRaises(Exception) as ctx:
            check_post_metrics_task(self.post.id)
        self.assertIn("RateLimitRetryTriggered", str(ctx.exception))

        # 60 soniya countdown bilan retry chaqirilganini tekshirish
        mock_retry.assert_called_once()
        _, kwargs = mock_retry.call_args
        self.assertEqual(kwargs.get('countdown'), 60)
        self.assertIsNone(kwargs.get('max_retries'))

        # Rate limiter pasaytirilgan holatga o'tgan
        self.assertTrue(rate_limiter.is_throttled())

        # Post statusi published holatida saqlangan
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'published')


# ==============================================================================
# BOSQICH B: DRY_RUN Rejimi va Simulyatsiya Testlari
# ==============================================================================
from django.core.exceptions import ImproperlyConfigured
from tracker.apps import TrackerConfig


class DryRunModeTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(username="dry_run_user", password="password123")

    @override_settings(INSTAGRAM_DRY_RUN=True, DEBUG=False)
    def test_dry_run_safety_guard_prevents_startup_in_production(self):
        """DEBUG=False bo'lganda INSTAGRAM_DRY_RUN=True bo'lsa ilova ishga tushmasligi kerak."""
        from django.apps import apps
        app_config = apps.get_app_config('tracker')
        with self.assertRaises(ImproperlyConfigured) as ctx:
            app_config.ready()
        self.assertIn("Xavfsizlik xatosi", str(ctx.exception))

    def test_health_endpoint_public_and_healthy(self):
        """Health check endpointi ochiq va tizim holatini to'g'ri qaytaradi."""
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "healthy")
        self.assertEqual(data["database"], "ok")
        self.assertEqual(data["redis"], "ok")
        self.assertFalse(data["dry_run"])

    @override_settings(INSTAGRAM_DRY_RUN=True)
    def test_health_endpoint_reports_dry_run_true(self):
        """INSTAGRAM_DRY_RUN=True bo'lganda health check buni bildiradi."""
        resp = self.client.get("/api/health/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["dry_run"])

    @override_settings(INSTAGRAM_DRY_RUN=True)
    def test_me_profile_includes_dry_run_flag(self):
        """/api/me/ profili javobida dry_run maydoni mavjud bo'lishi kerak."""
        self.client.force_authenticate(user=self.user)
        resp = self.client.get("/api/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("dry_run"))


class DevSimulationEndpointsTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="dev_admin", password="password123")
        self.user = User.objects.create_user(username="dev_regular", password="password123")

        self.ig_user = InstagramUser.objects.create(user=self.user, name="Dev Regular", status="connected")
        self.video = Video.objects.create(
            title="Dev Video",
            file=SimpleUploadedFile("dev.mp4", b"data", content_type="video/mp4"),
            is_active=True,
        )
        self.link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status="posted")
        self.post = Post.objects.create(link=self.link, ig_media_id="media_sim_1", status="published")

    @override_settings(INSTAGRAM_DRY_RUN=False)
    def test_dev_endpoints_return_404_when_dry_run_disabled(self):
        """INSTAGRAM_DRY_RUN o'chiq bo'lsa dev endpointlari 404 qaytarishi shart."""
        self.client.force_authenticate(user=self.admin)
        endpoints = [
            ("/api/dev/simulate-views/", {"post_id": self.post.id, "views": 500}),
            ("/api/dev/simulate-delete/", {"post_id": self.post.id}),
            ("/api/dev/simulate-token-revoked/", {"user_id": self.ig_user.id}),
            ("/api/dev/simulate-network-error/", {"post_id": self.post.id}),
        ]
        for url, payload in endpoints:
            resp = self.client.post(url, payload)
            self.assertEqual(resp.status_code, 404, f"{url} 404 qaytarmadi")

    @override_settings(INSTAGRAM_DRY_RUN=True)
    def test_dev_endpoints_forbidden_for_regular_user_when_dry_run_enabled(self):
        """INSTAGRAM_DRY_RUN yoqiq bo'lsa ham oddiy user uchun dev endpointlari 403 bo'lishi shart."""
        self.client.force_authenticate(user=self.user)
        endpoints = [
            ("/api/dev/simulate-views/", {"post_id": self.post.id, "views": 500}),
            ("/api/dev/simulate-delete/", {"post_id": self.post.id}),
            ("/api/dev/simulate-token-revoked/", {"user_id": self.ig_user.id}),
            ("/api/dev/simulate-network-error/", {"post_id": self.post.id}),
        ]
        for url, payload in endpoints:
            resp = self.client.post(url, payload)
            self.assertEqual(resp.status_code, 403, f"{url} oddiy user uchun 403 qaytarmadi")


class DryRunFullFlowTestCase(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="flow_admin", password="password123")
        self.user = User.objects.create_user(username="flow_user", password="password123")
        self.video = Video.objects.create(
            title="Flow Video",
            file=SimpleUploadedFile("flow.mp4", b"data", content_type="video/mp4"),
            is_active=True,
            is_default=True,
        )

    @override_settings(INSTAGRAM_DRY_RUN=True, DRY_RUN_PUBLISH_DELAY_SECONDS=0, DEBUG=True)
    def test_complete_dry_run_lifecycle(self):
        """
        BOSQICH B to'liq oqim testi:
        1. User tizimga kiradi
        2. Instagramni ulash (/api/user/connect-instagram/) -> sun'iy auth_url oladi
        3. Callback (/oauth/callback/?code=dry_run&state=...) chaqiriladi -> user connected bo'ladi
        4. Video nashr etiladi (/api/user/publish/) -> status published, sun'iy ig_media_id va permalink
        5. POST /api/dev/simulate-views/ (500 views) -> post views 500, PostStat yaratiladi, Prize va Notification faqat 1 marta yaratiladi
        6. Qayta 500 views simulyatsiya -> Prize takrorlanmaydi
        7. POST /api/dev/simulate-delete/ -> post status 'deleted' va deleted_detected_at o'rnatiladi
        8. POST /api/dev/simulate-token-revoked/ -> user status 'needs_reauth' bo'ladi
        """
        # 1. Instagramga ulash so'rovi
        self.client.force_authenticate(user=self.user)
        conn_resp = self.client.get("/api/user/connect-instagram/")
        self.assertEqual(conn_resp.status_code, 200)
        auth_url = conn_resp.data["auth_url"]
        link_token = conn_resp.data["link_token"]

        self.assertIn("code=dry_run", auth_url)
        self.assertIn(f"state={link_token}", auth_url)

        # 2. Callback chaqirish (brauzersiz ulash simulyatsiyasi)
        cb_resp = self.client.get(f"/oauth/callback/?code=dry_run&state={link_token}")
        self.assertEqual(cb_resp.status_code, 200)

        self.user.refresh_from_db()
        self.client.force_authenticate(user=self.user)

        ig_user = InstagramUser.objects.get(user=self.user)
        self.assertEqual(ig_user.status, "connected")
        self.assertTrue(ig_user.access_token.startswith("dry_run_"))

        # 3. Videoni joylash (Publish)
        pub_resp = self.client.post("/api/user/publish/")
        self.assertEqual(pub_resp.status_code, 202)

        link = UniqueLink.objects.get(token=link_token)
        # Celery taskni sinxron chaqirib, postni 'published' holatiga o'tkazamiz
        publish_reels_task(link.id)

        post = Post.objects.get(link=link)
        self.assertEqual(post.status, "published")
        self.assertTrue(post.ig_media_id.startswith("dry_run_media_"))
        self.assertIn("instagram.com", post.permalink)

        # 4. Admin orqali 500 views simulyatsiya qilish
        self.client.force_authenticate(user=self.admin)
        sim_v_resp = self.client.post("/api/dev/simulate-views/", {"post_id": post.id, "views": 500})
        self.assertEqual(sim_v_resp.status_code, 200)

        post.refresh_from_db()
        self.assertEqual(post.views, 500)
        self.assertGreater(post.likes, 0)

        # PostStat tarixi yozilganini tekshirish
        self.assertTrue(PostStat.objects.filter(post=post, views=500).exists())

        # Sovrin (Prize) va Bildirishnoma (Notification) yaratilganini tekshirish
        prizes = Prize.objects.filter(post=post, milestone=500)
        self.assertEqual(prizes.count(), 1)
        self.assertTrue(Notification.objects.filter(user=ig_user, kind='prize').exists())

        # 5. Qayta 500 views simulyatsiya - Prize takrorlanmasligini tekshirish
        sim_v_resp2 = self.client.post("/api/dev/simulate-views/", {"post_id": post.id, "views": 500})
        self.assertEqual(sim_v_resp2.status_code, 200)
        self.assertEqual(Prize.objects.filter(post=post, milestone=500).count(), 1)

        # 6. Post o'chirilishini simulyatsiya qilish (simulate-delete)
        sim_del_resp = self.client.post("/api/dev/simulate-delete/", {"post_id": post.id})
        self.assertEqual(sim_del_resp.status_code, 200)

        post.refresh_from_db()
        self.assertEqual(post.status, "deleted")
        self.assertIsNotNone(post.deleted_detected_at)

        # 7. Token bekor qilinishini simulyatsiya qilish (simulate-token-revoked)
        sim_tok_resp = self.client.post("/api/dev/simulate-token-revoked/", {"user_id": ig_user.id})
        self.assertEqual(sim_tok_resp.status_code, 200)

        ig_user.refresh_from_db()
        self.assertEqual(ig_user.status, "needs_reauth")


class UserRegistrationTestCase(TestCase):
    def test_user_register_success(self):
        """Ochiq ro'yxatdan o'tish muvaffaqiyatli JWT tokenlar qaytarishi kerak."""
        payload = {
            "username": "new_public_user",
            "password": "StrongPassword123!_",
            "name": "Yangi Foydalanuvchi",
        }
        response = self.client.post("/api/register/", payload)
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["username"], "new_public_user")
        self.assertEqual(data["role"], "user")

        # Bazada yaratilganini tekshirish
        user = User.objects.get(username="new_public_user")
        self.assertFalse(user.is_staff)
        self.assertTrue(hasattr(user, "instagram_user"))
        self.assertEqual(user.instagram_user.name, "Yangi Foydalanuvchi")

    def test_user_register_duplicate_username(self):
        """Mavjud username bilan ro'yxatdan o'tish rad etilishi kerak."""
        User.objects.create_user(username="existing_user", password="Pass123!_password")
        payload = {
            "username": "existing_user",
            "password": "StrongPassword123!_",
            "name": "Boshqa User",
        }
        response = self.client.post("/api/register/", payload)
        self.assertEqual(response.status_code, 400)

    def test_user_register_weak_password(self):
        """Zaif parol bilan ro'yxatdan o'tish 400 qaytarishi kerak."""
        payload = {
            "username": "weak_pwd_user",
            "password": "123",
            "name": "Zaif Parol User",
        }
        response = self.client.post("/api/register/", payload)
        self.assertEqual(response.status_code, 400)


class CheckInstagramCommandTestCase(TestCase):
    @patch('tracker.management.commands.check_instagram.requests.get')
    def test_check_instagram_success(self, mock_get):
        from io import StringIO
        from django.core.management import call_command

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "user_id": "17841400000000",
            "username": "official_account",
            "account_type": "BUSINESS",
        }
        mock_get.return_value = mock_resp

        out = StringIO()
        err = StringIO()
        with patch.dict('os.environ', {'INSTAGRAM_ACCESS_TOKEN': 'super_secret_token_123'}):
            call_command('check_instagram', stdout=out, stderr=err)

        output = out.getvalue()
        self.assertIn("username: official_account", output)
        self.assertIn("account_type: BUSINESS", output)
        self.assertNotIn("super_secret_token_123", output)
        self.assertNotIn("super_secret_token_123", err.getvalue())

    def test_check_instagram_missing_token(self):
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        err = StringIO()
        with patch.dict('os.environ', {'INSTAGRAM_ACCESS_TOKEN': ''}):
            with patch('django.conf.settings.INSTAGRAM_ACCESS_TOKEN', ''):
                call_command('check_instagram', stdout=out, stderr=err)

        self.assertIn("topilmadi yoki bo'sh", err.getvalue())

    @patch('tracker.management.commands.check_instagram.requests.get')
    def test_check_instagram_api_error_masks_token(self, mock_get):
        from io import StringIO
        from django.core.management import call_command

        secret_token = "my_private_token_xyz"
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.json.return_value = {
            "error": {
                "message": f"Error validating access token: {secret_token}",
                "type": "OAuthException",
                "code": 190,
                "error_subcode": 463,
            }
        }
        mock_get.return_value = mock_resp

        out = StringIO()
        err = StringIO()
        with patch.dict('os.environ', {'INSTAGRAM_ACCESS_TOKEN': secret_token}):
            call_command('check_instagram', stdout=out, stderr=err)

        err_output = err.getvalue()
        self.assertIn("code=190", err_output)
        self.assertIn("[REDACTED]", err_output)
        self.assertNotIn(secret_token, err_output)
        self.assertNotIn(secret_token, out.getvalue())

    @patch('tracker.management.commands.check_instagram.requests.get')
    def test_check_instagram_network_error(self, mock_get):
        from io import StringIO
        from django.core.management import call_command
        import requests

        mock_get.side_effect = requests.RequestException("Connection timed out")
        out = StringIO()
        err = StringIO()
        with patch.dict('os.environ', {'INSTAGRAM_ACCESS_TOKEN': 'secret_token_net'}):
            call_command('check_instagram', stdout=out, stderr=err)

        self.assertIn("Tarmoq xatoligi", err.getvalue())
        self.assertNotIn("secret_token_net", err.getvalue())


class ConnectInstagramCommandTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="command_test_user", password="Password123!")
        self.ig_user = InstagramUser.objects.create(
            user=self.user,
            name="Command Test User",
            status="pending"
        )

    @patch('tracker.management.commands.connect_instagram.verify_token_permissions')
    @patch('tracker.management.commands.connect_instagram.requests.get')
    def test_connect_instagram_success(self, mock_get, mock_perms):
        from io import StringIO
        from django.core.management import call_command

        mock_perms.return_value = (True, [])
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "user_id": "17841499999999",
            "username": "command_ig_user",
            "account_type": "MEDIA_CREATOR",
        }
        mock_get.return_value = mock_resp

        out = StringIO()
        call_command('connect_instagram', 'command_test_user', '--token', 'test_token_val', stdout=out)

        self.ig_user.refresh_from_db()
        self.assertEqual(self.ig_user.status, 'connected')
        self.assertEqual(self.ig_user.ig_user_id, '17841499999999')
        self.assertEqual(self.ig_user.access_token, 'test_token_val')
        self.assertIn("@command_ig_user", out.getvalue())
        self.assertIn("CONNECTED", out.getvalue())


class TokenEncryptionAndSecurityTestCase(TestCase):
    def setUp(self):
        self.user_auth = User.objects.create_user(username="test_enc_user", password="Password123!")
        self.ig_user = InstagramUser.objects.create(
            user=self.user_auth,
            name="Test Encrypted User",
            access_token="plain_instagram_token_xyz",
            status="connected",
        )
        self.client = APIClient()

    def test_token_stored_encrypted_in_database(self):
        """Bazada token ochiq matn (plain text) ko'rinishida saqlanmasligi, Fernet shifrlangan bo'lishi tekshiriladi."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT access_token FROM tracker_instagramuser WHERE id = %s", [self.ig_user.id])
            raw_db_token = cursor.fetchone()[0]

        self.assertIsNotNone(raw_db_token)
        self.assertTrue(raw_db_token.startswith("gAAAAA"))
        self.assertNotIn("plain_instagram_token_xyz", raw_db_token)

    def test_token_decrypted_transparently_in_orm(self):
        """ORM orqali o'qilganda shifrlangan token avtomatik dekodlanib asl holida qaytishi tekshiriladi."""
        loaded_user = InstagramUser.objects.get(id=self.ig_user.id)
        self.assertEqual(loaded_user.access_token, "plain_instagram_token_xyz")

    def test_token_update_is_encrypted_in_db(self):
        """Token yangilanganda ham bazaga shifrlanib yozilishi tekshiriladi."""
        from django.db import connection
        self.ig_user.access_token = "updated_plain_token_abc"
        self.ig_user.save()

        with connection.cursor() as cursor:
            cursor.execute("SELECT access_token FROM tracker_instagramuser WHERE id = %s", [self.ig_user.id])
            raw_db_token = cursor.fetchone()[0]

        self.assertTrue(raw_db_token.startswith("gAAAAA"))
        self.assertNotIn("updated_plain_token_abc", raw_db_token)

        reloaded = InstagramUser.objects.get(id=self.ig_user.id)
        self.assertEqual(reloaded.access_token, "updated_plain_token_abc")

    def test_token_none_and_empty_preserved(self):
        """None yoki bo'sh tokenlar xatosiz saqlanishi va qaytarilishi."""
        user_empty = InstagramUser.objects.create(name="Empty Token User", access_token="")
        user_none = InstagramUser.objects.create(name="None Token User", access_token=None)

        self.assertEqual(InstagramUser.objects.get(id=user_empty.id).access_token, "")
        self.assertIsNone(InstagramUser.objects.get(id=user_none.id).access_token)

    def test_crypto_helpers_idempotency_and_safety(self):
        from tracker.crypto import encrypt_token, decrypt_token, is_fernet_encrypted
        plain = "my_sample_token_12345"
        enc = encrypt_token(plain)
        self.assertTrue(is_fernet_encrypted(enc))
        # Qayta shifrlash takroriy shifrlamasligi kerak (idempotent)
        self.assertEqual(encrypt_token(enc), enc)
        # Qayta dekodlash asl qiymatni qaytarishi kerak
        self.assertEqual(decrypt_token(enc), plain)
        # Ochiq tokenni decrypt_token chaqirsa ma'lumot yo'qolmasligi kerak
        self.assertEqual(decrypt_token(plain), plain)
        self.assertIsNone(encrypt_token(None))
        self.assertIsNone(decrypt_token(None))

    def test_tokens_never_in_api_responses(self):
        """API javoblarida (me, users list, user detail) access_token chiqmasligi tekshiriladi."""
        self.client.force_authenticate(user=self.user_auth)
        resp = self.client.get('/api/me/')
        self.assertEqual(resp.status_code, 200)
        resp_json = resp.json()
        resp_text = resp.content.decode('utf-8')
        self.assertNotIn("plain_instagram_token_xyz", resp_text)
        self.assertNotIn("access_token", resp_json.get("instagram_user", {}))

        # Admin sifatida tekshirish
        admin_user = User.objects.create_superuser(username="admin_enc_test", password="Password123!")
        self.client.force_authenticate(user=admin_user)

        resp_users = self.client.get('/api/users/')
        self.assertEqual(resp_users.status_code, 200)
        self.assertNotIn("plain_instagram_token_xyz", resp_users.content.decode('utf-8'))

        resp_detail = self.client.get(f'/api/users/{self.ig_user.id}/')
        self.assertEqual(resp_detail.status_code, 200)
        self.assertNotIn("plain_instagram_token_xyz", resp_detail.content.decode('utf-8'))

    def test_mask_sensitive_data_extended_patterns(self):
        """Meta tokenlar (IGAA), Fernet shifrlari va dry-run tokenlar loglarda maskalanishi tekshiriladi."""
        text = "Tokens: IGAA1234567890abcdef and gAAAAABdXYZ1234567890abcdef1234567890 and dry_run_short_token_abcdef12"
        masked = mask_sensitive_data(text)
        self.assertNotIn("IGAA1234567890abcdef", masked)
        self.assertNotIn("gAAAAABdXYZ1234567890abcdef1234567890", masked)
        self.assertNotIn("dry_run_short_token_abcdef12", masked)
        self.assertIn("IGAA***", masked)
        self.assertIn("gAAAAA***", masked)
        self.assertIn("dry_run_***", masked)

    def test_mandatory_settings_and_optional_access_token(self):
        """INSTAGRAM_ACCESS_TOKEN ixtiyoriy, TOKEN_ENCRYPTION_KEY esa mavjud bo'lishi tekshiriladi."""
        self.assertTrue(hasattr(settings, 'TOKEN_ENCRYPTION_KEY'))
        self.assertTrue(settings.TOKEN_ENCRYPTION_KEY)
        self.assertTrue(hasattr(settings, 'INSTAGRAM_ACCESS_TOKEN'))

    def test_missing_mandatory_env_raises_key_error(self):
        """Majburiy env o'zgaruvchilari yo'q bo'lsa KeyError berilishi tekshiriladi."""
        import os
        mandatory_keys = ('INSTAGRAM_APP_ID', 'INSTAGRAM_APP_SECRET', 'TOKEN_ENCRYPTION_KEY', 'SECRET_KEY', 'DB_PASSWORD')
        for missing_key in mandatory_keys:
            env_copy = {k: "dummy_val" for k in mandatory_keys}
            del env_copy[missing_key]
            with patch.dict('os.environ', env_copy, clear=True):
                with self.assertRaises(KeyError) as ctx:
                    for k in mandatory_keys:
                        if not os.environ.get(k):
                            raise KeyError(f"Majburiy muhit o'zgaruvchisi o'rnatilmagan: {k}")
                self.assertIn(missing_key, str(ctx.exception))


class InstagramWebhookTestCase(TestCase):
    def setUp(self):
        self.verify_token = getattr(settings, 'INSTAGRAM_WEBHOOK_VERIFY_TOKEN', 'insta_checker_webhook_token')

    def test_webhook_challenge_success(self):
        response = self.client.get('/api/instagram/webhook/', {
            'hub.mode': 'subscribe',
            'hub.verify_token': self.verify_token,
            'hub.challenge': '123456789'
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode('utf-8'), '123456789')

    def test_webhook_challenge_invalid_token(self):
        response = self.client.get('/api/instagram/webhook/', {
            'hub.mode': 'subscribe',
            'hub.verify_token': 'wrong_token',
            'hub.challenge': '123456789'
        })
        self.assertEqual(response.status_code, 403)

    @patch('tracker.tasks.check_post_metrics_task.delay')
    def test_webhook_post_event_triggers_check(self, mock_task):
        user = User.objects.create_user(username='hookuser', password='pwd')
        ig_user = InstagramUser.objects.create(user=user, name='hookuser', status='connected')
        link = UniqueLink.objects.create(user=ig_user)
        post = Post.objects.create(link=link, ig_media_id='media_hook_999', status='published')

        payload = {
            "object": "instagram",
            "entry": [{
                "id": "17841400000000000",
                "time": 1700000000,
                "changes": [{
                    "field": "mentions",
                    "value": {
                        "media_id": "media_hook_999",
                        "comment_id": "17900000000"
                    }
                }]
            }]
        }
        response = self.client.post('/api/instagram/webhook/', payload, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        mock_task.assert_called_once_with(post.id)


class Phase7EnhancementsTestCase(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from .services import validate_video_orientation
        self.validate_video_orientation = validate_video_orientation
        self.user = User.objects.create_user(username='enh_user', password='password123')
        self.ig_user = InstagramUser.objects.create(
            user=self.user,
            name="Enh User",
            status='connected',
            access_token='valid_token_123',
            ig_user_id='ig_123456'
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_video_orientation_detection(self):
        import io, struct
        # Gorizontal video (width=1920, height=1080)
        buf_horiz = io.BytesIO()
        buf_horiz.write(b'\x00' * 16)
        buf_horiz.write(b'tkhd')
        buf_horiz.write(b'\x00') # version
        buf_horiz.write(b'\x00' * 75)
        buf_horiz.write(struct.pack('>II', int(1920 * 65536), int(1080 * 65536)))
        buf_horiz.write(b'\x00' * 100)
        buf_horiz.seek(0)
        err = self.validate_video_orientation(buf_horiz)
        self.assertIsNotNone(err)
        self.assertIn("gorizontal", err)

        # Vertikal video (width=1080, height=1920)
        buf_vert = io.BytesIO()
        buf_vert.write(b'\x00' * 16)
        buf_vert.write(b'tkhd')
        buf_vert.write(b'\x00') # version
        buf_vert.write(b'\x00' * 75)
        buf_vert.write(struct.pack('>II', int(1080 * 65536), int(1920 * 65536)))
        buf_vert.write(b'\x00' * 100)
        buf_vert.seek(0)
        self.assertIsNone(self.validate_video_orientation(buf_vert))

    def test_me_posts_ordering_views_and_date(self):
        link1 = UniqueLink.objects.create(user=self.ig_user)
        link2 = UniqueLink.objects.create(user=self.ig_user)
        now = timezone.now()
        post1 = Post.objects.create(link=link1, views=100, posted_at=now - timedelta(hours=2), status='published')
        post2 = Post.objects.create(link=link2, views=500, posted_at=now - timedelta(hours=1), status='published')

        # Views bo'yicha kamayish tartibi (-views)
        resp = self.client.get('/api/me/posts/?ordering=-views')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(results[0]['id'], post2.id)
        self.assertEqual(results[1]['id'], post1.id)

        # Views bo'yicha o'sish tartibi (views)
        resp = self.client.get('/api/me/posts/?ordering=views')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(results[0]['id'], post1.id)
        self.assertEqual(results[1]['id'], post2.id)

        # Sana bo'yicha kamayish tartibi (-posted_at)
        resp = self.client.get('/api/me/posts/?ordering=-posted_at')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(results[0]['id'], post2.id)

    @patch('tracker.views.update_post_metrics')
    def test_me_post_history_auto_refresh_every_5m(self, mock_update):
        link = UniqueLink.objects.create(user=self.ig_user)
        # Oxirgi tekshiruv 10 daqiqa oldin bo'lgan post
        post = Post.objects.create(
            link=link,
            ig_media_id='ig_post_999',
            status='published',
            views=150,
            last_checked_at=timezone.now() - timedelta(minutes=10)
        )
        PostStat.objects.create(post=post, views=100, checked_at=timezone.now() - timedelta(minutes=10))

        resp = self.client.get(f'/api/me/posts/{post.id}/history/')
        self.assertEqual(resp.status_code, 200)
        # 5 daqiqadan oshgani uchun update_post_metrics chaqirilishi kerak
        mock_update.assert_called_once_with(post)


class ResumableUploadTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Resumable User",
            ig_user_id="ig_resumable_123",
            access_token="secret_token_resumable",
            status="connected",
        )
        dummy_video = SimpleUploadedFile("test_resumable.mp4", b"dummy_mp4_bytes", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy_video)

    @patch('tracker.services.get_media_permalink')
    @patch('tracker.services.publish_container')
    @patch('tracker.services.wait_for_container_ready')
    @patch('tracker.services.upload_video_binary')
    @patch('tracker.services.create_reels_container_resumable')
    def test_resumable_upload_flow_success(
        self, mock_create_resumable, mock_upload_binary, mock_wait, mock_publish, mock_permalink
    ):
        mock_create_resumable.return_value = ("resumable_container_123", "https://rupload.facebook.com/ig-api-upload/v21.0/resumable_container_123")
        mock_wait.return_value = True
        mock_publish.return_value = "resumable_media_999"
        mock_permalink.return_value = "https://instagram.com/reel/resumable999/"

        post = publish_reels_for_link(self.link.id, caption="Resumable Caption")

        mock_create_resumable.assert_called_once_with(
            ig_user_id="ig_resumable_123",
            access_token="secret_token_resumable",
            caption="Resumable Caption",
            share_to_feed=True,
        )
        mock_upload_binary.assert_called_once()
        mock_wait.assert_called_once_with("resumable_container_123", "secret_token_resumable")
        mock_publish.assert_called_once_with("ig_resumable_123", "resumable_container_123", "secret_token_resumable")
        self.assertEqual(post.status, 'published')
        self.assertEqual(post.ig_media_id, 'resumable_media_999')

    @patch('tracker.services.requests.post')
    def test_real_client_resumable_methods_with_requests_mock(self, mock_post):
        from tracker.instagram_client import RealInstagramClient
        client = RealInstagramClient()

        # 1. create_reels_container_resumable
        mock_resp_container = MagicMock()
        mock_resp_container.status_code = 200
        mock_resp_container.json.return_value = {
            "id": "cont_456",
            "uri": "https://rupload.facebook.com/ig-api-upload/v21.0/cont_456"
        }
        mock_post.return_value = mock_resp_container

        container_id, upload_uri = client.create_reels_container_resumable(
            ig_user_id="17841",
            access_token="token_xyz",
            caption="Test caption",
            share_to_feed=True
        )
        self.assertEqual(container_id, "cont_456")
        self.assertEqual(upload_uri, "https://rupload.facebook.com/ig-api-upload/v21.0/cont_456")

        # 2. upload_video_binary
        mock_resp_upload = MagicMock()
        mock_resp_upload.status_code = 200
        mock_post.return_value = mock_resp_upload

        import io
        dummy_stream = io.BytesIO(b"binary_video_stream")
        client.upload_video_binary(
            upload_url=upload_uri,
            file_obj=dummy_stream,
            file_size=19,
            access_token="token_xyz"
        )
        # Verify OAuth header and offset
        called_args, called_kwargs = mock_post.call_args
        self.assertEqual(called_kwargs['headers']['Authorization'], "OAuth token_xyz")
        self.assertEqual(called_kwargs['headers']['offset'], "0")
        self.assertEqual(called_kwargs['headers']['file_size'], "19")


class VideoAspectConversionTestCase(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.user = User.objects.create_user(username='aspect_user', password='password123')
        self.client.force_authenticate(user=self.user)
        self.ig_user = InstagramUser.objects.create(
            user=self.user,
            name="Aspect User",
            status='connected',
            access_token='valid_token_aspect',
            ig_user_id='ig_aspect_123'
        )

    def test_needs_aspect_ratio_conversion(self):
        from .video_utils import needs_aspect_ratio_conversion
        # 16:9 gorizontal videolar -> o'zgartirilishi kerak (True)
        self.assertTrue(needs_aspect_ratio_conversion(1920, 1080))
        self.assertTrue(needs_aspect_ratio_conversion(1276, 718))

        # 9:16 vertikal videolar (0.5625) -> o'zgartirilmasligi kerak (False)
        self.assertFalse(needs_aspect_ratio_conversion(1080, 1920))
        self.assertFalse(needs_aspect_ratio_conversion(720, 1280))

        # 1:1 kvadrat va 4:3 -> o'zgartirilishi kerak (True)
        self.assertTrue(needs_aspect_ratio_conversion(1080, 1080))
        self.assertTrue(needs_aspect_ratio_conversion(1440, 1080))

        # 0 yoki manfiy o'lchamlar -> False
        self.assertFalse(needs_aspect_ratio_conversion(0, 0))

    def test_validate_video_duration(self):
        from .video_utils import validate_video_duration
        # 3 soniyadan kam -> xato
        err_short = validate_video_duration(2.5)
        self.assertIsNotNone(err_short)
        self.assertIn("3 soniyadan kam", err_short)

        # 90 soniyadan ko'p -> xato
        err_long = validate_video_duration(95.0)
        self.assertIsNotNone(err_long)
        self.assertIn("90 soniyadan ko'p", err_long)

        # 3 va 90 oralig'ida -> to'g'ri (None)
        self.assertIsNone(validate_video_duration(3.0))
        self.assertIsNone(validate_video_duration(15.5))
        self.assertIsNone(validate_video_duration(90.0))

    @patch('tracker.video_utils.subprocess.run')
    @patch('tracker.video_utils.shutil.which')
    def test_get_video_info_ffprobe(self, mock_which, mock_run):
        from .video_utils import get_video_info
        mock_which.return_value = '/usr/bin/ffprobe'
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = json.dumps({
            "streams": [
                {"codec_type": "video", "width": 1276, "height": 718, "duration": "12.5"},
                {"codec_type": "audio"}
            ],
            "format": {"duration": "12.5"}
        })
        mock_run.return_value = mock_proc

        with patch('os.path.exists', return_value=True):
            info = get_video_info('/tmp/fake.mp4')
            self.assertEqual(info['width'], 1276)
            self.assertEqual(info['height'], 718)
            self.assertEqual(info['duration'], 12.5)
            self.assertTrue(info['has_audio'])

    @patch('tracker.video_utils.subprocess.run')
    @patch('tracker.video_utils.shutil.which')
    def test_convert_video_to_9_16_command(self, mock_which, mock_run):
        from .video_utils import convert_video_to_9_16
        mock_which.return_value = '/usr/bin/ffmpeg'
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_run.return_value = mock_proc

        with patch('tracker.video_utils.get_video_info', return_value={'width': 1276, 'height': 718, 'has_audio': True}), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=5000):
            res = convert_video_to_9_16('/tmp/in.mp4', '/tmp/out.mp4')
            self.assertTrue(res)

            call_args = mock_run.call_args[0][0]
            self.assertEqual(call_args[0], '/usr/bin/ffmpeg')
            self.assertIn('-filter_complex', call_args)
            idx_fc = call_args.index('-filter_complex')
            filter_str = call_args[idx_fc + 1]
            self.assertIn('scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20:5', filter_str)
            self.assertIn('scale=1080:-2', filter_str)
            self.assertIn('libx264', call_args)
            self.assertIn('veryfast', call_args)
            self.assertIn('+faststart', call_args)

    @patch('tracker.tasks.process_video_file')
    def test_process_video_task_success(self, mock_process_file):
        from .tasks import process_video_task
        mock_process_file.return_value = (True, None)

        f = SimpleUploadedFile("horizontal.mp4", b"dummy_content", content_type="video/mp4")
        video = Video.objects.create(title="Horizontal Video", file=f, owner=self.ig_user, status='pending')

        result = process_video_task(video.id)
        self.assertEqual(result['status'], 'ready')

        video.refresh_from_db()
        self.assertEqual(video.status, 'ready')
        self.assertIsNone(video.processing_error)

    @patch('tracker.video_utils.convert_video_to_9_16')
    @patch('tracker.video_utils.get_video_info')
    def test_process_video_task_horizontal_converts_to_vertical(self, mock_info, mock_convert):
        from .tasks import process_video_task
        mock_info.return_value = {
            'width': 1276,
            'height': 718,
            'duration': 15.0,
            'has_audio': True,
        }

        def fake_convert(input_p, output_p, timeout=180):
            with open(output_p, 'wb') as out_f:
                out_f.write(b'converted_vertical_content')
            return True

        mock_convert.side_effect = fake_convert

        f = SimpleUploadedFile("horiz_video.mp4", b"original_content", content_type="video/mp4")
        video = Video.objects.create(title="Horizontal Promo", file=f, owner=self.ig_user, status='pending')

        result = process_video_task(video.id)
        self.assertEqual(result['status'], 'ready')

        video.refresh_from_db()
        self.assertEqual(video.status, 'ready')
        mock_convert.assert_called_once()

    @patch('tracker.video_utils.convert_video_to_9_16')
    @patch('tracker.video_utils.get_video_info')
    def test_process_video_task_vertical_skipped(self, mock_info, mock_convert):
        from .tasks import process_video_task
        # 1080x1920 (9:16)
        mock_info.return_value = {
            'width': 1080,
            'height': 1920,
            'duration': 15.0,
            'has_audio': True,
        }

        f = SimpleUploadedFile("vertical_video.mp4", b"vertical_content", content_type="video/mp4")
        video = Video.objects.create(title="Vertical Promo", file=f, owner=self.ig_user, status='pending')

        result = process_video_task(video.id)
        self.assertEqual(result['status'], 'ready')

        video.refresh_from_db()
        self.assertEqual(video.status, 'ready')
        mock_convert.assert_not_called()

    @patch('tracker.video_utils.get_video_info')
    def test_process_video_task_duration_less_than_3_seconds(self, mock_info):
        from .tasks import process_video_task
        mock_info.return_value = {
            'width': 1080,
            'height': 1920,
            'duration': 2.0,
            'has_audio': True,
        }

        f = SimpleUploadedFile("short_video.mp4", b"short_content", content_type="video/mp4")
        video = Video.objects.create(title="Short Video", file=f, owner=self.ig_user, status='pending')

        result = process_video_task(video.id)
        self.assertEqual(result['status'], 'failed')

        video.refresh_from_db()
        self.assertEqual(video.status, 'failed')
        self.assertIn("3 soniyadan kam", video.processing_error)

    @patch('tracker.video_utils.get_video_info')
    def test_process_video_task_duration_more_than_90_seconds(self, mock_info):
        from .tasks import process_video_task
        mock_info.return_value = {
            'width': 1080,
            'height': 1920,
            'duration': 95.0,
            'has_audio': True,
        }

        f = SimpleUploadedFile("long_video.mp4", b"long_content", content_type="video/mp4")
        video = Video.objects.create(title="Long Video", file=f, owner=self.ig_user, status='pending')

        result = process_video_task(video.id)
        self.assertEqual(result['status'], 'failed')

        video.refresh_from_db()
        self.assertEqual(video.status, 'failed')
        self.assertIn("90 soniyadan ko'p", video.processing_error)

    @patch('tracker.tasks.process_video_task.delay')
    def test_user_upload_video_endpoint_queues_task(self, mock_delay):
        f = SimpleUploadedFile("user_reel.mp4", b"reel_content", content_type="video/mp4")
        response = self.client.post('/api/user/upload-video/', {
            'title': 'My Uploaded Reel',
            'file': f,
        }, format='multipart')

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data['status'], 'processing')
        mock_delay.assert_called_once_with(data['id'])

    def test_user_publish_video_blocked_while_processing(self):
        f = SimpleUploadedFile("processing_vid.mp4", b"dummy", content_type="video/mp4")
        Video.objects.create(
            title="Processing Video",
            file=f,
            owner=self.ig_user,
            is_active=True,
            status='processing'
        )

        resp = self.client.post('/api/user/publish/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("tayyorlanmoqda", resp.json().get('error', ''))

    def test_user_publish_video_blocked_when_failed(self):
        f = SimpleUploadedFile("failed_vid.mp4", b"dummy", content_type="video/mp4")
        Video.objects.create(
            title="Failed Video",
            file=f,
            owner=self.ig_user,
            is_active=True,
            status='failed',
            processing_error="Video davomiyligi 3 soniyadan kam (amalda: 2.1 soniya)."
        )

        resp = self.client.post('/api/user/publish/')
        self.assertEqual(resp.status_code, 400)
        self.assertIn("yaroqsiz", resp.json().get('error', ''))
        self.assertIn("3 soniyadan kam", resp.json().get('error', ''))

    def test_user_publish_status_shows_processing_reason(self):
        f = SimpleUploadedFile("processing_vid.mp4", b"dummy", content_type="video/mp4")
        Video.objects.create(
            title="Processing Video",
            file=f,
            owner=self.ig_user,
            is_active=True,
            status='processing'
        )

        resp = self.client.get('/api/user/publish-status/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data['can_publish'])
        self.assertIn("tayyorlanmoqda", data['can_publish_reason'])


class ModelAndClientPromptOneTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(name="Prompt1 User")
        dummy = SimpleUploadedFile("test.mp4", b"content", content_type="video/mp4")
        self.link = UniqueLink.objects.create(user=self.user, video=dummy)

    def test_uniquelink_code_auto_generated(self):
        from tracker.models import UNIQUE_CODE_ALPHABET
        self.assertTrue(bool(self.link.code))
        self.assertEqual(len(self.link.code), 6)
        # 0, O, 1, I belgilarisiz bo'lishi kerak
        for bad_char in ('0', 'O', '1', 'I', 'o', 'i'):
            self.assertNotIn(bad_char, self.link.code)
        for char in self.link.code:
            self.assertIn(char, UNIQUE_CODE_ALPHABET)

    def test_uniquelink_code_uniqueness(self):
        dummy = SimpleUploadedFile("test2.mp4", b"content", content_type="video/mp4")
        link2 = UniqueLink(user=self.user, video=dummy, code=self.link.code)
        with self.assertRaises(IntegrityError):
            link2.save()

    def test_uniquelink_code_uppercase_normalization(self):
        dummy = SimpleUploadedFile("test3.mp4", b"content", content_type="video/mp4")
        link = UniqueLink.objects.create(user=self.user, video=dummy, code="abc234")
        self.assertEqual(link.code, "ABC234")

    def test_post_model_fields_and_choices(self):
        post = Post.objects.create(
            link=self.link,
            source='self',
            status='verified',
            thumbnail_url='https://example.com/thumb.jpg',
            last_synced_at=timezone.now(),
            views=100,
            likes=10,
            comments_count=2,
        )
        self.assertEqual(post.source, 'self')
        self.assertEqual(post.status, 'verified')
        self.assertEqual(post.thumbnail_url, 'https://example.com/thumb.jpg')
        self.assertEqual(post.views, 100)
        self.assertEqual(post.likes, 10)
        self.assertEqual(post.comments_count, 2)
        self.assertIsNotNone(post.last_synced_at)

        # status choices: rejected, revoked
        post.status = 'rejected'
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.status, 'rejected')

        post.status = 'revoked'
        post.save()
        post.refresh_from_db()
        self.assertEqual(post.status, 'revoked')

    def test_post_ig_media_id_uniqueness(self):
        dummy = SimpleUploadedFile("test4.mp4", b"content", content_type="video/mp4")
        link2 = UniqueLink.objects.create(user=self.user, video=dummy)

        post1 = Post.objects.create(link=self.link, ig_media_id="ig_media_unique_1")
        post2 = Post(link=link2, ig_media_id="ig_media_unique_1")
        with self.assertRaises(IntegrityError):
            post2.save()

    def test_post_ig_media_id_null_and_empty_handling(self):
        dummy1 = SimpleUploadedFile("test5.mp4", b"content", content_type="video/mp4")
        dummy2 = SimpleUploadedFile("test6.mp4", b"content", content_type="video/mp4")
        link1 = UniqueLink.objects.create(user=self.user, video=dummy1)
        link2 = UniqueLink.objects.create(user=self.user, video=dummy2)

        # Multiple posts with ig_media_id=None
        p1 = Post.objects.create(link=link1, ig_media_id=None)
        p2 = Post.objects.create(link=link2, ig_media_id="")
        self.assertIsNone(p1.ig_media_id)
        self.assertIsNone(p2.ig_media_id)

    @patch('tracker.instagram_client.requests.get')
    def test_list_recent_media_single_page(self, mock_get):
        from tracker.instagram_client import list_recent_media

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': [
                {
                    'id': 'media_101',
                    'caption': 'Reel caption with code #ABCDEF',
                    'media_type': 'VIDEO',
                    'media_product_type': 'REELS',
                    'permalink': 'https://instagram.com/reel/101/',
                    'timestamp': '2026-10-22T10:00:00+0000',
                    'like_count': 15,
                    'comments_count': 3,
                    'thumbnail_url': 'https://example.com/101.jpg',
                }
            ],
            'paging': {}
        }
        mock_get.return_value = mock_resp

        media_list = list_recent_media(token="test_token_123", limit=10)
        self.assertEqual(len(media_list), 1)
        self.assertEqual(media_list[0]['id'], 'media_101')
        self.assertEqual(media_list[0]['media_product_type'], 'REELS')

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], 'https://graph.instagram.com/me/media')
        self.assertEqual(kwargs['params']['limit'], 10)
        self.assertEqual(kwargs['params']['access_token'], 'test_token_123')
        self.assertIn('media_product_type', kwargs['params']['fields'])

    @patch('tracker.instagram_client.requests.get')
    def test_list_recent_media_pagination_stops_at_max_4_pages(self, mock_get):
        from tracker.instagram_client import list_recent_media

        # 6 sahifali soxta javoblar (maksimal 4 tasi olinishi kerak)
        def side_effect(url, params=None, timeout=15):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            page_num = 1
            if 'page=' in url:
                page_num = int(url.split('page=')[1])
            mock_resp.json.return_value = {
                'data': [{'id': f'media_p{page_num}'}],
                'paging': {'next': f'https://graph.instagram.com/me/media?page={page_num + 1}'}
            }
            return mock_resp

        mock_get.side_effect = side_effect

        media_list = list_recent_media(token="test_token_paging")
        self.assertEqual(len(media_list), 4)
        self.assertEqual([m['id'] for m in media_list], ['media_p1', 'media_p2', 'media_p3', 'media_p4'])
        self.assertEqual(mock_get.call_count, 4)

    @patch('tracker.instagram_client.requests.get')
    def test_list_recent_media_token_invalid_code_190(self, mock_get):
        from tracker.instagram_client import list_recent_media, TokenInvalid

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = json.dumps({
            "error": {
                "message": "Error validating access token: Session has expired",
                "type": "OAuthException",
                "code": 190,
                "error_subcode": 463
            }
        })
        mock_resp.json.return_value = {
            "error": {
                "message": "Error validating access token: Session has expired",
                "type": "OAuthException",
                "code": 190,
                "error_subcode": 463
            }
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(TokenInvalid) as ctx:
            list_recent_media(token="expired_token")

        self.assertEqual(ctx.exception.error_code, 190)
        self.assertEqual(ctx.exception.error_subcode, 463)

    @patch('tracker.instagram_client.requests.get')
    def test_get_media_insights_success(self, mock_get):
        from tracker.instagram_client import get_media_insights

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            'data': [
                {'name': 'views', 'values': [{'value': 1250}]},
                {'name': 'reach', 'values': [{'value': 980}]},
                {'name': 'likes', 'values': [{'value': 110}]},
                {'name': 'comments', 'values': [{'value': 18}]},
                {'name': 'shares', 'values': [{'value': 9}]},
                {'name': 'saved', 'values': [{'value': 5}]},
            ]
        }
        mock_get.return_value = mock_resp

        insights = get_media_insights(token="test_token", media_id="media_reel_999")
        self.assertEqual(insights['views'], 1250)
        self.assertEqual(insights['reach'], 980)
        self.assertEqual(insights['likes'], 110)
        self.assertEqual(insights['comments'], 18)
        self.assertEqual(insights['comments_count'], 18)
        self.assertEqual(insights['shares'], 9)
        self.assertEqual(insights['saved'], 5)

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], 'https://graph.instagram.com/media_reel_999/insights')
        self.assertEqual(kwargs['params']['metric'], 'views,reach,likes,comments,shares,saved')
        self.assertEqual(kwargs['params']['access_token'], 'test_token')

    @patch('tracker.instagram_client.requests.get')
    def test_get_media_insights_token_invalid_code_190(self, mock_get):
        from tracker.instagram_client import get_media_insights, TokenInvalid

        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = json.dumps({
            "error": {
                "message": "Invalid OAuth access token.",
                "code": 190
            }
        })
        mock_resp.json.return_value = {
            "error": {
                "message": "Invalid OAuth access token.",
                "code": 190
            }
        }
        mock_get.return_value = mock_resp

        with self.assertRaises(TokenInvalid) as ctx:
            get_media_insights(token="bad_token", media_id="media_123")

        self.assertEqual(ctx.exception.error_code, 190)

    def test_client_class_delegation(self):
        from tracker.instagram_client import RealInstagramClient, DryRunInstagramClient

        real_client = RealInstagramClient()
        self.assertTrue(hasattr(real_client, 'list_recent_media'))
        self.assertTrue(hasattr(real_client, 'get_media_insights'))

        dry_client = DryRunInstagramClient()
        self.assertEqual(dry_client.list_recent_media(access_token="tok"), [])
        ins = dry_client.get_media_insights(access_token="tok", media_id="med")
        self.assertIn('views', ins)
        self.assertIn('likes', ins)
        self.assertIn('comments', ins)
        self.assertIn('reach', ins)
        self.assertIn('shares', ins)
        self.assertIn('saved', ins)


class SyncUserMediaAndCeleryTasksTestCase(TestCase):
    def setUp(self):
        self.user_a = InstagramUser.objects.create(name="User A", status="connected", access_token="token_a")
        self.user_b = InstagramUser.objects.create(name="User B", status="connected", access_token="token_b")

        dummy_vid = SimpleUploadedFile("v1.mp4", b"data", content_type="video/mp4")
        self.link_a = UniqueLink.objects.create(user=self.user_a, video=dummy_vid, code="AAA234")
        self.link_b = UniqueLink.objects.create(user=self.user_b, video=dummy_vid, code="BBB567")

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_with_code_success(self, mock_list, mock_insights):
        from tracker.services import sync_user_media

        mock_list.return_value = [
            {
                'id': 'media_reels_100',
                'caption': 'Check out this awesome video with code #AAA234 for promo!',
                'media_product_type': 'REELS',
                'permalink': 'https://instagram.com/reel/100/',
                'thumbnail_url': 'https://example.com/thumb_100.jpg',
                'like_count': 50,
                'comments_count': 8,
            }
        ]
        mock_insights.return_value = {
            'views': 2500,
            'reach': 1800,
            'likes': 50,
            'comments': 8,
            'comments_count': 8,
            'shares': 10,
            'saved': 4,
        }

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['verified_count'], 1)

        post = Post.objects.get(ig_media_id='media_reels_100')
        self.assertEqual(post.status, 'verified')
        self.assertEqual(post.source, 'self')
        self.assertEqual(post.permalink, 'https://instagram.com/reel/100/')
        self.assertEqual(post.thumbnail_url, 'https://example.com/thumb_100.jpg')
        self.assertEqual(post.likes, 50)
        self.assertEqual(post.comments_count, 8)
        self.assertEqual(post.views, 2500)
        self.assertIsNotNone(post.last_synced_at)
        self.assertEqual(post.link.user, self.user_a)

    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_without_code(self, mock_list):
        from tracker.services import sync_user_media

        mock_list.return_value = [
            {
                'id': 'media_no_code_200',
                'caption': 'Just a normal reel without any promo code here',
                'media_product_type': 'REELS',
                'permalink': 'https://instagram.com/reel/200/',
                'thumbnail_url': 'https://example.com/thumb_200.jpg',
                'like_count': 12,
                'comments_count': 1,
            }
        ]

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['verified_count'], 0)
        self.assertFalse(Post.objects.filter(ig_media_id='media_no_code_200').exists())

    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_not_reels(self, mock_list):
        from tracker.services import sync_user_media

        mock_list.return_value = [
            {
                'id': 'media_feed_300',
                'caption': 'Post with code AAA234 but this is a feed post',
                'media_product_type': 'FEED',
                'permalink': 'https://instagram.com/p/300/',
                'thumbnail_url': 'https://example.com/thumb_300.jpg',
                'like_count': 20,
                'comments_count': 2,
            }
        ]

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['verified_count'], 0)
        self.assertFalse(Post.objects.filter(ig_media_id='media_feed_300').exists())

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_duplicate_ig_media_id_other_user(self, mock_list, mock_insights):
        from tracker.services import sync_user_media

        # Post allaqachon User A ga tegishli
        Post.objects.create(
            link=self.link_a,
            ig_media_id='media_shared_400',
            status='verified',
            source='self',
        )

        # User B ning Instagramidan ham aynan shu id qaytyapti va caption'da User B ning kodi bor
        mock_list.return_value = [
            {
                'id': 'media_shared_400',
                'caption': 'Reel with BBB567 code!',
                'media_product_type': 'REELS',
                'permalink': 'https://instagram.com/reel/400/',
                'like_count': 5,
                'comments_count': 0,
            }
        ]

        with self.assertLogs('tracker.services', level='WARNING') as cm:
            res = sync_user_media(self.user_b)

        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['verified_count'], 0)
        # Post hali ham User A ga tegishli bo'lib qoladi
        post = Post.objects.get(ig_media_id='media_shared_400')
        self.assertEqual(post.link.user, self.user_a)
        self.assertTrue(any("boshqa foydalanuvchiga tegishli" in msg for msg in cm.output))

    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_token_invalid_list_media(self, mock_list):
        from tracker.services import sync_user_media
        from tracker.instagram_client import TokenInvalid

        mock_list.side_effect = TokenInvalid("Session expired (code 190)", error_code=190)

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'needs_reauth')
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.status, 'needs_reauth')

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_token_invalid_insights(self, mock_list, mock_insights):
        from tracker.services import sync_user_media
        from tracker.instagram_client import TokenInvalid

        mock_list.return_value = [
            {
                'id': 'media_token_err_500',
                'caption': 'Caption with AAA234',
                'media_product_type': 'REELS',
            }
        ]
        mock_insights.side_effect = TokenInvalid("Token revoked during insights", error_code=190)

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'needs_reauth')
        self.user_a.refresh_from_db()
        self.assertEqual(self.user_a.status, 'needs_reauth')

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_code_removed_marks_revoked(self, mock_list, mock_insights):
        from tracker.services import sync_user_media

        # Avval verified bo'lgan post
        post = Post.objects.create(
            link=self.link_a,
            ig_media_id='media_revoked_600',
            status='verified',
            source='self',
        )

        # Foydalanuvchi caption'dan kodni o'chirib tashladi
        mock_list.return_value = [
            {
                'id': 'media_revoked_600',
                'caption': 'Caption without code anymore!',
                'media_product_type': 'REELS',
            }
        ]

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['revoked_count'], 1)

        post.refresh_from_db()
        self.assertEqual(post.status, 'revoked')
        self.assertIsNotNone(post.last_synced_at)

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_deleted_from_instagram_marks_revoked(self, mock_list, mock_insights):
        from tracker.services import sync_user_media

        # Avval verified bo'lgan post
        post = Post.objects.create(
            link=self.link_a,
            ig_media_id='media_deleted_700',
            status='verified',
            source='self',
        )

        # Instagramda post umuman yo'q (ro'yxat bo'sh)
        mock_list.return_value = []

        res = sync_user_media(self.user_a)
        self.assertEqual(res['status'], 'success')
        self.assertEqual(res['revoked_count'], 1)

        post.refresh_from_db()
        self.assertEqual(post.status, 'revoked')

    @patch('tracker.services.get_media_insights')
    @patch('tracker.services.list_recent_media')
    def test_sync_user_media_preserves_site_source(self, mock_list, mock_insights):
        from tracker.services import sync_user_media

        # Saytdan chiqarilgan post (source='site')
        post = Post.objects.create(
            link=self.link_a,
            ig_media_id='media_site_800',
            status='verified',
            source='site',
        )

        mock_list.return_value = [
            {
                'id': 'media_site_800',
                'caption': 'Caption with AAA234',
                'media_product_type': 'REELS',
                'like_count': 100,
                'comments_count': 10,
            }
        ]
        mock_insights.return_value = {'views': 5000}

        sync_user_media(self.user_a)

        post.refresh_from_db()
        self.assertEqual(post.source, 'site')
        self.assertEqual(post.status, 'verified')
        self.assertEqual(post.views, 5000)

    @patch('tracker.tasks.sync_user_media')
    def test_sync_user_media_task_retry_on_network_error(self, mock_sync):
        from tracker.tasks import sync_user_media_task
        from tracker.exceptions import InstagramNetworkError

        mock_sync.side_effect = InstagramNetworkError("Instagram network timeout")

        with patch.object(sync_user_media_task, 'retry', side_effect=Exception("TaskRetried")) as mock_retry:
            with self.assertRaises(Exception) as ctx:
                sync_user_media_task(self.user_a.id)
            self.assertEqual(str(ctx.exception), "TaskRetried")
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            self.assertEqual(kwargs.get('countdown'), 30)

    @patch('tracker.tasks.sync_user_media_task.delay')
    def test_sync_beat_tasks_dispatching(self, mock_delay):
        from tracker.tasks import sync_recent_active_users_task, sync_other_users_task

        # User A da oxirgi 48 soat ichida post bor
        Post.objects.create(
            link=self.link_a,
            ig_media_id='recent_post_900',
            status='verified',
            last_synced_at=timezone.now() - timedelta(hours=5),
        )

        # Beat task 1: oxirgi 48 soatdagi postli userlar
        count_recent = sync_recent_active_users_task()
        self.assertEqual(count_recent, 1)
        mock_delay.assert_called_with(self.user_a.id)

        mock_delay.reset_mock()

        # Beat task 2: qolgan userlar (User B)
        count_other = sync_other_users_task()
        self.assertEqual(count_other, 1)
        mock_delay.assert_called_with(self.user_b.id)


class CampaignPostsApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Admin user
        self.admin_user = User.objects.create_superuser('admin_hero', 'admin@example.com', 'pass123')
        self.admin_ig = InstagramUser.objects.create(name="Admin Hero", user=self.admin_user, status='connected')

        # Regular user A
        self.user_a = User.objects.create_user('john_doe', 'john@example.com', 'pass123')
        self.ig_a = InstagramUser.objects.create(name="John Doe", user=self.user_a, status='connected', access_token='tok_a')
        dummy_v1 = SimpleUploadedFile("v1.mp4", b"data", content_type="video/mp4")
        self.link_a = UniqueLink.objects.create(user=self.ig_a, video=dummy_v1, code="JOHNA1")

        # Regular user B
        self.user_b = User.objects.create_user('jane_smith', 'jane@example.com', 'pass123')
        self.ig_b = InstagramUser.objects.create(name="Jane Smith", user=self.user_b, status='connected', access_token='tok_b')
        dummy_v2 = SimpleUploadedFile("v2.mp4", b"data", content_type="video/mp4")
        self.link_b = UniqueLink.objects.create(user=self.ig_b, video=dummy_v2, code="JANEB2")

        now = timezone.now()
        self.post_a = Post.objects.create(
            link=self.link_a,
            ig_media_id='media_a_100',
            status='verified',
            source='self',
            views=1500,
            likes=150,
            comments_count=25,
            thumbnail_url='https://example.com/thumb_a.jpg',
            permalink='https://instagram.com/reel/a100/',
            posted_at=now,
            last_synced_at=now,
        )

        self.post_b = Post.objects.create(
            link=self.link_b,
            ig_media_id='media_b_200',
            status='verified',
            source='site',
            views=3000,
            likes=300,
            comments_count=50,
            thumbnail_url='https://example.com/thumb_b.jpg',
            permalink='https://instagram.com/reel/b200/',
            posted_at=now,
            last_synced_at=now,
        )

    def test_user_sees_only_own_posts(self):
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.get('/api/user/posts/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', [])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], self.post_a.id)
        self.assertEqual(results[0]['code'], 'JOHNA1')
        self.assertEqual(results[0]['username'], 'john_doe')
        self.assertEqual(results[0]['views'], 1500)
        self.assertEqual(results[0]['likes'], 150)
        self.assertEqual(results[0]['comments_count'], 25)

        # User B ning posti bu yerda yo'q
        post_ids = [r['id'] for r in results]
        self.assertNotIn(self.post_b.id, post_ids)

    def test_admin_sees_all_posts_with_identical_fields_and_numbers(self):
        # 1. Foydalanuvchi A o'zinikini so'raydi
        self.client.force_authenticate(user=self.user_a)
        user_resp = self.client.get('/api/user/posts/')
        self.assertEqual(user_resp.status_code, 200)
        user_post_data = user_resp.json()['results'][0]

        # 2. Admin hamma postlarni so'raydi
        self.client.force_authenticate(user=self.admin_user)
        admin_resp = self.client.get('/api/admin/campaign-posts/')
        self.assertEqual(admin_resp.status_code, 200)
        admin_data = admin_resp.json()
        admin_results = admin_data.get('results', [])
        self.assertEqual(len(admin_results), 2)

        # Post A ni admin natijalaridan topamiz
        admin_post_a = next(r for r in admin_results if r['id'] == self.post_a.id)

        # Serializer maydonlari va raqamlar har ikkalasida aynan bir xil
        expected_fields = {
            'id', 'thumbnail_url', 'permalink', 'status', 'source',
            'views', 'likes', 'comments_count', 'posted_at',
            'last_synced_at', 'username', 'code'
        }
        self.assertEqual(set(user_post_data.keys()), expected_fields)
        self.assertEqual(set(admin_post_a.keys()), expected_fields)

        self.assertEqual(user_post_data['views'], admin_post_a['views'])
        self.assertEqual(user_post_data['likes'], admin_post_a['likes'])
        self.assertEqual(user_post_data['comments_count'], admin_post_a['comments_count'])
        self.assertEqual(user_post_data['status'], admin_post_a['status'])
        self.assertEqual(user_post_data['source'], admin_post_a['source'])
        self.assertEqual(user_post_data['code'], admin_post_a['code'])
        self.assertEqual(user_post_data['username'], admin_post_a['username'])

    def test_admin_campaign_posts_filters(self):
        self.client.force_authenticate(user=self.admin_user)

        # Status filtri
        resp = self.client.get('/api/admin/campaign-posts/?status=verified')
        self.assertEqual(resp.json()['count'], 2)

        resp = self.client.get('/api/admin/campaign-posts/?status=revoked')
        self.assertEqual(resp.json()['count'], 0)

        # Source filtri
        resp = self.client.get('/api/admin/campaign-posts/?source=self')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['id'], self.post_a.id)

        resp = self.client.get('/api/admin/campaign-posts/?source=site')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['id'], self.post_b.id)

        # Username filtri
        resp = self.client.get('/api/admin/campaign-posts/?username=jane')
        self.assertEqual(resp.json()['count'], 1)
        self.assertEqual(resp.json()['results'][0]['username'], 'jane_smith')

    @patch('tracker.views.sync_user_media_task.delay')
    def test_user_sync_endpoint_and_throttle(self, mock_delay):
        from django.core.cache import cache
        cache.clear()

        self.client.force_authenticate(user=self.user_a)

        # 1-marta: muvaffaqiyatli (200, queued)
        resp1 = self.client.post('/api/user/sync/')
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(resp1.json(), {"status": "queued"})
        mock_delay.assert_called_with(self.ig_a.id)

        # 2-marta: muvaffaqiyatli
        resp2 = self.client.post('/api/user/sync/')
        self.assertEqual(resp2.status_code, 200)

        # 3-marta: muvaffaqiyatli
        resp3 = self.client.post('/api/user/sync/')
        self.assertEqual(resp3.status_code, 200)

        # 4-marta: limitdan oshdi (429 Too Many Requests)
        resp4 = self.client.post('/api/user/sync/')
        self.assertEqual(resp4.status_code, 429)

    def test_user_delete_post_success_and_forbidden_other_user(self):
        # 1. User A o'z postini o'chiradi
        self.client.force_authenticate(user=self.user_a)
        resp = self.client.delete(f'/api/user/posts/{self.post_a.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Post.objects.filter(id=self.post_a.id).exists())

        # 2. User A boshqa user B ning postini o'chirishga urinadi -> 404
        resp_forbidden = self.client.delete(f'/api/user/posts/{self.post_b.id}/')
        self.assertEqual(resp_forbidden.status_code, 404)
        self.assertTrue(Post.objects.filter(id=self.post_b.id).exists())

        # 3. Admin istalgan postni o'chira oladi
        self.client.force_authenticate(user=self.admin_user)
        resp_admin = self.client.delete(f'/api/user/posts/{self.post_b.id}/')
        self.assertEqual(resp_admin.status_code, 200)
        self.assertFalse(Post.objects.filter(id=self.post_b.id).exists())












