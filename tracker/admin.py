from django.contrib import admin
from .models import InstagramUser, UniqueLink, Post, Prize
from .tasks import publish_reels_task


@admin.register(InstagramUser)
class InstagramUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'ig_user_id', 'status', 'token_expires_at', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name', 'ig_user_id')


@admin.register(UniqueLink)
class UniqueLinkAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'full_link', 'status', 'expires_at', 'created_at')
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
    actions = ['retry_publish_action']

    @admin.action(description="Tanlangan postlarni qayta Reels qilib joylash")
    def retry_publish_action(self, request, queryset):
        count = 0
        for post in queryset:
            publish_reels_task.delay(post.link_id)
            count += 1
        self.message_user(request, f"{count} ta post uchun qayta joylash navbatga qo'yildi.")


@admin.register(Prize)
class PrizeAdmin(admin.ModelAdmin):
    list_display = ('id', 'post', 'milestone', 'sent_at')
    list_filter = ('milestone', 'sent_at')
