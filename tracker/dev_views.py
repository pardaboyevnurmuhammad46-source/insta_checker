import logging
from django.conf import settings
from django.db import connection
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.core.exceptions import PermissionDenied
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

from .models import Post, InstagramUser
from .services import update_post_metrics, InstagramMetricsError, InstagramNetworkError
from .instagram_errors import get_redis_client
from .serializers import (
    HealthCheckOutputSerializer,
    SimulateViewsInputSerializer,
    SimulatePostActionInputSerializer,
    SimulateUserActionInputSerializer,
)

logger = logging.getLogger(__name__)


def require_dry_run_and_admin(request):
    """
    Faqat INSTAGRAM_DRY_RUN=True bo'lganda va faqat admin foydalanuvchiga ruxsat beradi.
    Aks holda (DRY_RUN o'chiq bo'lsa) 404 qaytaradi, oddiy user bo'lsa 403 qaytaradi.
    """
    if not getattr(settings, 'INSTAGRAM_DRY_RUN', False):
        raise Http404("Bu endpoint faqat INSTAGRAM_DRY_RUN=True rejimida mavjud.")

    if not request.user or not request.user.is_authenticated:
        raise PermissionDenied("Autentifikatsiyadan o'tilmagan.")

    if not (request.user.is_staff or request.user.is_superuser):
        raise PermissionDenied("Faqat admin uchun ruxsat berilgan.")


@extend_schema(
    responses={200: HealthCheckOutputSerializer},
    description="Tizim holatini (Database, Redis va DRY_RUN rejimi) tekshirish.",
)
@api_view(['GET'])
@permission_classes([AllowAny])
def health_check(request):
    """
    Tizim sog'lomligi (Health check) ochiq endpointi.
    Database va Redis bilan aloqani tekshiradi.
    """
    db_status = "ok"
    redis_status = "ok"

    # Database tekshirish
    try:
        connection.ensure_connection()
    except Exception as exc:
        db_status = f"error: {exc}"

    # Redis tekshirish
    try:
        r = get_redis_client()
        if not r.ping():
            redis_status = "error: ping failed"
    except Exception as exc:
        redis_status = f"error: {exc}"

    is_dry_run = bool(getattr(settings, 'INSTAGRAM_DRY_RUN', False))
    overall_status = "healthy" if db_status == "ok" and redis_status == "ok" else "unhealthy"

    data = {
        "status": overall_status,
        "database": db_status,
        "redis": redis_status,
        "dry_run": is_dry_run,
    }

    http_status = status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response(HealthCheckOutputSerializer(data).data, status=http_status)


@extend_schema(
    request=SimulateViewsInputSerializer,
    responses={200: dict},
    description="Faqat DRY_RUN rejimida: Post ko'rishlarini Instagram'da simulyatsiya qilish va haqiqiy tekshiruv quvurini (prizlar, statistika) ishga tushirish.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_views(request):
    require_dry_run_and_admin(request)

    serializer = SimulateViewsInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    post_id = serializer.validated_data['post_id']
    views = serializer.validated_data['views']

    post = get_object_or_404(Post, pk=post_id)
    if not post.link.user.access_token or post.link.user.status != 'connected':
        post.link.user.status = 'connected'
        if not post.link.user.access_token:
            post.link.user.access_token = 'dry_run_auto_token'
        post.link.user.save(update_fields=['status', 'access_token'])

    r = get_redis_client()
    # Post uchun simulyatsiya ko'rishlarini yozamiz va xatolik bayrog'ini tozalaymiz
    r.set(f"dry_run:sim:post:{post.id}:views", views, ex=300)
    r.delete(f"dry_run:sim:post:{post.id}:error")

    # Haqiqiy tekshiruv quvurini ishga tushirish (PostStat, Prize, Notification)
    updated_post = update_post_metrics(post)

    return Response({
        "message": f"Post #{post.id} uchun {views} ta ko'rish simulyatsiya qilindi va tekshiruv quvuri muvaffaqiyatli bajarildi.",
        "post_id": updated_post.id,
        "views": updated_post.views,
        "likes": updated_post.likes,
        "comments_count": updated_post.comments_count,
        "status": updated_post.status,
    })


@extend_schema(
    request=SimulatePostActionInputSerializer,
    responses={200: dict},
    description="Faqat DRY_RUN rejimida: Instagram'da post o'chirilganini (Code 100/33 yoki 404) simulyatsiya qilish va tekshiruv quvurini ishga tushirish.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_delete(request):
    require_dry_run_and_admin(request)

    serializer = SimulatePostActionInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    post_id = serializer.validated_data['post_id']

    post = get_object_or_404(Post, pk=post_id)
    if not post.link.user.access_token or post.link.user.status != 'connected':
        post.link.user.status = 'connected'
        if not post.link.user.access_token:
            post.link.user.access_token = 'dry_run_auto_token'
        post.link.user.save(update_fields=['status', 'access_token'])

    r = get_redis_client()
    # Keyingi tekshiruvda media_not_found berish uchun simulyatsiya bayrog'ini o'rnatamiz
    r.set(f"dry_run:sim:post:{post.id}:error", "media_not_found", ex=300)

    # Haqiqiy tekshiruv quvurini ishga tushiramiz (post o'chirilgan holatga o'tadi)
    updated_post = update_post_metrics(post)

    return Response({
        "message": f"Post #{post.id} o'chirilishi simulyatsiya qilindi va post holati 'deleted' ga o'tdi.",
        "post_id": updated_post.id,
        "status": updated_post.status,
        "deleted_detected_at": updated_post.deleted_detected_at,
        "error": updated_post.error,
    })


@extend_schema(
    request=SimulateUserActionInputSerializer,
    responses={200: dict},
    description="Faqat DRY_RUN rejimida: Instagram foydalanuvchi tokeni bekor qilinganini (Code 190) simulyatsiya qilish.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_token_revoked(request):
    require_dry_run_and_admin(request)

    serializer = SimulateUserActionInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user_id = serializer.validated_data['user_id']

    ig_user = get_object_or_404(InstagramUser, pk=user_id)

    r = get_redis_client()
    r.set(f"dry_run:sim:user:{ig_user.id}:error", "token_invalid", ex=300)
    if ig_user.access_token:
        r.set(f"dry_run:sim:token:{ig_user.access_token}:error", "token_invalid", ex=300)

    # Foydalanuvchining so'nggi posti orqali haqiqiy quvurni ishga tushiramiz
    post = Post.objects.filter(link__user=ig_user, status='published').first()
    if post:
        update_post_metrics(post)
    else:
        ig_user.status = 'needs_reauth'
        ig_user.save(update_fields=['status'])

    ig_user.refresh_from_db()

    return Response({
        "message": f"User #{ig_user.id} ({ig_user.name}) tokeni bekor qilinishi simulyatsiya qilindi.",
        "user_id": ig_user.id,
        "status": ig_user.status,
    })


@extend_schema(
    request=SimulatePostActionInputSerializer,
    responses={200: dict},
    description="Faqat DRY_RUN rejimida: Instagram vaqtinchalik tarmoq/server xatosini simulyatsiya qilish.",
)
@api_view(['POST'])
@permission_classes([AllowAny])
def simulate_network_error(request):
    require_dry_run_and_admin(request)

    serializer = SimulatePostActionInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    post_id = serializer.validated_data['post_id']

    post = get_object_or_404(Post, pk=post_id)
    if not post.link.user.access_token or post.link.user.status != 'connected':
        post.link.user.status = 'connected'
        if not post.link.user.access_token:
            post.link.user.access_token = 'dry_run_auto_token'
        post.link.user.save(update_fields=['status', 'access_token'])

    r = get_redis_client()
    r.set(f"dry_run:sim:post:{post.id}:error", "network_error", ex=300)

    # Quvurni ishga tushiramiz - tarmoq xatosi bo'lganda post o'zgarmasdan keyinga suriladi
    try:
        update_post_metrics(post)
    except InstagramNetworkError:
        pass

    post.refresh_from_db()

    return Response({
        "message": f"Post #{post.id} uchun vaqtinchalik tarmoq xatosi simulyatsiya qilindi. Post holati o'zgarishsiz qoldi.",
        "post_id": post.id,
        "status": post.status,
    })
