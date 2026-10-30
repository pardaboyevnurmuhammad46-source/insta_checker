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



class Phase7EnhancementsTestCase(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from tracker.services import validate_video_orientation
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
        from django.core.cache import cache
        cache.clear()

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

    @patch('tracker.tasks.check_post_metrics_task.delay')
    def test_me_post_history_auto_refresh_every_5m(self, mock_task):
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
        # 5 daqiqadan oshgani uchun check_post_metrics_task asinxron navbatga qo'yilishi kerak
        mock_task.assert_called_once_with(post.id)


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
            account_id=self.user.id,
        )
        mock_upload_binary.assert_called_once()
        mock_wait.assert_called_once_with("resumable_container_123", "secret_token_resumable", account_id=self.user.id)
        mock_publish.assert_called_once_with("ig_resumable_123", "resumable_container_123", "secret_token_resumable", account_id=self.user.id)
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
        from tracker.video_utils import needs_aspect_ratio_conversion
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
        from tracker.video_utils import validate_video_duration
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
        from tracker.video_utils import get_video_info
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
        from tracker.video_utils import convert_video_to_9_16
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
        from tracker.tasks import process_video_task
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
        from tracker.tasks import process_video_task
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
        from tracker.tasks import process_video_task
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
        from tracker.tasks import process_video_task
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
        from tracker.tasks import process_video_task
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
