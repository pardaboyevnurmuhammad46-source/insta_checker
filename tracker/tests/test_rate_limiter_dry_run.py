import requests
from django.core.cache import cache
import concurrent.futures
import os
import io
import struct
import base64
import hashlib
import hmac
import json
import uuid
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.contrib.admin.sites import AdminSite
from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from tracker.models import (
    InstagramUser,
    UniqueLink,
    Post,
    Prize,
    DataDeletionRequest,
    Video,
    PostStat,
    Notification,
    CampaignConfig,
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
    InstagramRateLimitError,
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


def create_mock_signed_request(payload: dict, secret: str) -> str:
    payload_json = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8').rstrip('=')
    sig = hmac.new(secret.encode('utf-8'), payload_b64.encode('utf-8'), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('utf-8').rstrip('=')
    return f"{sig_b64}.{payload_b64}"



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
