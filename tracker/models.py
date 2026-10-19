import os
import uuid
from django.conf import settings
from django.db import models


def video_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if not ext:
        ext = '.mp4'
    random_filename = f"{uuid.uuid4().hex}{ext}"
    return os.path.join('videos', random_filename)


class InstagramUser(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('connected', 'Connected'),
        ('needs_reauth', 'Needs Reauth'),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='instagram_user',
    )
    name = models.CharField(max_length=255)
    ig_user_id = models.CharField(max_length=100, null=True, blank=True)
    access_token = models.TextField(null=True, blank=True)
    token_expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_admin(self) -> bool:
        return bool(self.user and (self.user.is_staff or self.user.is_superuser))

    @property
    def role(self) -> str:
        return 'admin' if self.is_admin else 'user'

    def __str__(self):
        return self.name


class Video(models.Model):
    title = models.CharField(max_length=255)
    # file = models.FileField(upload_to='videos/')
    file = models.FileField(upload_to=video_upload_path)
    is_default = models.BooleanField(default=False)
    owner = models.ForeignKey(
        InstagramUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='videos',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['is_default'],
                condition=models.Q(is_default=True),
                name='unique_default_video',
            )
        ]

    def save(self, *args, **kwargs):
        if self.is_default:
            # Faqat bittasi True bo'lishi kerak: boshqa videolardan is_default olib tashlanadi
            Video.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def url(self):
        return self.file.url if self.file else ''

    @property
    def name(self):
        return self.file.name if self.file else ''

    def __str__(self):
        default_label = " (Default)" if self.is_default else ""
        return f"{self.title}{default_label}"


def get_video_for_user(user: InstagramUser | None = None) -> Video | None:
    """
    Video tanlash qoidasi:
    1. Userning faol shaxsiy videosi bor bo'lsa shu (owner=user, is_active=True).
    2. Yo'qsa is_default=True bo'lgan umumiy video (is_active=True).
    """
    if user:
        personal_video = Video.objects.filter(owner=user, is_active=True).order_by('-created_at').first()
        if personal_video:
            return personal_video

    return Video.objects.filter(is_default=True, is_active=True).first()


class UniqueLink(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('opened', 'Opened'),
        ('posted', 'Posted'),
        ('failed', 'Failed'),
    )

    user = models.ForeignKey(InstagramUser, on_delete=models.CASCADE, related_name='links')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # video = models.FileField(upload_to='videos/')
    video = models.ForeignKey(
        Video,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='links',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __init__(self, *args, **kwargs):
        video_arg = kwargs.get('video')
        if video_arg is not None and not isinstance(video_arg, (Video, int)):
            from django.core.files.base import File
            if hasattr(video_arg, 'read') or isinstance(video_arg, (File, str)):
                user_obj = kwargs.get('user')
                title = getattr(video_arg, 'name', 'Uploaded Video')
                video_obj = Video.objects.create(
                    title=str(title),
                    file=video_arg,
                    owner=user_obj if isinstance(user_obj, InstagramUser) else None,
                    is_active=True,
                )
                kwargs['video'] = video_obj
        super().__init__(*args, **kwargs)

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
    deleted_detected_at = models.DateTimeField(null=True, blank=True)
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    next_check_at = models.DateTimeField(null=True, blank=True, db_index=True)
    error = models.TextField(null=True, blank=True)
    retry_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-id']
        indexes = [
            models.Index(fields=['status', 'next_check_at']),
            models.Index(fields=['link', 'posted_at']),
        ]

    def __str__(self):
        return f"Post: {self.link.user.name} ({self.status})"


class PostStat(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='stats')
    views = models.PositiveIntegerField(default=0)
    likes = models.PositiveIntegerField(default=0)
    comments_count = models.PositiveIntegerField(default=0)
    checked_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-checked_at']
        indexes = [
            models.Index(fields=['post', '-checked_at']),
        ]

    def __str__(self):
        return f"PostStat #{self.id} for Post #{self.post_id} at {self.checked_at}"


class Prize(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='prizes')
    milestone = models.PositiveIntegerField()
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('post', 'milestone')
        constraints = [
            models.UniqueConstraint(fields=['post', 'milestone'], name='unique_post_milestone')
        ]

    def __str__(self):
        return f"Prize {self.milestone} - Post #{self.post_id}"


class Notification(models.Model):
    KIND_CHOICES = (
        ('prize', 'Prize'),
        ('system', 'System'),
    )

    user = models.ForeignKey(InstagramUser, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default='system')
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    related_prize = models.ForeignKey(
        Prize,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notifications',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notification ({self.kind}) for {self.user.name}"


class DataDeletionRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    )

    confirmation_code = models.CharField(max_length=100, unique=True, db_index=True)
    user_id = models.CharField(max_length=100)
    # status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField(auto_now_add=True)
    details = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Deletion {self.confirmation_code} (User {self.user_id})"
