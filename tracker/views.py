from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from .models import UserLink, VideoTemplate, InstagramPost
from .serializers import UserLinkSerializer, VideoTemplateSerializer, InstagramPostSerializer

class VideoTemplateViewSet(viewsets.ModelViewSet):
    queryset = VideoTemplate.objects.all()
    serializer_class = VideoTemplateSerializer

class UserLinkViewSet(viewsets.ModelViewSet):
    queryset = UserLink.objects.all()
    serializer_class = UserLinkSerializer

@api_view(['GET'])
def link_info(request):
    return Response({
        "message": "Unikal link formati: /link/<token>/",
        "example": "Adminkadan (http://127.0.0.1:8000/admin/) yangi User Link yarating va berilgan unikal linkka kiring.",
        "api_users_url": "/api/users/"
    })

@api_view(['GET'])
def redirect_to_instagram(request, token):
    """
    Bu yerda user o'ziga berilgan linkni bosganda keladigan endpoint.
    Haqiqiy loyihada biz bu yerdan userni Instagram OAuth sahifasiga redirect qilamiz.
    User ruxsat bergach, qaytib kelganida uning nomidan avtomatik post joylaymiz.
    Hozir test uchun shunchaki stub qilib qo'ydik.
    """
    user_link = get_object_or_404(UserLink, unique_token=token)
    
    # Kelajakda: 
    # 1. Instagram OAuth URL yaratiladi (App ID va redirect_uri bilan)
    # 2. Foydalanuvchi u erga yo'naltiriladi.
    # 3. Instagramdan qaytganida biz Graph API orqali videoni yuklaymiz.
    
    # Hozircha esa biz shunchaki post yaratilgan deb faraz qilamiz:
    post, created = InstagramPost.objects.get_or_create(
        user_link=user_link,
        defaults={
            'ig_post_id': f"mock_ig_id_{token.split('-')[0]}",
            'post_url': "https://instagram.com/p/mockedurl/"
        }
    )
    
    return Response({
        "message": "Foydalanuvchi Instagramga yo'naltirildi.",
        "oauth_url_stub": f"https://api.instagram.com/oauth/authorize?client_id=APP_ID&redirect_uri=OUR_URL&scope=user_profile,user_media,instagram_content_publish",
        "mock_post_created": created,
        "token": token
    })
