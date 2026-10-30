from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from tracker.models import InstagramUser, UniqueLink, Post, PostStat, Prize, Video
from tracker.tasks import check_all_due_posts_task, check_users_chunk_task
from tracker.exceptions import (
    InstagramMetricsError,
    InstagramRateLimitError,
    TokenInvalid,
)
from tracker.instagram_errors import get_redis_client, InstagramErrorType


class ChunksAndTasksTestCase(TestCase):
    def setUp(self):
        self.video = Video.objects.create(title="Test Video", is_default=True)
        self.now = timezone.now()

        # 3 ta test foydalanuvchisi va ularning postlari
        self.users = []
        self.posts = []
        for i in range(1, 4):
            u = InstagramUser.objects.create(
                name=f"User {i}",
                ig_user_id=f"178414000{i}",
                access_token=f"IGAATokenUser_{i}_abc123",
                status="connected",
            )
            self.users.append(u)
            link = UniqueLink.objects.create(user=u, video=self.video, status="posted")
            post = Post.objects.create(
                link=link,
                ig_media_id=f"media_chunk_{i}",
                status="published",
                views=100,
                likes=10,
                comments_count=2,
                next_check_at=self.now - timedelta(minutes=5),
            )
            self.posts.append(post)

    @override_settings(CHECK_BATCH_SIZE=100, CHECK_USER_CHUNK_SIZE=2)
    @patch('tracker.tasks.group')
    def test_check_all_due_posts_chunks_users(self, mock_group):
        """check_all_due_posts_task userlarni 2 tadan chunk qilib Celery group orqali yuborishi va tarkibini to'g'ri taqsimlashi kerak."""
        mock_job = MagicMock()
        mock_group.return_value = mock_job

        res = check_all_due_posts_task()
        self.assertEqual(res, 3)  # 3 ta post topildi
        mock_group.assert_called_once()
        mock_job.apply_async.assert_called_once()

        # group ga uzatilgan signaturalar va ularning chunk tarkibini tekshiramiz:
        generator_or_list = mock_group.call_args[0][0]
        signatures = list(generator_or_list)
        self.assertEqual(len(signatures), 2)  # 3 ta user / chunk_size 2 => 2 ta chunk

        # 1-chunk: [User 1, User 2]
        chunk1_user_ids = signatures[0].args[0]
        self.assertEqual(chunk1_user_ids, [self.users[0].id, self.users[1].id])

        # 2-chunk: [User 3]
        chunk2_user_ids = signatures[1].args[0]
        self.assertEqual(chunk2_user_ids, [self.users[2].id])

    def test_check_all_due_posts_redis_lock(self):
        """Redis lock mavjud bo'lganda yangi dispatcher ishga tushmasligi kerak."""
        r = get_redis_client()
        lock_key = "lock:celery_beat:check_all_due_posts"
        r.set(lock_key, "running", ex=60)

        try:
            res = check_all_due_posts_task()
            self.assertEqual(res, 0)
        finally:
            r.delete(lock_key)

    @patch('tracker.tasks.get_instagram_client')
    def test_chunk_task_single_user_error_does_not_stop_others(self, mock_get_client):
        """
        Bitta user xatosi (token yaroqsiz) boshqa userlarning muvaffaqiyatli tekshirilishiga
        va sovrin olishiga to'sqinlik qilmasligi kerak.
        """
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        def fake_list(access_token, limit=25, return_paging_info=False):
            if "User_1" in access_token:
                raise TokenInvalid("Token expired", error_code=190)
            elif "User_2" in access_token:
                return ([{'id': self.posts[1].ig_media_id, 'like_count': 50, 'comments_count': 12}], True)
            elif "User_3" in access_token:
                raise InstagramRateLimitError("Rate limit reached", status_code=429)
            return ([], True)

        mock_client.list_recent_media.side_effect = fake_list
        mock_client.get_media_insights.return_value = {'views': 550}

        user_ids = [u.id for u in self.users]
        res = check_users_chunk_task(user_ids)

        self.assertEqual(res['processed_users'], 3)

        # 1. User 1: needs_reauth bo'lishi va postda xato yozilishi kerak
        self.users[0].refresh_from_db()
        self.posts[0].refresh_from_db()
        self.assertEqual(self.users[0].status, 'needs_reauth')
        self.assertIn("needs_reauth", self.posts[0].error)

        # 2. User 2: muvaffaqiyatli yangilangan, views=550 va Prize(500) yaratilgan bo'lishi kerak
        self.posts[1].refresh_from_db()
        self.assertEqual(self.posts[1].views, 550)
        self.assertTrue(Prize.objects.filter(post=self.posts[1], milestone=500).exists())
        self.assertTrue(PostStat.objects.filter(post=self.posts[1], views=550).exists())

        # 3. User 3: rate limit tufayli next_check_at qayta surilgan bo'lishi kerak
        self.posts[2].refresh_from_db()
        self.assertGreater(self.posts[2].next_check_at, self.now)

    @patch('tracker.tasks.get_instagram_client')
    @patch('tracker.tasks.rate_limiter.acquire')
    def test_chunk_task_rate_limiter_skips_without_sleep(self, mock_acquire, mock_get_client):
        """Rate limiter ruxsat bermasa, task sleep qilmaydi, userni keyingi vaqtga suradi."""
        # User 1 ruxsat yo'q (15 soniya kutish kerak), User 2 ga ruxsat bor
        def fake_acquire(account_id=None, requests_count=1, **kwargs):
            if account_id == self.users[0].id:
                return (False, 15.0, 'account_rate_limit')
            return (True, 0.0, 'ok')

        mock_acquire.side_effect = fake_acquire

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.list_recent_media.return_value = ([
            {'id': self.posts[1].ig_media_id, 'like_count': 20, 'comments_count': 4}
        ], True)
        mock_client.get_media_insights.return_value = {'views': 200}

        user_ids = [self.users[0].id, self.users[1].id]
        res = check_users_chunk_task(user_ids)

        # User 1 post tekshirilmagan, lekin next_check_at surilgan:
        self.posts[0].refresh_from_db()
        self.assertGreaterEqual(self.posts[0].next_check_at, self.now + timedelta(seconds=14))

        # User 2 post muvaffaqiyatli tekshirilgan:
        self.posts[1].refresh_from_db()
        self.assertEqual(self.posts[1].views, 200)

    @patch('tracker.tasks.group')
    def test_worker_death_claim_mechanism(self, mock_group):
        """Worker chunk o'rtasida o'lsa (yoki umuman yetib bormasa), postlar 2 soatlik claim sababli keyinroq qayta olinishini isbotlovchi test."""
        # 1. Dispatcher ishga tushadi
        res = check_all_due_posts_task()
        self.assertEqual(res, 3)

        # 2. Barcha postlarning next_check_at vaqti taxminan 2 soatga surilganini tekshiramiz (claim)
        for p in self.posts:
            p.refresh_from_db()
            self.assertGreaterEqual(p.next_check_at, self.now + timedelta(hours=1, minutes=59))

        # 3. Vaqt 2 soat oldinga surilsa, bu postlar qayta olinishini ko'rsatamiz
        future_now = self.now + timedelta(hours=2, minutes=5)
        with patch('tracker.tasks.timezone.now', return_value=future_now):
            res2 = check_all_due_posts_task()
            self.assertEqual(res2, 3) # O'sha postlar yana topildi, chunk qayta ishga tushirildi

    @patch('tracker.tasks.get_instagram_client')
    def test_phase_c_me_media_and_insights_flow(self, mock_get_client):
        """C-bosqich: /me/media orqali like, comment va insights orqali views to'g'ri olinishi."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # /me/media 1 ta so'rovda like va commentlarni qaytaradi:
        mock_client.list_recent_media.return_value = ([
            {
                'id': self.posts[0].ig_media_id,
                'like_count': 85,
                'comments_count': 16,
            }
        ], True)

        # /{media-id}/insights views ni qaytaradi (800 views -> 500 sovrini berilishi kerak):
        mock_client.get_media_insights.return_value = {'views': 800}

        res = check_users_chunk_task([self.users[0].id])
        self.assertEqual(res['processed_users'], 1)

        self.posts[0].refresh_from_db()
        self.assertEqual(self.posts[0].likes, 85)
        self.assertEqual(self.posts[0].comments_count, 16)
        self.assertEqual(self.posts[0].views, 800)
        self.assertTrue(Prize.objects.filter(post=self.posts[0], milestone=500).exists())

    @patch('tracker.tasks.get_instagram_client')
    def test_phase_c_media_deleted_when_pagination_completed(self, mock_get_client):
        """C-bosqich: Barcha sahifalar to'liq o'qilganda media topilmasa, post o'chirilgan (deleted) deb belgilanishi."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Userning boshqa postlari bor, lekin self.posts[0] ro'yxatda yo'q, pagination tugagan (True):
        mock_client.list_recent_media.return_value = ([
            {'id': 'other_media_999', 'like_count': 10, 'comments_count': 1}
        ], True)

        check_users_chunk_task([self.users[0].id])

        self.posts[0].refresh_from_db()
        self.assertEqual(self.posts[0].status, 'deleted')
        self.assertIsNotNone(self.posts[0].deleted_detected_at)
        self.assertIn("o'chirilgan", self.posts[0].error)

    @patch('tracker.tasks.fetch_post_metrics_from_instagram')
    @patch('tracker.tasks.get_instagram_client')
    def test_phase_c_media_not_deleted_when_pagination_incomplete(self, mock_get_client, mock_fetch):
        """C-bosqich: Pagination tugamagan bo'lsa (False), post o'chirilgan deb belgilanmasligi, zaxira fetch ishlatilishi."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        # Ro'yxatda topilmadi, lekin pagination tugamagan (False):
        mock_client.list_recent_media.return_value = ([
            {'id': 'other_media_999', 'like_count': 10, 'comments_count': 1}
        ], False)

        # Zaxira (fallback) fetch_post_metrics muvaffaqiyatli ma'lumot qaytaradi:
        mock_fetch.return_value = {'views': 350, 'likes': 35, 'comments_count': 7}

        check_users_chunk_task([self.users[0].id])

        self.posts[0].refresh_from_db()
        # Post o'chirilgan deb belgilanmasligi kerak:
        self.assertEqual(self.posts[0].status, 'published')
        self.assertEqual(self.posts[0].views, 350)
        self.assertEqual(self.posts[0].likes, 35)

    def test_phase_d_adaptive_frequency_rules(self):
        """D-bosqich: views >= 5000 va o'chirilgan/tokeni yaroqsiz postlar chastotasi."""
        from tracker.services import calculate_next_check
        now = timezone.now()

        # 1. Views >= 5000 bo'lgan post 24 soatga rejalashtirilishi kerak
        self.posts[0].views = 5200
        next_check = calculate_next_check(self.posts[0], now=now)
        self.assertEqual(next_check, now + timedelta(hours=24))

        # 2. O'chirilgan (deleted) post tekshirilmasligi kerak (None)
        self.posts[0].status = 'deleted'
        self.assertIsNone(calculate_next_check(self.posts[0], now=now))

        # 3. Foydalanuvchi akkaunti ulangan bo'lmasa (needs_reauth), tekshirilmasligi kerak (None)
        self.posts[0].status = 'published'
        self.users[0].status = 'needs_reauth'
        self.users[0].save()
        self.assertIsNone(calculate_next_check(self.posts[0], now=now))
