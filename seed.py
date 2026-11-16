from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
from tracker.models import InstagramUser, UniqueLink, Post

U = get_user_model()
pw = make_password('loadtest123')   # bir marta hash, aks holda 1000 x 0.4s
N, POSTS_PER_USER = 1000, 3
now = timezone.now()

for i in range(1, N + 1):
    u, created = U.objects.get_or_create(username=f'loadtest{i}', defaults={'password': pw})
    if not created:
        u.password = pw
        u.save(update_fields=['password'])
    ig, _ = InstagramUser.objects.get_or_create(user=u, defaults={'name': f'lt{i}'})
    ig.ig_user_id = f'1784{i:010d}'
    ig.access_token = f'dry_run_tok_{i}'
    ig.status = 'connected'
    ig.token_expires_at = now + timedelta(days=60)
    ig.save()
    for j in range(POSTS_PER_USER):
        if Post.objects.filter(ig_media_id=f'dry_run_media_{i}_{j}').exists():
            continue
        link = UniqueLink.objects.create(user=ig, status='posted')
        Post.objects.create(
            link=link,
            ig_media_id=f'dry_run_media_{i}_{j}',
            status='published',
            posted_at=now - timedelta(hours=j * 5),
            views=100 * j,
            next_check_at=now,
        )
print('ok')
