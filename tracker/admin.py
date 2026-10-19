from django.contrib import admin
# from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .models import (
    InstagramUser,
    UniqueLink,
    Post,
    Prize,
    DataDeletionRequest,
    Video,
    PostStat,
    Notification,
)
from .tasks import publish_reels_task, check_post_metrics_task
from .services import refresh_user_token


@admin.register(InstagramUser)
class InstagramUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'ig_user_id', 'status', 'token_expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'ig_user_id')
    actions = ['refresh_token_action']

    @admin.action(description="Tanlangan foydalanuvchilar tokenini yangilash")
    def refresh_token_action(self, request, queryset):
        success_count = 0
        for user in queryset:
            if refresh_user_token(user):
                success_count += 1
        self.message_user(request, f"{success_count}/{queryset.count()} ta foydalanuvchi tokeni yangilandi.")


@admin.register(Video)
class VideoAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'owner', 'is_default', 'is_active', 'created_at')
    list_filter = ('is_default', 'is_active', 'created_at')
    search_fields = ('title', 'owner__name')


@admin.register(UniqueLink)
class UniqueLinkAdmin(admin.ModelAdmin):
    # list_display = ('id', 'user', 'full_link', 'status', 'expires_at', 'created_at')
    list_display = ('id', 'user', 'video', 'full_link', 'status', 'expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__name', 'token')
    readonly_fields = ('token', 'created_at')
    actions = ['publish_reels_action']

    def full_link(self, obj):
        return f"http://127.0.0.1:8000/link/{obj.token}/"
    full_link.short_description = "To'liq link"

    @admin.action(description="Tanlangan linklar uchun videoni Reels qilib joylash")
    def publish_reels_action(self, request, queryset):
        count = 0
        for link in queryset:
            publish_reels_task.delay(link.id)
            count += 1
        self.message_user(request, f"{count} ta link uchun Reels joylash vazifasi navbatga qo'yildi.")


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('id', 'link', 'status', 'views', 'likes', 'comments_count', 'next_check_at', 'posted_at')
    list_filter = ('status', 'posted_at')
    search_fields = ('ig_media_id', 'permalink')
    actions = ['retry_publish_action', 'check_metrics_action']

    @admin.action(description="Tanlangan postlarni qayta Reels qilib joylash")
    def retry_publish_action(self, request, queryset):
        count = 0
        for post in queryset:
            publish_reels_task.delay(post.link_id)
            count += 1
        self.message_user(request, f"{count} ta post uchun qayta joylash navbatga qo'yildi.")

    @admin.action(description="Tanlangan postlar statistikasini hozir tekshirish")
    def check_metrics_action(self, request, queryset):
        count = 0
        for post in queryset:
            check_post_metrics_task.delay(post.id)
            count += 1
        self.message_user(request, f"{count} ta post statistikasi tekshirish navbatiga qo'yildi.")


@admin.register(PostStat)
class PostStatAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'views', 'likes', 'comments_count', 'checked_at')
    list_filter = ('checked_at',)
    search_fields = ('post__id', 'post__ig_media_id')


@admin.register(Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'milestone', 'sent_at')
    list_filter = ('milestone', 'sent_at')
    search_fields = ('post__id', 'milestone')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kind', 'is_read', 'created_at')
    list_filter = ('kind', 'is_read', 'created_at')
    search_fields = ('user__name', 'message')


@admin.register(DataDeletionRequest)
class DataDeletionRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'confirmation_code', 'user_id', 'status', 'requested_at')
    list_filter = ('status', 'requested_at')
    search_fields = ('confirmation_code', 'user_id')
    readonly_fields = ('confirmation_code', 'requested_at')
