import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.conf import settings
from django.db import IntegrityError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.contrib.admin.sites import AdminSite

from tracker.models import InstagramUser, UniqueLink, Post, Prize
from tracker.admin import UniqueLinkAdmin
from tracker.services import (
    InstagramOAuthError,
    build_instagram_auth_url,
    complete_instagram_oauth,
)


class SettingsEnvTestCase(TestCase):
    def test_settings_loaded_from_env(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertIn('default', settings.DATABASES)


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
        self.assertIn("https://api.instagram.com/oauth/authorize", url)
        self.assertIn(f"state={self.link.token}", url)
        self.assertIn("response_type=code", url)

    @override_settings(INSTAGRAM_APP_ID='test_app_id', INSTAGRAM_APP_SECRET='test_secret')
    def test_redirect_to_instagram_success(self):
        response = self.client.get(f"/link/{self.link.token}/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("api.instagram.com/oauth/authorize", response.headers['Location'])

        self.link.refresh_from_db()
        self.assertEqual(self.link.status, 'opened')

    def test_redirect_expired_link(self):
        self.link.expires_at = timezone.now() - timedelta(days=1)
        self.link.save()

        response = self.client.get(f"/link/{self.link.token}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("muddati tugagan", response.json().get('error', ''))

    def test_redirect_invalid_status(self):
        self.link.status = 'posted'
        self.link.save()

        response = self.client.get(f"/link/{self.link.token}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("amal bajarib bo'lmaydi", response.json().get('error', ''))

    @patch('tracker.services.requests.get')
    @patch('tracker.services.requests.post')
    def test_complete_instagram_oauth_success(self, mock_post, mock_get):
        # Mock short-lived token response
        mock_post_resp = MagicMock()
        mock_post_resp.status_code = 200
        mock_post_resp.json.return_value = {
            'access_token': 'short_token_123',
            'user_id': '1784140001',
        }
        mock_post.return_value = mock_post_resp

        # Mock long-lived token response
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

    @patch('tracker.views.complete_instagram_oauth')
    def test_callback_endpoint_success(self, mock_complete):
        mock_user = self.user
        mock_user.status = 'connected'
        mock_user.ig_user_id = '178414999'
        mock_complete.return_value = (mock_user, self.link)

        response = self.client.get(f"/oauth/callback/?code=test_code&state={self.link.token}")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('user_status'), 'connected')
        self.assertEqual(data.get('ig_user_id'), '178414999')
