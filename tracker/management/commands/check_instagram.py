import os
import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "INSTAGRAM_ACCESS_TOKEN bilan Instagram profil ma'lumotlarini (username, account_type) tekshiradi."

    def handle(self, *args, **options):
        token = os.environ.get('INSTAGRAM_ACCESS_TOKEN') or getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '')
        if not token:
            self.stderr.write("Xatolik: INSTAGRAM_ACCESS_TOKEN muhit o'zgaruvchisi topilmadi yoki bo'sh.")
            return

        url = "https://graph.instagram.com/me"
        params = {
            'fields': 'user_id,username,account_type',
            'access_token': token,
        }

        try:
            response = requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            msg = str(exc).replace(token, '[REDACTED]')
            self.stderr.write(f"Tarmoq xatoligi: {msg}")
            return

        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                self.stderr.write("Xatolik: Instagram serveridan noto'g'ri JSON javob qaytdi.")
                return

            username = data.get('username')
            account_type = data.get('account_type')
            self.stdout.write(f"username: {username}")
            self.stdout.write(f"account_type: {account_type}")
            return

        # Xatolik yuz berganda
        try:
            err_json = response.json()
            err_data = err_json.get('error', {})
            code = err_data.get('code', response.status_code)
            message = err_data.get('message', response.text)
        except Exception:
            code = response.status_code
            message = response.text

        clean_message = str(message).replace(token, '[REDACTED]')
        self.stderr.write(f"Instagram xatosi: code={code}, message={clean_message}")
