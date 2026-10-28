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
