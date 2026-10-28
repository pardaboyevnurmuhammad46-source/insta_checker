from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import serializers
# from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest, Video, PostStat, Notification, CampaignConfig


class CampaignConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampaignConfig
        fields = [
            'id', 'topic', 'brand_name', 'required_keywords',
            'ai_prompt_instructions', 'points_reward', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_at']


class InstagramUserSerializer(serializers.ModelSerializer):
    has_token = serializers.SerializerMethodField()
    role = serializers.CharField(read_only=True)
    username = serializers.CharField(source='user.username', read_only=True, default='')

    class Meta:
        model = InstagramUser
        fields = ['id', 'user', 'username', 'name', 'ig_user_id', 'status', 'role', 'token_expires_at', 'created_at', 'has_token']
        read_only_fields = ['ig_user_id', 'status', 'token_expires_at', 'created_at', 'role']

    def get_has_token(self, obj):
        return bool(obj.access_token)


class VideoSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.name', read_only=True)
    video_url = serializers.SerializerMethodField()
    title = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = Video
        fields = ['id', 'title', 'file', 'video_url', 'is_default', 'owner', 'owner_name', 'is_active', 'status', 'processing_error', 'created_at']
        read_only_fields = ['id', 'created_at', 'video_url', 'status', 'processing_error']

    def get_video_url(self, obj):
        return obj.url

    def validate(self, attrs):
        if not attrs.get('title') and attrs.get('file'):
            attrs['title'] = getattr(attrs['file'], 'name', 'Video')
        return attrs

    def validate_file(self, value):
        if not value:
            raise serializers.ValidationError("Fayl bo'sh bo'lishi mumkin emas.")

        file_name = getattr(value, 'name', '')
        if not file_name.lower().endswith('.mp4'):
            raise serializers.ValidationError("Faqat .mp4 formatidagi videolar qabul qilinadi.")

        if value.size == 0:
            raise serializers.ValidationError("Video fayl bo'sh bo'lishi mumkin emas.")

        max_bytes = getattr(settings, 'MAX_VIDEO_SIZE_BYTES', 100 * 1024 * 1024)
        max_mb = getattr(settings, 'MAX_VIDEO_SIZE_MB', 100)
        if value.size > max_bytes:
            raise serializers.ValidationError(f"Video hajmi {max_mb}MB dan oshmasligi kerak.")

        return value


class UniqueLinkSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)
    full_link = serializers.SerializerMethodField()
    video_url = serializers.SerializerMethodField()
    video = serializers.PrimaryKeyRelatedField(
        queryset=Video.objects.all(),
        required=False,
        allow_null=True,
    )
    video_file = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = UniqueLink
        fields = [
            'id', 'user', 'user_name', 'token', 'full_link',
            'video', 'video_file', 'video_url', 'status', 'expires_at', 'created_at'
        ]
        read_only_fields = ['token', 'status', 'created_at']

    def get_full_link(self, obj):
        return f"{settings.SITE_URL}/link/{obj.token}/"

    def get_video_url(self, obj):
        return obj.video.url if obj.video else ''

    def to_internal_value(self, data):
        data = data.copy()
        video_val = data.get('video')
        if hasattr(video_val, 'read') or hasattr(video_val, 'chunks'):
            data['video_file'] = video_val
            data.pop('video', None)
        elif video_val == '' or video_val == 'null':
            data.pop('video', None)

        return super().to_internal_value(data)

    def validate_video_file(self, value):
        if not value:
            return value
        file_name = getattr(value, 'name', '')
        if not file_name.lower().endswith('.mp4'):
            raise serializers.ValidationError("Faqat .mp4 formatidagi videolar qabul qilinadi.")
        if value.size == 0:
            raise serializers.ValidationError("Video fayl bo'sh bo'lishi mumkin emas.")
        max_bytes = getattr(settings, 'MAX_VIDEO_SIZE_BYTES', 100 * 1024 * 1024)
        max_mb = getattr(settings, 'MAX_VIDEO_SIZE_MB', 100)
        if value.size > max_bytes:
            raise serializers.ValidationError(f"Video hajmi {max_mb}MB dan oshmasligi kerak.")
        return value

    def create(self, validated_data):
        video_file = validated_data.pop('video_file', None)
        user = validated_data.get('user')
        if video_file:
            title = getattr(video_file, 'name', 'Uploaded Video')
            new_video = Video.objects.create(
                title=title,
                file=video_file,
                owner=user,
                is_active=True,
            )
            validated_data['video'] = new_video
        elif not validated_data.get('video'):
            from .models import get_video_for_user
            chosen = get_video_for_user(user)
            if chosen:
                validated_data['video'] = chosen

        return super().create(validated_data)


class PostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='link.user.name', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'link', 'user_name', 'permalink', 'status', 'posted_at',
            'deleted_detected_at', 'views', 'likes', 'comments_count',
            'last_checked_at'
        ]
        read_only_fields = fields


class AdminPostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='link.user.name', read_only=True)

    class Meta:
        model = Post
        fields = [
            'id', 'link', 'user_name', 'ig_media_id', 'permalink', 'status',
            'posted_at', 'deleted_detected_at', 'views', 'likes', 'comments_count',
            'last_checked_at', 'next_check_at', 'error', 'retry_count'
        ]
        read_only_fields = fields


class CampaignPostSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    code = serializers.CharField(source='link.code', read_only=True, default='')

    class Meta:
        model = Post
        fields = [
            'id',
            'thumbnail_url',
            'permalink',
            'status',
            'source',
            'views',
            'likes',
            'comments_count',
            'posted_at',
            'last_synced_at',
            'last_checked_at',
            'next_check_at',
            'username',
            'code',
            'ai_verified',
            'ai_confidence',
            'ai_detection_source',
            'transcript',
            'ai_explanation',
            'points_awarded',
        ]
        read_only_fields = fields

    def get_username(self, obj):
        if obj.link and obj.link.user:
            if obj.link.user.user and obj.link.user.user.username:
                return obj.link.user.user.username
            return obj.link.user.name or ''
        return ''


class PostStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostStat
        fields = ['id', 'post', 'views', 'likes', 'comments_count', 'checked_at']
        read_only_fields = fields


class PrizeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='post.link.user.name', read_only=True)

    class Meta:
        model = Prize
        fields = ['id', 'post', 'user_name', 'milestone', 'sent_at']
        read_only_fields = fields


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'user', 'kind', 'message', 'is_read', 'created_at', 'related_prize']
        read_only_fields = fields


class DataDeletionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDeletionRequest
        fields = ['id', 'confirmation_code', 'user_id', 'status', 'requested_at', 'details']
        read_only_fields = fields


from django.db import transaction
from django.contrib.auth.password_validation import validate_password

class MeSummarySerializer(serializers.Serializer):
    total_views = serializers.IntegerField(default=0)
    total_likes = serializers.IntegerField(default=0)
    total_comments = serializers.IntegerField(default=0)
    posts_count = serializers.IntegerField(default=0)
    prizes_count = serializers.IntegerField(default=0)
    last_checked_at = serializers.DateTimeField(allow_null=True)
    next_milestone = serializers.IntegerField(allow_null=True)
    views_remaining = serializers.IntegerField(allow_null=True)
    progress_percent = serializers.FloatField(default=0.0)
    milestones = serializers.ListField(child=serializers.IntegerField())

class AdminSummarySerializer(serializers.Serializer):
    total_users = serializers.IntegerField()
    connected_users = serializers.IntegerField()
    needs_reauth_users = serializers.IntegerField()
    posts_by_status = serializers.DictField(child=serializers.IntegerField())
    total_metrics = serializers.DictField(child=serializers.IntegerField())
    total_views = serializers.IntegerField()
    total_likes = serializers.IntegerField()
    total_comments = serializers.IntegerField()
    total_prizes = serializers.IntegerField()
    expiring_tokens_count = serializers.IntegerField()
    users_by_status = serializers.DictField(child=serializers.IntegerField())
    links_by_status = serializers.DictField(child=serializers.IntegerField())
    instagram_errors_last_hour = serializers.DictField(child=serializers.IntegerField(), required=False)
    rate_limited_accounts_count = serializers.IntegerField(default=0, required=False)
    dry_run = serializers.BooleanField(default=False, required=False)

class UserPublishStatusOutputSerializer(serializers.Serializer):
    has_post = serializers.BooleanField()
    status = serializers.CharField()
    post_id = serializers.IntegerField(allow_null=True, required=False)
    posted_at = serializers.DateTimeField(allow_null=True, required=False)
    views = serializers.IntegerField(required=False)
    likes = serializers.IntegerField(required=False)
    comments_count = serializers.IntegerField(required=False)
    permalink = serializers.URLField(allow_null=True, required=False)
    error = serializers.CharField(allow_null=True, required=False)
    retry_count = serializers.IntegerField(required=False)
    can_retry = serializers.BooleanField(default=False)
    retries_left = serializers.IntegerField(default=0)
    can_publish = serializers.BooleanField(default=False)
    can_publish_reason = serializers.CharField(allow_null=True, required=False)
    code = serializers.CharField(allow_null=True, required=False)
    upload_limits = serializers.DictField(required=False)
    ai_verified = serializers.BooleanField(default=False, required=False)
    ai_confidence = serializers.FloatField(default=0.0, required=False)
    ai_detection_source = serializers.CharField(allow_null=True, required=False)
    transcript = serializers.CharField(allow_null=True, required=False)
    ai_explanation = serializers.CharField(allow_null=True, required=False)
    points_awarded = serializers.IntegerField(default=0, required=False)
    last_checked_at = serializers.DateTimeField(allow_null=True, required=False)
    next_check_at = serializers.DateTimeField(allow_null=True, required=False)

class UserProfileOutputSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    is_staff = serializers.BooleanField()
    role = serializers.CharField()
    instagram_user = InstagramUserSerializer(allow_null=True)
    dry_run = serializers.BooleanField(default=False, required=False)


class HealthCheckOutputSerializer(serializers.Serializer):
    status = serializers.CharField()
    database = serializers.CharField()
    redis = serializers.CharField()
    dry_run = serializers.BooleanField()


class SimulateViewsInputSerializer(serializers.Serializer):
    post_id = serializers.IntegerField()
    views = serializers.IntegerField(min_value=0)


class SimulatePostActionInputSerializer(serializers.Serializer):
    post_id = serializers.IntegerField()


class SimulateUserActionInputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
class AdminCreateUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=255)
    is_staff = serializers.BooleanField(default=False, required=False)
    ig_user_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Bunday username band. Boshqa username tanlang.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        username = validated_data['username']
        password = validated_data['password']
        name = validated_data['name']
        is_staff = validated_data.get('is_staff', False)
        ig_user_id = validated_data.get('ig_user_id', '') or None

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                is_staff=is_staff,
            )
            ig_user = InstagramUser.objects.create(
                user=user,
                name=name,
                ig_user_id=ig_user_id,
                status='pending',
            )
        return ig_user

class AdminCreateUserOutputSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(source='user.id', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    role = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(source='user.is_staff', read_only=True)
    instagram_user = InstagramUserSerializer(source='*', read_only=True)

    def get_role(self, obj):
        return "admin" if obj.user.is_staff else "user"

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value


class UserRegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)
    name = serializers.CharField(max_length=255)
    ig_user_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_username(self, value):
        val = value.strip()
        if len(val) < 3:
            raise serializers.ValidationError("Foydalanuvchi nomi kamida 3 ta belgidan iborat bo'lishi kerak.")
        if User.objects.filter(username__iexact=val).exists():
            raise serializers.ValidationError("Bunday foydalanuvchi nomi band. Iltimos boshqasini tanlang.")
        return val

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        username = validated_data['username'].strip()
        password = validated_data['password']
        name = validated_data['name'].strip()
        ig_user_id = validated_data.get('ig_user_id', '').strip() or None

        with transaction.atomic():
            user = User.objects.create_user(
                username=username,
                password=password,
                is_staff=False,
            )
            ig_user = InstagramUser.objects.create(
                user=user,
                name=name,
                ig_user_id=ig_user_id,
                status='pending',
            )
        return ig_user


class ResetPasswordSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
