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

    @override_settings(INSTAGRAM_APP_SECRET=None)
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
