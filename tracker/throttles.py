from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class UserSyncThrottle(UserRateThrottle):
    scope = 'user_sync'
    rate = '3/minute'


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        role = "admin" if (user.is_staff or user.is_superuser) else "user"
        data['role'] = role
        data['username'] = user.username
        data['user_id'] = user.id
        if hasattr(user, 'instagram_user') and user.instagram_user:
            data['name'] = user.instagram_user.name
            data['instagram_user_id'] = user.instagram_user.id
        return data


class LoginView(TokenObtainPairView):
    # throttle_classes = [LoginThrottle]
    throttle_classes = [LoginThrottle]
    serializer_class = CustomTokenObtainPairSerializer
