import os
import django
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from tracker.models import InstagramUser, UniqueLink
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings

def generate_test_links(count=5):
    print(f"Generating {count} test users and links...")
    
    # Create a dummy video file if it doesn't exist
    video_content = b"fake video content for testing"
    
    links = []
    for i in range(count):
        # 1. Create a User
        user = InstagramUser.objects.create(
            name=f"Test User {i+1}",
            status="pending"
        )
        
        # 2. Create a Link
        video_file = SimpleUploadedFile(f"test_video_{i+1}.mp4", video_content, content_type="video/mp4")
        link = UniqueLink.objects.create(
            user=user,
            video=video_file,
            status="pending"
        )
        
        full_url = f"{settings.SITE_URL.rstrip('/')}/link/{link.token}/"
        links.append(full_url)
        print(f"Created: {full_url}")
        
    print("\nTest links generation complete!")
    print("O'z telefoningiz yoki brauzeringiz orqali yuqoridagi manzillarga kiring va Instagram orqali ruxsat bering.")

if __name__ == '__main__':
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    generate_test_links(count)
