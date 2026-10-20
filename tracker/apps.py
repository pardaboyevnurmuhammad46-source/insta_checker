from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class TrackerConfig(AppConfig):
    name = 'tracker'

    def ready(self):
        if getattr(settings, 'INSTAGRAM_DRY_RUN', False) and not getattr(settings, 'DEBUG', False):
            raise ImproperlyConfigured(
                "Xavfsizlik xatosi: INSTAGRAM_DRY_RUN=True ishlab chiqarish rejimida (DEBUG=False) ishlatilishi mumkin emas! "
                "Iltimos, INSTAGRAM_DRY_RUN=False qiling yoki sinov uchun DEBUG=True rejimini yoqing."
            )
        import tracker.signals
