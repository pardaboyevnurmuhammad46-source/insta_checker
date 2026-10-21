from django.core.management.base import BaseCommand, CommandError
from tracker.models import InstagramUser, UniqueLink, get_video_for_user
from tracker.services import build_instagram_auth_url


class Command(BaseCommand):
    help = "Foydalanuvchi uchun yangi UniqueLink yaratib, Instagram authorize URL ni ko'rsatadi."

    def add_arguments(self, parser):
        parser.add_argument('user_id', type=str, help="InstagramUser ID yoki Foydalanuvchi nomi")

    def handle(self, *args, **options):
        user_identifier = options['user_id']

        ig_user = None
        if user_identifier.isdigit():
            ig_user = InstagramUser.objects.filter(id=int(user_identifier)).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(name__iexact=user_identifier).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(user__username__iexact=user_identifier).first()

        if not ig_user:
            raise CommandError(f"Foydalanuvchi topilmadi: '{user_identifier}'")

        chosen_video = get_video_for_user(ig_user)
        link = UniqueLink.objects.create(user=ig_user, video=chosen_video)

        auth_url = build_instagram_auth_url(str(link.token))

        self.stdout.write(self.style.SUCCESS(f"Foydalanuvchi: {ig_user.name} (ID: {ig_user.id})"))
        self.stdout.write(self.style.SUCCESS(f"Yaratilgan Link Token: {link.token}"))
        self.stdout.write("Instagram Authorize URL:")
        self.stdout.write(auth_url)
