
from rest_framework.permissions import BasePermission


class IsAdminRole(BasePermission):
    """
    Faqat admin (is_staff=True yoki is_superuser=True) foydalanuvchilar uchun ruxsat.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))


class IsOwnerOrAdmin(BasePermission):
    """
    Obyekt darajasidagi ruxsat:
    - Admin barcha obyektlarni ko'ra oladi va boshqara oladi.
    - Oddiy user faqat o'ziga tegishli obyektlarni ko'ra oladi.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False

        if request.user.is_staff or request.user.is_superuser:
            return True

        # InstagramUser
        if hasattr(obj, 'user') and obj.user == request.user:
            return True

        # UniqueLink
        if hasattr(obj, 'user') and hasattr(obj.user, 'user') and obj.user.user == request.user:
            return True

        # Post
        if hasattr(obj, 'link') and hasattr(obj.link, 'user') and hasattr(obj.link.user, 'user') and obj.link.user.user == request.user:
            return True

        # PostStat
        if hasattr(obj, 'post') and hasattr(obj.post, 'link') and hasattr(obj.post.link, 'user') and hasattr(obj.post.link.user, 'user') and obj.post.link.user.user == request.user:
            return True

        # Prize
        if hasattr(obj, 'post') and hasattr(obj.post, 'link') and hasattr(obj.post.link, 'user') and hasattr(obj.post.link.user, 'user') and obj.post.link.user.user == request.user:
            return True

        # Notification
        if hasattr(obj, 'user') and hasattr(obj.user, 'user') and obj.user.user == request.user:
            return True

        # Video
        if hasattr(obj, 'owner') and hasattr(obj.owner, 'user') and obj.owner.user == request.user:
            return True

        return False


from rest_framework.permissions import SAFE_METHODS


class IsAdminOrReadOnlyOwnerVideo(BasePermission):
    """
    Faqat admin video yuklay oladi, o'zgartira oladi va o'chira oladi.
    Oddiy user faqat GET qilishi mumkin va faqat o'z faol videosi yoki default videoni ko'radi.
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        return request.method in SAFE_METHODS

    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        if request.method not in SAFE_METHODS:
            return False
        # Oddiy user faqat o'z shaxsiy videosini yoki faol umumiy (default) videoni ko'ra oladi
        if obj.owner and hasattr(obj.owner, 'user') and obj.owner.user == request.user:
            return True
        if obj.is_default and obj.is_active:
            return True
        return False

