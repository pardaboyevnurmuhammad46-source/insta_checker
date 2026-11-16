import time
from tracker.models import InstagramUser, UniqueLink, Post
from tracker.tasks import publish_reels_task

users = list(InstagramUser.objects.filter(status='connected')[:500])
links = [UniqueLink.objects.create(user=u) for u in users]
ids = [l.id for l in links]
t0 = time.time()
for lid in ids:
    publish_reels_task.delay(lid)
print("navbatga qo'yildi:", len(ids))
while time.time() - t0 < 1800:   # 30 daqiqadan ortiq kutmaydi
    done = Post.objects.filter(link_id__in=ids, status__in=['published', 'failed']).count()
    print(f"{time.time()-t0:6.1f}s  tugadi: {done}/{len(ids)}", flush=True)
    if done == len(ids):
        break
    time.sleep(5)
total = time.time() - t0
pub = Post.objects.filter(link_id__in=ids, status='published').count()
fail = Post.objects.filter(link_id__in=ids, status='failed').count()
print(f"JAMI {total:.0f}s -> {len(ids)/total*3600:.0f} post/soat, {len(ids)/total*86400:.0f} post/sutka")
print("published:", pub, "failed:", fail)
