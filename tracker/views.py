from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import InstagramUser, UniqueLink, Post, Prize
from .serializers import (
    InstagramUserSerializer,
    UniqueLinkSerializer,
    PostSerializer,
    PrizeSerializer,
)
from .services import (
    InstagramOAuthError,
    build_instagram_auth_url,
    complete_instagram_oauth,
)
from .tasks import publish_reels_task



class InstagramUserViewSet(viewsets.ModelViewSet):
    queryset = InstagramUser.objects.all()
    serializer_class = InstagramUserSerializer


class UniqueLinkViewSet(viewsets.ModelViewSet):
    queryset = UniqueLink.objects.all()
    serializer_class = UniqueLinkSerializer


class PostViewSet(viewsets.ModelViewSet):
    queryset = Post.objects.all()
    serializer_class = PostSerializer


class PrizeViewSet(viewsets.ModelViewSet):
    queryset = Prize.objects.all()
    serializer_class = PrizeSerializer


@api_view(['GET'])
def link_info(request):
    return Response({
        "message": "Unikal link formati: /link/<token>/",
        "example": "Admin paneldan yangi UniqueLink yarating va linkka kiring."
    })


@api_view(['GET'])
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
def instagram_callback(request):
    # Foydalanuvchi rad etgan yoki Instagram xatolik qaytargan holat
    if request.GET.get('error'):
        state = request.GET.get('state')
        if state:
            UniqueLink.objects.filter(token=state).update(status='failed')
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

    try:
        user, link = complete_instagram_oauth(code=code, token=state)
    except InstagramOAuthError as exc:
        UniqueLink.objects.filter(token=state).update(status='failed')
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

