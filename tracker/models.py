import uuid
from django.db import models

class VideoTemplate(models.Model):
    title = models.CharField(max_length=255)
    video_file = models.FileField(upload_to='videos/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class UserLink(models.Model):
    unique_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    video_template = models.ForeignKey(VideoTemplate, on_delete=models.SET_NULL, null=True)

    def __str__(self):
        return str(self.unique_token)

class InstagramPost(models.Model):
    user_link = models.ForeignKey(UserLink, on_delete=models.CASCADE, related_name='posts')
    ig_post_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    post_url = models.URLField(null=True, blank=True)
    views = models.IntegerField(default=0)
    likes = models.IntegerField(default=0)
    comments = models.IntegerField(default=0)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_checked_at = models.DateTimeField(auto_now=True)
    
    # Milestones
    milestone_500_reached = models.BooleanField(default=False)
    milestone_1000_reached = models.BooleanField(default=False)
    milestone_5000_reached = models.BooleanField(default=False)

    def __str__(self):
        return f"Post {self.ig_post_id or 'Pending'} - {self.views} views"
