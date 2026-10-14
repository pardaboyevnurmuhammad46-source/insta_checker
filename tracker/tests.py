from django.test import TestCase

from django.conf import settings


class SettingsEnvTestCase(TestCase):
    def test_settings_loaded_from_env(self):
        self.assertTrue(settings.SECRET_KEY)
        self.assertIsInstance(settings.ALLOWED_HOSTS, list)
        self.assertIn('default', settings.DATABASES)
        self.assertIn('ig_tracker', settings.DATABASES['default']['NAME'])

