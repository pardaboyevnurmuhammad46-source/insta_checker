from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InstagramUserViewSet,
    UniqueLinkViewSet,
    PostViewSet,
    PrizeViewSet,
    DataDeletionRequestViewSet,
    redirect_to_instagram,
    instagram_callback,
    instagram_deauthorize,
    instagram_data_deletion,
    data_deletion_status,
    link_info,
    dashboard_stats,
    user_portal,
    user_portal_api,
)

router = DefaultRouter()
router.register(r'users', InstagramUserViewSet)
router.register(r'links', UniqueLinkViewSet)
router.register(r'posts', PostViewSet)
router.register(r'prizes', PrizeViewSet)
router.register(r'data-deletions', DataDeletionRequestViewSet)

urlpatterns = [
    path('api/dashboard/', dashboard_stats, name='dashboard_stats'),
    path('api/public/post/<uuid:token>/', user_portal_api, name='user_portal_api'),
    path('api/', include(router.urls)),
    path('link/', link_info, name='link_info'),
    path('link/<uuid:token>/', redirect_to_instagram, name='user_redirect'),
    path('my-post/<uuid:token>/', user_portal, name='user_portal'),
    path('oauth/callback/', instagram_callback, name='instagram_callback'),
    path('oauth/deauthorize/', instagram_deauthorize, name='instagram_deauthorize'),
    path('oauth/data-deletion/', instagram_data_deletion, name='instagram_data_deletion'),
    path('oauth/data-deletion/status/<str:confirmation_code>/', data_deletion_status, name='data_deletion_status'),
]
