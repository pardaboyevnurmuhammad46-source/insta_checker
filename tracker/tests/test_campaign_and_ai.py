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
            'last_synced_at', 'last_checked_at', 'next_check_at', 'username', 'code',
            'ai_verified', 'ai_confidence', 'ai_detection_source',
            'transcript', 'ai_explanation', 'points_awarded',
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


class AIVerificationTestCase(APITestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(name="AI Test User", status="connected")
        self.link = UniqueLink.objects.create(user=self.user, code="WIN999")
        self.post = Post.objects.create(link=self.link, status="published", caption="Homiy aksiyasi: #WIN999 bilan qatnashing!")

    def test_verify_video_advertisement_caption(self):
        from tracker.ai_verifier import verify_video_advertisement
        result = verify_video_advertisement(
            caption="Homiy aksiyasi: #WIN999 bilan qatnashing!",
            expected_code="WIN999",
        )
        self.assertTrue(result['is_verified'])
        self.assertEqual(result['detection_source'], 'caption')
        self.assertGreater(result['points'], 0)

    def test_verify_video_advertisement_negative(self):
        from tracker.ai_verifier import verify_video_advertisement
        result = verify_video_advertisement(
            caption="Bugun ob-havo juda yaxshi, do'stlar bilan aylanyapmiz.",
            expected_code="WIN999",
        )
        self.assertFalse(result['is_verified'])
        self.assertEqual(result['detection_source'], 'none')
        self.assertEqual(result['points'], 0)

    def test_process_and_verify_post_ai(self):
        from tracker.ai_verifier import process_and_verify_post_ai
        process_and_verify_post_ai(self.post)
        self.post.refresh_from_db()
        self.assertTrue(self.post.ai_verified)
        self.assertGreater(self.post.points_awarded, 0)
        self.assertTrue(Notification.objects.filter(user=self.user, kind='ai_verified').exists())

    def test_celery_beat_5_minute_schedule(self):
        schedule = settings.CELERY_BEAT_SCHEDULE
        self.assertEqual(schedule['check-all-due-posts-metrics']['schedule'], 300.0)
        self.assertEqual(schedule['sync-recent-active-users-media']['schedule'], 300.0)

    def test_admin_campaign_config_api(self):
        admin = User.objects.create_superuser(username="admin_ai", password="123")
        self.client.force_authenticate(user=admin)

        # 1. GET
        get_res = self.client.get('/api/admin/campaign-config/')
        self.assertEqual(get_res.status_code, 200)
        self.assertIn('topic', get_res.json())

        # 2. PUT / PATCH
        patch_res = self.client.patch('/api/admin/campaign-config/', {
            'topic': 'Yangi Yil Aksiya Tanlovi',
            'required_keywords': 'yangi yil, chegirma, aksiya',
            'points_reward': 150,
        })
        self.assertEqual(patch_res.status_code, 200)
        self.assertEqual(patch_res.json()['topic'], 'Yangi Yil Aksiya Tanlovi')
        self.assertEqual(patch_res.json()['points_reward'], 150)

    def test_admin_reverify_post_ai_api(self):
        admin = User.objects.create_superuser(username="admin_ai2", password="123")
        self.client.force_authenticate(user=admin)

        res = self.client.post(f'/api/admin/posts/{self.post.id}/re-verify-ai/')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['ai_verified'])
        self.assertGreater(res.json()['points_awarded'], 0)

    def test_verify_without_expected_code_rejected(self):
        from tracker.ai_verifier import verify_video_advertisement
        # Umumiy aksiya/reklama so'zlari bor, lekin unikal kod (WIN999) yo'q
        result = verify_video_advertisement(
            caption="Ushbu videoda ajoyib aksiya va homiy reklama bor, qatnashing!",
            expected_code="WIN999",
        )
        self.assertFalse(result['is_verified'])
        self.assertEqual(result['detection_source'], 'none')
        self.assertIn("topilmadi", result['explanation'])

    def test_prizes_not_awarded_for_rejected_or_revoked_posts(self):
        from tracker.services import check_and_award_prizes
        for invalid_status in ['rejected', 'revoked', 'deleted', 'failed']:
            lk = UniqueLink.objects.create(user=self.user)
            p = Post.objects.create(
                link=lk,
                status=invalid_status,
                views=5000,
            )
            awarded = check_and_award_prizes(p)
            self.assertEqual(len(awarded), 0)
            self.assertEqual(Prize.objects.filter(post=p).count(), 0)

    def test_admin_retry_limit_capped_at_10(self):
        admin = User.objects.create_superuser(username="admin_retry_test", password="123")
        self.client.force_authenticate(user=admin)
        lk = UniqueLink.objects.create(user=self.user)
        post = Post.objects.create(link=lk, status='failed', retry_count=10)
        res = self.client.post(f'/api/posts/{post.id}/retry/')
        self.assertEqual(res.status_code, 400)
        self.assertIn("10 marta", res.json()['error'])

    def test_webhook_invalid_signature_rejected(self):
        payload = {"object": "instagram", "entry": []}
        res = self.client.post(
            '/api/instagram/webhook/',
            payload,
            content_type='application/json',
            HTTP_X_HUB_SIGNATURE_256='sha256=invalid_signature_hash'
        )
        self.assertEqual(res.status_code, 403)

    def test_webhook_missing_signature_rejected(self):
        payload = {"object": "instagram", "entry": []}
        res = self.client.post(
            '/api/instagram/webhook/',
            payload,
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 403)
