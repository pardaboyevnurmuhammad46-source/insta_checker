from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserLinkViewSet, VideoTemplateViewSet, redirect_to_instagram, link_info

router = DefaultRouter()
router.register(r'users', UserLinkViewSet)
router.register(r'videos', VideoTemplateViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('link/', link_info, name='link_info'),
    path('link/<str:token>/', redirect_to_instagram, name='user_redirect'),
]
