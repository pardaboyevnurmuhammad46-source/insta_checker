from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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


class InstagramUserViewSet(viewsets.ModelViewSet):
    queryset = InstagramUser.objects.all()
    serializer_class = InstagramUserSerializer

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
    queryset = UniqueLink.objects.all()
    serializer_class = UniqueLinkSerializer


class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer

    @action(detail=True, methods=['post'], url_path='check-metrics')
    def check_metrics(self, request, pk=None):
        post = self.get_object()
        task = check_post_metrics_task.delay(post.id)
        return Response({"message": "Post statistikasini tekshirish vazifasi navbatga qo'yildi.", "task_id": task.id})


class PrizeViewSet(viewsets.ModelViewSet):
    queryset = Prize.objects.all()
    serializer_class = PrizeSerializer


class DataDeletionRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DataDeletionRequest.objects.all().order_by('-requested_at')
    serializer_class = DataDeletionRequestSerializer


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
            # --- Eski kod (komentga olindi): UniqueLink.objects.filter(token=state).update(status='failed')
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
    if link_obj.status in ('posted', 'failed') or hasattr(link_obj, 'post'):
        return Response({"error": "Bu link allaqachon ishlatilgan."}, status=status.HTTP_400_BAD_REQUEST)
    if link_obj.expires_at and timezone.now() > link_obj.expires_at:
        return Response({"error": "Link muddati tugagan."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        user, link = complete_instagram_oauth(code=code, token=state)
    except InstagramOAuthError as exc:
        # --- Eski kod (komentga olindi): UniqueLink.objects.filter(token=state).update(status='failed')
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
    Foydalanuvchi ilovadan ruxsatni olib tashlaganida Meta tomonidan POST so'rovi yuboriladi.
    """
    # --- Eski kod (komentga olindi): signed_request = request.POST.get('signed_request') or request.data.get('signed_request')
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
    Meta foydalanuvchi ma'lumotlarini o'chirish so'rovini yuboradi.
    Meta formati bo'yicha javob qaytaramiz: {"url": "...", "confirmation_code": "..."}
    """
    # --- Eski kod (komentga olindi): signed_request = request.POST.get('signed_request') or request.data.get('signed_request')
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

    # --- Eski qotirib yozilgan xabar (komentga olindi):
    # message = "Instagram hisobingizga oid saqlangan ma'lumotlar to'liq o'chirildi."
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
