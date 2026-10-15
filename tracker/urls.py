from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InstagramUserViewSet,
    UniqueLinkViewSet,
    PostViewSet,
    PrizeViewSet,
    redirect_to_instagram,
    instagram_callback,
    link_info,
)

router = DefaultRouter()
router.register(r'users', InstagramUserViewSet)
router.register(r'links', UniqueLinkViewSet)
router.register(r'posts', PostViewSet)
router.register(r'prizes', PrizeViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('link/', link_info, name='link_info'),
    path('link/<uuid:token>/', redirect_to_instagram, name='user_redirect'),
    path('oauth/callback/', instagram_callback, name='instagram_callback'),
]
