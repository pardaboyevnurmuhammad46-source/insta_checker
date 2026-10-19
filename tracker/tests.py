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
        expected_url = f"http://127.0.0.1:8000/link/{self.link.token}/"
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

        # 0 to 24 hours -> 15 minutes
        self.post.posted_at = base_now - timedelta(hours=2)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(minutes=15))

        # 2 days -> 1 hour
        self.post.posted_at = base_now - timedelta(days=2)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(hours=1))

        # 5 days -> 4 hours
        self.post.posted_at = base_now - timedelta(days=5)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(hours=4))

        # 10 days -> 12 hours
        self.post.posted_at = base_now - timedelta(days=10)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(hours=12))

        # 20 days -> 24 hours
        self.post.posted_at = base_now - timedelta(days=20)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(days=1))

        # 35 days -> checks daily to verify post still exists and track milestones
        self.post.posted_at = base_now - timedelta(days=35)
        next_check = calculate_next_check(self.post, now=base_now)
        self.assertEqual(next_check, base_now + timedelta(days=1))


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
        notif = Notification.objects.create(
            user=self.ig_user,
            kind='prize',
            message="1000 views to'plandi!",
            related_prize=prize,
        )
        self.assertFalse(notif.is_read)
        self.assertEqual(self.ig_user.notifications.count(), 1)


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

