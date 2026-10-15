import uuid
from django.db import models


class InstagramUser(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('connected', 'Connected'),
        ('needs_reauth', 'Needs Reauth'),
    )

    name = models.CharField(max_length=255)
    ig_user_id = models.CharField(max_length=100, null=True, blank=True)
    access_token = models.TextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class UniqueLink(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('opened', 'Opened'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(InstagramUser, on_delete=models.CASCADE, related_name='links')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    video = models.FileField(upload_to='videos/')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.name} ({self.token})"


class Post(models.Model):
    STATUS_CHOICES = (
        ('queued', 'Queued'),
        ('publishing', 'Publishing'),
        ('published', 'Published'),
        ('deleted', 'Deleted'),
        ('failed', 'Failed'),
    )

    link = models.OneToOneField(UniqueLink, on_delete=models.CASCADE, related_name='post')
    ig_media_id = models.CharField(max_length=100, null=True, blank=True)
    permalink = models.URLField(max_length=500, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    posted_at = models.DateTimeField(null=True, blank=True)
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Post: {self.link.user.name} ({self.status})"


class Prize(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='prizes')
    milestone = models.PositiveIntegerField()
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'milestone')

    def __str__(self):
        return f"Prize {self.milestone} - Post #{self.post_id}"


class DataDeletionRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    confirmation_code = models.CharField(max_length=100, unique=True, db_index=True)
    user_id = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    requested_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Deletion {self.confirmation_code} (User {self.user_id})"

