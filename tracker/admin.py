from django.contrib import admin
from .models import VideoTemplate, UserLink, InstagramPost

@admin.register(VideoTemplate)
class VideoTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'video_file', 'created_at')
    search_fields = ('title',)

@admin.register(UserLink)
class UserLinkAdmin(admin.ModelAdmin):
    list_display = ('id', 'unique_token', 'video_template', 'created_at', 'get_link')
    list_filter = ('video_template', 'created_at')
    search_fields = ('unique_token',)

    def get_link(self, obj):
        return f"/link/{obj.unique_token}/"
    get_link.short_description = "Unikal Link Path"

@admin.register(InstagramPost)
class InstagramPostAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_link', 'ig_post_id', 'views', 'likes', 'comments', 'is_deleted', 'milestone_500_reached', 'milestone_1000_reached', 'milestone_5000_reached', 'last_checked_at')
    list_filter = ('is_deleted', 'milestone_500_reached', 'milestone_1000_reached', 'milestone_5000_reached')
    search_fields = ('ig_post_id', 'post_url')
