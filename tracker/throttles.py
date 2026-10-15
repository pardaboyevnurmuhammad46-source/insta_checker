from rest_framework.throttling import AnonRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView


class LoginThrottle(AnonRateThrottle):
    scope = 'login'


class LoginView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]
