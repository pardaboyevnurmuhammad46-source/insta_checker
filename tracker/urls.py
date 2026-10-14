from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import UserLinkViewSet, VideoTemplateViewSet, redirect_to_instagram

router = DefaultRouter()
router.register(r'users', UserLinkViewSet)
router.register(r'videos', VideoTemplateViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('link/<str:token>/', redirect_to_instagram, name='user_redirect'),
]
