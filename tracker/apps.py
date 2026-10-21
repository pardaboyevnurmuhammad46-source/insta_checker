from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class TrackerConfig(AppConfig):
    name = 'tracker'

    def ready(self):
        is_mock = getattr(settings, 'INSTAGRAM_MODE', 'real') == 'mock' or getattr(settings, 'INSTAGRAM_DRY_RUN', False)
        if is_mock and not getattr(settings, 'DEBUG', False):
            raise ImproperlyConfigured(
                "Xavfsizlik xatosi: Soxta rejim (INSTAGRAM_MODE='mock' / INSTAGRAM_DRY_RUN=True) "
                "ishlab chiqarish rejimida (DEBUG=False) ishlatilishi mumkin emas! "
                "Iltimos, INSTAGRAM_MODE='real' qiling yoki sinov uchun DEBUG=True rejimini yoqing."
            )
        import tracker.signals
