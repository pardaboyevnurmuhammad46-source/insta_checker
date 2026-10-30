import os
import django
from django.utils import timezone
from datetime import timedelta
from django.core.files.base import ContentFile

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from tracker.models import InstagramUser, UniqueLink, Post, PostStat, Prize, Notification, Video


def generate_demo_data():
    print("Namunaviy ko'rgazmali ma'lumotlarni yaratish boshlandi...")

    # 1. Admin foydalanuvchi
    admin_user, _ = User.objects.get_or_create(
        username="admin",
        defaults={"is_staff": True, "is_superuser": True}
    )
    admin_user.set_password("admin123")
    admin_user.is_staff = True
    admin_user.is_superuser = True
    admin_user.save()

    ig_admin, _ = InstagramUser.objects.get_or_create(
        user=admin_user,
        defaults={
            "name": "Bosh Administrator",
            "ig_user_id": "1784140001",
            "status": "connected",
        }
    )

    # 2. Umumiy (Default) Video
    default_video, _ = Video.objects.get_or_create(
        title="Rasmiy Promo Video (Default)",
        is_default=True,
        defaults={
            "is_active": True,
        }
    )
    if not default_video.file:
        default_video.file.save("default_promo.mp4", ContentFile(b"fake_mp4_video_content_data"))
        default_video.save()

    # 3. Foydalanuvchi 1: Bekzod (Faol, postlari va sovrinlari bor)
    user_bekzod, _ = User.objects.get_or_create(username="bekzod")
    user_bekzod.set_password("user123")
    user_bekzod.save()

    ig_bekzod, _ = InstagramUser.objects.get_or_create(
        user=user_bekzod,
        defaults={
            "name": "Bekzod Aliyev",
            "ig_user_id": "1784140002",
            "access_token": "demo_long_lived_token_bekzod",
            "status": "connected",
            "token_expires_at": timezone.now() + timedelta(days=45),
        }
    )
    ig_bekzod.status = 'connected'
    ig_bekzod.access_token = 'demo_long_lived_token_bekzod'
    ig_bekzod.token_expires_at = timezone.now() + timedelta(days=45)
    ig_bekzod.save()

    # Bekzodning shaxsiy videosi
    personal_video, _ = Video.objects.get_or_create(
        title="Bekzod Maxsus Reels",
        owner=ig_bekzod,
        defaults={"is_active": True, "is_default": False}
    )
    if not personal_video.file:
        personal_video.file.save("bekzod_reels.mp4", ContentFile(b"fake_bekzod_mp4_data"))
        personal_video.save()

    # Bekzodning Post 1: 1 250 ko'rish (500 va 1000 marralarga yetgan)
    link1 = UniqueLink.objects.filter(user=ig_bekzod, video=personal_video).first()
    if not link1:
        link1 = UniqueLink.objects.create(user=ig_bekzod, status="posted", video=personal_video)
    post1, _ = Post.objects.get_or_create(
        link=link1,
        defaults={
            "status": "published",
            "ig_media_id": "18012345678",
            "permalink": "https://www.instagram.com/reel/C123456789/",
            "views": 1250,
            "likes": 94,
            "comments_count": 22,
            "posted_at": timezone.now() - timedelta(days=4),
            "last_checked_at": timezone.now() - timedelta(minutes=10),
            "next_check_at": timezone.now() + timedelta(hours=3),
        }
    )
    post1.views = 1250
    post1.likes = 94
    post1.comments_count = 22
    post1.save()

    # Tarix (PostStat) yozish
    if post1.stats.count() == 0:
        PostStat.objects.create(post=post1, views=120, likes=10, comments_count=2, checked_at=timezone.now() - timedelta(days=3, hours=18))
        PostStat.objects.create(post=post1, views=350, likes=28, comments_count=7, checked_at=timezone.now() - timedelta(days=3))
        PostStat.objects.create(post=post1, views=580, likes=45, comments_count=11, checked_at=timezone.now() - timedelta(days=2))
        PostStat.objects.create(post=post1, views=920, likes=71, comments_count=16, checked_at=timezone.now() - timedelta(days=1))
        PostStat.objects.create(post=post1, views=1250, likes=94, comments_count=22, checked_at=timezone.now() - timedelta(minutes=10))

    # Prizlar (500 va 1000)
    Prize.objects.get_or_create(post=post1, milestone=500, defaults={"sent_at": timezone.now() - timedelta(days=2)})
    Prize.objects.get_or_create(post=post1, milestone=1000, defaults={"sent_at": timezone.now() - timedelta(days=1)})

    # Bekzodning Post 2: 420 ko'rish (500 marraga yaqinlashgan, 80% dan oshgan!)
    link2, _ = UniqueLink.objects.get_or_create(
        user=ig_bekzod,
        token="b1234567-89ab-cdef-0123-456789abcdef",
        defaults={"status": "posted", "video": personal_video}
    )
    post2, _ = Post.objects.get_or_create(
        link=link2,
        defaults={
            "status": "published",
            "ig_media_id": "18098765432",
            "permalink": "https://www.instagram.com/reel/C987654321/",
            "views": 420,
            "likes": 35,
            "comments_count": 8,
            "posted_at": timezone.now() - timedelta(hours=14),
            "last_checked_at": timezone.now() - timedelta(minutes=12),
            "next_check_at": timezone.now() + timedelta(minutes=15),
        }
    )

    # Bekzodning Post 3: O'chirilgan post (Deleted)
    link3, _ = UniqueLink.objects.get_or_create(
        user=ig_bekzod,
        token="c1234567-89ab-cdef-0123-456789abcdef",
        defaults={"status": "posted", "video": default_video}
    )
    Post.objects.get_or_create(
        link=link3,
        defaults={
            "status": "deleted",
            "ig_media_id": "18011223344",
            "views": 65,
            "likes": 4,
            "comments_count": 1,
            "posted_at": timezone.now() - timedelta(days=8),
            "deleted_detected_at": timezone.now() - timedelta(days=2),
            "error": "Instagram'dan post o'chirilgan.",
        }
    )

    # 4. Foydalanuvchi 2: Dilshod (Token muddati 3 kundan keyin tugaydi - warning uchun)
    user_dilshod, _ = User.objects.get_or_create(username="dilshod")
    user_dilshod.set_password("user123")
    user_dilshod.save()

    ig_dilshod, _ = InstagramUser.objects.get_or_create(
        user=user_dilshod,
        defaults={
            "name": "Dilshod Karimov",
            "ig_user_id": "1784140003",
            "status": "connected",
            "token_expires_at": timezone.now() + timedelta(days=3),
        }
    )

    link_dilshod = UniqueLink.objects.filter(user=ig_dilshod, video=default_video).first()
    if not link_dilshod:
        link_dilshod = UniqueLink.objects.create(user=ig_dilshod, status="posted", video=default_video)
    post_dilshod = Post.objects.filter(link=link_dilshod).first()
    if not post_dilshod:
        post_dilshod = Post.objects.create(
            link=link_dilshod,
            status="published",
            ig_media_id="18055667788",
            permalink="https://www.instagram.com/reel/C556677889/",
            views=530,
            likes=42,
            comments_count=9,
            posted_at=timezone.now() - timedelta(days=2),
            last_checked_at=timezone.now() - timedelta(hours=2),
        )

    # 5. Foydalanuvchi 3: Nodira (Yangi ro'yxatdan o'tgan, Instagramga hali ulanmagan)
    user_nodira, _ = User.objects.get_or_create(username="nodira")
    user_nodira.set_password("user123")
    user_nodira.save()

    InstagramUser.objects.get_or_create(
        user=user_nodira,
        defaults={
            "name": "Nodira Rustamova",
            "status": "pending",
        }
    )

    # 6. Asosiy Foydalanuvchi: nurmuhammad va nurmuhmmad_pardaboyev (Instagram to'liq ulangan, Reels va sovrinlar mavjud)
    for idx, un in enumerate(["nurmuhammad", "nurmuhmmad_pardaboyev"], start=1):
        u_nur, _ = User.objects.get_or_create(username=un)
        u_nur.set_password("user123")
        u_nur.first_name = "Nurmuhammad"
        u_nur.last_name = "Pardaboyev"
        u_nur.save()

        ig_nur, _ = InstagramUser.objects.get_or_create(
            user=u_nur,
            defaults={
                "name": "nurmuhammad_pardaboyev",
                "ig_user_id": f"1784146856371300{idx}",
                "access_token": f"demo_token_nurmuhammad_2026_{idx}",
                "status": "connected",
                "token_expires_at": timezone.now() + timedelta(days=60),
            }
        )
        ig_nur.name = "nurmuhammad_pardaboyev"
        ig_nur.ig_user_id = f"1784146856371300{idx}"
        ig_nur.status = "connected"
        ig_nur.access_token = f"demo_token_nurmuhammad_2026_{idx}"
        ig_nur.token_expires_at = timezone.now() + timedelta(days=60)
        ig_nur.save()

        link_nur = UniqueLink.objects.filter(user=ig_nur, video=default_video).first()
        if not link_nur:
            link_nur = UniqueLink.objects.create(user=ig_nur, status="posted", video=default_video)

        post_nur = Post.objects.filter(link=link_nur).first()
        if not post_nur:
            post_nur = Post.objects.create(
                link=link_nur,
                status="published",
                ig_media_id=f"17841468563713006_reel_{idx}",
                permalink=f"https://www.instagram.com/reel/nurmuhammad_pardaboyev_{idx}/",
                views=2500,
                likes=180,
                comments_count=35,
                posted_at=timezone.now() - timedelta(days=3),
                last_checked_at=timezone.now() - timedelta(minutes=5),
            )
        post_nur.views = 2500
        post_nur.likes = 180
        post_nur.comments_count = 35
        post_nur.save()

        Prize.objects.get_or_create(post=post_nur, milestone=500, defaults={"sent_at": timezone.now() - timedelta(days=2)})
        Prize.objects.get_or_create(post=post_nur, milestone=1000, defaults={"sent_at": timezone.now() - timedelta(days=1)})

    print("\n" + "=" * 50)
    print("NAMUNAVIY MA'LUMOTLAR MUVAFFAQIYATLI YARATILDI!")
    print("=" * 50)
    print("Kirish ma'lumotlari (Web panel uchun):")
    print("1. Administrator:")
    print("   Login:    admin")
    print("   Parol:    admin123")
    print("   Panel:    http://localhost:8080/admin-panel")
    print("")
    print("2. Faol Foydalanuvchi (Postlari va sovrinlari bor):")
    print("   Login:    bekzod")
    print("   Parol:    user123")
    print("   Panel:    http://localhost:8080/app")
    print("")
    print("3. Ogohlantirishli Foydalanuvchi (Token muddati yaqin):")
    print("   Login:    dilshod")
    print("   Parol:    user123")
    print("")
    print("4. Yangi Foydalanuvchi (Ulanmagan):")
    print("   Login:    nodira")
    print("   Parol:    user123")
    print("=" * 50)


def generate_benchmark_data(num_users: int = 1000, clear_existing: bool = False):
    """
    3-bosqich tezlikni o'lchash (benchmark) uchun sintetik ma'lumotlar yaratadi.
    Xavfsizlik: Faqat INSTAGRAM_MODE='mock' yoki INSTAGRAM_DRY_RUN=True rejimida ishlaydi.
    Har bir user uchun IGAA... sintetik token va 1-3 ta tekshirishga tayyor (due) post yaratiladi.
    """
    from django.conf import settings
    import uuid
    import random
    from tracker.models import generate_unique_link_code

    is_mock = getattr(settings, 'INSTAGRAM_MODE', 'real') == 'mock' or getattr(settings, 'INSTAGRAM_DRY_RUN', False)
    if not is_mock:
        raise ValueError(
            "Xavfsizlik xatosi: Benchmark ma'lumotlarini yaratish faqat INSTAGRAM_MODE='mock' "
            "yoki INSTAGRAM_DRY_RUN=True rejimida ruxsat etiladi! Haqiqiy Instagram rejimida sinov ma'lumotlari yaratilmaydi."
        )

    print(f"\n[BENCHMARK] {num_users} ta foydalanuvchi uchun sinov ma'lumotlarini yaratish boshlandi...")

    if clear_existing:
        print("[BENCHMARK] Eski benchmark ma'lumotlari o'chirilmoqda...")
        benchmark_users = InstagramUser.objects.filter(name__startswith="Benchmark User ")
        deleted_count, _ = benchmark_users.delete()
        print(f"[BENCHMARK] {deleted_count} ta eski yozuv tozalandi.")

    default_video, _ = Video.objects.get_or_create(
        title="Rasmiy Promo Video (Default)",
        is_default=True,
        defaults={"is_active": True}
    )
    if not default_video.file:
        default_video.file.save("default_promo.mp4", ContentFile(b"fake_mp4_video_content_data"))
        default_video.save()

    now = timezone.now()
    batch_size = 2000

    # 1. InstagramUser yaratish (bulk_create)
    print(f"[BENCHMARK] {num_users} ta InstagramUser yaratilmoqda...")
    users_to_create = []
    base_id = int(timezone.now().timestamp())
    for i in range(1, num_users + 1):
        u = InstagramUser(
            name=f"Benchmark User {i}",
            ig_user_id=f"1784149{base_id % 100000:05d}{i:05d}",
            access_token=f"IGAABenchmarkToken_{i}_{uuid.uuid4().hex[:12]}",
            token_expires_at=now + timedelta(days=60),
            status="connected",
        )
        users_to_create.append(u)
        if len(users_to_create) >= batch_size:
            InstagramUser.objects.bulk_create(users_to_create)
            users_to_create = []

    if users_to_create:
        InstagramUser.objects.bulk_create(users_to_create)

    # Yaratilgan userlarni to'g'ridan-to'g'ri sanash (agar num_users > 0 bo'lsa)
    created_users = []
    if num_users > 0:
        created_users = list(
            InstagramUser.objects.filter(name__startswith="Benchmark User ").order_by('-id')[:num_users]
        )

    # 2. UniqueLink lar yaratish (har userga 1-3 ta)
    print(f"[BENCHMARK] Har bir userga 1-3 tadan UniqueLink yaratilmoqda...")
    used_codes = set(UniqueLink.objects.values_list('code', flat=True))
    links_to_create = []
    for u in created_users:
        posts_count = random.randint(1, 3)
        for _ in range(posts_count):
            while True:
                candidate = generate_unique_link_code()
                if candidate not in used_codes:
                    used_codes.add(candidate)
                    break
            links_to_create.append(
                UniqueLink(
                    user=u,
                    video=default_video,
                    status="posted",
                    code=candidate,
                )
            )
            if len(links_to_create) >= batch_size:
                UniqueLink.objects.bulk_create(links_to_create)
                links_to_create = []

    if links_to_create:
        UniqueLink.objects.bulk_create(links_to_create)

    created_links = list(
        UniqueLink.objects.filter(user__in=created_users).order_by('id')
    )

    # 3. Post lar yaratish (har link uchun 1 ta)
    import json
    from tracker.instagram_errors import get_redis_client
    r = get_redis_client()

    print(f"[BENCHMARK] {len(created_links)} ta Post yaratilmoqda...")
    posts_to_create = []
    post_idx = 1
    
    # Redis'ga user postlari xaritasini saqlash
    user_media_map = {}

    for link in created_links:
        ig_media_id = f"18999{base_id % 10000:04d}{post_idx:07d}"
        posts_to_create.append(
            Post(
                link=link,
                ig_media_id=ig_media_id,
                status="published",
                views=random.randint(50, 480),
                likes=random.randint(5, 45),
                comments_count=random.randint(1, 10),
                posted_at=now - timedelta(hours=random.randint(1, 48)),
                last_checked_at=now - timedelta(minutes=random.randint(10, 120)),
                next_check_at=now - timedelta(seconds=random.randint(5, 300)), # o'tmishda, darhol due
            )
        )
        post_idx += 1
        
        # Redis xaritasiga qo'shish
        user_media_map.setdefault(link.user.access_token, []).append(ig_media_id)
        
        if len(posts_to_create) >= batch_size:
            Post.objects.bulk_create(posts_to_create)
            posts_to_create = []

    if posts_to_create:
        Post.objects.bulk_create(posts_to_create)

    # Redis'ga bitta pipeline'da yozish
    pipe = r.pipeline()
    for token, media_ids in user_media_map.items():
        pipe.set(f"dry_run:sim:token_media:{token}", json.dumps(media_ids), ex=86400)
    pipe.execute()

    total_posts = Post.objects.filter(link__user__in=created_users).count()
    print(f"[BENCHMARK] Muvaffaqiyatli yakunlandi! Jami: {len(created_users)} ta user va {total_posts} ta post yaratildi.")
    print("=" * 50)


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="InstaChecker test va benchmark ma'lumotlarini yaratish")
    parser.add_argument('--benchmark', action='store_true', help="3-bosqich benchmark uchun sintetik ma'lumotlar yaratish")
    parser.add_argument('--users', type=int, default=1000, help="Benchmark uchun yaratiladigan userlar soni (default: 1000)")
    parser.add_argument('--clear', action='store_true', help="Eski benchmark userlarini tozalash")

    args = parser.parse_args()

    if args.benchmark:
        generate_benchmark_data(num_users=args.users, clear_existing=args.clear)
    else:
        generate_demo_data()
