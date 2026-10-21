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
    register_user,
    admin_create_user,
    admin_reset_password,
    change_password,
    user_connect_instagram,
    user_publish_video,
    user_publish_status,
    user_retry_publish,
    user_upload_video,
    admin_summary,
    admin_users_list,
    admin_user_detail,
    admin_posts_list,
    admin_stats_daily,
    admin_export_posts_csv,
    me_summary,
    me_posts,
    me_post_history,
    me_notifications,
    me_notifications_read,
    me_prizes,
)

from .dev_views import (
    health_check,
    simulate_views,
    simulate_delete,
    simulate_token_revoked,
    simulate_network_error,
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
    # User endpoints
    path('api/register/', register_user, name='register_user'),
    path('api/auth/register/', register_user, name='auth_register'),
    path('api/me/', current_user_profile, name='current_user_profile'),
    path('api/me/summary/', me_summary, name='me_summary'),
    path('api/me/posts/', me_posts, name='me_posts'),
    path('api/me/posts/<int:post_id>/history/', me_post_history, name='me_post_history'),
    path('api/me/notifications/', me_notifications, name='me_notifications'),
    path('api/me/notifications/read/', me_notifications_read, name='me_notifications_read'),
    path('api/me/prizes/', me_prizes, name='me_prizes'),
    path('api/user/connect-instagram/', user_connect_instagram, name='user_connect_instagram'),
    path('api/user/publish/', user_publish_video, name='user_publish_video'),
    path('api/user/publish-status/', user_publish_status, name='user_publish_status'),
    path('api/user/retry/', user_retry_publish, name='user_retry_publish'),
    path('api/user/upload-video/', user_upload_video, name='user_upload_video'),

    # Admin endpoints
    path('api/admin/summary/', admin_summary, name='admin_summary'),
    path('api/admin/users/', admin_users_list, name='admin_users_list'),
    path('api/admin/users/<int:user_id>/', admin_user_detail, name='admin_user_detail'),
    path('api/admin/posts/', admin_posts_list, name='admin_posts_list'),
    path('api/admin/stats/daily/', admin_stats_daily, name='admin_stats_daily'),
    path('api/admin/export/posts.csv', admin_export_posts_csv, name='admin_export_posts_csv'),
    path('api/admin/create-user/', admin_create_user, name='admin_create_user'),
    path('api/admin/reset-password/', admin_reset_password, name='admin_reset_password'),
    path('api/dashboard/', dashboard_stats, name='dashboard_stats'),
    path('api/change-password/', change_password, name='change_password'),
    path('api/public/post/<uuid:token>/', user_portal_api, name='user_portal_api'),
    path('api/health/', health_check, name='health_check'),
    # Dev / Simulation endpoints (faol faqat INSTAGRAM_DRY_RUN=True va admin bo'lganda)
    path('api/dev/simulate-views/', simulate_views, name='simulate_views'),
    path('api/dev/simulate-delete/', simulate_delete, name='simulate_delete'),
    path('api/dev/simulate-token-revoked/', simulate_token_revoked, name='simulate_token_revoked'),
    path('api/dev/simulate-network-error/', simulate_network_error, name='simulate_network_error'),
    path('api/', include(router.urls)),
    path('link/', link_info, name='link_info'),
    path('link/<uuid:token>/', redirect_to_instagram, name='user_redirect'),
    path('my-post/<uuid:token>/', user_portal, name='user_portal'),
    path('oauth/callback/', instagram_callback, name='instagram_callback'),
    path('oauth/deauthorize/', instagram_deauthorize, name='instagram_deauthorize'),
    path('oauth/data-deletion/', instagram_data_deletion, name='instagram_data_deletion'),
    path('oauth/data-deletion/status/<str:confirmation_code>/', data_deletion_status, name='data_deletion_status'),
]
