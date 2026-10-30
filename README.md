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
| `MAX_POSTS_PER_USER_PER_DAY` | Foydalanuvchi kunlik post joylash yuqori chegarasi (standart: `100`, taxminiy chegara) |
| `POST_COOLDOWN_SECONDS` | Postlar orasidagi kutish oralig'i (standart: `420` soniya / 7 daqiqa, `0` bo'lsa o'chadi) |
| `PUBLISHING_LIMIT_CACHE_TTL` | Instagram publishing limit Redis kesh muddati (standart: `120` soniya) |
| `INSTAGRAM_USAGE_SLOWDOWN_PERCENT` | Meta Business Usage chegarasi (standart: `80`%) |
| `INSTAGRAM_API_RATE_LIMIT` | Celery uchun Instagram so'rovlari tezlik cheklovi (standart: `50`/sekund, taxminiy chegara) |

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

---

## 🎬 Instagram Reels Joylash Usullari va Monitoring Jadvali

Tizimda foydalanuvchilar videoni ikkita qulay usulda joylashtirishlari mumkin:

### 1-usul: "Saytdan joylash" (Avtomatik oqim)
1. **Video tanlash**: Foydalanuvchi umumiy aksiya videosini yoki shaxsiy yuklangan videoni tanlaydi.
2. **Joylashni boshlash**: "Saytdan joylash" tugmasi bosiladi (`POST /api/user/publish/`).
3. **Fon vazifasi**: Celery ishchisi (`publish_reels_task`) videoni Meta Instagram Graph API orqali to'g'ridan-to'g'ri Reels formatida joylaydi.
4. **Monitoring boshlanishi**: Post holati `queued` -> `publishing` -> `published` ga o'tadi va birinchi tekshiruv 15 soniyadan so'ng avtomatik bajariladi.

### 2-usul: "O'zim joylayman" (Mustaqil / Manual oqim)
1. **Unikal kod olish**: Foydalanuvchi kabinetida unikal aksiya kodi (masalan: `WIN789`) ko'rsatiladi va nusxalanadi.
2. **Instagramda joylash**: Foydalanuvchi videoni Instagram ilovasi orqali Reels qilib joylaydi va tavsif (caption) qismiga o'z unikal kodini kiritadi.
3. **Avtomatik topish**: Davriy vazifa (`sync_recent_active_users_task`) har 5 daqiqada yangi postlarni tekshiradi yoki foydalanuvchi "Postni tekshirish" tugmasini bosganda (`POST /api/user/sync-media/`) post darhol topiladi va tizimga `source='self'` sifatida ulanadi.
4. **AI Tasdiqlash**: AI verifikator (`process_and_verify_post_ai`) tavsif va audioda unikal kod borligini tekshiradi hamda monitoringni boshlaydi.

### 📊 Adaptiv Statistika Monitoring Jadvali (`calculate_next_check`)

Postlar yoshiga, ko'rishlar soniga va sovrin marrasiga yaqinligiga qarab oraliq intervallar sozlamalar orqali adaptiv tarzda belgilanadi:

| Postning Yoshi / Sharti | Standart Oraliq | Sozlama Parametri | Vazifasi va Maqsadi |
| :--- | :--- | :--- | :--- |
| **0 – 24 soat** | **Har 30 daqiqada** | `CHECK_INTERVAL_0_24H=30` | Yangi Reels eng ko'p ko'riladigan dastlabki sutkada tezkor ko'rishlar statistikasini ushlash. |
| **1 – 7 kun** | **Har 3 soatda (180 min)** | `CHECK_INTERVAL_1_7D=180` | Faol o'sish davridagi postlarni muntazam va barqaror monitoring qilish. |
| **7 – 30 kun** | **Har 12 soatda (720 min)** | `CHECK_INTERVAL_7_30D=720` | Sekinlashgan postlarni optimal oraliqda tekshirish. |
| **30 kundan eski yoki views >= 5000** | **Har 24 soatda (1440 min)** | `CHECK_INTERVAL_OLDER_30D=1440` | Marraga yetgan yoki eski postlar uchun Meta API limitlarini tejash. |
| **Keyingi marraning 80% iga yetganda** | **Har 15 daqiqada** | `CHECK_INTERVAL_CLOSE_TO_PRIZE=15` | Sovrin (Prize) marrasiga yaqinlashganda (masalan, 500 ning 400 tasida) sovrinni tezkor berish. |

---

## ⚡ Ishlash tezligi va Masshtabdorlik (Benchmark)

Tizim katta hajmdagi foydalanuvchilar (10 000 — 1 000 000) va postlarni parallel tekshirish uchun quyidagi arxitektura optimizatsiyalariga ega:
- **Chunk tasks (`check_users_chunk_task`)**: Foydalanuvchilar `CHECK_USER_CHUNK_SIZE` (standart: 100) ta userdan iborat paketlarga bo'linadi va Celery `group` orqali parallel workerlarga tarqatiladi.
- **/me/media oqimi**: Har bir post uchun alohida media so'rovi yuborish o'rniga, foydalanuvchining barcha Reels videolari bitta `/me/media` so'rovida (paging bilan) olinadi. Faqat ko'rishlar (views) uchun `/{media-id}/insights` chaqiriladi.
- **Bulk SQL operatsiyalari (`bulk_save_posts_metrics`)**: Postlar metrikalari va `PostStat` yozuvlari `bulk_update` va `bulk_create` (batch_size=500) yordamida bitta SQL so'rovda saqlanadi (N+1 muammosi bartaraf etilgan).
- **Redis Sliding Window Rate Limiter**: Lua skripti orqali soniyalik va soatlik cheklovlar ta'minlanadi.

### 1. Benchmark Natijalari Jadvali (`benchmark_run.py`)

Benchmark sinovlari `INSTAGRAM_MODE=mock` (haqiqiy Instagramga so'rov ketmagan holda, `DryRunInstagramClient` bilan) o'tkazildi:

| Userlar | Postlar | API Kechikishi (Min-Max) | Concurrency | Umumiy vaqt | Ishlash tezligi | So'rovlar soni (`list_recent_media` / `get_media_insights` / `fetch_post_metrics`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **10 000** | 20 035 | 0.0 – 0.0 s | 4 | **75.93 s** | **263.85 post/s** | 30 035 (10 000 / 20 035 / 0) |
| **500** | 1 000 | 0.2 – 0.5 s | 4 | **193.21 s** | **5.18 post/s** | 1 500 (500 / 1 000 / 0) |
| **500** | 1 019 | 0.2 – 0.5 s | 8 | **116.89 s** | **8.72 post/s** | 1 519 (500 / 1 019 / 0) |

> **Muhim tekshiruv natijasi**: Barcha sinovlarda `fetch_post_metrics` hisoblagichi `0` ga teng bo'ldi, `list_recent_media` esa foydalanuvchilar soniga aynan teng bo'ldi. Bu yangi samarali `/me/media` oqimi to'liq ishlaganligini tasdiqlaydi.

### 2. Hisoblash Formulasi va Masshtab Taxminlari

Tizimning davriy tekshiruv aylanishi vaqti quyidagi formula bilan ifodalanadi:

$$\text{Vaqt} \approx \frac{\text{Userlar} \times \text{Userga so'rovlar soni} \times \text{O'rtacha kechikish}}{\text{Concurrency}}$$

- **Userga so'rovlar**: 1 ta `/me/media` + har bir post uchun 1 ta `insights` (o'rtacha har userga 2 ta post = 3 ta so'rov).
- **O'rtacha kechikish ($\text{delay}_{avg}$)**: Meta API tarmoq kechikishi o'rtacha $0.35\text{ s}$ ($0.2\text{ s} - 0.5\text{ s}$).

#### Nazariy Proektsiya Taxminlari *(DIQQAT: Bu hisob-kitoblar faqat nazariy formula bo'yicha taxmin, real tizimda o'lchangan emas)*:

| Foydalanuvchilar soni | Concurrency | Taxminiy umumiy vaqt (sekund) | Taxminiy umumiy vaqt (soat) | Izoh |
| :--- | :--- | :--- | :--- | :--- |
| **100 000** | 4 | ~26 250 s | ~7.29 soat | API kechikishi 0.35s bilan |
| **100 000** | 8 | ~13 125 s | ~3.65 soat | Workerlar soni 8 ta bo'lganda |
| **100 000** | 32 | ~3 281 s | ~0.91 soat (55 daqiqa) | Katta klasterda parallel ishlaganda |
| **100 000** | 64 | ~1 640 s | ~0.46 soat (27 daqiqa) | Gorizontal kengaytirilgan workerlar |
| **1 000 000** | 32 | ~32 812 s | ~9.11 soat | 1 million foydalanuvchi to'plami |
| **1 000 000** | 64 | ~16 406 s | ~4.56 soat | 64 parallel worker jarayoni bilan |

### 3. Asosiy Sozlamalar (Chunk va Chastota)

Quyidagi parametrlar `config/settings.py` va `.env` orqali boshqariladi:
- `CHECK_USER_CHUNK_SIZE` (default: `100`): Bitta Celery taskiga biriktiriladigan foydalanuvchilar soni.
- `CHECK_BATCH_SIZE` (default: `1000`): Dispatcher bitta SQL tranzaksiyasida bazadan bloklaydigan postlar soni.
- `MAX_POSTS_PER_RUN` (default: `50000`): Bitta dispatcher aylanishida navbatga qo'yiladigan maksimal postlar chegarasi.
- `CHECK_INTERVAL_0_24H` (default: `30` min): 0-24 soatlik postlar tekshirish oralig'i.
- `CHECK_INTERVAL_1_7D` (default: `180` min): 1-7 kunlik postlar oralig'i.
- `CHECK_INTERVAL_7_30D` (default: `720` min): 7-30 kunlik postlar oralig'i.
- `CHECK_INTERVAL_OLDER_30D` (default: `1440` min): 30 kundan eski yoki views >= 5000 postlar oralig'i.
- `CHECK_INTERVAL_CLOSE_TO_PRIZE` (default: `15` min): Sovrin marrasiga 80% yetgan postlar oralig'i.

### 4. Muhim Cheklovlar va Ochiq Eslatmalar

Muhandislik shaffofligi yuzasidan quyidagi jihatlar ochiq qayd etiladi:
1. **Natijalar sun'iy (mock) kechikish bilan o'lchangan**: Benchmark natijalari `DryRunInstagramClient` sun'iy kechikishida olingan bo'lib, haqiqiy Meta Instagram Graph API serverlarining javob berish tezligi, mintaqaviy kechikishlar va TLS handshakes ko'rsatkichlari farq qilishi mumkin.
2. **Instagram rate limit raqami tasdiqlanmagan**: Meta hujjatlarida Instagram Graph API uchun sekundiga aniq umumiy so'rovlar limiti ochiqlanmagan. Tizimdagi `INSTAGRAM_API_RATE_LIMIT=50` parametri ehtiyotkorlik chegarasi sifatida olingan, tasdiqlangan rasmiy ko'rsatkich emas.
3. **Views >= 5000 postlar chastotasi**: 5000 ko'rishdan oshgan postlar sutkada 1 marta (24 soatda) tekshiriladi. Shu sababli, foydalanuvchi videoni Instagram'dan o'chirib tashlasa yoki keyingi marraga erishsa, bu holat 24 soatgacha kech aniqlanishi mumkin.
4. **Meta App Development rejimi**: Ilova hozirda Development rejimida bo'lib, faqat Meta for Developers paneliga qo'shilgan Instagram Tester akkauntlari bilan ishlaydi. Minglab real foydalanuvchilarni qamrab olish uchun Meta App Review jarayonidan o'tish va ruxsatlar bo'yicha **Advanced Access** olish shart.
5. **Haqiqiy Instagram bilan to'liq yuklama sinovi hali o'tkazilmagan**: Minglab real akkauntlar bilan jonli tarmoqda yuklama sinovi o'tkazilmagan (faqat sintetik benchmark va birlik testlari bajarilgan).
6. **Kelajakdagi optimizatsiya rejalari**: `PostStat` yozuvlarini davriy agregatsiya qilish (ma'lumotlar bazasi hajmini kamaytirish uchun eski daqiqalik yozuvlarni soatlik/kunlikka jamlash) hamda `sync_recent_active_users_task` vazifasini ham chunk arxitekturasiga birlashtirish kelgusi bosqich vazifasi hisoblanadi.

---

## 🛡️ Limitlar va Himoya Mexanizmlari (Rate Limiting, Cooldown, Quota)

Tizimda Meta (Instagram) serverlarining spam-blokirovkasiga tushmaslik va foydalanuvchilarga xavfsiz xizmat ko'rsatish uchun 4 bosqichli himoya mexanizmi amal qiladi:

### 1. Kunlik Post Limiti (`content_publishing_limit`)
- **Instagram'dan o'qish**: Video joylashdan oldin `GET /{ig_user_id}/content_publishing_limit?fields=quota_usage,config` chaqirilib, foydalanuvchining so'nggi 24 soatlik amaldagi kvotasi (`quota_usage`) va umumiy ruxsat etilgan soni (`quota_total`) o'qiladi.
- **Chegara**: Amaldagi chegara `min(quota_total, MAX_POSTS_PER_USER_PER_DAY)` formulasiga ko'ra belgilanadi (standart: `MAX_POSTS_PER_USER_PER_DAY=100`, taxminiy yuqori chegara).
- **Kesh**: Har bir post urinishida API ga ortiqcha yuk tushirmaslik uchun limit natijasi Redis'da `120` soniya (`PUBLISHING_LIMIT_CACHE_TTL`) davomida keshlanadi.
- **Xabar berish**: Agar foydalanuvchining kvotasi to'lgan bo'lsa, post qilish boshlanmaydi va foydalanuvchiga aniq tushunarli xabar qaytariladi:  
  *`"Instagram kunlik post limiti tugadi (100/100). Taxminan 24 soatdan keyin yana urinib ko'ring."`*
- **Xatolikka bardoshlilik (Fallback)**: Agar Meta API'dan kvota olishda xatolik (server error, tarmoq uzilishi) yuz bersa, tizim post joylashni asossiz to'xtatmaydi, xatoni logga yozib jarayonni davom ettiradi.

### 2. Postlar orasida kutish (Cooldown)
- **Alohida foydalanuvchi hisobi**: `POST_COOLDOWN_SECONDS` (standart: `420` soniya / 7 daqiqa). Har bir foydalanuvchi uchun alohida hisoblanadi — foydalanuvchilar bir-birini kutmaydi.
- **Rad etilmasdan navbatga tushish**: Foydalanuvchi oxirgi muvaffaqiyatli postidan so'ng 7 daqiqa o'tmasdan yana video joylashni so'rasa, so'rov **rad etilmaydi**. Post `queued` holatiga o'tadi va Celery `apply_async(countdown=remaining_seconds)` orqali cooldown tugagan vaqtda avtomatik ravishda Instagram'ga chiqariladi.
- **Aniq vaqt ko'rsatish**: API javobida va holat tekshiruvida foydalanuvchiga qancha kutishi kerakligi aniq vaqt bilan qaytariladi (`"keyingi post: 17:35 da avtomatik joylanadi"`).
- **Poyga holatlaridan (Race Condition) himoya**: Bir vaqtda bir nechta parallel so'rov yuborib cooldown'ni aylanib o'tmaslik uchun Redis atomik qulfi (`SET NX`, TTL 10–15s) ishlatiladi.
- **O'chirish imkoniyati**: `POST_COOLDOWN_SECONDS=0` qilinsa, postlar orasidagi kutish o'chiriladi.
- *Eslatma: 24 soatlik limit umumiy postlar sonini cheklaydi, cooldown esa qisqa vaqt ichida ketma-ket agressiv video joylashning oldini oladi.*

### 3. Rate Limiterni Meta Sarlavhalariga Moslash (`X-Business-Use-Case-Usage`)
- **Usage Foizlarini O'qish**: Meta Graph API har bir so'rov javobida `X-Business-Use-Case-Usage` sarlavhasini qaytaradi. Undagi `type=instagram` bo'lgan yozuvning `call_count`, `total_time` va `total_cputime` foizlari tekshiriladi.
- **Sekinlashtirish / To'xtatish**: Agar foiz `INSTAGRAM_USAGE_SLOWDOWN_PERCENT` (standart: `80`%) dan oshsa, o'sha akkaunt uchun so'rovlar sarlavhadagi `estimated_time_to_regain_access` (daqiqada) muddati bo'yicha Redis'da to'xtatib turiladi (`account_usage_slowdown`). Celery chunk tasklari bu foydalanuvchini kutib turmasdan keyingi aylanishga qoldiradi.
- **Xato kodlari bilan boshqaruv**:
  - Kodlar `4, 9, 17, 341, 613`: Akkaunt vaqtincha to'xtatiladi, qayta urinilmaydi (`retry` qilinmaydi), keyingi monitoring aylanishiga qoldiriladi.
  - Subcode `1390008` (qisqa muddatli throttle): Qayta urinishga loyiq (`self.retry(countdown=60)`).
  - Subcode `2207042` (24 soatlik kunlik publishing limiti): Qayta urinilmaydi, post `failed` qilinadi va foydalanuvchiga tizim bildirishnomasi (Notification) yuboriladi.
- **Taxminiy chegaralar**: Koddagi `5` so'rov/sekund va `200` so'rov/soat ko'rsatkichlari rasmiy kafolatlangan raqam emas, balki sozlanuvchi **taxminiy xavfsizlik chegaralari** hisoblanadi.

### 4. Ochiq Cheklovlar va Eslatmalar
1. **Haqiqiy Instagram bilan to'liq yuklama sinovi o'tkazilmagan**: Cooldown va sarlavhalar logikasi birlik testlari va `mock`/simulyatsiya rejimida sinovdan o'tkazildi, minglab real akkauntlar bilan jonli tarmoqda sinov o'tkazilmagan.
2. **Meta hujjatlaridagi ziddiyat**: Meta rasmiy qo'llanmalarida Instagram Reels uchun kunlik limit ba'zi sahifalarda 25 ta, boshqa joylarda 50 yoki 100 ta deb ziddiyatli ko'rsatilgan. Tizim `content_publishing_limit` orqali aynan o'sha akkauntga berilgan real kvotani o'qiydi.
3. **App Review**: Barcha ushbu imkoniyatlar keng omma uchun ishlashi uchun Meta App Review'dan o'tish talab etiladi.

---

## 📮 Postman bilan sinash (Newman E2E)

Loyihada to'liq API testi, negativ ssenariylar va avtomatlashtirilgan E2E oqimi uchun Postman to'plami tayyorlangan.

### 1. Fayllar tuzilishi
- `postman/insta_checker.postman_collection.json` — Postman Collection v2.1 (12 ta papka, 103 ta to'liq so'rov, barcha 47+ endpointlar va avtomatlashgan test skriptlari).
- `postman/local.postman_environment.json` — Environment o'zgaruvchilari to'liq shabloni.
- `postman/files/sample.mp4` — Sinov uchun minimal MP4 video fayli.

### 2. Postman dasturiga import qilish
1. **Kolleksiyani yuklash**: Postman ilovasida `Import` tugmasini bosing va `postman/insta_checker.postman_collection.json` faylini tanlang.
2. **Muhitni yuklash**: `postman/local.postman_environment.json` faylini `Environments` bo'limiga import qiling.
3. **OpenAPI Sxemani import qilish**:
   - Postman ilovasida: `File` → `Import` → `Link`.
   - Manzil: `http://localhost:8080/api/schema/` (yoki `http://127.0.0.1:8000/api/schema/`).
   - Bu orqali API spetsifikatsiyasi to'g'ridan-to'g'ri Postman'da paydo bo'ladi.

### 3. Environment o'zgaruvchilarini to'ldirish
`Local (InstaChecker)` muhitini tanlang va quyidagi qiymatlarni kiriting:
- `base_url`: `http://localhost:8080` (yoki `http://localhost:8000`)
- `admin_username`: administrator foydalanuvchi nomi (masalan: `admin`)
- `admin_password`: administrator paroli (masalan: `admin123`)
- `user_username`: oddiy foydalanuvchi nomi (masalan: `bekzod`)
- `user_password`: oddiy foydalanuvchi paroli (masalan: `user123`)

> ⚠️ **Muhim eslatma (Postman UI da fayl tanlash)**:
> Postman desktop ilovasi xavfsizlik nuqtai nazaridan import qilingan kolleksiyalardagi mahalliy fayl yo'llarini avtomatik tanlamaydi. Shuning uchun Postman UI dan foydalanganda quyidagi so'rovlarning `Body` (form-data) bo'limida `file` maydoniga `postman/files/sample.mp4` faylini qo'lda biriktirishingiz kerak:
> - `03 Admin – Videolar / Upload Video (Multipart)`
> - `10 E2E – To'liq oqim / E2E 03 - Upload Video`

### 4. Newman orqali avtomatik E2E ishga tushirish (CI/CD)
Hech qanday qo'lda fayl tanlamasdan, barcha 103 ta so'rov va to'liq testlarni Docker ichida to'liq avtomatik yurgizish:

```bash
# Docker Compose orqali:
docker compose --profile e2e run --rm newman

# yoki Makefile orqali:
make e2e
```

**Talab**: E2E testi faqat `INSTAGRAM_DRY_RUN=True` bo'lganda ishlaydi. Agar ushbu rejim yoqilmagan bo'lsa, test dastlabki `00 Health` bosqichidayoq aniq ogohlantirish bilan to'xtaydi.
