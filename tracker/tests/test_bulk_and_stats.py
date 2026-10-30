from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from tracker.models import InstagramUser, UniqueLink, Post, PostStat, Prize, Video
from tracker.services import update_post_metrics, bulk_save_posts_metrics, check_and_award_prizes


class BulkAndStatsTestCase(TestCase):
    def setUp(self):
        self.user = InstagramUser.objects.create(
            name="Test User",
            ig_user_id="12345678",
            access_token="tok_real_simulation_123",
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
