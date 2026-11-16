import time
from django.utils import timezone
from tracker.models import Post
from tracker.tasks import check_all_due_posts_task
from tracker.instagram_errors import get_redis_client

n = Post.objects.filter(status__in=['published', 'verified']).update(next_check_at=timezone.now())
print("tekshiriladigan postlar:", n)
r = get_redis_client()
r.delete('dry_run:sim:counters:total_chunks')
r.set('dry_run:sim:counters:completed_chunks', 0)
t = time.time()
check_all_due_posts_task.delay()
while time.time() - t < 1800:
    tot = r.get('dry_run:sim:counters:total_chunks')
    dn = r.get('dry_run:sim:counters:completed_chunks')
    print(round(time.time() - t), dn, '/', tot, flush=True)
    if tot and dn and int(dn) >= int(tot):
        break
    time.sleep(2)
el = time.time() - t
print('JAMI', round(el), 'soniya ->', round(n / el * 3600), 'post/soat')
