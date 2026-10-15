from django.conf import settings
from rest_framework import serializers
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest


class InstagramUserSerializer(serializers.ModelSerializer):
    has_token = serializers.SerializerMethodField()

    class Meta:
        model = InstagramUser
        fields = ['id', 'name', 'ig_user_id', 'status', 'token_expires_at', 'created_at', 'has_token']
        read_only_fields = ['ig_user_id', 'status', 'token_expires_at', 'created_at']

    def get_has_token(self, obj):
        return bool(obj.access_token)


class UniqueLinkSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)
    full_link = serializers.SerializerMethodField()

    class Meta:
        model = UniqueLink
        fields = ['id', 'user', 'user_name', 'token', 'full_link', 'video', 'status', 'expires_at', 'created_at']
        read_only_fields = ['token', 'status', 'created_at']

    def get_full_link(self, obj):
        return f"{settings.SITE_URL}/link/{obj.token}/"
        
    def validate_video(self, value):
        if not value.name.lower().endswith('.mp4'):
            raise serializers.ValidationError("Faqat .mp4 formatidagi videolar qabul qilinadi.")
        if value.size > 100 * 1024 * 1024:
            raise serializers.ValidationError("Video hajmi 100MB dan oshmasligi kerak.")
        return value


class PostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='link.user.name', read_only=True)

    class Meta:
        model = Post
        fields = '__all__'
        read_only_fields = [f.name for f in Post._meta.fields]


class PrizeSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='post.link.user.name', read_only=True)

    class Meta:
        model = Prize
        fields = '__all__'
        read_only_fields = [f.name for f in Prize._meta.fields]


class DataDeletionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDeletionRequest
        fields = '__all__'
        read_only_fields = [f.name for f in DataDeletionRequest._meta.fields]
