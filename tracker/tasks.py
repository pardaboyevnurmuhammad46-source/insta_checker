import logging
import math
from datetime import timedelta
from celery import shared_task
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from .models import Post, InstagramUser
from .rate_limiter import rate_limiter
from .instagram_errors import mask_sensitive_data
from .services import (
    publish_reels_for_link,
    update_post_metrics,
    refresh_user_token,
    sync_user_media,
    InstagramPublishError,
    InstagramMetricsError,
    InstagramRateLimitError,
    InstagramNetworkError,
    TokenInvalid,
)
from .video_utils import process_video_file

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def publish_reels_task(self, link_id: int, caption: str = ''):
    logger.info("Reels yuklash vazifasi boshlandi: link_id=%s", link_id)
    try:
        post = publish_reels_for_link(link_id=link_id, caption=caption)
        logger.info("Reels muvaffaqiyatli yuklandi: post_id=%s, media_id=%s", post.id, post.ig_media_id)
        # Yangi chiqqan post statistikasini 15 soniyadan so'ng darhol birinchi marta tekshirish
        check_post_metrics_task.apply_async(args=[post.id], countdown=15)
        return {"post_id": post.id, "ig_media_id": post.ig_media_id, "status": post.status}
    except InstagramPublishError as exc:
        logger.error("Reels yuklashda xatolik (link_id=%s): %s", link_id, mask_sensitive_data(str(exc)))
        # if "tarmoq" in str(exc).lower() or "timeout" in str(exc).lower():
        #     raise self.retry(exc=exc)
        if isinstance(exc, InstagramNetworkError):
            raise self.retry(exc=exc)
        return {"error": mask_sensitive_data(str(exc)), "status": "failed"}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik (link_id=%s): %s", link_id, mask_sensitive_data(str(exc)))
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
        logger.warning("Post statistikasini olishda xatolik (post_id=%s): %s", post_id, mask_sensitive_data(str(exc)))
        if isinstance(exc, InstagramNetworkError):
            raise self.retry(exc=exc)
        return {"error": mask_sensitive_data(str(exc)), "status": "failed"}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik post statistikasini tekshirishda (post_id=%s): %s", post_id, mask_sensitive_data(str(exc)))
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
                .filter(
                    models.Q(status__in=['published', 'verified']),
                    models.Q(next_check_at__lte=now) | models.Q(next_check_at__isnull=True)
                )
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
def verify_post_ai_task(post_id: int):
    """
    Berilgan post uchun fon rejimida AI audio va matn tekshiruvini amalga oshiradi.
    """
    try:
        from .ai_verifier import process_and_verify_post_ai
        post = Post.objects.select_related('link__video', 'link__user').get(id=post_id)
        return process_and_verify_post_ai(post)
    except Post.DoesNotExist:
        logger.warning("verify_post_ai_task: Post topilmadi id=%s", post_id)
        return None
    except Exception as exc:
        logger.exception("verify_post_ai_task da xatolik (post_id=%s): %s", post_id, exc)
        return None


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


@shared_task(bind=True, max_retries=1, default_retry_delay=10)
def process_video_task(self, video_id: int):
    """
    Celery vazifasi: Yuklangan videoni tekshiradi va kerak bo'lsa 9:16 formatga o'tkazadi.
    1. Davomiylikni tekshiradi (3 - 90 soniya).
    2. Nisbat 9:16 bo'lmasa, ffmpeg yordamida blur-fonli 1080x1920 MP4 ga o'tkazadi.
    3. Natijaga ko'ra Video.status ('ready' yoki 'failed') ni yangilaydi.
    """
    logger.info("Video konvertatsiya vazifasi boshlandi: video_id=%s", video_id)
    try:
        from .models import Video
        video = Video.objects.get(id=video_id)
    except Video.DoesNotExist:
        logger.warning("Video topilmadi: video_id=%s", video_id)
        return {"error": f"Video #{video_id} topilmadi"}

    video.status = 'processing'
    video.processing_error = None
    video.save(update_fields=['status', 'processing_error'])

    try:
        success, error_msg = process_video_file(video)
        if success:
            video.status = 'ready'
            video.processing_error = None
            video.save(update_fields=['status', 'processing_error'])
            logger.info("Video tayyor holatga keltirildi: video_id=%s", video_id)
            return {"status": "ready", "video_id": video_id}
        else:
            video.status = 'failed'
            video.processing_error = error_msg
            video.save(update_fields=['status', 'processing_error'])
            logger.error("Video tayyorlashda xatolik: video_id=%s, xato=%s", video_id, error_msg)
            return {"status": "failed", "error": error_msg}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik videoni qayta ishlashda: video_id=%s", video_id)
        video.status = 'failed'
        video.processing_error = f"Kutilmagan xatolik: {exc}"
        video.save(update_fields=['status', 'processing_error'])
        return {"status": "failed", "error": str(exc)}


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def sync_user_media_task(self, user_id: int):
    """
    Foydalanuvchi Instagram medialarini (Reels) sinxronizatsiya qiluvchi Celery vazifasi.
    Xatolik bo'lsa 30 soniya oraliq bilan ko'pi bilan 3 marta qayta urinadi.
    """
    logger.info("Foydalanuvchi medialarini sinxronizatsiya qilish boshlandi: user_id=%s", user_id)
    try:
        user = InstagramUser.objects.get(id=user_id)
    except InstagramUser.DoesNotExist:
        logger.warning("InstagramUser topilmadi: user_id=%s", user_id)
        return {"error": f"InstagramUser #{user_id} topilmadi"}

    if not user.access_token or user.status == 'needs_reauth':
        logger.info("Foydalanuvchi tokeni mavjud emas yoki 'needs_reauth': user_id=%s", user_id)
        return {"status": "skipped", "reason": "no_token_or_needs_reauth"}

    # 1. Tezlik cheklagichdan ruxsat so'rash (bitta akkaunt soatiga 200 so'rovdan oshsa, xato bermasdan kutadi)
    allowed, retry_after, reason = rate_limiter.acquire(account_id=user.id)
    if not allowed:
        logger.info(
            "Rate limit cheklovi (%s): user_id=%s uchun %.2fs kutiladi",
            reason, user_id, retry_after
        )
        countdown = max(1, int(math.ceil(retry_after)))
        raise self.retry(countdown=countdown, max_retries=None)

    try:
        result = sync_user_media(user)
        logger.info("Foydalanuvchi medialari sinxronizatsiya qilindi: user_id=%s, natija=%s", user_id, result)
        return result
    except InstagramNetworkError as exc:
        logger.warning("sync_user_media_task tarmoq xatosi (user_id=%s): %s", user_id, mask_sensitive_data(str(exc)))
        raise self.retry(exc=exc, countdown=30)
    except TokenInvalid as exc:
        logger.warning("sync_user_media_task da token yaroqsiz (user_id=%s): %s", user_id, exc)
        user.status = 'needs_reauth'
        user.save(update_fields=['status'])
        return {"status": "needs_reauth", "error": str(exc)}
    except Exception as exc:
        logger.exception("Kutilmagan xatolik sync_user_media_task da (user_id=%s): %s", user_id, mask_sensitive_data(str(exc)))
        raise self.retry(exc=exc, countdown=30)


@shared_task
def sync_recent_active_users_task():
    """
    Har 5 daqiqada ishga tushadi:
    Oxirgi 48 soat ichida faol bo'lgan (link olgan, ro'yxatdan o'tgan yoki posti bor)
    barcha ulangan foydalanuvchilar uchun sync_user_media_task vazifalarini ishga tushiradi.
    Foydalanuvchi o'zi Instagramda joylagan postni 5-10 daqiqada topishni kafolatlaydi.
    """
    threshold = timezone.now() - timedelta(hours=48)
    user_ids = list(
        InstagramUser.objects.filter(
            status='connected',
            links__post__isnull=False,
        ).filter(
            models.Q(links__post__posted_at__gte=threshold) |
            models.Q(links__post__last_synced_at__gte=threshold) |
            models.Q(links__created_at__gte=threshold)
        ).exclude(access_token__isnull=True).exclude(access_token='')
        .values_list('id', flat=True)
        .distinct()
    )

    for uid in user_ids:
        sync_user_media_task.delay(uid)

    logger.info("Faol foydalanuvchilar medialari sinxronizatsiyaga yuborildi: count=%d", len(user_ids))
    return len(user_ids)


@shared_task
def sync_other_users_task():
    """
    Har soatda ishga tushadi:
    Oxirgi 48 soatda faol bo'lmagan qolgan barcha ulangan foydalanuvchilar
    uchun sync_user_media_task vazifalarini ishga tushiradi.
    """
    threshold = timezone.now() - timedelta(hours=48)
    recent_user_ids = set(
        InstagramUser.objects.filter(
            status='connected',
            links__post__isnull=False,
        ).filter(
            models.Q(links__post__posted_at__gte=threshold) |
            models.Q(links__post__last_synced_at__gte=threshold) |
            models.Q(links__created_at__gte=threshold)
        ).exclude(access_token__isnull=True).exclude(access_token='')
        .values_list('id', flat=True)
    )

    other_user_ids = list(
        InstagramUser.objects.filter(status='connected')
        .exclude(access_token__isnull=True)
        .exclude(access_token='')
        .exclude(id__in=recent_user_ids)
        .values_list('id', flat=True)
        .distinct()
    )

    for uid in other_user_ids:
        sync_user_media_task.delay(uid)

    logger.info("Qolgan foydalanuvchilar sinxronizatsiyaga yuborildi: count=%d", len(other_user_ids))
    return len(other_user_ids)


