from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from tracker.models import InstagramUser, UniqueLink, Video, get_video_for_user


class Command(BaseCommand):
    help = "Foydalanuvchi uchun unikal havola (UniqueLink) yaratadi va to'liq https havolani ko'rsatadi."

    def add_arguments(self, parser):
        parser.add_argument('user_id_or_name', type=str, help="InstagramUser ID yoki Foydalanuvchi nomi")
        parser.add_argument('--video', type=int, help="Biriktiriladigan Video ID (ixtiyoriy)")

    def handle(self, *args, **options):
        identifier = options['user_id_or_name']
        video_id = options.get('video')

        ig_user = None
        if identifier.isdigit():
            ig_user = InstagramUser.objects.filter(id=int(identifier)).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(name__iexact=identifier).first()
        if not ig_user:
            ig_user = InstagramUser.objects.filter(user__username__iexact=identifier).first()

        if not ig_user:
            raise CommandError(f"Foydalanuvchi topilmadi: '{identifier}'")

        chosen_video = None
        if video_id:
            chosen_video = Video.objects.filter(id=video_id, is_active=True).first()
            if not chosen_video:
                raise CommandError(f"Faol video topilmadi: ID={video_id}")
        else:
            chosen_video = get_video_for_user(ig_user)

        link = UniqueLink.objects.create(user=ig_user, video=chosen_video)

        base_url = (getattr(settings, 'PUBLIC_BASE_URL', '') or getattr(settings, 'SITE_URL', 'http://127.0.0.1:8000')).rstrip('/')
        full_url = f"{base_url}/link/{link.token}/"

        self.stdout.write(self.style.SUCCESS(f"Foydalanuvchi: {ig_user.name} (ID: {ig_user.id})"))
        if chosen_video:
            self.stdout.write(self.style.SUCCESS(f"Video: {chosen_video.title} (ID: {chosen_video.id})"))
        else:
            self.stdout.write(self.style.WARNING("Video: Biriktirilmadi (tizimda video mavjud emas)"))

        self.stdout.write(self.style.SUCCESS(f"Unikal Link: {full_url}"))
