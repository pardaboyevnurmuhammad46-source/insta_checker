from django.conf import settings
from django.contrib.auth.models import User
from rest_framework import serializers
# from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest, Video, PostStat, Notification


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

    class Meta:
        model = Video
        fields = ['id', 'title', 'file', 'video_url', 'is_default', 'owner', 'owner_name', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at', 'video_url']

    def get_video_url(self, obj):
        return obj.url

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

    class Meta:
        model = UniqueLink
        fields = ['id', 'user', 'user_name', 'token', 'full_link', 'video', 'video_url', 'status', 'expires_at', 'created_at']
        read_only_fields = ['token', 'status', 'created_at']

    def get_full_link(self, obj):
        return f"{settings.SITE_URL}/link/{obj.token}/"

    def get_video_url(self, obj):
        return obj.video.url if obj.video else ''

    def validate_video(self, value):
        if hasattr(value, 'file'):
            file_name = value.file.name
            file_size = value.file.size
        else:
            file_name = getattr(value, 'name', '')
            file_size = getattr(value, 'size', 0)

        if file_name and not file_name.lower().endswith('.mp4'):
            raise serializers.ValidationError("Faqat .mp4 formatidagi videolar qabul qilinadi.")
        if file_size and file_size > 100 * 1024 * 1024:
            raise serializers.ValidationError("Video hajmi 100MB dan oshmasligi kerak.")
        return value


class PostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='link.user.name', read_only=True)

    class Meta:
        model = Post
        fields = '__all__'
        read_only_fields = [f.name for f in Post._meta.fields]


class PostStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostStat
        fields = '__all__'
        read_only_fields = [f.name for f in PostStat._meta.fields]


class PrizeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='post.link.user.name', read_only=True)

    class Meta:
        model = Prize
        fields = '__all__'
        read_only_fields = [f.name for f in Prize._meta.fields]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['id', 'created_at']


class DataDeletionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDeletionRequest
        fields = '__all__'
        read_only_fields = [f.name for f in DataDeletionRequest._meta.fields]


class AdminCreateUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=6)
    name = serializers.CharField(max_length=255)
    is_staff = serializers.BooleanField(default=False, required=False)
    ig_user_id = serializers.CharField(max_length=100, required=False, allow_blank=True, default='')

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Bunday username band. Boshqa username tanlang.")
        return value

    def create(self, validated_data):
        username = validated_data['username']
        password = validated_data['password']
        name = validated_data['name']
        is_staff = validated_data.get('is_staff', False)
        ig_user_id = validated_data.get('ig_user_id', '') or None

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
        return {
            "user_id": user.id,
            "username": user.username,
            "role": "admin" if user.is_staff else "user",
            "is_staff": user.is_staff,
            "instagram_user": {
                "id": ig_user.id,
                "name": ig_user.name,
                "ig_user_id": ig_user.ig_user_id,
                "status": ig_user.status,
                "created_at": ig_user.created_at,
            }
        }


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=6)


class ResetPasswordSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    new_password = serializers.CharField(write_only=True, min_length=6)
