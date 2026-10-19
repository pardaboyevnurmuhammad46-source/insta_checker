from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    InstagramUserViewSet,
    VideoViewSet,
    UniqueLinkViewSet,
    PostViewSet,
    PrizeViewSet,
    PostStatViewSet,
    NotificationViewSet,
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
    current_user_profile,
    admin_create_user,
    admin_reset_password,
    change_password,
    user_connect_instagram,
    user_publish_video,
    user_publish_status,
    user_retry_publish,
)

router = DefaultRouter()
router.register(r'users', InstagramUserViewSet)
router.register(r'videos', VideoViewSet)
router.register(r'links', UniqueLinkViewSet)
router.register(r'posts', PostViewSet)
router.register(r'prizes', PrizeViewSet)
router.register(r'post-stats', PostStatViewSet)
router.register(r'notifications', NotificationViewSet)
router.register(r'data-deletions', DataDeletionRequestViewSet)

urlpatterns = [
    path('api/me/', current_user_profile, name='current_user_profile'),
    path('api/user/connect-instagram/', user_connect_instagram, name='user_connect_instagram'),
    path('api/user/publish/', user_publish_video, name='user_publish_video'),
    path('api/user/publish-status/', user_publish_status, name='user_publish_status'),
    path('api/user/retry/', user_retry_publish, name='user_retry_publish'),
    path('api/admin/create-user/', admin_create_user, name='admin_create_user'),
    path('api/admin/reset-password/', admin_reset_password, name='admin_reset_password'),
    path('api/change-password/', change_password, name='change_password'),
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
