import json
import time
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from tracker.models import InstagramUser, UniqueLink, Video, Post, Notification
from tracker.rate_limiter import rate_limiter
from tracker.services import (
    check_content_publishing_limit,
    get_user_post_cooldown,
    publish_reels_for_link,
    InstagramPublishError,
)
from tracker.tasks import publish_reels_task, check_post_metrics_task
from tracker.instagram_errors import get_redis_client, is_retryable_rate_limit, InstagramErrorType
from tracker.exceptions import InstagramRateLimitError


class PublishingLimitsAndCooldownTests(TestCase):
    def setUp(self):
        rate_limiter.reset()
        self.r = get_redis_client()
        try:
            self.r.delete("lock:celery_beat:check_all_due_posts")
        except Exception:
            pass

        self.user = User.objects.create_user(username="test_creator", password="password123")
        self.ig_user = InstagramUser.objects.create(
            user=self.user,
            ig_user_id="ig_12345678",
            name="Test Creator",
            access_token="valid_token_abc123",
            status="connected",
        )
        self.video = Video.objects.create(
            title="Aksiya Reels",
            status="ready",
            is_active=True,
            is_default=True,
            owner=self.ig_user,
            file="videos/test_reels.mp4",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        rate_limiter.reset(self.ig_user.id)
        if self.r:
            try:
                self.r.delete(
                    f"ig:publishing_limit:{self.ig_user.id}",
                    f"lock:user_publish:{self.ig_user.id}",
                    f"{{ig_rate}}:acc:{self.ig_user.id}:paused",
                )
            except Exception:
                pass

    # 1. Limit tugaganda post boshlanmasligi tekshiruvi
    @patch('tracker.services.get_instagram_client')
    def test_limit_reached_blocks_publishing(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_content_publishing_limit.return_value = {
            "quota_usage": 25,
            "quota_total": 25,
            "quota_duration": 86400,
        }
        mock_get_client.return_value = mock_client

        allowed, reason, data = check_content_publishing_limit(self.ig_user)
        self.assertFalse(allowed)
        self.assertIn("Instagram kunlik post limiti tugadi", reason)
        self.assertIn("25/25", reason)

        # API orqali chaqirilganda 429 xatolik qaytishi va post yaratilmasligi
        resp = self.client.post("/api/user/publish/")
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Instagram kunlik post limiti tugadi", resp.data["error"])
        self.assertFalse(Post.objects.filter(link__user=self.ig_user, status='queued').exists())

    # 2. Instagram limit so'rovi xato bersa, post to'xtamasligi
    @patch('tracker.services.get_instagram_client')
    def test_instagram_error_does_not_block_publishing(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_content_publishing_limit.side_effect = Exception("Meta API Server Error 500")
        mock_get_client.return_value = mock_client

        allowed, reason, data = check_content_publishing_limit(self.ig_user)
        self.assertTrue(allowed)
        self.assertIsNone(reason)

    # 3. Cooldown ichida ikkinchi post navbatga tushishi va Celery countdown orqali rejalashtirilishi
    @override_settings(POST_COOLDOWN_SECONDS=420)
    @patch('tracker.views.publish_reels_task.apply_async')
    def test_cooldown_delays_second_post_via_celery_countdown(self, mock_apply_async):
        # 1-post: 60 soniya oldin muvaffaqiyatli published bo'lgan
        link1 = UniqueLink.objects.create(user=self.ig_user, video=self.video, status='posted')
        Post.objects.create(
            link=link1,
            status='published',
            posted_at=timezone.now() - timedelta(seconds=60),
            ig_media_id="media_111",
        )

        is_active, rem_sec, next_time, formatted_time = get_user_post_cooldown(self.ig_user)
        self.assertTrue(is_active)
        self.assertGreater(rem_sec, 300)
        self.assertLessEqual(rem_sec, 360)
        self.assertIsNotNone(formatted_time)

        # Foydalanuvchi ikkinchi postni joylamoqchi bo'ladi: rad etilmaydi!
        with patch('tracker.views.check_content_publishing_limit', return_value=(True, None, None)):
            resp = self.client.post("/api/user/publish/")

        self.assertEqual(resp.status_code, 202)
        self.assertTrue(resp.data["cooldown_active"])
        self.assertIn("avtomatik joylanadi", resp.data["message"])
        self.assertEqual(resp.data["next_post_time"], formatted_time)

        # Celery apply_async countdown parametri bilan chaqirilgan bo'lishi kerak
        mock_apply_async.assert_called_once()
        _, kwargs = mock_apply_async.call_args
        self.assertIn("countdown", kwargs)
        self.assertGreaterEqual(kwargs["countdown"], 300)

    # 4. Ikki parallel so'rov cooldown'ni aylanib o'tmasligi (Redis qulfi)
    def test_two_concurrent_requests_cannot_bypass_cooldown(self):
        # Qulf sun'iy band qilinadi
        if self.r:
            self.r.set(f"lock:user_publish:{self.ig_user.id}", "1", ex=10)

        with patch('tracker.views.check_content_publishing_limit', return_value=(True, None, None)):
            resp = self.client.post("/api/user/publish/")

        self.assertEqual(resp.status_code, 409)
        self.assertIn("Jarayonda bo'lgan so'rov mavjud", resp.data["error"])

    # 5. Sarlavha foizi 80 dan oshsa akkaunt to'xtatilishi (X-Business-Use-Case-Usage)
    @override_settings(INSTAGRAM_USAGE_SLOWDOWN_PERCENT=80)
    def test_usage_header_exceeding_80_percent_pauses_user(self):
        headers = {
            'X-Business-Use-Case-Usage': json.dumps({
                "ig_account_1": [
                    {
                        "type": "instagram",
                        "call_count": 85,
                        "total_time": 60,
                        "total_cputime": 40,
                        "estimated_time_to_regain_access": 15,
                    }
                ]
            })
        }

        is_paused, max_pct, pause_sec = rate_limiter.parse_and_apply_business_usage(headers, account_id=self.ig_user.id)
        self.assertTrue(is_paused)
        self.assertEqual(max_pct, 85)
        self.assertEqual(pause_sec, 900)  # 15 daqiqa * 60 = 900 soniya

        # Endi rate_limiter.acquire akkauntni o'tkazib yuboradi
        allowed, retry_after, reason = rate_limiter.acquire(account_id=self.ig_user.id)
        self.assertFalse(allowed)
        self.assertEqual(reason, 'account_usage_slowdown')
        self.assertGreater(retry_after, 800)

    # 6. Subcode 2207042 (24 soatlik limit) qayta urinilmasligi va Notification yaratilishi
    @patch('tracker.tasks.publish_reels_for_link')
    def test_subcode_2207042_is_not_retried_and_notifies_user(self, mock_publish):
        link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status='pending')
        post = Post.objects.create(link=link, status='queued')

        err = InstagramPublishError("Daily limit reached [code=24, subcode=2207042]")
        err.error_code = 24
        err.error_subcode = 2207042
        mock_publish.side_effect = err

        result = publish_reels_task.apply(args=[link.id]).result
        self.assertEqual(result.get("status"), "failed")

        # Post failed bo'lishi va foydalanuvchiga bildirishnoma yaratilishi kerak
        post.refresh_from_db()
        self.assertEqual(post.status, 'failed')
        self.assertIn("24 soatlik limit", post.error)
        self.assertTrue(Notification.objects.filter(user=self.ig_user, kind='system').exists())

    # 7. Subcode 1390008 qisqa muddatli throttle qayta urinishga loyiqligi
    def test_subcode_1390008_classification(self):
        self.assertTrue(is_retryable_rate_limit(error_code=4, error_subcode=1390008))
        self.assertFalse(is_retryable_rate_limit(error_code=24, error_subcode=2207042))
        self.assertFalse(is_retryable_rate_limit(error_code=4, error_subcode=1349210))
        self.assertFalse(is_retryable_rate_limit(error_code=613, error_subcode=None))

    # 8. Yagona akkaunt ID (InstagramUser.id) bo'yicha pauza uyg'unligi
    @patch('tracker.tasks.update_post_metrics')
    def test_unified_account_id_pause_consistency(self, mock_update):
        link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status='posted')
        post = Post.objects.create(link=link, status='published', ig_media_id="media_pause_test")

        # Rate limit xatosi (kod 4) simulate qilinadi
        err = InstagramRateLimitError("Rate limit exceeded")
        err.error_code = 4
        err.error_subcode = None
        mock_update.side_effect = err

        # check_post_metrics_task ishga tushadi (production yo'li)
        res = check_post_metrics_task.apply(args=[post.id]).result
        self.assertTrue(res.get("account_paused"))

        # Endi aynan shu InstagramUser.id bilan rate_limiter.acquire tekshiriladi
        allowed, retry_after, reason = rate_limiter.acquire(account_id=self.ig_user.id)
        self.assertFalse(allowed)
        self.assertEqual(reason, 'account_usage_slowdown')
        self.assertGreater(retry_after, 500)

    # 9. Akkaunt to'xtatilgan bo'lsa publish so'rovi Instagramga ketmasligi va task qayta rejalashtirilishi
    @patch('tracker.services.get_instagram_client')
    def test_publish_blocked_when_account_paused_and_task_retried(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Akkaunt pauza qilinadi
        if self.r:
            self.r.set(f"{{ig_rate}}:acc:{self.ig_user.id}:paused", "85", ex=300)

        link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status='pending')
        post = Post.objects.create(link=link, status='queued')

        # publish_reels_task chaqiriladi
        with patch.object(publish_reels_task, 'retry', side_effect=Exception("Task retried with countdown")) as mock_retry:
            with self.assertRaises(Exception) as ctx:
                publish_reels_task(link.id)
            self.assertIn("Task retried with countdown", str(ctx.exception))
            mock_retry.assert_called_once()
            _, kwargs = mock_retry.call_args
            self.assertGreaterEqual(kwargs.get("countdown", 0), 200)

        # Instagram API ga biron so'rov ketmagan bo'lishi kerak
        mock_client.create_reels_container_resumable.assert_not_called()
        mock_client.publish_container.assert_not_called()

    # 10. Polling so'rovlari progressiv kengayishi (delays=[2, 3, 5, 8, 10])
    @patch('tracker.instagram_client.time.sleep')
    @patch('tracker.instagram_client.RealInstagramClient.check_container_status')
    def test_wait_for_container_ready_progressive_delays(self, mock_check, mock_sleep):
        from tracker.instagram_client import RealInstagramClient
        client = RealInstagramClient()

        # 4 marta IN_PROGRESS, 5-marta FINISHED
        mock_check.side_effect = [
            {"status_code": "IN_PROGRESS"},
            {"status_code": "IN_PROGRESS"},
            {"status_code": "IN_PROGRESS"},
            {"status_code": "IN_PROGRESS"},
            {"status_code": "FINISHED"},
        ]

        result = client.wait_for_container_ready("container_test_123", "token_123", max_attempts=10, delay=2)
        self.assertTrue(result)
        # 4 marta sleep chaqirilgan, progressiv qiymatlar: 2, 3, 5, 8
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        self.assertEqual(sleep_calls, [2, 3, 5, 8])

    # 11. Kunlik limit to'lganda link 'pending' qolishi va ertasi kuni qayta urinish mumkinligi
    @patch('tracker.services.get_instagram_client')
    def test_daily_limit_keeps_link_pending_for_next_day_retry(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.get_content_publishing_limit.return_value = {
            "quota_usage": 100,
            "quota_total": 100,
            "quota_duration": 86400,
        }
        mock_get_client.return_value = mock_client

        link = UniqueLink.objects.create(user=self.ig_user, video=self.video, status='pending')
        post = Post.objects.create(link=link, status='queued')

        with self.assertRaises(InstagramPublishError):
            publish_reels_for_link(link.id)

        # Post failed bo'ladi, lekin link pending holatda qoladi
        post.refresh_from_db()
        link.refresh_from_db()
        self.assertEqual(post.status, 'failed')
        self.assertEqual(link.status, 'pending')

