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
    queryset = InstagramUser.objects.all()
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


@api_view(['GET'])
@permission_classes([AllowAny])
def redirect_to_instagram(request, token):
    link = get_object_or_404(UniqueLink, token=token)

    # Muddati o'tganligini tekshirish
    if link.expires_at and timezone.now() > link.expires_at:
        return Response(
            {"error": "Ushbu unikal linkning amal qilish muddati tugagan."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Yakunlangan yoki xato linklarni tekshirish
    if link.status in ('posted', 'failed'):
        return Response(
            {"error": f"Ushbu link bilan amal bajarib bo'lmaydi (status: {link.status})."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Statusni ochilgan holatga o'tkazish
    if link.status == 'pending':
        link.status = 'opened'
        link.save(update_fields=['status'])

    auth_url = build_instagram_auth_url(str(link.token))

    # Agar INSTAGRAM_APP_ID belgilanmagan bo'lsa (dev/test), preview qaytaramiz
    if not settings.INSTAGRAM_APP_ID:
        return Response({
            "message": "INSTAGRAM_APP_ID sozlanmagan (.env faylida ko'rsating).",
            "auth_url_preview": auth_url,
            "token": str(link.token),
            "status": link.status,
        }, status=status.HTTP_200_OK)

    return HttpResponseRedirect(auth_url)


@api_view(['GET'])
@permission_classes([AllowAny])
def instagram_callback(request):
    # Foydalanuvchi rad etgan yoki Instagram xatolik qaytargan holat
    if request.GET.get('error'):
        state = request.GET.get('state')
        if state:
            UniqueLink.objects.filter(token=state, status__in=('pending', 'opened')).update(status='failed')
        return Response({
            "error": request.GET.get('error'),
            "reason": request.GET.get('error_reason'),
            "description": request.GET.get('error_description') or "Instagram orqali ruxsat berilmadi."
        }, status=status.HTTP_400_BAD_REQUEST)

    code = request.GET.get('code')
    state = request.GET.get('state')

    if not code or not state:
        return Response(
            {"error": "'code' va 'state' parametrlari talab qilinadi."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Callback link holati va muddatini tekshirish (qayta ishlatilgan yoki muddati o'tgan linklar uchun)
    link_obj = get_object_or_404(UniqueLink, token=state)
    if link_obj.status in ('posted', 'failed') or (hasattr(link_obj, 'post') and link_obj.post.status == 'published'):
        return Response({"error": "Bu link allaqachon ishlatilgan."}, status=status.HTTP_400_BAD_REQUEST)
    if link_obj.expires_at and timezone.now() > link_obj.expires_at:
        return Response({"error": "Link muddati tugagan."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user, link = complete_instagram_oauth(code=code, token=state)
    except InstagramOAuthError as exc:
        UniqueLink.objects.filter(token=state, status__in=('pending', 'opened')).update(status='failed')
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    # Reels videoni Instagram'ga joylash vazifasini Celery orqali ishga tushirish
    publish_reels_task.delay(link.id)

    return Response({
        "message": "Instagram hisobi muvaffaqiyatli ulandi va video Reels qilib joylanmoqda!",
        "user_name": user.name,
        "ig_user_id": user.ig_user_id,
        "user_status": user.status,
        "link_status": link.status,
    }, status=status.HTTP_200_OK)


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
