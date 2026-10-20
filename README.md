# Insta Checker — Instagram Reels Tracker & Prize System

Instagram Reels videolarini avtomatik joylash, ko'rishlar (views), like va izohlar statistikasini kuzatish hamda belgilangan marralar (500, 1000, 5000 ko'rish) bo'yicha sovrinlar va bildirishnomalarni boshqarish tizimi.

---

## 🏗 Arxitektura

- **Backend**: Django 6 + Django REST Framework + SimpleJWT + Celery + Redis + PostgreSQL
- **Frontend**: React 19 + TypeScript + Vite + Tailwind CSS + Recharts + Lucide Icons
- **Infratuzilma**: Docker Compose (web, worker, beat, db, redis, nginx)

---

## 🚀 Ishga tushirish (Docker)

1. **Muhit o'zgaruvchilari**:
   ```bash
   cp .env.example .env
   ```
2. **Docker konteynerlarni ishga tushirish**:
   ```bash
   docker compose up -d --build
   ```
3. **Namunaviy test ma'lumotlarini yuklash (ixtiyoriy)**:
   ```bash
   docker compose exec web python generate_test_data.py
   ```
4. **Testlarni ishga tushirish**:
   ```bash
   docker compose exec web python manage.py test
   ```

---

## 🔑 Panellarga kirish

Tizim `http://localhost:8080` (yoki NGINX porti) orqali ochiladi.
Yagona kirish sahifasi: `/login` (rolga qarab avtomatik yo'naltiradi).

| Rol | Login | Parol | Yo'naltiriladigan panel |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin` | `admin123` | `http://localhost:8080/admin-panel` |
| **Foydalanuvchi** | `bekzod` | `user123` | `http://localhost:8080/app` |
| **Django Admin** | `admin` | `admin123` | `http://localhost:8080/admin/` |

---

## ⚙️ `.env.example` O'zgaruvchilar Izohi

| O'zgaruvchi | Tavsifi va misol |
| :--- | :--- |
| `SECRET_KEY` | Django xavfsizlik kaliti |
| `DEBUG` | Ishlab chiqish rejimi (`True` yoki production uchun `False`) |
| `ALLOWED_HOSTS` | Ruxsat etilgan domenlar (`localhost,127.0.0.1,web` yoki `*`) |
| `CSRF_TRUSTED_ORIGINS` | CSRF ishonchli domenlar (`http://localhost:8080,https://ngrok-url`) |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL ma'lumotlar bazasi rekvizitlari |
| `DB_HOST`, `DB_PORT` | Baza hosti (`db` konteynerda) va porti (`5432`) |
| `CELERY_BROKER_URL` | Redis manzili (`redis://redis:6379/0`) |
| `SITE_URL` | Tizimning tashqi manzili (masalan ngrok: `https://abcd.ngrok-free.app`) |
| `INSTAGRAM_APP_ID` | Meta for Developers ilovasining App ID raqami |
| `INSTAGRAM_APP_SECRET` | Meta ilovasi App Secret kaliti |
| `INSTAGRAM_REDIRECT_URI` | OAuth callback manzili (`{SITE_URL}/oauth/callback/`) |
| `INSTAGRAM_SCOPE` | Kerakli ruxsatlar (`instagram_business_basic,instagram_business_content_publish,...`) |
| `PRIZE_MILESTONES` | Sovrin marralari (masalan `500,1000,5000,10000,50000,100000`) |
| `MAX_VIDEO_SIZE_MB` | Ruxsat etilgan maksimal video hajmi (`100`) |
| `INSTAGRAM_API_RATE_LIMIT` | Celery uchun Instagram so'rovlari tezlik cheklovi (`50` so'rov/sekund) |

---

## 🌐 Ngrok orqali Instagram Meta App sozlash

Instagram Graph API vebxuklar va OAuth uchun HTTPS bilan ishlaydigan ochiq manzil talab qiladi:

1. **Ngrokni ishga tushirish**:
   ```bash
   ngrok http 8080
   ```
   (Masalan, hosil bo'lgan havola: `https://xyz.ngrok-free.app`)

2. **`.env` faylini yangilash**:
   ```env
   SITE_URL=https://xyz.ngrok-free.app
   INSTAGRAM_REDIRECT_URI=https://xyz.ngrok-free.app/oauth/callback/
   CSRF_TRUSTED_ORIGINS=http://localhost:8080,https://xyz.ngrok-free.app
   ```
   So'ng konteynerlarni qayta ishga tushiring: `docker compose up -d`

3. **Meta for Developers (developers.facebook.com) da sozlash**:
   - Ilova yarating (App type: **Business**).
   - **Instagram Graph API** va **Instagram Login** mahsulotlarini qo'shing.
   - **Instagram Login -> Settings**:
     - *Valid OAuth Redirect URIs* ga: `https://xyz.ngrok-free.app/oauth/callback/`
     - *Deauthorize Callback URL* ga: `https://xyz.ngrok-free.app/oauth/deauthorize/`
     - *Data Deletion Request URL* ga: `https://xyz.ngrok-free.app/oauth/data-deletion/`
   - **App Review / Permissions**:
     Quyidagi 3 ta ruxsatni sozlashingiz shart:
     1. `instagram_business_content_publish`
     2. `instagram_business_manage_insights`
     3. `instagram_business_manage_comments`
   - Test foydalanuvchilar (Instagram Tester) qo'shing va ularning akkaunti **Professional (Business yoki Creator)** ekaniga ishonch hosil qiling.

---

## 🧪 Avtomatlashtirilgan Testlar

Tizimda barcha bosqichlar (OAuth, Reels publishing, RBAC ruxsatlar, video boshqaruvi, adaptiv jadval, N+1 optimizatsiyasi, Rate limiting, Meta xatolar klassifikatsiyasi va DRY_RUN simulyatsiyasi) 127 ta avtomatlashtirilgan test bilan himoyalangan:

```bash
docker compose exec web python manage.py test
```

---

## 🚀 Instagram'siz sinash (DRY_RUN Rejimi)

Meta ilovasi (App Review) yoki haqiqiy Instagram akkauntsiz tizimning barcha biznes-funksiyalarini to'liq sinab ko'rish uchun **DRY_RUN** rejimi mavjud.

### 1. Qanday yoqiladi?
`.env` faylida quyidagi parametrlarni o'rnating:
```env
DEBUG=True
INSTAGRAM_DRY_RUN=True
DRY_RUN_PUBLISH_DELAY_SECONDS=2
```
> **Diqqat (Xavfsizlik qoidasi):** `DEBUG=False` bo'lganda `INSTAGRAM_DRY_RUN=True` qilib qo'yilsa, ilova ishga tushmaydi (`ImproperlyConfigured` xatosi bilan himoyalangan).

### 2. Oqim ketma-ketligi (Test Flow):

1. **Hisobga kirish**:
   - Oddiy user: `POST /api/token/` (`username: bekzod`, `password: user123`) -> `access` token olinadi.
2. **Instagram hisobini ulash (brauzersiz)**:
   - `GET /api/user/connect-instagram/` so'rovi yuboriladi. Javobda sun'iy `auth_url` olinadi:
     `http://localhost:8080/oauth/callback/?code=dry_run&state=<link_token>`
   - Ushbu manzilga oddiy `GET` so'rov yuborish kifoya. Tizim avtomatik tarzda sun'iy tokenni saqlaydi va user holatini `connected` ga o'tkazadi.
3. **Videoni Reels qilib joylash**:
   - `POST /api/user/publish/` so'rovi yuboriladi.
   - Post `queued` -> `publishing` (2 soniya simulyatsiya kechikishi) -> `published` holatiga o'tadi.
   - `GET /api/user/publish-status/` orqali jarayonni kuzatish mumkin.
4. **Ko'rishlar (Views) va Sovrinlarni simulyatsiya qilish (Faqat Admin)**:
   - `POST /api/dev/simulate-views/`
     ```json
     {
       "post_id": 1,
       "views": 500
     }
     ```
     Bu endpoint Instagram'da 500 ko'rish to'planganini simulyatsiya qiladi va haqiqiy tekshiruv quvurini ishga tushiradi (`PostStat` yoziladi, 500 marra uchun `Prize` va `Notification` yaratiladi).
5. **Post o'chirilishini simulyatsiya qilish**:
   - `POST /api/dev/simulate-delete/` (`{"post_id": 1}`)
   - Post holati `deleted` bo'ladi va `deleted_detected_at` o'rnatiladi.
6. **Token bekor qilinishini simulyatsiya qilish**:
   - `POST /api/dev/simulate-token-revoked/` (`{"user_id": 1}`)
   - User holati `needs_reauth` ga o'tadi.
7. **Vaqtinchalik tarmoq xatosini simulyatsiya qilish**:
   - `POST /api/dev/simulate-network-error/` (`{"post_id": 1}`)
   - Post o'chirilmaydi va navbatdagi tekshiruv keyinroqqa qoldiriladi.
