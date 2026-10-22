import logging
import csv
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
# from django.http import HttpResponseRedirect
from django.http import HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
# from django.db.models import Count, Sum
from django.db.models import Count, Sum, Max, Min
from django.db.models.functions import Coalesce, TruncDate
from datetime import timedelta
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets, serializers
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Q

from rest_framework_simplejwt.tokens import RefreshToken

# from .permissions import IsAdminRole, IsOwnerOrAdmin
from .permissions import IsAdminRole, IsOwnerOrAdmin, IsAdminOrReadOnlyOwnerVideo
# from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .models import (
    InstagramUser,
    UniqueLink,
    Post,
    Prize,
    DataDeletionRequest,
    Video,
    PostStat,
    Notification,
)
from .instagram_errors import mask_sensitive_data
from .serializers import (
    InstagramUserSerializer,
    VideoSerializer,
    UniqueLinkSerializer,
    PostSerializer,
    AdminPostSerializer,
    PrizeSerializer,
    DataDeletionRequestSerializer,
    PostStatSerializer,
    NotificationSerializer,
    AdminCreateUserSerializer,
    AdminCreateUserOutputSerializer,
    UserRegisterSerializer,
    ChangePasswordSerializer,
    ResetPasswordSerializer,
    MeSummarySerializer,
    AdminSummarySerializer,
    UserProfileOutputSerializer,
    UserPublishStatusOutputSerializer,
)
from .services import (
    InstagramOAuthError,
    InstagramNetworkError,
    InstagramPublishError,
    InstagramPublishNetworkError,
    InstagramMetricsError,
    InstagramRateLimitError,
    InstagramMetricsNetworkError,
    MetaWebhookError,
    build_instagram_auth_url,
    complete_instagram_oauth,
    parse_signed_request,
    handle_deauthorize_request,
    handle_data_deletion_request,
    refresh_user_token,
    get_configured_milestones,
    update_post_metrics,
)
from .tasks import publish_reels_task, check_post_metrics_task
from .instagram_errors import get_instagram_errors_last_hour

logger = logging.getLogger(__name__)


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class InstagramUserViewSet(viewsets.ModelViewSet):
    # queryset = InstagramUser.objects.all().order_by("-id")
    queryset = InstagramUser.objects.all().order_by("-id")
    serializer_class = InstagramUserSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminRole]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'ig_user_id']
    # ordering_fields = ['created_at']
    ordering_fields = ['created_at', 'id']
    ordering = ['-id']

    @action(detail=True, methods=['post'], url_path='refresh-token')
    def refresh_token(self, request, pk=None):
        user = self.get_object()
        success = refresh_user_token(user)
        if success:
            return Response({"message": "Token muvaffaqiyatli yangilandi.", "status": user.status})
        return Response(
            {"error": "Tokenni yangilab bo'lmadi. Foydalanuvchi qayta ruxsat berishi kerak.", "status": user.status},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(detail=False, methods=['post'], url_path='create-user', permission_classes=[IsAdminRole])
    def create_user(self, request):
        serializer = AdminCreateUserSerializer(data=request.data)
        if serializer.is_valid():
            result = serializer.save()
            return Response(result, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='reset-password', permission_classes=[IsAdminRole])
    def reset_password(self, request, pk=None):
        ig_user = self.get_object()
        if not ig_user.user:
            return Response({"error": "Ushbu Instagram foydalanuvchisi Django User ga ulanmagan."}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ResetPasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        new_password = serializer.validated_data['new_password']
        ig_user.user.set_password(new_password)
        ig_user.user.save()
        return Response({"message": f"Foydalanuvchi ({ig_user.user.username}) paroli muvaffaqiyatli tiklandi."})


class VideoViewSet(viewsets.ModelViewSet):
    queryset = Video.objects.all().order_by('-created_at')
    serializer_class = VideoSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminOrReadOnlyOwnerVideo]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_default', 'is_active', 'owner']
    search_fields = ['title', 'owner__name']
    ordering_fields = ['created_at', 'title', 'id']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Video.objects.none()
        if user.is_staff or user.is_superuser:
            return Video.objects.select_related('owner').all().order_by('-created_at')
        return Video.objects.select_related('owner').filter(
            Q(owner__user=user, is_active=True) |
            Q(is_default=True, is_active=True)
        ).distinct().order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='set-default', permission_classes=[IsAdminRole])
    def set_default(self, request, pk=None):
        video = self.get_object()
        with transaction.atomic():
            Video.objects.filter(is_default=True).exclude(pk=video.pk).update(is_default=False)
            video.is_default = True
            video.is_active = True
            video.save(update_fields=['is_default', 'is_active'])
        return Response({
            "message": f"'{video.title}' umumiy video (default) sifatida belgilandi.",
            "video_id": video.id,
            "is_default": video.is_default,
        })

    @action(detail=True, methods=['post'], url_path='assign-owner', permission_classes=[IsAdminRole])
    def assign_owner(self, request, pk=None):
        video = self.get_object()
        owner_id = request.data.get('owner_id')
        if not owner_id:
            video.owner = None
            video.save(update_fields=['owner'])
            return Response({"message": "Video umumiy qilindi (owner olib tashlandi)."})
        try:
            ig_user = InstagramUser.objects.get(pk=owner_id)
        except InstagramUser.DoesNotExist:
            return Response({"error": "Bunday Instagram foydalanuvchisi topilmadi."}, status=status.HTTP_404_NOT_FOUND)
        video.owner = ig_user
        video.save(update_fields=['owner'])
        return Response({"message": f"Video '{ig_user.name}' ga biriktirildi.", "owner_id": ig_user.id})


class UniqueLinkViewSet(viewsets.ModelViewSet):
    # queryset = UniqueLink.objects.select_related('user').all()
    queryset = UniqueLink.objects.select_related('user').all().order_by('-id')
    serializer_class = UniqueLinkSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'user']
    search_fields = ['user__name']
    # ordering_fields = ['created_at']
    ordering_fields = ['created_at', 'id']
    ordering = ['-id']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return UniqueLink.objects.none()
        if user.is_staff or user.is_superuser:
            return UniqueLink.objects.select_related('user').all().order_by('-id')
        return UniqueLink.objects.select_related('user').filter(user__user=user).order_by('-id')

    def perform_create(self, serializer):
        user = self.request.user
        if not (user.is_staff or user.is_superuser):
            try:
                ig_user = InstagramUser.objects.get(user=user)
                serializer.save(user=ig_user)
            except InstagramUser.DoesNotExist:
                raise serializers.ValidationError({"user": "Foydalanuvchida bog'langan Instagram akkaunt topilmadi."})
        else:
            serializer.save()

    @action(detail=True, methods=['post'], url_path='resend')
    def resend(self, request, pk=None):
        link = self.get_object()
        if link.status != 'failed':
            return Response({"error": "Faqat failed linkni qayta yuborish mumkin."}, status=status.HTTP_400_BAD_REQUEST)
        link.status = 'pending'
        link.save(update_fields=['status'])
        if hasattr(link, 'post'):
            link.post.delete()
        return Response({"message": "Link holati 'pending' ga o'zgartirildi."})


class PostViewSet(viewsets.ReadOnlyModelViewSet):
    # queryset = Post.objects.select_related('link__user').all()
    queryset = Post.objects.select_related('link__user').all().order_by('-id')
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'link__user']
    search_fields = ['link__user__name', 'ig_media_id']
    # ordering_fields = ['views', 'posted_at']
    ordering_fields = ['views', 'posted_at', 'id']
    ordering = ['-id']

    def get_serializer_class(self):
        user = self.request.user
        if user and user.is_authenticated and (user.is_staff or user.is_superuser):
            return AdminPostSerializer
        return PostSerializer

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Post.objects.none()
        if user.is_staff or user.is_superuser:
            return Post.objects.select_related('link__user').all().order_by('-id')
        return Post.objects.select_related('link__user').filter(link__user__user=user).order_by('-id')

    @action(detail=True, methods=['get'], url_path='stats')
    def stats(self, request, pk=None):
        post = self.get_object()
        if post.status == 'published' and post.ig_media_id:
            now = timezone.now()
            if not post.last_checked_at or (now - post.last_checked_at) >= timedelta(minutes=5):
                try:
                    update_post_metrics(post)
                except Exception as exc:
                    logger.warning("PostViewSet.stats ichida metrikalarni yangilashda xatolik: %s", exc)
        stats_qs = post.stats.all().order_by('-checked_at')
        return Response(PostStatSerializer(stats_qs, many=True).data)

    @action(detail=True, methods=['post'], url_path='check-metrics')
    def check_metrics(self, request, pk=None):
        post = self.get_object()
        task = check_post_metrics_task.delay(post.id)
        return Response({"message": "Post statistikasini tekshirish vazifasi navbatga qo'yildi.", "task_id": task.id})

    @action(detail=True, methods=['post'], url_path='retry')
    def retry(self, request, pk=None):
        post = self.get_object()
        if post.status != 'failed':
            return Response({"error": "Faqat failed postni qayta joylash mumkin."}, status=status.HTTP_400_BAD_REQUEST)
        if not (request.user.is_staff or request.user.is_superuser) and post.retry_count >= 3:
            return Response({
                "error": "Qayta urinishlar soni tugadi (maksimal: 3 marta).",
                "retry_count": post.retry_count
            }, status=status.HTTP_400_BAD_REQUEST)
        post.retry_count += 1
        post.status = 'queued'
        post.error = None
        post.save(update_fields=['status', 'error', 'retry_count'])
        publish_reels_task.delay(post.link.id)
        return Response({
            "message": "Post qayta joylash uchun navbatga qo'yildi.",
            "retry_count": post.retry_count
        })


class PostStatViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PostStat.objects.select_related('post__link__user').all().order_by('-checked_at')
    serializer_class = PostStatSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    ordering = ['-checked_at']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return PostStat.objects.none()
        if user.is_staff or user.is_superuser:
            return PostStat.objects.select_related('post__link__user').all().order_by('-checked_at')
        return PostStat.objects.select_related('post__link__user').filter(post__link__user__user=user).order_by('-checked_at')


class PrizeViewSet(viewsets.ReadOnlyModelViewSet):
    # queryset = Prize.objects.select_related('post__link__user').all()
    queryset = Prize.objects.select_related('post__link__user').all().order_by('-id')
    serializer_class = PrizeSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    # ordering_fields = ['sent_at', 'milestone']
    ordering_fields = ['sent_at', 'milestone', 'id']
    ordering = ['-id']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Prize.objects.none()
        if user.is_staff or user.is_superuser:
            return Prize.objects.select_related('post__link__user').all().order_by('-id')
        return Prize.objects.select_related('post__link__user').filter(post__link__user__user=user).order_by('-id')


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Notification.objects.select_related('user').all().order_by('-created_at')
    serializer_class = NotificationSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Notification.objects.none()
        if user.is_staff or user.is_superuser:
            return Notification.objects.select_related('user').all().order_by('-created_at')
        return Notification.objects.select_related('user').filter(user__user=user).order_by('-created_at')

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({"message": "Bildirishnoma o'qildi deb belgilandi."})


class DataDeletionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    # queryset = DataDeletionRequest.objects.all().order_by('-requested_at')
    queryset = DataDeletionRequest.objects.all().order_by('-requested_at')
    serializer_class = DataDeletionRequestSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsAdminRole]
    ordering = ['-requested_at']


class Echo:
    def write(self, value):
        return value


@extend_schema(responses={200: AdminSummarySerializer})
@api_view(['GET'])
# @permission_classes([IsAdminUser])
@permission_classes([IsAdminRole])
def admin_summary(request):
    """
    Admin uchun umumiy statistika (Redis keshda 60 soniya saqlanadi).
    """
    cached_data = cache.get('admin_summary_cache')
    if cached_data is not None:
        cached_data["instagram_errors_last_hour"] = get_instagram_errors_last_hour()
        cached_data["dry_run"] = bool(getattr(settings, 'INSTAGRAM_DRY_RUN', False))
        return Response(AdminSummarySerializer(cached_data).data)

    total_users = InstagramUser.objects.count()
    connected_users = InstagramUser.objects.filter(status='connected').count()
    needs_reauth_users = InstagramUser.objects.filter(status='needs_reauth').count()

    posts_by_status = Post.objects.values('status').annotate(count=Count('id'))
    status_counts = {'published': 0, 'deleted': 0, 'failed': 0, 'queued': 0, 'publishing': 0}
    for item in posts_by_status:
        status_counts[item['status']] = item['count']

    total_metrics = Post.objects.aggregate(
        total_views=Coalesce(Sum('views'), 0),
        total_likes=Coalesce(Sum('likes'), 0),
        total_comments=Coalesce(Sum('comments_count'), 0),
    )

    total_prizes = Prize.objects.count()

    seven_days_from_now = timezone.now() + timedelta(days=7)
    expiring_tokens_count = InstagramUser.objects.filter(
        token_expires_at__isnull=False,
        token_expires_at__lte=seven_days_from_now,
        status='connected'
    ).count()

    users_by_status = InstagramUser.objects.values('status').annotate(count=Count('id'))
    links_by_status = UniqueLink.objects.values('status').annotate(count=Count('id'))

    errors_last_hour = get_instagram_errors_last_hour()

    data = {
        "total_users": total_users,
        "connected_users": connected_users,
        "needs_reauth_users": needs_reauth_users,
        "posts_by_status": status_counts,
        "total_metrics": {
            "total_views": total_metrics['total_views'],
            "total_likes": total_metrics['total_likes'],
            "total_comments": total_metrics['total_comments'],
        },
        "total_views": total_metrics['total_views'],
        "total_likes": total_metrics['total_likes'],
        "total_comments": total_metrics['total_comments'],
        "total_prizes": total_prizes,
        "expiring_tokens_count": expiring_tokens_count,
        # dashboard_stats mosligi uchun:
        "users_by_status": {item['status']: item['count'] for item in users_by_status},
        "links_by_status": {item['status']: item['count'] for item in links_by_status},
        "instagram_errors_last_hour": errors_last_hour,
        "dry_run": bool(getattr(settings, 'INSTAGRAM_DRY_RUN', False)),
    }

    cache.set('admin_summary_cache', data, timeout=60)
    return Response(AdminSummarySerializer(data).data)

dashboard_stats = admin_summary


# ==========================================
# User Statistika API lari (/api/me/...)
# ==========================================

@extend_schema(responses={200: MeSummarySerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_summary(request):
    """
    Faqat joriy foydalanuvchining o'z statistikasi:
    jami views, like, comment, postlar soni, prizlar soni, oxirgi tekshiruv vaqti.
    BOSQICH A: progress va milestone ma'lumotlari bilan qaytadi.
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    milestones = get_configured_milestones()
    
    if not ig_user:
        data = {
            "total_views": 0,
            "total_likes": 0,
            "total_comments": 0,
            "posts_count": 0,
            "prizes_count": 0,
            "last_checked_at": None,
            "next_milestone": milestones[0] if milestones else None,
            "views_remaining": milestones[0] if milestones else None,
            "progress_percent": 0.0,
            "milestones": milestones,
        }
        return Response(MeSummarySerializer(data).data)

    posts_qs = Post.objects.filter(link__user=ig_user)
    metrics = posts_qs.aggregate(
        total_views=Coalesce(Sum('views'), 0),
        total_likes=Coalesce(Sum('likes'), 0),
        total_comments=Coalesce(Sum('comments_count'), 0),
        last_checked_at=Max('last_checked_at'),
    )

    total_views = metrics['total_views']
    
    next_milestone = None
    prev_milestone = 0
    for m in sorted(milestones):
        if total_views < m:
            next_milestone = m
            break
        prev_milestone = m

    views_remaining = (next_milestone - total_views) if next_milestone else 0
    progress_percent = 100.0
    if next_milestone:
        range_size = next_milestone - prev_milestone
        current_in_range = total_views - prev_milestone
        progress_percent = min(100.0, max(0.0, (current_in_range / range_size) * 100.0)) if range_size > 0 else 0.0

    posts_count = posts_qs.count()
    prizes_count = Prize.objects.filter(post__link__user=ig_user).count()

    data = {
        "total_views": total_views,
        "total_likes": metrics['total_likes'],
        "total_comments": metrics['total_comments'],
        "posts_count": posts_count,
        "prizes_count": prizes_count,
        "last_checked_at": metrics['last_checked_at'],
        "next_milestone": next_milestone,
        "views_remaining": views_remaining,
        "progress_percent": progress_percent,
        "milestones": milestones,
    }

    return Response(MeSummarySerializer(data).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_posts(request):
    """
    Foydalanuvchining o'z postlari (pagination bilan va tartiblash imkoniyati).
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    if not ig_user:
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    ordering = request.GET.get('ordering', '-id')
    allowed_orderings = {
        'id', '-id',
        'views', '-views',
        'posted_at', '-posted_at',
        'likes', '-likes',
        'comments_count', '-comments_count',
        'status', '-status',
    }
    if ordering not in allowed_orderings:
        ordering = '-id'

    qs = Post.objects.select_related('link__user').filter(link__user=ig_user).order_by(ordering)
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = PostSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_post_history(request, post_id):
    """
    PostStat tarixi (grafik uchun, vaqt bo'yicha o'sish tartibida).
    Agar post nashr qilingan bo'lsa va oxirgi tekshiruvdan kamida 5 daqiqa o'tgan bo'lsa,
    foydalanuvchi ko'rganda yangi metrikalar olinib, PostStat yoziladi.
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    if not ig_user:
        return Response({"error": "Post topilmadi"}, status=status.HTTP_404_NOT_FOUND)

    post = get_object_or_404(Post.objects.select_related('link__user'), id=post_id, link__user=ig_user)

    if post.status == 'published' and post.ig_media_id:
        now = timezone.now()
        if not post.last_checked_at or (now - post.last_checked_at) >= timedelta(minutes=5):
            try:
                update_post_metrics(post)
            except Exception as exc:
                logger.warning("me_post_history ichida post metrikasini yangilashda xatolik: %s", exc)

    stats = post.stats.all().order_by('checked_at')
    data = [
        {
            "id": s.id,
            "checked_at": s.checked_at,
            "views": s.views,
            "likes": s.likes,
            "comments_count": s.comments_count,
        }
        for s in stats
    ]
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_notifications(request):
    """
    Foydalanuvchining bildirishnomalari va o'qilmaganlar soni.
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    if not ig_user:
        return Response({"unread_count": 0, "count": 0, "next": None, "previous": None, "results": []})

    qs = Notification.objects.filter(user=ig_user).order_by('-created_at')
    unread_count = qs.filter(is_read=False).count()

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = NotificationSerializer(page, many=True)
    resp = paginator.get_paginated_response(serializer.data)
    resp.data['unread_count'] = unread_count
    return resp


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def me_notifications_read(request):
    """
    Bildirishnomani o'qilgan deb belgilash (bitta yoki barchasini).
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    if not ig_user:
        return Response({"message": "Barcha bildirishnomalar o'qildi deb belgilandi.", "affected": 0})

    notif_id = request.data.get('id')
    if notif_id:
        notif = get_object_or_404(Notification, id=notif_id, user=ig_user)
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        return Response({"message": "Bildirishnoma o'qildi deb belgilandi.", "affected": 1})

    affected = Notification.objects.filter(user=ig_user, is_read=False).update(is_read=True)
    return Response({"message": "Barcha bildirishnomalar o'qildi deb belgilandi.", "affected": affected})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me_prizes(request):
    """
    Foydalanuvchining sovrinlari.
    """
    user = request.user
    ig_user = getattr(user, 'instagram_user', None)
    if not ig_user:
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    qs = Prize.objects.filter(post__link__user=ig_user).select_related('post__link__user').order_by('-id')
    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = PrizeSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


# ==========================================
# Admin Statistika API lari (/api/admin/...)
# ==========================================

@api_view(['GET'])
@permission_classes([IsAdminRole])
def admin_users_list(request):
    """
    Admin: Har user bo'yicha statistika (postlar, views, likes, comments, oxirgi post sanasi, holati),
    qidiruv, filtr, saralash va pagination bilan. N+1 yo'q.
    """
    qs = InstagramUser.objects.select_related('user').annotate(
        posts_count=Count('links__post', distinct=True),
        total_views=Coalesce(Sum('links__post__views'), 0),
        total_likes=Coalesce(Sum('links__post__likes'), 0),
        total_comments=Coalesce(Sum('links__post__comments_count'), 0),
        last_posted_at=Max('links__post__posted_at'),
    )

    search = request.query_params.get('search')
    if search:
        qs = qs.filter(
            Q(name__icontains=search) |
            Q(user__username__icontains=search) |
            Q(ig_user_id__icontains=search)
        )

    status_param = request.query_params.get('status')
    if status_param:
        qs = qs.filter(status=status_param)

    ordering = request.query_params.get('ordering', '-id')
    valid_orderings = ['id', '-id', 'total_views', '-total_views', 'posts_count', '-posts_count', 'created_at', '-created_at', 'last_posted_at', '-last_posted_at']
    if ordering in valid_orderings:
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by('-id')

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request)
    data = [
        {
            "id": u.id,
            "username": u.user.username if u.user else "",
            "name": u.name,
            "ig_user_id": u.ig_user_id,
            "status": u.status,
            "posts_count": u.posts_count,
            "total_views": u.total_views,
            "total_likes": u.total_likes,
            "total_comments": u.total_comments,
            "last_posted_at": u.last_posted_at,
            "created_at": u.created_at,
            "has_token": bool(u.access_token),
        }
        for u in page
    ]
    return paginator.get_paginated_response(data)


@api_view(['GET'])
@permission_classes([IsAdminRole])
def admin_user_detail(request, user_id):
    """
    Admin: Foydalanuvchi tafsilotlari va uning postlari / statistikasi tarixi.
    """
    u = get_object_or_404(
        InstagramUser.objects.select_related('user').annotate(
            posts_count=Count('links__post', distinct=True),
            total_views=Coalesce(Sum('links__post__views'), 0),
            total_likes=Coalesce(Sum('links__post__likes'), 0),
            total_comments=Coalesce(Sum('links__post__comments_count'), 0),
            last_posted_at=Max('links__post__posted_at'),
        ),
        pk=user_id
    )

    posts = Post.objects.filter(link__user=u).order_by('-id').prefetch_related('stats')
    posts_data = []
    all_history = []
    
    for p in posts:
        history_list = []
        for s in p.stats.all():
            hist_item = {
                "checked_at": s.checked_at,
                "views": s.views,
                "likes": s.likes,
                "comments_count": s.comments_count,
            }
            history_list.append(hist_item)
            
            all_history.append({
                "checked_at": s.checked_at,
                "views": s.views,
                "likes": s.likes,
                "timestamp": s.checked_at.timestamp() * 1000
            })
            
        posts_data.append({
            "id": p.id,
            "status": p.status,
            "permalink": p.permalink,
            "views": p.views,
            "likes": p.likes,
            "comments_count": p.comments_count,
            "posted_at": p.posted_at,
            "deleted_detected_at": p.deleted_detected_at,
            "history": history_list
        })
        
    # Tarixni vaqt bo'yicha o'sish tartibida saralash (chart uchun)
    all_history.sort(key=lambda x: x["timestamp"])
    # Front-end kutilayotgan formatga o'tkazish
    formatted_history = []
    for h in all_history:
        formatted_history.append({
            "time": h["checked_at"].strftime('%d %b %H:%M') if h["checked_at"] else "",
            "timestamp": h["timestamp"],
            "views": h["views"],
            "likes": h["likes"]
        })

    return Response({
        "id": u.id,
        "username": u.user.username if u.user else "",
        "name": u.name,
        "ig_user_id": u.ig_user_id,
        "status": u.status,
        "posts_count": u.posts_count,
        "total_views": u.total_views,
        "total_likes": u.total_likes,
        "total_comments": u.total_comments,
        "last_posted_at": u.last_posted_at,
        "created_at": u.created_at,
        "posts": posts_data,
        "all_history": formatted_history
    })


@api_view(['GET'])
@permission_classes([IsAdminRole])
def admin_posts_list(request):
    """
    Admin: Filtr (status, sana oralig'i, user), saralash (views), pagination bilan postlar ro'yxati.
    O'chirilgan postlar va deleted_detected_at ko'rinadi.
    """
    qs = Post.objects.select_related('link__user').all()

    status_param = request.query_params.get('status')
    if status_param:
        qs = qs.filter(status=status_param)

    user_param = request.query_params.get('user')
    if user_param:
        qs = qs.filter(link__user_id=user_param)

    start_date = request.query_params.get('start_date')
    if start_date:
        qs = qs.filter(posted_at__date__gte=start_date)
    end_date = request.query_params.get('end_date')
    if end_date:
        qs = qs.filter(posted_at__date__lte=end_date)

    ordering = request.query_params.get('ordering', '-id')
    valid_orderings = ['views', '-views', 'posted_at', '-posted_at', 'id', '-id']
    if ordering in valid_orderings:
        qs = qs.order_by(ordering)
    else:
        qs = qs.order_by('-id')

    paginator = StandardResultsSetPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = PostSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAdminRole])
def admin_stats_daily(request):
    """
    Admin: Kunlar bo'yicha yangi postlar va jami views (grafik uchun).
    """
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')

    qs = Post.objects.filter(posted_at__isnull=False)
    if start_date:
        qs = qs.filter(posted_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(posted_at__date__lte=end_date)
    if not start_date and not end_date:
        thirty_days_ago = timezone.now().date() - timedelta(days=30)
        qs = qs.filter(posted_at__date__gte=thirty_days_ago)

    daily_stats = (
        qs.annotate(date=TruncDate('posted_at'))
        .values('date')
        .annotate(
            new_posts=Count('id'),
            total_views=Coalesce(Sum('views'), 0),
            total_likes=Coalesce(Sum('likes'), 0),
        )
        .order_by('date')
    )
    return Response(list(daily_stats))


@api_view(['GET'])
@permission_classes([IsAdminRole])
def admin_export_posts_csv(request):
    """
    Admin: Filtrga mos postlarni oqimli (StreamingHttpResponse) CSV qilib eksport qilish.
    Katta ma'lumotlarda xotirani to'ldirmaydi.
    """
    qs = Post.objects.select_related('link__user').all()

    status_param = request.query_params.get('status')
    if status_param:
        qs = qs.filter(status=status_param)

    user_param = request.query_params.get('user')
    if user_param:
        qs = qs.filter(link__user_id=user_param)

    start_date = request.query_params.get('start_date')
    if start_date:
        qs = qs.filter(posted_at__date__gte=start_date)
    end_date = request.query_params.get('end_date')
    if end_date:
        qs = qs.filter(posted_at__date__lte=end_date)

    qs = qs.order_by('-id')

    def row_generator():
        pseudo_buffer = Echo()
        writer = csv.writer(pseudo_buffer)
        yield writer.writerow(['Post ID', 'User', 'Status', 'Views', 'Likes', 'Comments', 'Posted At', 'Deleted Detected At', 'Permalink'])
        for post in qs.iterator(chunk_size=2000):
            user_name = post.link.user.name if hasattr(post, 'link') and post.link and post.link.user else ""
            yield writer.writerow([
                post.id,
                user_name,
                post.status,
                post.views,
                post.likes,
                post.comments_count,
                post.posted_at.strftime('%Y-%m-%d %H:%M:%S') if post.posted_at else "",
                post.deleted_detected_at.strftime('%Y-%m-%d %H:%M:%S') if post.deleted_detected_at else "",
                post.permalink or "",
            ])

    response = StreamingHttpResponse(row_generator(), content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="posts.csv"'
    return response


@extend_schema(responses={200: UserProfileOutputSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_profile(request):
    """
    Joriy tizimga kirgan foydalanuvchi ma'lumotlari va roli (/api/me/).
    """
    user = request.user
    ig_profile = getattr(user, 'instagram_user', None)
    
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "role": "admin" if (user.is_staff or user.is_superuser) else "user",
        "instagram_user": ig_profile,
        "dry_run": bool(getattr(settings, 'INSTAGRAM_DRY_RUN', False)),
    }
    return Response(UserProfileOutputSerializer(data).data)


@extend_schema(request=AdminCreateUserSerializer, responses={201: AdminCreateUserOutputSerializer, 400: dict})
@api_view(['POST'])
@permission_classes([IsAdminRole])
def admin_create_user(request):
    """
    Faqat admin uchun: Yangi foydalanuvchi (Django User + InstagramUser) yaratish.
    """
    serializer = AdminCreateUserSerializer(data=request.data)
    if serializer.is_valid():
        ig_user = serializer.save()
        output = AdminCreateUserOutputSerializer(ig_user).data
        return Response(output, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(request=UserRegisterSerializer, responses={201: dict, 400: dict})
@api_view(['POST'])
@permission_classes([AllowAny])
def register_user(request):
    """
    Ommaviy ro'yxatdan o'tish (Sign Up) API si.
    Yangi foydalanuvchi va uning Instagram profilini yaratadi,
    darhol JWT access va refresh tokenlarini qaytaradi.
    """
    serializer = UserRegisterSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    ig_user = serializer.save()
    user = ig_user.user

    refresh = RefreshToken.for_user(user)
    access = str(refresh.access_token)

    return Response({
        "message": "Muvaffaqiyatli ro'yxatdan o'tdingiz!",
        "access": access,
        "refresh": str(refresh),
        "role": "user",
        "username": user.username,
        "user_id": user.id,
        "name": ig_user.name,
        "instagram_user_id": ig_user.id,
        "status": ig_user.status,
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Oddiy user yoki admin o'z parolini eski parolni kiritish orqali yangilaydi.
    """
    serializer = ChangePasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    old_password = serializer.validated_data['old_password']
    new_password = serializer.validated_data['new_password']
    if not request.user.check_password(old_password):
        return Response({"error": "Eski parol noto'g'ri kiritildi."}, status=status.HTTP_400_BAD_REQUEST)
    request.user.set_password(new_password)
    request.user.save()
    return Response({"message": "Parol muvaffaqiyatli o'zgartirildi."})


@api_view(['POST'])
@permission_classes([IsAdminRole])
def admin_reset_password(request):
    """
    Faqat admin uchun: istalgan userning parolini tiklash.
    """
    serializer = ResetPasswordSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    user_id = serializer.validated_data.get('user_id')
    new_password = serializer.validated_data['new_password']
    try:
        target_user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return Response({"error": "Foydalanuvchi topilmadi."}, status=status.HTTP_404_NOT_FOUND)
    target_user.set_password(new_password)
    target_user.save()
    return Response({"message": f"Foydalanuvchi ({target_user.username}) paroli muvaffaqiyatli tiklandi."})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def user_connect_instagram(request):
    """
    Foydalanuvchi o'z kabinetidan Instagramga ulanish oqimini boshlaydi.
    """
    ig_user, _ = InstagramUser.objects.get_or_create(
        user=request.user,
        defaults={'name': request.user.username}
    )
    from .models import get_video_for_user
    chosen_video = get_video_for_user(ig_user)

    link = UniqueLink.objects.filter(user=ig_user, status__in=['pending', 'opened']).order_by('-id').first()
    if not link:
        link = UniqueLink.objects.create(user=ig_user, video=chosen_video)
    elif not link.video and chosen_video:
        link.video = chosen_video
        link.save(update_fields=['video'])

    auth_url = build_instagram_auth_url(str(link.token))
    return Response({
        "auth_url": auth_url,
        "link_token": str(link.token),
        "status": ig_user.status,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_publish_video(request):
    """
    Ulangan foydalanuvchi uchun videoni Reels qilib joylash vazifasini boshlaydi.
    Takroriy bosishdan himoyalangan (queued/publishing bo'lsa yangisini boshlamaydi).
    """
    ig_user = getattr(request.user, 'instagram_user', None)
    if not ig_user or ig_user.status != 'connected' or not ig_user.access_token:
        return Response(
            {"error": "Instagram hisobingiz ulanmagan. Iltimos, avval hisobingizni ulang."},
            status=status.HTTP_400_BAD_REQUEST
        )

    from .models import get_video_for_user
    chosen_video = get_video_for_user(ig_user)
    if not chosen_video:
        return Response(
            {"error": "Joylash uchun video topilmadi. Iltimos, avval 'Mening videom' sahifasida video yuklang yoki admin umumiy video yuklashini kuting."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Takroriy bosishdan himoya: faqat haqiqatan jarayondagi postlar (failed postlar bloklamaydi)
    active_post = Post.objects.filter(
        link__user=ig_user,
        status__in=['queued', 'publishing']
    ).first()
    if active_post:
        ref_time = active_post.posted_at or active_post.link.created_at
        if ref_time and (timezone.now() - ref_time) > timedelta(minutes=10):
            active_post.status = 'failed'
            active_post.error = "Jarayon vaqti tugadi (timeout). Qayta urinib ko'ring."
            active_post.save(update_fields=['status', 'error'])
            active_post = None

    if active_post:
        return Response({
            "error": "Videoni joylash allaqachon jarayonda. Iltimos, jarayon yakunlanishini kuting.",
            "post_id": active_post.id,
            "status": active_post.status,
        }, status=status.HTTP_409_CONFLICT)

    link = UniqueLink.objects.filter(user=ig_user, post__isnull=True).order_by('-id').first()
    if not link:
        link = UniqueLink.objects.create(user=ig_user, video=chosen_video)
    else:
        if link.video != chosen_video:
            link.video = chosen_video
            link.save(update_fields=['video'])

    post, _ = Post.objects.get_or_create(link=link)
    post.status = 'queued'
    post.error = None
    post.save(update_fields=['status', 'error'])

    publish_reels_task.delay(link.id)

    return Response({
        "message": "Video Reels sifatida joylash navbatiga qo'yildi.",
        "post_id": post.id,
        "status": post.status,
        "link_token": str(link.token)
    }, status=status.HTTP_202_ACCEPTED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_upload_video(request):
    """
    Foydalanuvchi o'zining shaxsiy Reels videosini yuklaydi.
    """
    ig_user, _ = InstagramUser.objects.get_or_create(
        user=request.user,
        defaults={'name': request.user.username}
    )
    if not request.FILES.get('file'):
        return Response({"error": "Video fayl tanlanishi shart."}, status=status.HTTP_400_BAD_REQUEST)

    serializer = VideoSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    video = serializer.save(owner=ig_user, is_default=False, is_active=True)
    return Response(VideoSerializer(video).data, status=status.HTTP_201_CREATED)


@extend_schema(responses={200: UserPublishStatusOutputSerializer})
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_publish_status(request):
    """
    Foydalanuvchi o'zining so'nggi post holatini (polling) tekshiradi.
    BOSQICH A: can_publish, can_publish_reason, can_retry, retries_left, upload_limits maydonlari qo'shiladi.
    """
    ig_user = getattr(request.user, 'instagram_user', None)
    
    upload_limits = {
        "max_size_mb": getattr(settings, 'MAX_VIDEO_SIZE_MB', 100),
        "allowed_types": [".mp4"]
    }

    base_response = {
        "upload_limits": upload_limits,
        "can_publish": False,
        "can_publish_reason": None,
        "can_retry": False,
        "retries_left": 0,
        "has_post": False,
        "status": "none",
    }

    if not ig_user or ig_user.status != 'connected':
        base_response["can_publish_reason"] = "Instagram hisob ulanmagan."
        return Response(UserPublishStatusOutputSerializer(base_response).data)

    from .models import get_video_for_user
    chosen_video = get_video_for_user(ig_user)
    has_video = bool(chosen_video)

    post = Post.objects.filter(link__user=ig_user).order_by('-id').first()
    
    if not post:
        if not has_video:
            base_response["can_publish"] = False
            base_response["can_publish_reason"] = "Joylash uchun video mavjud emas. Iltimos, video yuklang."
        else:
            base_response["can_publish"] = True
        return Response(UserPublishStatusOutputSerializer(base_response).data)

    retries_left = max(0, 3 - post.retry_count)
    can_retry = post.status == 'failed' and retries_left > 0
    
    can_publish = False
    can_publish_reason = None
    
    if post.status in ['queued', 'publishing']:
        ref_time = post.posted_at or post.link.created_at
        if ref_time and (timezone.now() - ref_time) > timedelta(minutes=10):
            post.status = 'failed'
            post.error = "Jarayon vaqti tugadi (timeout). Qayta urinib ko'ring."
            post.save(update_fields=['status', 'error'])
            retries_left = max(0, 3 - post.retry_count)
            can_retry = retries_left > 0
            if not has_video:
                can_publish = False
                can_publish_reason = "Joylash uchun video mavjud emas. Iltimos, video yuklang."
            else:
                can_publish = True
        else:
            can_publish_reason = "Jarayonda bo'lgan post mavjud."
    elif not has_video:
        can_publish = False
        can_publish_reason = "Joylash uchun video mavjud emas. Iltimos, video yuklang."
    else:
        can_publish = True

    response_data = {
        **base_response,
        "has_post": True,
        "post_id": post.id,
        "status": post.status,
        "posted_at": post.posted_at,
        "views": post.views,
        "likes": post.likes,
        "comments_count": post.comments_count,
        "permalink": post.permalink,
        "error": post.error,
        "retry_count": post.retry_count,
        "can_retry": can_retry,
        "retries_left": retries_left,
        "can_publish": can_publish,
        "can_publish_reason": can_publish_reason,
    }

    return Response(UserPublishStatusOutputSerializer(response_data).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_retry_publish(request):
    """
    Muvaffaqiyatsiz bo'lgan postni qayta urinish (maksimal 3 marta).
    """
    ig_user = getattr(request.user, 'instagram_user', None)
    if not ig_user:
        return Response({"error": "Instagram foydalanuvchisi topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    post = Post.objects.filter(link__user=ig_user, status='failed').order_by('-id').first()
    if not post:
        return Response({"error": "Qayta urinish uchun xato bo'lgan post topilmadi."}, status=status.HTTP_404_NOT_FOUND)

    if post.retry_count >= 3:
        return Response({
            "error": "Qayta urinishlar soni tugadi (maksimal: 3 marta). Iltimos administrator bilan bog'laning.",
            "retry_count": post.retry_count
        }, status=status.HTTP_400_BAD_REQUEST)

    post.retry_count += 1
    post.status = 'queued'
    post.error = None
    post.save(update_fields=['status', 'error', 'retry_count'])

    publish_reels_task.delay(post.link.id)

    return Response({
        "message": "Video qayta joylash navbatiga qo'yildi.",
        "post_id": post.id,
        "status": post.status,
        "retry_count": post.retry_count
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def link_info(request):
    return Response({
        "message": "Unikal link formati: /link/<token>/",
        "example": "Admin paneldan yangi UniqueLink yarating va linkka kiring."
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def redirect_to_instagram(request, token):
    link = get_object_or_404(UniqueLink, token=token)

    # Muddati o'tganligini tekshirish
    if link.expires_at and timezone.now() > link.expires_at:
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Link muddati tugagan',
            'message': 'Ushbu unikal linkning amal qilish muddati tugagan. Iltimos yangi link so\'rang.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Yakunlangan yoki xato linklarni tekshirish
    if link.status in ('posted', 'failed'):
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Link faol emas',
            'message': f"Ushbu link allaqachon ishlatilgan yoki bekor qilingan (holati: {link.status})."
        }, status=status.HTTP_400_BAD_REQUEST)

    # Statusni ochilgan holatga o'tkazish
    if link.status == 'pending':
        link.status = 'opened'
        link.save(update_fields=['status'])

    auth_url = build_instagram_auth_url(str(link.token))

    # Agar INSTAGRAM_APP_ID belgilanmagan bo'lsa (dev/test), preview qaytaramiz
    if not settings.INSTAGRAM_APP_ID:
        return render(request, 'tracker/status.html', {
            'is_success': True,
            'status_class': 'success',
            'title': 'Test Rejimi',
            'message': 'INSTAGRAM_APP_ID sozlanmagan.',
            'description': f'Aslida quyidagi manzilga o\'tilishi kerak edi: {auth_url}'
        })

    # return render(request, 'tracker/landing.html', {
    #     'auth_url': auth_url
    # })
    return HttpResponseRedirect(auth_url)


@api_view(['GET'])
@permission_classes([AllowAny])
def instagram_callback(request):
    # Foydalanuvchi rad etgan yoki Instagram xatolik qaytargan holat
    if request.GET.get('error'):
        state = request.GET.get('state')
        if state:
            UniqueLink.objects.filter(token=state, status__in=('pending', 'opened')).update(status='failed')
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Ruxsat rad etildi',
            'message': 'Siz Instagram orqali ruxsat bermadingiz.',
            'description': request.GET.get('error_description') or "Instagram xatolik qaytardi."
        }, status=status.HTTP_400_BAD_REQUEST)

    code = request.GET.get('code')
    state = request.GET.get('state')

    if not code or not state:
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Xatolik',
            'message': 'Kerakli parametrlar (code va state) topilmadi.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Callback link holati va muddatini tekshirish (qayta ishlatilgan yoki muddati o'tgan linklar uchun)
    link_obj = get_object_or_404(UniqueLink, token=state)
    if link_obj.status in ('posted', 'failed') or (hasattr(link_obj, 'post') and link_obj.post.status == 'published'):
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Link ishlatilgan',
            'message': 'Bu link orqali allaqachon amal bajarilgan.'
        }, status=status.HTTP_400_BAD_REQUEST)

    if link_obj.expires_at and timezone.now() > link_obj.expires_at:
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Link muddati tugagan',
            'message': 'Linkning amal qilish muddati tugagan.'
        }, status=status.HTTP_400_BAD_REQUEST)

    try:
        user, link = complete_instagram_oauth(code=code, token=state)
    except InstagramOAuthError as exc:
        logger.error("InstagramOAuthError: %s", mask_sensitive_data(str(exc)))
        UniqueLink.objects.filter(token=state, status__in=('pending', 'opened')).update(status='failed')
        return render(request, 'tracker/status.html', {
            'is_success': False,
            'status_class': 'error',
            'title': 'Avtorizatsiya xatosi',
            'message': 'Instagram bilan ulanishda xatolik yuz berdi.',
            'description': 'Iltimos, qaytadan urinib ko\'ring yoki administrator bilan bog\'laning.'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Reels videoni Instagram'ga joylash vazifasini Celery orqali ishga tushirish
    publish_reels_task.delay(link.id)

    return render(request, 'tracker/status.html', {
        'is_success': True,
        'status_class': 'success',
        'title': 'Muvaffaqiyatli Ulandi!',
        'message': f'Salom {user.name}, hisobingiz ulandi.',
        'portal_url': f'/my-post/{link.token}/',
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def user_portal(request, token):
    link = get_object_or_404(UniqueLink, token=token)
    post = getattr(link, 'post', None)
    prizes = post.prizes.all().order_by('milestone') if post else []
    return render(request, 'tracker/user_portal.html', {
        'link': link,
        'post': post,
        'prizes': prizes,
    })


@api_view(['GET'])
@permission_classes([AllowAny])
def user_portal_api(request, token):
    link = get_object_or_404(UniqueLink, token=token)
    post = getattr(link, 'post', None)

    if not post:
        return Response({"status": "pending"}, status=status.HTTP_200_OK)

    return Response({
        "status": post.status,
        "permalink": post.permalink,
        "views": post.views,
        "likes": post.likes,
        "comments_count": post.comments_count,
        "posted_at": post.posted_at,
        # "last_checked_at": post.last_checked_at,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def instagram_deauthorize(request):
    """
    Meta Deauthorize Callback URL.
    """
    signed_request = request.data.get('signed_request')
    if not signed_request:
        return Response(
            {"error": "'signed_request' parametri talab qilinadi."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        data = parse_signed_request(signed_request, settings.INSTAGRAM_APP_SECRET)
    except MetaWebhookError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user_id = data.get('user_id')
    if not user_id:
        return Response({"error": "signed_request ichida 'user_id' topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

    updated_count = handle_deauthorize_request(user_id)
    return Response({
        "success": True,
        "message": "Foydalanuvchi muvaffaqiyatli deautorizatsiya qilindi.",
        "affected_records": updated_count,
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([AllowAny])
def instagram_data_deletion(request):
    """
    Meta Data Deletion Request Callback URL.
    """
    signed_request = request.data.get('signed_request')
    if not signed_request:
        return Response(
            {"error": "'signed_request' parametri talab qilinadi."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        data = parse_signed_request(signed_request, settings.INSTAGRAM_APP_SECRET)
    except MetaWebhookError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    user_id = data.get('user_id')
    if not user_id:
        return Response({"error": "signed_request ichida 'user_id' topilmadi."}, status=status.HTTP_400_BAD_REQUEST)

    status_url, confirmation_code = handle_data_deletion_request(user_id)

    return Response({
        "url": status_url,
        "confirmation_code": confirmation_code
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def data_deletion_status(request, confirmation_code):
    record = get_object_or_404(DataDeletionRequest, confirmation_code=confirmation_code)

    if record.status == 'completed':
        message = "Sizning barcha ma'lumotlaringiz tizimdan to'liq o'chirildi."
    elif record.status == 'pending':
        message = "Ma'lumotlarni o'chirish so'rovi qabul qilindi va navbatda turibdi."
    else:
        message = "Ma'lumotlarni o'chirishda xatolik yuz berdi. Iltimos qayta murojaat qiling."

    return Response({
        "confirmation_code": record.confirmation_code,
        "status": record.status,
        "requested_at": record.requested_at,
        "message": message,
    }, status=status.HTTP_200_OK)


@api_view(['GET', 'POST'])
@permission_classes([AllowAny])
def instagram_webhook(request):
    """
    Meta Instagram Webhook endpoint:
    - GET: hub.challenge tekshiruvi (Meta Developers App Dashboard orqali ulanishda)
    - POST: real-vaqt hodisalari (mentions, comments, media container yangilanishlari)
    """
    from django.http import HttpResponse

    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        verify_token = getattr(settings, 'INSTAGRAM_WEBHOOK_VERIFY_TOKEN', 'insta_checker_webhook_token')
        if mode == 'subscribe' and token == verify_token:
            return HttpResponse(challenge, content_type="text/plain")
        return HttpResponse("Forbidden", status=status.HTTP_403_FORBIDDEN)

    # POST so'rovi
    data = request.data
    logger.info("Instagram Webhook hodisasi qabul qilindi: %s", data)

    try:
        entries = data.get('entry', []) if isinstance(data, dict) else []
        for entry in entries:
            changes = entry.get('changes', [])
            for change in changes:
                val = change.get('value', {})
                media_id = val.get('media_id')
                if media_id:
                    post = Post.objects.filter(ig_media_id=str(media_id)).first()
                    if post:
                        from .tasks import check_post_metrics_task
                        check_post_metrics_task.delay(post.id)
    except Exception as exc:
        logger.error("Instagram Webhook event qayta ishlashda xatolik: %s", exc)

    return Response({"status": "ok"}, status=status.HTTP_200_OK)

