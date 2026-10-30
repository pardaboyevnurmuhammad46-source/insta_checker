from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from tracker.models import InstagramUser, UniqueLink, Post, PostStat, Prize, Video
from tracker.services import (
    update_post_metrics,
    bulk_save_posts_metrics,
    check_and_award_prizes,
    is_simulated_mode,
)
from tracker.instagram_client import RealInstagramClient, DryRunInstagramClient


class BulkAndStatsTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Test User",
            ig_user_id="12345678",
            access_token="IGAATestToken1234567890",
            status="connected",
        )
        self.video = Video.objects.create(title="Test Video", is_default=True)
        self.link = UniqueLink.objects.create(user=self.user, video=self.video, status="posted")
        self.post = Post.objects.create(
            link=self.link,
            ig_media_id="media_111",
            status="published",
            views=100,
            likes=10,
            comments_count=2,
            last_checked_at=timezone.now() - timedelta(hours=1),
        )

    @patch('tracker.services.fetch_post_metrics_from_instagram')
    def test_update_post_metrics_no_duplicate_stat_when_unchanged(self, mock_fetch):
        # 1. Metrikalar o'zgarmagan holat:
        mock_fetch.return_value = {'views': 100, 'likes': 10, 'comments_count': 2}
        initial_stats_count = PostStat.objects.filter(post=self.post).count()

        old_checked_at = self.post.last_checked_at
        update_post_metrics(self.post)
        self.post.refresh_from_db()

        # PostStat qo'shilmasligi kerak:
        self.assertEqual(PostStat.objects.filter(post=self.post).count(), initial_stats_count)
        # Lekin last_checked_at yangilanishi kerak:
        self.assertGreater(self.post.last_checked_at, old_checked_at)
        self.assertIsNotNone(self.post.next_check_at)

    @patch('tracker.services.fetch_post_metrics_from_instagram')
    def test_update_post_metrics_creates_stat_and_prize_when_changed(self, mock_fetch):
        # 2. Metrikalar o'zgargan va marraga (500) yetgan holat:
        mock_fetch.return_value = {'views': 520, 'likes': 25, 'comments_count': 5}
        initial_stats_count = PostStat.objects.filter(post=self.post).count()

        update_post_metrics(self.post)
        self.post.refresh_from_db()

        # Yangi PostStat yaratilishi kerak:
        self.assertEqual(PostStat.objects.filter(post=self.post).count(), initial_stats_count + 1)
        stat = PostStat.objects.filter(post=self.post).latest('id')
        self.assertEqual(stat.views, 520)
        self.assertEqual(stat.likes, 25)

        # 500 marra uchun Prize yaratilishi kerak:
        self.assertTrue(Prize.objects.filter(post=self.post, milestone=500).exists())

    def test_bulk_save_posts_metrics(self):
        # 3 ta post yaratamiz
        link2 = UniqueLink.objects.create(user=self.user, video=self.video, status="posted")
        post2 = Post.objects.create(
            link=link2,
            ig_media_id="media_222",
            status="published",
            views=300,
            likes=30,
            comments_count=5,
        )

        link3 = UniqueLink.objects.create(user=self.user, video=self.video, status="posted")
        post3 = Post.objects.create(
            link=link3,
            ig_media_id="media_333",
            status="published",
            views=450,
            likes=40,
            comments_count=8,
        )

        updates = [
            # Post 1: o'zgarmagan (views 100 -> 100)
            {
                'post': self.post,
                'metrics': {'views': 100, 'likes': 10, 'comments_count': 2},
            },
            # Post 2: o'zgargan (views 300 -> 350)
            {
                'post': post2,
                'metrics': {'views': 350, 'likes': 35, 'comments_count': 7},
            },
            # Post 3: o'zgargan va 1000 marraga yetgan (views 450 -> 1050)
            {
                'post': post3,
                'metrics': {'views': 1050, 'likes': 90, 'comments_count': 20},
            },
        ]

        result = bulk_save_posts_metrics(updates)

        self.assertEqual(result['updated_posts_count'], 3)
        # Faqat post2 va post3 uchun yangi PostStat yaratilishi kerak (jami 2 ta):
        self.assertEqual(result['created_stats_count'], 2)
        # Post 3 uchun 500 va 1000 marralar (jami 2 ta sovrin) berilishi kerak:
        self.assertEqual(result['awarded_prizes_count'], 2)

        self.post.refresh_from_db()
        post2.refresh_from_db()
        post3.refresh_from_db()

        # Post 1 uchun yangi PostStat yo'q
        self.assertEqual(PostStat.objects.filter(post=self.post).count(), 0)
        self.assertIsNotNone(self.post.last_checked_at)

        # Post 2 uchun PostStat bor
        self.assertEqual(PostStat.objects.filter(post=post2).count(), 1)
        self.assertEqual(post2.views, 350)

        # Post 3 uchun PostStat va sovrinlar bor
        self.assertEqual(PostStat.objects.filter(post=post3).count(), 1)
        self.assertEqual(post3.views, 1050)
        self.assertTrue(Prize.objects.filter(post=post3, milestone=500).exists())
        self.assertTrue(Prize.objects.filter(post=post3, milestone=1000).exists())

    # =========================================================================
    # Simulyatsiya va Rejim tekshiruvlari: (a), (b), (c), (d)
    # =========================================================================

    @override_settings(INSTAGRAM_MODE='real', INSTAGRAM_DRY_RUN=False)
    @patch.object(RealInstagramClient, 'fetch_post_metrics')
    def test_real_mode_with_igaa_token_reaches_real_client(self, mock_real_fetch):
        """(a) real rejim + IGAA token: Haqiqiy Graph API klientiga boradi."""
        mock_real_fetch.return_value = {'views': 200, 'likes': 20, 'comments_count': 3}
        self.user.access_token = "IGAARealUserToken12345"
        self.user.save()

        update_post_metrics(self.post)
        self.assertTrue(mock_real_fetch.called)

    @override_settings(INSTAGRAM_MODE='real', INSTAGRAM_DRY_RUN=False)
    @patch.object(RealInstagramClient, 'fetch_post_metrics')
    def test_real_mode_with_test_token_does_not_bypass(self, mock_real_fetch):
        """(b) real rejim + test_ token: chetlab o'tmaydi (production xavfsizligi, Graph API ga boradi)."""
        mock_real_fetch.return_value = {'views': 200, 'likes': 20, 'comments_count': 3}
        self.user.access_token = "test_accidental_token_in_prod"
        self.user.save()

        # is_simulated_mode real rejimda har doim False bo'lishi kerak:
        self.assertFalse(is_simulated_mode(self.user.access_token))

        update_post_metrics(self.post)
        # Productionda Graph API klientiga chaqiruv ketishi shart:
        self.assertTrue(mock_real_fetch.called)

    @override_settings(INSTAGRAM_MODE='mock', INSTAGRAM_DRY_RUN=True, DEBUG=True)
    @patch.object(DryRunInstagramClient, 'fetch_post_metrics')
    def test_mock_mode_with_igaa_token_passes_through_dry_run_client(self, mock_dry_fetch):
        """(c) mock rejim + IGAA token: DryRunInstagramClient orqali o'tadi, chetlab o'tmaydi."""
        mock_dry_fetch.return_value = {'views': 300, 'likes': 30, 'comments_count': 5}
        self.user.access_token = "IGAABenchmarkToken999"
        self.user.save()

        self.assertFalse(is_simulated_mode(self.user.access_token))

        update_post_metrics(self.post)
        self.assertTrue(mock_dry_fetch.called)

    @override_settings(INSTAGRAM_MODE='mock', INSTAGRAM_DRY_RUN=True, DEBUG=True)
    @patch.object(DryRunInstagramClient, 'fetch_post_metrics')
    def test_mock_mode_with_demo_token_bypasses(self, mock_dry_fetch):
        """(d) mock rejim + demo_ token: chetlab o'tadi (DryRunInstagramClient chaqirilmaydi)."""
        self.user.access_token = "demo_long_lived_token_bekzod"
        self.user.save()

        self.assertTrue(is_simulated_mode(self.user.access_token))

        update_post_metrics(self.post)
        # Klient chaqirilmasdan to'g'ridan-to'g'ri qaytadi:
        self.assertFalse(mock_dry_fetch.called)
