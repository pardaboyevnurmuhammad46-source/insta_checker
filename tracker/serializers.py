from rest_framework import serializers
from .models import UserLink, VideoTemplate, InstagramPost

class VideoTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoTemplate
        fields = '__all__'

class UserLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLink
        fields = ['id', 'unique_token', 'video_template', 'created_at']
        read_only_fields = ['unique_token']

class InstagramPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramPost
        fields = '__all__'
