import logging
import math
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import Post, InstagramUser
from .rate_limiter import rate_limiter
from .services import (
    publish_reels_for_link,
    update_post_metrics,
    refresh_user_token,
    InstagramPublishError,
    InstagramMetricsError,
    InstagramRateLimitError,
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


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def check_post_metrics_task(self, post_id: int):
    """
    Bitta post uchun Instagram metrikalarini (views, likes, comments) yangilaydi.
    So'rov yuborishdan oldin Redis umumiy tezlik cheklagichidan ruxsat oladi.
    """
    logger.info("Post statistikasini tekshirish boshlandi: post_id=%s", post_id)
    try:
        post = Post.objects.select_related('link__user').get(id=post_id)
    except Post.DoesNotExist:
        logger.warning("Post topilmadi: post_id=%s", post_id)
        return {"error": f"Post #{post_id} topilmadi"}

    # Akkaunt ID (agar bog'langan bo'lsa)
    account_id = None
    if post.link and post.link.user_id:
        account_id = post.link.user_id

    # 1. Tezlik cheklagichdan ruxsat so'rash (barcha workerlar uchun umumiy)
    allowed, retry_after, reason = rate_limiter.acquire(account_id=account_id)
    if not allowed:
        logger.info(
            "Rate limit cheklovi (%s): post_id=%s, account_id=%s uchun %.2fs kutiladi",
            reason, post_id, account_id, retry_after
        )
        countdown = max(1, int(math.ceil(retry_after)))
        # Ruxsat bo'lmasa, vazifa xato hisoblanmasin va post statusi o'zgarmasin:
        # qisqa kechiktirib qayta navbatga qo'yilsin
        raise self.retry(countdown=countdown, max_retries=None)

    try:
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
    except InstagramRateLimitError as exc:
        # Instagram'dan rate limit xatosi: post o'chirilmasin, xato deb belgilanmasin
        rate_limiter.trigger_backoff(duration_seconds=60)
        logger.warning(
            "Instagram rate limit xatosi (post_id=%s): vazifa 60 soniyaga kechiktirildi",
            post_id,
        )
        raise self.retry(countdown=60, max_retries=None)
    except InstagramMetricsError as exc:
        logger.warning("Post statistikasini olishda xatolik (post_id=%s): %s", post_id, exc)
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
    Katta hajmdagi ma'lumotlar bazasi (1,000,000+ posts) uchun tsikl orqali ko'proq postlarni qamrab oladi.
    """
    now = timezone.now()
    total_dispatched = 0
    max_to_dispatch_per_run = getattr(settings, 'MAX_POSTS_PER_RUN', 50000)
    batch_size = getattr(settings, 'CHECK_BATCH_SIZE', 1000)
    
    while total_dispatched < max_to_dispatch_per_run:
        with transaction.atomic():
            ids = list(
                Post.objects.select_for_update(skip_locked=True)
                .filter(status='published', next_check_at__lte=now)
                .order_by('next_check_at')
                .values_list('id', flat=True)[:batch_size]
            )
            if not ids:
                break
                
            # Keyingi tekshiruvni vaqtinchalik 2 soatga kechiktiramiz, to worker uni haqiqatda qayta ishlamaguncha
            Post.objects.filter(id__in=ids).update(next_check_at=now + timedelta(hours=2))

        for post_id in ids:
            check_post_metrics_task.delay(post_id)
            
        total_dispatched += len(ids)

    logger.info("Vaqti yetgan postlar tekshiruvi: %d ta post topildi va navbatga qo'yildi", total_dispatched)
    return total_dispatched


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
