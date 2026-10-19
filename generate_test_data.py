import os
import django
from django.utils import timezone
from datetime import timedelta
import time
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracker.models import InstagramUser, UniqueLink, Post, Video
from tracker.tasks import check_all_due_posts_task
from django.contrib.auth.models import User

def run():
    print("Test ma'lumotlarini yaratish boshlandi...")
    
    # 1. Tizim uchun yagona default video yaratamiz
    video, _ = Video.objects.get_or_create(
        title="Load Test Video",
        is_default=True,
        defaults={'file': 'videos/load_test.mp4'}
    )
    
    # 2. Bitta foydalanuvchi yaratamiz
    user, _ = User.objects.get_or_create(username="loadtest_user", defaults={"password": "password"})
    ig_user, _ = InstagramUser.objects.get_or_create(
        user=user,
        defaults={
            "name": "Load Test",
            "ig_user_id": "123456789",
            "access_token": "fake_token",
            "status": "connected"
        }
    )
    
    # 3. 10 000 ta "tekshiruv vaqti kelgan" postlarni ommaviy (bulk) yaratamiz
    total_posts = 10000
    links_to_create = []
    
    # Eskilarini tozalash (agar kerak bo'lsa)
    print("Eski load test ma'lumotlari tozalanmoqda...")
    UniqueLink.objects.filter(user=ig_user).delete()
    
    print(f"{total_posts} ta UniqueLink yaratilmoqda...")
    for i in range(total_posts):
        links_to_create.append(UniqueLink(user=ig_user, video=video, status='posted'))
    UniqueLink.objects.bulk_create(links_to_create, batch_size=2000)
    
    created_links = list(UniqueLink.objects.filter(user=ig_user).values_list('id', flat=True))
    
    print(f"{total_posts} ta Post yaratilmoqda...")
    now = timezone.now()
    past_due = now - timedelta(minutes=5)
    posts_to_create = []
    
    for i, link_id in enumerate(created_links):
        posts_to_create.append(Post(
            link_id=link_id,
            status='published',
            ig_media_id=f"media_{i}",
            permalink=f"https://instagram.com/reel/media_{i}/",
            posted_at=now - timedelta(days=1),
            next_check_at=past_due,
            views=random.randint(100, 400)
        ))
        
    Post.objects.bulk_create(posts_to_create, batch_size=2000)
    
    print("Barcha ma'lumotlar yaratildi. check_all_due_posts_task ishga tushirilmoqda...")
    
    start_time = time.time()
    dispatched = check_all_due_posts_task()
    end_time = time.time()
    
    print(f"Jami yuborilgan postlar: {dispatched}")
    print(f"Bajarishga ketgan vaqt: {end_time - start_time:.2f} soniya")

if __name__ == '__main__':
    run()
