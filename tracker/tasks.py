import logging
from datetime import timedelta
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from .models import InstagramUser, Post
from .services import (
    publish_reels_for_link,
    update_post_metrics,
    refresh_user_token,
    InstagramPublishError,
    InstagramMetricsError,
    InstagramNetworkError,
)

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_reels_task(self, link_id: int, caption: str = ''):
    logger.info("Reels yuklash vazifasi boshlandi: link_id=%s", link_id)
    try:
        post = publish_reels_for_link(link_id=link_id, caption=caption)
        logger.info("Reels muvaffaqiyatli yuklandi: post_id=%s, media_id=%s", post.id, post.ig_media_id)
        return {"post_id": post.id, "ig_media_id": post.ig_media_id, "status": post.status}
    except InstagramPublishError as exc:
        logger.error("Reels yuklashda xatolik (link_id=%s): %s", link_id, exc)
        # if "tarmoq" in str(exc).lower() or "timeout" in str(exc).lower():
        #     raise self.retry(exc=exc)
        if isinstance(exc, InstagramNetworkError):
            raise self.retry(exc=exc)
        return {"error": str(exc), "status": "failed"}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik (link_id=%s): %s", link_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def check_post_metrics_task(self, post_id: int):
    """
    Bitta post uchun Instagram metrikalarini (views, likes, comments) yangilaydi.
    """
    logger.info("Post statistikasini tekshirish boshlandi: post_id=%s", post_id)
    try:
        post = Post.objects.select_related('link__user').get(id=post_id)
        updated_post = update_post_metrics(post)
        logger.info(
            "Post statistikasi yangilandi: post_id=%s, views=%s, likes=%s, comments=%s, status=%s",
            updated_post.id,
            updated_post.views,
            updated_post.likes,
            updated_post.comments_count,
            updated_post.status,
        )
        return {
            "post_id": updated_post.id,
            "views": updated_post.views,
            "likes": updated_post.likes,
            "comments_count": updated_post.comments_count,
            "status": updated_post.status,
        }
    except Post.DoesNotExist:
        logger.warning("Post topilmadi: post_id=%s", post_id)
        return {"error": f"Post #{post_id} topilmadi"}
    except InstagramMetricsError as exc:
        logger.warning("Post statistikasini olishda xatolik (post_id=%s): %s", post_id, exc)
        # if "tarmoq" in str(exc).lower():
        #     raise self.retry(exc=exc)
        if isinstance(exc, InstagramNetworkError):
            raise self.retry(exc=exc)
        return {"error": str(exc), "status": "failed"}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik post statistikasini tekshirishda (post_id=%s): %s", post_id, exc)
        raise self.retry(exc=exc)




@shared_task
def check_all_due_posts_task():
    """
    next_check_at vaqti kelgan barcha faol (published) postlar uchun fonda tekshiruv vazifalarini ishga tushiradi.
    Worker orqada qolsa ham postlar qayta-qayta navbatga tushmasligi uchun darhol 10 daqiqaga 'band' qilinadi.
    """
    now = timezone.now()
    with transaction.atomic():
        ids = list(
            Post.objects.select_for_update(skip_locked=True)
            .filter(status='published', next_check_at__lte=now)
            .order_by('next_check_at')
            .values_list('id', flat=True)[:500]
        )
        if ids:
            Post.objects.filter(id__in=ids).update(next_check_at=now + timedelta(minutes=10))

    logger.info("Vaqti yetgan postlar tekshiruvi: %d ta post topildi va navbatga qo'yildi", len(ids))
    for post_id in ids:
        check_post_metrics_task.delay(post_id)

    return len(ids)


@shared_task
def refresh_expiring_tokens_task():
    """
    Muddati 14 kun ichida tugaydigan bog'langan Instagram akkauntlari tokenlarini avtomatik yangilaydi.
    """
    threshold = timezone.now() + timedelta(days=14)
    expiring_users = InstagramUser.objects.filter(
        status='connected',
        token_expires_at__lte=threshold,
    ).exclude(access_token__isnull=True).exclude(access_token='')

    refreshed_count = 0
    failed_count = 0

    for user in expiring_users:
        success = refresh_user_token(user)
        if success:
            refreshed_count += 1
        else:
            failed_count += 1

    logger.info("Tokenlarni yangilash yakunlandi: muvaffaqiyatli=%d, xato=%d", refreshed_count, failed_count)
    return {"refreshed_count": refreshed_count, "failed_count": failed_count}
