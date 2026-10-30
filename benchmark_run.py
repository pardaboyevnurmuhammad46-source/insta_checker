#!/usr/bin/env python3
"""
Benchmark Run Script for InstaChecker
O'lchov senariylari:
  a) DRY_RUN_API_DELAY_MIN=0 MAX=0, 10 000 user, concurrency 4 (Celery + DB tezligi)
  b1) DRY_RUN_API_DELAY_MIN=0.2 MAX=0.5, 500 user, concurrency 4
  b2) DRY_RUN_API_DELAY_MIN=0.2 MAX=0.5, 500 user, concurrency 8

INSTAGRAM_MODE=mock, haqiqiy Instagramga so'rov ketmaydi.
"""

import os
import sys
import time
import signal
import subprocess
import argparse

# Django muhitini sozlash
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
os.environ['INSTAGRAM_MODE'] = 'mock'
os.environ['INSTAGRAM_DRY_RUN'] = 'True'
os.environ['INSTAGRAM_API_RATE_LIMIT'] = '100000'
os.environ['INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_SEC'] = '1000'
os.environ['INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR'] = '100000'

import django
django.setup()

from django.conf import settings
from tracker.models import InstagramUser, Post
from tracker.tasks import check_all_due_posts_task
from tracker.instagram_errors import get_redis_client
from generate_test_data import generate_benchmark_data


def start_celery_worker(concurrency: int, delay_min: float, delay_max: float):
    """Celery worker jarayonini alohida muhit o'zgaruvchilari bilan ishga tushiradi."""
    env = os.environ.copy()
    env['INSTAGRAM_MODE'] = 'mock'
    env['INSTAGRAM_DRY_RUN'] = 'True'
    env['INSTAGRAM_API_RATE_LIMIT'] = '100000'
    env['INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_SEC'] = '1000'
    env['INSTAGRAM_ACCOUNT_RATE_LIMIT_PER_HOUR'] = '100000'
    env['DRY_RUN_API_DELAY_MIN'] = str(delay_min)
    env['DRY_RUN_API_DELAY_MAX'] = str(delay_max)

    cmd = [
        sys.executable,
        "-m", "celery",
        "-A", "config",
        "worker",
        "--loglevel=WARNING",
        f"--concurrency={concurrency}",
        "-Q", "celery",
    ]
    print(f"[*] Celery worker ishga tushirilmoqda (concurrency={concurrency}, delay={delay_min}-{delay_max}s)...")
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)  # Worker ishga tushishi va Redis ga ulanishi uchun kutish
    return proc


def stop_celery_worker(proc):
    """Worker jarayonini xavfsiz to'xtatadi."""
    if proc and proc.poll() is None:
        print("[*] Celery worker to'xtatilmoqda...")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def clean_benchmark_data_and_counters(r):
    """Eski benchmark foydalanuvchilari va Redis hisoblagichlarini tozalaydi."""
    print("[*] Benchmark ma'lumotlari va Redis hisoblagichlari tozalanmoqda...")
    # Redis tozalash
    counter_keys = [
        "dry_run:sim:counters:list_recent_media",
        "dry_run:sim:counters:get_media_insights",
        "dry_run:sim:counters:fetch_post_metrics",
        "dry_run:sim:counters:completed_chunks",
        "dry_run:sim:counters:total_chunks",
        "lock:celery_beat:check_all_due_posts",
        "{ig_rate}:global",
        "{ig_rate}:throttle_backoff",
    ]
    for k in counter_keys:
        try:
            r.delete(k)
        except Exception:
            pass

    # Celery navbatini tozalash
    try:
        r.delete("celery")
    except Exception:
        pass

    # DB dan Benchmark userlarini o'chirish
    try:
        InstagramUser.objects.filter(name__startswith="Benchmark User ").delete()
    except Exception as exc:
        print(f"[!] DB tozalashda ogohlantirish: {exc}")


def run_single_benchmark(num_users: int, concurrency: int, delay_min: float, delay_max: float):
    """Bitta benchmark senariysini to'liq bajaradi."""
    r = get_redis_client()

    print("\n" + "=" * 65)
    print(f"BENCHMARK BOSHLANDI: users={num_users}, concurrency={concurrency}, delay={delay_min}-{delay_max}s")
    print("=" * 65)

    # 1. Eski ma'lumotlarni tozalash
    clean_benchmark_data_and_counters(r)

    # 2. Yangi benchmark ma'lumotlarini generatsiya qilish
    # Sozlamalarni joriy run ga moslash
    setattr(settings, 'DRY_RUN_API_DELAY_MIN', delay_min)
    setattr(settings, 'DRY_RUN_API_DELAY_MAX', delay_max)
    setattr(settings, 'INSTAGRAM_API_RATE_LIMIT', 100000)

    print(f"[*] {num_users} ta foydalanuvchi ma'lumotlari yaratilmoqda...")
    generate_benchmark_data(num_users=num_users, clear_existing=True)

    from django.utils import timezone
    from datetime import timedelta
    # Boshqa mavjud postlarni 1 kunga suramiz, to dispatcher faqat benchmark postlarini tekshirsin
    now_ts = timezone.now()
    Post.objects.exclude(link__user__name__startswith="Benchmark User ").update(
        next_check_at=now_ts + timedelta(days=1)
    )

    total_posts = Post.objects.filter(link__user__name__startswith="Benchmark User ").count()
    print(f"[+] Ma'lumotlar tayyor: {num_users} user, {total_posts} post.")

    # Redis hisoblagichlarini nollash
    r.set("dry_run:sim:counters:list_recent_media", 0)
    r.set("dry_run:sim:counters:get_media_insights", 0)
    r.set("dry_run:sim:counters:fetch_post_metrics", 0)
    r.set("dry_run:sim:counters:completed_chunks", 0)
    r.set("dry_run:sim:counters:total_chunks", 0)

    # 3. Celery workerni ishga tushirish
    worker_proc = start_celery_worker(concurrency, delay_min, delay_max)

    try:
        # 4. Dispatcher vazifasini ishga tushirish
        print("[*] Dispatcher (check_all_due_posts_task) ishga tushirilmoqda...")
        t_start = time.time()
        dispatched_posts = check_all_due_posts_task()
        print(f"[+] Dispatcher {dispatched_posts} ta postni navbatga qo'ydi.")

        # 5. Hamma chunk tugaguncha kutish
        total_chunks = int(r.get("dry_run:sim:counters:total_chunks") or 0)
        print(f"[*] Jami chunklar: {total_chunks}. Bajarilish kutilmoqda...")

        last_log = 0
        timeout = 1800  # 30 daqiqa maks
        while time.time() - t_start < timeout:
            completed_chunks = int(r.get("dry_run:sim:counters:completed_chunks") or 0)
            cur_total = int(r.get("dry_run:sim:counters:total_chunks") or total_chunks)
            queue_len = r.llen("celery")

            if time.time() - last_log >= 3:
                pct = (completed_chunks / cur_total * 100) if cur_total > 0 else 0
                print(f"  -> Progress: {completed_chunks}/{cur_total} chunks ({pct:.1f}%), navbatda: {queue_len}")
                last_log = time.time()

            if cur_total > 0 and completed_chunks >= cur_total and queue_len == 0:
                print(f"[+] Barcha {cur_total} ta chunk muvaffaqiyatli yakunlandi!")
                break

            time.sleep(0.3)

        t_end = time.time()
        elapsed = t_end - t_start

        # 6. Hisoblagichlarni o'qish
        cnt_list_media = int(r.get("dry_run:sim:counters:list_recent_media") or 0)
        cnt_insights = int(r.get("dry_run:sim:counters:get_media_insights") or 0)
        cnt_fetch = int(r.get("dry_run:sim:counters:fetch_post_metrics") or 0)
        total_requests = cnt_list_media + cnt_insights + cnt_fetch
        posts_per_sec = total_posts / elapsed if elapsed > 0 else 0

        result = {
            "users": num_users,
            "posts": total_posts,
            "delay": f"{delay_min}-{delay_max}s",
            "delay_avg": (delay_min + delay_max) / 2.0,
            "concurrency": concurrency,
            "elapsed": round(elapsed, 2),
            "posts_per_sec": round(posts_per_sec, 2),
            "list_recent_media": cnt_list_media,
            "get_media_insights": cnt_insights,
            "fetch_post_metrics": cnt_fetch,
            "total_requests": total_requests,
        }

        print("\n" + "-" * 50)
        print(f"Natijalar (users={num_users}, conc={concurrency}, delay={delay_min}-{delay_max}s):")
        print(f"  Umumiy vaqt: {result['elapsed']} s")
        print(f"  Tezlik: {result['posts_per_sec']} post/s")
        print(f"  Hisoblagichlar:")
        print(f"    - list_recent_media: {cnt_list_media} (kutilgan: ~{num_users})")
        print(f"    - get_media_insights: {cnt_insights} (kutilgan: ~{total_posts})")
        print(f"    - fetch_post_metrics: {cnt_fetch} (kutilgan: ~0)")
        print(f"    - Jami so'rovlar: {total_requests}")
        print("-" * 50)

        # Muhim tekshiruv:
        if cnt_fetch > 0:
            print(f"[OGOHLANTIRISH] fetch_post_metrics hisoblagichi 0 emas ({cnt_fetch}). /me/media oqimi to'liq ishlamagan bo'lishi mumkin!")
        if cnt_list_media != num_users:
            print(f"[OGOHLANTIRISH] list_recent_media ({cnt_list_media}) userlar soniga ({num_users}) teng emas!")

        return result

    finally:
        # 7. Celery worker to'xtatish
        stop_celery_worker(worker_proc)
        # 8. Ma'lumotlarni tozalash
        clean_benchmark_data_and_counters(r)


def print_results_table(results):
    """Barcha natijalarni va hisob-kitoblarni chiroyli Markdown jadvalida chiqaradi."""
    print("\n" + "=" * 90)
    print("BENCHMARK NATIJALARI JADVALI")
    print("=" * 90)

    headers = ["Userlar", "Postlar", "Kechikish", "Concurrency", "Umumiy vaqt", "Post/sekund", "So'rovlar soni"]
    fmt_row = "| {:<8} | {:<8} | {:<12} | {:<11} | {:<12} | {:<12} | {:<14} |"
    sep = "|" + "|".join(["-" * 10, "-" * 10, "-" * 14, "-" * 13, "-" * 14, "-" * 14, "-" * 16]) + "|"

    print(fmt_row.format(*headers))
    print(sep)
    for r in results:
        print(fmt_row.format(
            r["users"],
            r["posts"],
            r["delay"],
            r["concurrency"],
            f"{r['elapsed']} s",
            f"{r['posts_per_sec']} p/s",
            r["total_requests"],
        ))

    print("\n" + "=" * 90)
    print("TEZRETIK FORMULA VA MASSHTAB TAXMINLARI")
    print("=" * 90)
    print("Formula:")
    print("  vaqt ≈ (userlar × userga_so'rovlar × o'rtacha_kechikish) / concurrency")
    print("  Bu yerda userga_so'rovlar ≈ 1 ta (list_recent_media) + o'rtacha 2 ta (get_media_insights) = 3 ta so'rov.")
    print("  O'rtacha kechikish delay_avg = (0.2 + 0.5) / 2 = 0.35 soniya (API kechikishi mavjud bo'lganda).")
    print("\nNazariy / Proektsiya taxminlari (faqat taxmin, o'lchangan emas):")

    for total_users in (100_000, 1_000_000):
        print(f"\n--- {total_users:,} USER UCHUN TAXMINLAR ---")
        for conc in (4, 8, 32, 64):
            # A) Kechikishsiz (Celery + DB, sof tizim tezligi):
            # Agar 10k user 4 conc bilan t_0 s vaqt olsa, tezlik v_0 = posts / t_0
            # B) Kechikish bilan (delay=0.35s, 3 ta so'rov/user):
            # t = (total_users * 3 * 0.35) / conc
            t_delay = (total_users * 3 * 0.35) / conc
            hours = t_delay / 3600.0
            print(f"  Concurrency {conc:<2}: vaqt ≈ {t_delay:,.1f} s ({hours:.2f} soat) [kechikish 0.35s bilan]")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="InstaChecker Benchmark Runner")
    parser.add_argument('--run-all', action='store_true', help="Barcha 3 ta senariyni (a, b1, b2) ketma-ket bajarish")
    parser.add_argument('--scenario', choices=['a', 'b1', 'b2'], help="Bitta aniq senariyni tanlash")
    parser.add_argument('--users', type=int, default=500, help="Foydalanuvchilar soni")
    parser.add_argument('--concurrency', type=int, default=4, help="Celery worker concurrency")
    parser.add_argument('--delay-min', type=float, default=0.0, help="DRY_RUN_API_DELAY_MIN")
    parser.add_argument('--delay-max', type=float, default=0.0, help="DRY_RUN_API_DELAY_MAX")

    args = parser.parse_args()

    results = []

    if args.run_all:
        print("[*] Barcha senariylar (a, b1, b2) ishga tushiriladi...")
        # Senariy a: delay=0, 10 000 user, concurrency=4
        res_a = run_single_benchmark(num_users=10000, concurrency=4, delay_min=0.0, delay_max=0.0)
        results.append(res_a)

        # Senariy b1: delay=0.2..0.5, 500 user, concurrency=4
        res_b1 = run_single_benchmark(num_users=500, concurrency=4, delay_min=0.2, delay_max=0.5)
        results.append(res_b1)

        # Senariy b2: delay=0.2..0.5, 500 user, concurrency=8
        res_b2 = run_single_benchmark(num_users=500, concurrency=8, delay_min=0.2, delay_max=0.5)
        results.append(res_b2)

        print_results_table(results)

    elif args.scenario == 'a':
        res = run_single_benchmark(num_users=10000, concurrency=4, delay_min=0.0, delay_max=0.0)
        print_results_table([res])
    elif args.scenario == 'b1':
        res = run_single_benchmark(num_users=500, concurrency=4, delay_min=0.2, delay_max=0.5)
        print_results_table([res])
    elif args.scenario == 'b2':
        res = run_single_benchmark(num_users=500, concurrency=8, delay_min=0.2, delay_max=0.5)
        print_results_table([res])
    else:
        res = run_single_benchmark(
            num_users=args.users,
            concurrency=args.concurrency,
            delay_min=args.delay_min,
            delay_max=args.delay_max,
        )
        print_results_table([res])
