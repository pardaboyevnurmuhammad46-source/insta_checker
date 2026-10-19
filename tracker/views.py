import logging
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.db.models import Q

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
from .serializers import (
    InstagramUserSerializer,
    VideoSerializer,
    UniqueLinkSerializer,
    PostSerializer,
    PrizeSerializer,
    DataDeletionRequestSerializer,
    PostStatSerializer,
    NotificationSerializer,
    AdminCreateUserSerializer,
    ChangePasswordSerializer,
    ResetPasswordSerializer,
)
from .services import (
    InstagramOAuthError,
    MetaWebhookError,
    build_instagram_auth_url,
    complete_instagram_oauth,
    parse_signed_request,
    handle_deauthorize_request,
    handle_data_deletion_request,
    refresh_user_token,
)
from .tasks import publish_reels_task, check_post_metrics_task

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
    serializer_class = PostSerializer
    pagination_class = StandardResultsSetPagination
    permission_classes = [IsOwnerOrAdmin]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'link__user']
    search_fields = ['link__user__name', 'ig_media_id']
    # ordering_fields = ['views', 'posted_at']
    ordering_fields = ['views', 'posted_at', 'id']
    ordering = ['-id']

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
        post.status = 'queued'
        post.error = None
        post.save(update_fields=['status', 'error'])
        publish_reels_task.delay(post.link.id)
        return Response({"message": "Post qayta joylash uchun navbatga qo'yildi."})


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


@api_view(['GET'])
# @permission_classes([IsAdminUser])
@permission_classes([IsAdminRole])
def dashboard_stats(request):
    users_by_status = InstagramUser.objects.values('status').annotate(count=Count('id'))
    links_by_status = UniqueLink.objects.values('status').annotate(count=Count('id'))
    posts_by_status = Post.objects.values('status').annotate(count=Count('id'))

    total_metrics = Post.objects.aggregate(
        total_views=Sum('views'),
        total_likes=Sum('likes'),
        total_comments=Sum('comments_count')
    )

    total_prizes = Prize.objects.count()

    seven_days_from_now = timezone.now() + timedelta(days=7)
    expiring_tokens_count = InstagramUser.objects.filter(
        token_expires_at__isnull=False,
        token_expires_at__lte=seven_days_from_now,
        status='connected'
    ).count()

    return Response({
        "users_by_status": {item['status']: item['count'] for item in users_by_status},
        "links_by_status": {item['status']: item['count'] for item in links_by_status},
        "posts_by_status": {item['status']: item['count'] for item in posts_by_status},
        "total_metrics": total_metrics,
        "total_prizes": total_prizes,
        "expiring_tokens_count": expiring_tokens_count,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def current_user_profile(request):
    """
    Joriy tizimga kirgan foydalanuvchi ma'lumotlari va roli (/api/me/).
    """
    user = request.user
    role = "admin" if (user.is_staff or user.is_superuser) else "user"
    ig_profile = getattr(user, 'instagram_user', None)
    return Response({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
        "role": role,
        "instagram_user": InstagramUserSerializer(ig_profile).data if ig_profile else None
    })


@api_view(['POST'])
@permission_classes([IsAdminRole])
def admin_create_user(request):
    """
    Faqat admin uchun: Yangi foydalanuvchi (Django User + InstagramUser) yaratish.
    """
    serializer = AdminCreateUserSerializer(data=request.data)
    if serializer.is_valid():
        result = serializer.save()
        return Response(result, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
        logger.error(f"InstagramOAuthError: {exc}")
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
