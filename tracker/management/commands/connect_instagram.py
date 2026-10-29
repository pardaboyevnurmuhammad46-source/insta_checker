import os
from datetime import timedelta
import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from tracker.models import InstagramUser
from tracker.services import verify_token_permissions


class Command(BaseCommand):
    help = "INSTAGRAM_ACCESS_TOKEN orqali foydalanuvchini to'g'ridan-to'g'ri haqiqiy Instagram akkauntiga bog'laydi (ulash/connect)."

    def add_arguments(self, parser):
        parser.add_argument(
            'username_or_id',
            type=str,
            nargs='?',
<<<<<<< HEAD
            default='nurmuhammad_pardaboyev',
            help="Foydalanuvchi nomi (username) yoki InstagramUser ID (standart: nurmuhammad_pardaboyev)",
=======
            default='nurmuhmmad_pardaboyev',
            help="Foydalanuvchi nomi (username) yoki InstagramUser ID (standart: nurmuhmmad_pardaboyev)",
>>>>>>> origin/messi
        )
        parser.add_argument(
            '--token',
            type=str,
            default=None,
            help="Instagram Access Token (agar berilmasa, .env dagi INSTAGRAM_ACCESS_TOKEN ishlatiladi)",
        )

    def handle(self, *args, **options):
        identifier = options['username_or_id']
        custom_token = options.get('token')

        token = custom_token or os.environ.get('INSTAGRAM_ACCESS_TOKEN') or getattr(settings, 'INSTAGRAM_ACCESS_TOKEN', '')
        if not token:
            raise CommandError("INSTAGRAM_ACCESS_TOKEN topilmadi. Iltimos, .env faylini yoki --token parametrini tekshiring.")

        # 1. Instagram Graph API orqali tokenni tekshirish
        url = "https://graph.instagram.com/me"
        params = {
            'fields': 'user_id,username,account_type',
            'access_token': token,
        }
        try:
            res = requests.get(url, params=params, timeout=15)
        except requests.RequestException as exc:
            raise CommandError(f"Instagram serveriga ulanishda xatolik: {exc}")

        if res.status_code != 200:
            raise CommandError(f"Instagram tokenni qabul qilmadi (Status {res.status_code}): {res.text}")

        data = res.json()
        ig_username = data.get('username')
        ig_user_id = str(data.get('user_id') or data.get('id') or '')
        account_type = data.get('account_type', 'UNKNOWN')

        # 2. Token ruxsatlarini tekshirish
        has_perms, missing = verify_token_permissions(token)
        if not has_perms:
            self.stdout.write(self.style.WARNING(f"Ogohlantirish: Ba'zi ruxsatlar yetishmasligi mumkin: {missing}"))

        # 3. Django foydalanuvchisini topish
        ig_user = None
        if identifier.isdigit():
            ig_user = InstagramUser.objects.filter(id=int(identifier)).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(user__username__iexact=identifier).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(name__iexact=identifier).first()

        if not ig_user:
<<<<<<< HEAD
            # Agar foydalanuvchi mavjud bo'lmasa, uni yaratamiz
            django_user = User.objects.filter(username__iexact=identifier).first()
            if not django_user:
                django_user = User.objects.create_user(
                    username=identifier,
                    first_name=identifier,
                )
                django_user.set_unusable_password()
                django_user.save()
            ig_user, _ = InstagramUser.objects.get_or_create(
                user=django_user,
                defaults={'name': django_user.get_full_name() or django_user.username}
            )
=======
            # Agar foydalanuvchi Django auth User sifatida mavjud bo'lsa, unga InstagramUser yaratamiz
            django_user = User.objects.filter(username__iexact=identifier).first()
            if django_user:
                ig_user, _ = InstagramUser.objects.get_or_create(
                    user=django_user,
                    defaults={'name': django_user.get_full_name() or django_user.username}
                )
            else:
                raise CommandError(f"Foydalanuvchi topilmadi: '{identifier}'")
>>>>>>> origin/messi

        # 4. Foydalanuvchini ulash
        ig_user.ig_user_id = ig_user_id or ig_user.ig_user_id
        ig_user.name = ig_username or ig_user.name
        ig_user.access_token = token
        ig_user.status = 'connected'
        ig_user.token_expires_at = timezone.now() + timedelta(days=60)
        ig_user.save()

        self.stdout.write(self.style.SUCCESS("=" * 55))
        self.stdout.write(self.style.SUCCESS(f" [OK] Foydalanuvchi muvaffaqiyatli Instagramga ulandi!"))
        self.stdout.write(self.style.SUCCESS("=" * 55))
        self.stdout.write(f"Django User:        {ig_user.user.username if ig_user.user else 'None'}")
        self.stdout.write(f"Instagram Akkaunt:  @{ig_username}")
        self.stdout.write(f"Instagram ID:       {ig_user_id}")
        self.stdout.write(f"Akkaunt turi:       {account_type}")
        self.stdout.write(f"Holati:             {ig_user.status.upper()} (Reels ruxsati faol)")
        self.stdout.write(f"Amal qilish muddati: 60 kun")
        self.stdout.write(self.style.SUCCESS("=" * 55))
