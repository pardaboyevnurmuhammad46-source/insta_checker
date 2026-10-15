from rest_framework import serializers
from .models import InstagramUser, UniqueLink, Post, Prize, DataDeletionRequest


class InstagramUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstagramUser
        fields = '__all__'


class UniqueLinkSerializer(serializers.ModelSerializer):
    class Meta:
        model = UniqueLink
        fields = '__all__'
        read_only_fields = ['token']


class PostSerializer(serializers.ModelSerializer):
    class Meta:
        model = Post
        fields = '__all__'


class PrizeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prize
        fields = '__all__'


class DataDeletionRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataDeletionRequest
        fields = '__all__'

