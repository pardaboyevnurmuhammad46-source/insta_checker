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

    def test_instagram_auth_url_public(self):
        # Avtorizatsiyadan o'tmagan mijoz ham auth_url olishi mumkin
        resp = self.client.get("/api/auth/instagram/url/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("auth_url", data)
        self.assertIn("link_token", data)
        self.assertIn("instagram.com/oauth/authorize", data['auth_url'])

    @patch('tracker.views.publish_reels_task.delay')
    @patch('tracker.views.complete_instagram_oauth')
    def test_callback_registers_new_user_with_jwt(self, mock_complete, mock_task_delay):
        temp_ig = InstagramUser.objects.create(name="new_ig_celebrity", status="pending")
        temp_link = UniqueLink.objects.create(user=temp_ig, video=self.default_video)

        mock_complete.return_value = (temp_ig, temp_link)
        resp = self.client.get(f"/oauth/callback/?code=secret_code&state={temp_link.token}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("Muvaffaqiyatli Ulandi!", resp.content.decode())
        self.assertIn("app/video", resp.content.decode())

        temp_ig.refresh_from_db()
        self.assertIsNotNone(temp_ig.user)
        self.assertEqual(temp_ig.user.username, "new_ig_celebrity")

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

    def test_user_connect_instagram_without_token_returns_auth_url(self):
        self.client.force_authenticate(user=self.user1)
        resp = self.client.post("/api/user/connect-instagram/", {})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('auth_url', data)
        self.assertIn('instagram.com/oauth/authorize', data['auth_url'])

    def test_user_disconnect_instagram(self):
        self.client.force_authenticate(user=self.user1)
        self.ig_user1.status = 'connected'
        self.ig_user1.access_token = 'token_to_disconnect'
        self.ig_user1.ig_user_id = '1784100'
        self.ig_user1.save()

        resp = self.client.post("/api/user/disconnect-instagram/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'pending')

        self.ig_user1.refresh_from_db()
        self.assertEqual(self.ig_user1.status, 'pending')
        self.assertIsNone(self.ig_user1.access_token)
        self.assertIsNone(self.ig_user1.ig_user_id)

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
        
        # 0-24 soat -> 5 daqiqa
        self.post.posted_at = now - timedelta(hours=2)
        next_check = calculate_next_check(self.post, now=now)
        self.assertEqual(next_check, now + timedelta(minutes=5))
        
        # 1-7 kun -> 10 daqiqa
        self.post.posted_at = now - timedelta(days=2)
        next_check = calculate_next_check(self.post, now=now)
        self.assertEqual(next_check, now + timedelta(minutes=10))

        # Milestone 80% logic (500 * 0.8 = 400) -> 5 daqiqa
        self.post.posted_at = now - timedelta(days=10) # 7 kundan eski, lekin marraga yaqin
        self.post.views = 410
        next_check = calculate_next_check(self.post, now=now)
        self.assertEqual(next_check, now + timedelta(minutes=5))


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
