from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Sum
from datetime import timedelta
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .serializers import (
    InstagramUserSerializer,
    UniqueLinkSerializer,
    PostSerializer,
    PrizeSerializer,
    DataDeletionRequestSerializer,
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


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 100


class InstagramUserViewSet(viewsets.ModelViewSet):
    queryset = InstagramUser.objects.all().order_by("-id")
    serializer_class = InstagramUserSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'ig_user_id']
    ordering_fields = ['created_at']

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


class UniqueLinkViewSet(viewsets.ModelViewSet):
    queryset = UniqueLink.objects.select_related('user').all()
    serializer_class = UniqueLinkSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'user']
    search_fields = ['user__name']
    ordering_fields = ['created_at']

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
    queryset = Post.objects.select_related('link__user').all()
    serializer_class = PostSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'link__user']
    search_fields = ['link__user__name', 'ig_media_id']
    ordering_fields = ['views', 'posted_at']

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


class PrizeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Prize.objects.select_related('post__link__user').all()
    serializer_class = PrizeSerializer
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    ordering_fields = ['sent_at', 'milestone']


class DataDeletionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DataDeletionRequest.objects.all().order_by('-requested_at')
    serializer_class = DataDeletionRequestSerializer
    pagination_class = StandardResultsSetPagination


@api_view(['GET'])
@permission_classes([IsAdminUser])
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
@permission_classes([AllowAny])
def link_info(request):
    return Response({
        "message": "Unikal link formati: /link/<token>/",
        "example": "Admin paneldan yangi UniqueLink yarating va linkka kiring."
    })


from django.shortcuts import render

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
        import logging
        logging.getLogger(__name__).error(f"InstagramOAuthError: {exc}")
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
    prizes_data = []
    if post:
        prizes_data = [{'milestone': p.milestone, 'sent_at': p.sent_at} for p in post.prizes.all()]
    return Response({
        'user_name': link.user.name,
        'token': str(link.token),
        'status': link.status,
        'video_url': link.video.url if link.video else None,
        'post': {
            'status': post.status,
            'views': post.views,
            'likes': post.likes,
            'comments_count': post.comments_count,
            'permalink': post.permalink,
            'posted_at': post.posted_at,
        } if post else None,
        'prizes': prizes_data,
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
        "confirmation_code": confirmation_code,
    }, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([AllowAny])
def data_deletion_status(request, confirmation_code):
    """
    Foydalanuvchi o'z ma'lumotlari o'chirilganligini tekshirishi mumkin bo'lgan sahifa / API.
    """
    record = get_object_or_404(DataDeletionRequest, confirmation_code=confirmation_code)

    if record.status == 'completed':
        message = "Instagram hisobingizga oid saqlangan ma'lumotlar to'liq o'chirildi."
    elif record.status == 'failed':
        message = "Ma'lumotlarni o'chirish jarayonida xatolik yuz berdi. Iltimos qayta murojaat qiling."
    else:
        message = "Ma'lumotlarni o'chirish so'rovi qabul qilindi va ko'rib chiqilmoqda."

    return Response({
        "confirmation_code": record.confirmation_code,
        "user_id": record.user_id,
        "status": record.status,
        "requested_at": record.requested_at,
        "message": message,
    }, status=status.HTTP_200_OK)
