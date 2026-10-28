# InstaChecker Tizimi — Frontend Sahifalari va Backend Integratsiyasi Qo'llanmasi

Ushbu hujjatda **InstaChecker** loyihasining frontend (React + TypeScript) va backend (Django REST Framework + Celery + Redis + PostgreSQL) arxitekturasi bo'yicha barcha 12 ta asosiy sahifaning to'liq, sodda va batafsil tushuntirishi jamlangan.

---

## 📌 Asosiy Texnologik Terminlar Lug'ati (Yangi o'rganuvchilar uchun)

Loyiha kodida uchraydigan muhim terminlar va ularning bir gapli oddiy tushuntirishi:

1. **JWT (JSON Web Token):** Foydalanuvchi tizimga kirganida beriladigan raqamli "kirish guvohnomasi" (pasport) bo'lib, har bir API so'rovda serverga yuboriladi va server foydalanuvchini qayta login qilmasdan taniydi.
2. **OAuth (Open Authorization):** Foydalanuvchining Instagram parolini olmasdan turib, rasmiy Meta oynasi orqali uning hisobiga (videolar joylash, statistika ko'rish) xavfsiz ruxsat berish mexanizmi.
3. **Celery:** Sayt foydalanuvchisini kuttirib qo'ymaslik uchun og'ir va ko'p vaqt oladigan ishlarni (masalan, videoni qayta ishlash, Instagramga yuklash, AI orqali tekshirish) fonda (orqa fonda) alohida bajaradigan tizim.
4. **Redis:** Ma'lumotlarni qattiq diskda emas, kompyuterning tezkor xotirasida (RAM) saqlaydigan o'ta tezkor ma'lumotlar ombori; u Celery vazifalarini navbatga qo'yish (broker) va keshlash (cache) uchun ishlatiladi.
5. **Webhook:** Tashqi tizimda (masalan, Instagramda) biror voqea yuz berganda (postga yangi izoh yozilsa yoki post o'chirilsa), u avtomatik tarzda bizning serverimiz manziliga xabar yuborishi.
6. **Rate Limit:** Tizim yoki tashqi API (Instagram) haddan tashqari ko'p so'rovlar tufayli bloklanib qolmasligi uchun belgilangan vaqt ichida (masalan, minutiga 3 ta yoki soatiga 200 ta) yuboriladigan so'rovlar soniga qo'yilgan cheklov.
7. **Polling:** Frontend sahifasining har bir necha soniyada (masalan, har 2 soniyada) backendga avtomatik so'rov yuborib, orqa fondagi ish (masalan, video yuklanishi) bitgan yoki bitmaganini tekshirib turishi.

---

# I. FOYDALANUVCHI (USER) OYNALARI

---

## 1. LoginPage (Kirish va Ro'yxatdan o'tish)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Tizimga kirish va ro'yxatdan o'tish sahifasi (`LoginPage`)
- **Fayl yo'li:** `frontend/src/pages/LoginPage.tsx`

### 2. Nima uchun kerak
Foydalanuvchi va administratorlarning tizimga xavfsiz kirishi hamda yangi foydalanuvchilarning ro'yxatdan o'tishi uchun xizmat qiladi. Shuningdek, Instagram OAuth orqali to'g'ridan-to'g'ri avtorizatsiyadan o'tish tugmasini taqdim etadi.

### 3. Ekranda nimalar ko'rinadi
- **Logotip va Brend blok:** 📸 emojisi, "InstaChecker" sarlavhasi va qisqa izoh.
- **Tab almashtirgich (Tabs):** "Kirish" (`login`) va "Ro'yxatdan o'tish" (`register`) rejimlari.
- **Instagram tugmasi:** "Instagram orqali davom etish" (pushti Instagram belgisi bilan).
- **Forma maydonlari (Kirishda):** Login (`User` belgisi), Parol (`Lock` belgisi) va parolni ko'rsatish/yashirish ko'zchasi (`Eye`/`EyeOff`), "Tizimga kirish" tugmasi.
- **Forma maydonlari (Ro'yxatdan o'tishda):** Ism-familiya, Login, Parol va "Ro'yxatdan o'tish" tugmasi.
- **Test rejimi ogohlantirishi:** Test foydalanuvchilari (`bekzod`, `admin`) logini eslatmasi.

### 4. Frontend kodi
- **Komponentlar:** `LoginPage` (funksional komponent), Lucide ikonkalari (`Lock`, `User`, `UserPlus`, `LogIn`, `Camera`, `Eye`, `EyeOff`, `AlertTriangle`).
- **Hook va State-lar:**
  - `useState<'login' | 'register'>('login')` — qaysi tab ochiqligi.
  - `loginUsername`, `loginPassword`, `showPassword` — kirish formasi holatlari.
  - `regName`, `regUsername`, `regPassword` — ro'yxatdan o'tish formasi holatlari.
  - `loading` — so'rov yuborilayotgan paytda tugmalarni faolsizlantirish.
  - `useAuth()` (`login`, `register`) — autentifikatsiya kontekstidagi funksiyalar.
  - `useToast()` — xabarlar chiqarish (`showToast`).
  - `useNavigate()` — sahifalararo yo'naltirish.
  - `useEffect()` — URL qidiruv parametrlarida (`?access_token=...`) token kelgan bo'lsa, uni saqlab to'g'ridan-to'g'ri `/app/video` sahifasiga o'tkazish.
- **Axios so'rovlar:**
  - Kirishda: `POST /api/token/` (AuthContext orqali)
  - Ro'yxatdan o'tishda: `POST /api/register/` (AuthContext orqali)
  - Profilni tekshirish: `GET /api/me/` (AuthContext orqali)

### 5. Har bir tugma bosilganda nima bo'ladi (Batafsil zanjir)

#### A. "Tizimga kirish" tugmasi bosilganda:
1. **Frontend:** `handleLoginSubmit` chaqiriladi -> `useAuth().login(loginUsername, loginPassword)` chaqiriladi.
2. **API so'rov:** `POST /api/token/`, body: `{"username": "...", "password": "..."}`.
3. **URL yo'li:** `config/urls.py` -> `path('api/token/', LoginView.as_view(), name='token_obtain_pair')`.
4. **View & Throttle:** `tracker/throttles.py` dagi `LoginView` (TokenObtainPairView). Unda `LoginThrottle` (`5/minute` tezlik cheklovi) tekshiriladi.
5. **Serializer:** `CustomTokenObtainPairSerializer` chaqiriladi. Django `authenticate()` yordamida `User` tekshiriladi, JWT `access` va `refresh` tokenlari hamda foydalanuvchining roli (`admin` yoki `user`) tayyorlanadi.
6. **Frontend javob qabul qiladi:** Tokenlar `localStorage` ga yoziladi, so'ng `apiClient.get('/api/me/')` chaqirilib foydalanuvchi roli tasdiqlanadi. Agar rol `admin` bo'lsa `/admin-panel` ga, `user` bo'lsa `/app` sahifasiga yo'naltiriladi.

#### B. "Ro'yxatdan o'tish" tugmasi bosilganda:
1. **Frontend:** `handleRegisterSubmit` chaqiriladi -> `useAuth().register(...)`.
2. **API so'rov:** `POST /api/register/`, body: `{"name": "...", "username": "...", "password": "..."}`.
3. **URL yo'li:** `tracker/urls.py` -> `path('api/register/', register_user)`.
4. **View:** `tracker/views.py` dagi `register_user(request)` funksiyasi.
5. **Permissions:** `[AllowAny]` — har qanday tashrif buyuruvchi kura oladi.
6. **Serializer:** `UserRegisterSerializer` maydonlarni tekshiradi (login kamida 3 belgi, takrorlanmagan bo'lishi shart, parol talablari).
7. **Models:** `transaction.atomic()` ichida Django `User.objects.create_user()` va `InstagramUser.objects.create(status='pending')` jadvallariga yangi yozuv qo'shiladi.
8. **Natija:** JWT `access` va `refresh` tokenlari qaytariladi va foydalanuvchi to'g'ridan-to'g'ri `/app/video` ga o'tkaziladi.

#### C. "Instagram orqali davom etish" tugmasi bosilganda:
- `window.location.href = 'http://127.0.0.1:8000/api/auth/instagram/url/'` orqali backend OAuth yo'naltirishiga o'tiladi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `auth_user`: `id`, `username`, `password`, `is_staff`, `is_superuser`.
- `tracker_instagramuser`: `id`, `user_id`, `name`, `status` ('pending'), `created_at`.

### 7. Celery/Redis ishtiroki
- Kirish yoki ro'yxatdan o'tish paytida Celery task ishlamaydi.
- Redis login tezlik cheklovi (throttling) uchun foydalaniladi (`login: 5/minute`).

### 8. Xato holatlari
- **Noto'g'ri parol yoki login:** Qizil toast xabar: `"No active account found with the given credentials"`.
- **Tez-tez urinish (Rate limit):** Agar 1 daqiqada 5 martadan ko'p xato parol terilsa, 429 Too Many Requests: `"Request was throttled. Expected available in X seconds."`
- **Username band bo'lsa:** `"Bunday foydalanuvchi nomi band. Iltimos boshqasini tanlang."`
- **Parol talabga javob bermasa:** Django password validator xatoliklari chiqadi.

### 9. Xavfsizlik
- Har qanday tashrifchi (`AllowAny`) foydalana oladi.
- Parollar bazada `PBKDF2` algoritmi bilan xeshlanadi, ochiq holda saqlanmaydi.
- Brute-force (parolni tanlab buzish) hujumlaridan himoya qilish uchun Redis asosidagi `LoginThrottle` qo'llangan.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/LoginPage.tsx:67`
- **Muammo:** `window.location.href = 'http://127.0.0.1:8000/api/auth/instagram/url/'` kodi qattiq yozilgan (`hardcoded`). Agar dastur serverda boshqa port yoki haqiqiy domenda ishga tushsa, bu tugma foydalanuvchini noto'g'ri manzilga (lokal kompyuteriga) olib boradi.
- **Tuzatish taklifi:** Nisbiy URL (`/api/auth/instagram/url/`) yoki `apiClient.get('/api/auth/instagram/url/')` orqali backenddan olingan `res.data.auth_url` ga yo'naltirish kerak.

---

## 2. UserDashboardPage (Foydalanuvchi Boshqaruv Paneli)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Foydalanuvchi shaxsiy natijalari sahifasi (`UserDashboardPage`)
- **Fayl yo'li:** `frontend/src/pages/user/UserDashboardPage.tsx`

### 2. Nima uchun kerak
Foydalanuvchiga uning Instagram Reels videolari necha marta ko'rilgani, nechta layk va izoh to'plagani hamda navbatdagi qimmatbaho sovrinni yutib olish uchun yana nechta ko'rish yetishmayotganini grafik va progress bar shaklida ko'rsatish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Sarlavha va "Videoni joylash" tugmasi:** `/app/video` sahifasiga eltuvchi binafsharang tugma.
- **5 ta KPI statistik karta:**
  1. *Ko'rishlar:* Jami reels ko'rishlar soni.
  2. *Like'lar:* Jami yoqtirishlar soni.
  3. *Izohlar:* Jami fikrlar soni.
  4. *Postlar:* Yuklangan videolar soni.
  5. *Sovrinlar:* Erishilgan sovrinlar soni.
- **Sovrin Progress Kartasi:** Keyingi marra (masalan, 500 yoki 1000 ko'rish), yana qancha qolgani va foizli progress bar (gradientli chiziq).
- **Ko'rishlar O'sish Dinamikasi Grafigi (Recharts AreaChart):** 7 kun va 30 kunlik filtrlarga ega to'lqinsimon chizma grafik.
- **Bo'sh holat (Empty State):** Agar foydalanuvchi hali video joylamagan bo'lsa, grafik o'rnida "Hali post yo'q. Birinchi videoni joylang" taklifi chiqadi.

### 4. Frontend kodi
- **Komponentlar:** `ResponsiveContainer`, `AreaChart`, `Area`, `XAxis`, `YAxis`, `Tooltip`, `CartesianGrid` (Recharts kutubxonasi). Lucide ikonkalari (`Eye`, `Heart`, `MessageCircle`, `VideoIcon`, `Award`, `TrendingUp`, `Clock`, `Sparkles`).
- **Hook va State-lar:**
  - `summary: UserSummary | null` — umumiy raqamlar holati.
  - `allPosts: Post[]` — grafik yasash uchun postlar ro'yxati.
  - `timeRange: '7' | '30'` — vaqt filtri.
  - `loading: boolean` — yuklanish holati (skelet animatsiyasi).
- **Axios so'rovlar:**
  - `GET /api/me/summary/`
  - `GET /api/me/posts/?page_size=50`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"Videoni joylash" tugmasi:**
   - Brauzer marshrutini `/app/video` ga o'zgartiradi (React Router).
2. **"7 kun" / "30 kun" tugmalari:**
   - Hech qanday yangi backend so'rov yubormaydi; state'dagi `allPosts` ro'yxatini frontendning o'zida `nowMs - postMs <= daysLimit` formulasi bilan saralab grafikni qayta chizadi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_instagramuser`: joriy foydalanuvchining hisobi.
- `tracker_post`: `views`, `likes`, `comments_count`, `posted_at`, `status`.
- `tracker_prize`: `milestone`, `sent_at`.
- `settings.PRIZE_MILESTONES`: masalan `[500, 1000, 5000, 10000, 50000, 100000]`.

### 7. Celery/Redis ishtiroki
- Ushbu oynaning o'zi bevosita task ishga tushirmaydi, lekin Celery'dagi `check_all_due_posts_task` (har 5 daqiqada) va `check_post_metrics_task` Instagramdan olib kelgan yangi ma'lumotlarni ko'rsatadi.

### 8. Xato holatlari
- **Token eskirgan (401 Unauthorized):** Axios interceptor avtomatik `/api/token/refresh/` ga so'rov yuboradi. Agar refresh token ham eskirgan bo'lsa, login sahifasiga haydaydi.
- **Post yo'q bo'lsa:** Barcha kartalarda `0` ko'rinadi, progress 0% bo'ladi va grafik o'rnida qulay yo'riqnoma chiqadi.

### 9. Xavfsizlik
- Faqat tizimga kirgan oddiy foydalanuvchilar kira oladi (`UserProtectedLayout`).
- Backendda `IsAuthenticated` tekshiriladi; `request.user` faqat o'ziga tegishli ma'lumotlarni oladi, boshqa foydalanuvchilarning ko'rishlarini ko'ra olmaydi.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/user/UserDashboardPage.tsx:84`
- **Muammo:** `if (!p.posted_at) return true;` — agar postning `posted_at` maydoni `null` bo'lsa (masalan, hali yuklanayotgan post), u 7 kunlik filtrda ham, 30 kunlik filtrda ham cheksiz saqlanib qolib, grafik sanasini buzishi mumkin.
- **Tuzatish taklifi:** `if (!p.posted_at) return false;` deb o'zgartirish kerak.

---

## 3. UserVideoPage (Mening Videom va Reels Joylash)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Foydalanuvchi videosini ko'rish, yuklash va Reels sifatida Instagramga joylash sahifasi (`UserVideoPage`)
- **Fayl yo'li:** `frontend/src/pages/user/UserVideoPage.tsx`

### 2. Nima uchun kerak
Foydalanuvchi o'zining shaxsiy 9:16 vertikal videosini tizimga yuklaydi, Instagram hisobini ulaydi, videoni Reels qilib joylashni buyuradi va joylangan videoning holatini (AI tekshiruvi, transkripsiya, izoh kodi) kuzatadi.

### 3. Ekranda nimalar ko'rinadi
- **Instagram Ulanish Banneri:** Akkaunt ulangan/ulanmaganligi va "Instagramga ulash" tugmasi.
- **Video Pleyer Kartasi:** Yuklangan video (shaxsiy yoki tizimning default videosi), video tayyorlanish indikatori (`processing` — 9:16 formatga o'tkazilmoqda).
- **Yangi video yuklash modali:** Shaxsiy `.mp4` fayl tanlash va sarlavha kiritish oynasi.
- **Reels Joylash Bloki:**
  - "Videoni Reels qilib joylash" katta tugmasi.
  - Jonli yuklanish jarayoni: soniya hisoblagich (⏱ timer), Meta transkodlash qadami animatsiyasi.
  - Xatolik yuz bersa "Qayta urinish" (`Retry`) tugmasi (3 tagacha imkoniyat).
- **Muvaffaqiyatli Post Kartasi:** Ko'rishlar, layklar, permalink (Instagramda ko'rish havolasi).
- **AI Tekshiruv Bloki (Gemini/Whisper):** Post ovozida homiy va aksiya kalit so'zlari aytilgani, ishonch darajasi (AI Confidence %) va nutq matni (transkript).
- **Caption Nusxalash:** 6 belgili unikal kodli matnni nusxalash tugmasi.
- **Foydalanuvchi Postlari Jadvali:** O'zining barcha Reelslari va ularni o'chirish tugmasi.

### 4. Frontend kodi
- **Komponentlar:** Lucide (`Film`, `Instagram`, `Send`, `RotateCcw`, `RefreshCw`, `ExternalLink`, `CheckCircle2`, `AlertCircle`, `Loader2`, `ShieldCheck`, `UploadCloud`, `Copy`, `Trash2`).
- **Hook va State-lar:**
  - `video: VideoItem | null`, `publishStatus: PublishStatus | null`.
  - `uploadModalOpen`, `uploading`, `uploadProgress`, `selectedFile`, `videoTitle`.
  - `userPosts: CampaignPost[]`, `syncing`, `elapsedSeconds`.
  - Polling mexanizmi: `pollIntervalRef` — har 2 soniyada `/api/user/publish-status/` ni tekshirib turadi.
- **Axios so'rovlar:**
  - `GET /api/videos/`, `GET /api/user/publish-status/`, `GET /api/user/posts/`
  - `POST /api/user/connect-instagram/`
  - `POST /api/user/upload-video/` (FormData)
  - `POST /api/user/publish/`
  - `POST /api/user/retry/`
  - `POST /api/user/sync/`
  - `POST /api/posts/${id}/check-metrics/`
  - `DELETE /api/user/posts/${id}/`

### 5. Har bir tugma bosilganda nima bo'ladi (Batafsil zanjir)

#### A. "Videoni Reels qilib joylash" tugmasi:
1. **Frontend:** `handlePublish()` -> `apiClient.post('/api/user/publish/')`.
2. **URL & View:** `tracker/urls.py` -> `views.py:user_publish_video`.
3. **Permissions:** `IsAuthenticated` (tizimga kirgan user).
4. **Biznes mantiq:**
   - Foydalanuvchining Instagram tokeni borligi va ulanganligi tekshiriladi.
   - Uning videosi borligi va statusi `ready` ekanligi tekshiriladi (agar hali ffmpeg ishlayotgan bo'lsa xato qaytaradi).
   - Takroriy bosishdan himoya: Agar hozirda `queued` yoki `publishing` bo'lgan post bo'lsa, 409 Conflict qaytaradi.
   - Yangi `UniqueLink` va `Post(status='queued')` yaratiladi.
5. **Celery Task:** `publish_reels_task.delay(link.id)` chaqiriladi.
6. **Task jarayoni (`tracker/tasks.py`):**
   - Instagram Graph API ga video yuboriladi (resumable container upload).
   - Container `FINISHED` bo'lgach, `media_publish` qilinadi.
   - Post bazada `published` holatiga o'tadi va 15 soniyadan so'ng statistika tekshiruviga (`check_post_metrics_task`) qo'yiladi.
7. **Frontend Polling:** Foydalanuvchi ekrani har 2 soniyada `/api/user/publish-status/` ni so'rab turadi va natija chiqqach tabriklash xabari chiqadi.

#### B. "Video yuklash" tugmasi (Modal ichida):
1. **Frontend:** `handleUploadSubmit()` -> `multipart/form-data` bilan `apiClient.post('/api/user/upload-video/', formData)`.
2. **View:** `views.py:user_upload_video` -> `VideoSerializer`.
3. **Serializer:** Fayl formati `.mp4`, hajmi 100MB dan kamligi tekshiriladi.
4. **Models & Task:** `Video.objects.create(status='processing', owner=ig_user)` saqlanadi va `process_video_task.delay(video.id)` ishga tushadi.
5. **Celery Task (`process_video_task`):**
   - FFmpeg orqali video davomiyligi (3-90 soniya) va o'lchami tekshiriladi. Agar nisbat 9:16 bo'lmasa, blur-fon qo'shilib 1080x1920 MP4 ga o'tkaziladi.
   - Muvaffaqiyatli tugasa `video.status = 'ready'` deb yoziladi.

#### C. "Qayta urinish" (Retry) tugmasi:
1. **Frontend:** `handleRetry()` -> `POST /api/user/retry/`.
2. **View:** `views.py:user_retry_publish`.
3. **Mantiq:** Postning `retry_count` soni 3 dan oshmagan bo'lsa, 1 ga oshiriladi, status `queued` ga o'tkazilib, yana `publish_reels_task.delay(link.id)` chaqiriladi.

#### D. "Instagramdan yangilash" (Sinxronizatsiya) tugmasi:
1. **Frontend:** `handleSync()` -> `POST /api/user/sync/`.
2. **Throttle:** `UserSyncThrottle` (minutiga maksimum 3 ta so'rov).
3. **Task:** `sync_user_media_task.delay(ig_user.id)` fonda Instagramdan yangi yuklangan postlarni tortib oladi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_video`: `id`, `file`, `title`, `is_default`, `owner_id`, `status` ('ready', 'processing', 'failed'), `processing_error`.
- `tracker_uniquelink`: `id`, `user_id`, `token`, `code`, `video_id`, `status`.
- `tracker_post`: `id`, `link_id`, `ig_media_id`, `status`, `views`, `likes`, `ai_verified`, `ai_confidence`, `transcript`, `points_awarded`.

### 7. Celery/Redis ishtiroki
- `publish_reels_task`: Reelsni Meta serveriga yuklash.
- `process_video_task`: Videoni ffmpeg bilan 9:16 formatga konvertatsiya qilish.
- `sync_user_media_task`: Foydalanuvchining Instagramdagi yangi Reelslarini tekshirish.
- `verify_post_ai_task`: Post ovozi va matnini tahlil qilish.

### 8. Xato holatlari
- **Akkaunt ulanmagan bo'lsa:** "Iltimos, avval Instagram akkauntingizni ulang" xabari.
- **Video tayyorlanayotgan bo'lsa:** "Video tayyorlanmoqda (formatlanmoqda)..." sababi bilan joylash tugmasi nofaol bo'ladi.
- **Instagram token muddati tugasa:** Qayta ulanish talab qilinadi (`needs_reauth`).
- **Limitdan oshsa:** "Minutiga 3 martadan ko'p sinxronizatsiya qilib bo'lmaydi".

### 9. Xavfsizlik
- Foydalanuvchi faqat o'zi yuklagan videolarni yoki tizimning rasmiy default videosini ishlata oladi (`IsAdminOrReadOnlyOwnerVideo`).
- Birovning postini o'chira olmaydi (`user_delete_post` faqat `link__user=ig_user` postlarini o'chiradi).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/user/UserVideoPage.tsx:310`
- **Muammo:** `if (file.size > 100 * 1024 * 1024)` kodi 100MB cheklovini qattiq kodlagan. Agar serverda `MAX_VIDEO_SIZE_MB=50` yoki `200` deb o'zgartirilsa, frontend bu sozlamani bilmaydi.
- **Tuzatish taklifi:** Backenddan `publishStatus?.upload_limits?.max_size_mb` qiymatini olib, tekshiruvni dinamik qilish kerak.

---

## 4. UserPostsPage (Foydalanuvchi Postlari va Tarixi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Foydalanuvchining barcha postlari ro'yxati va statistik ko'rsatkichlari sahifasi (`UserPostsPage`)
- **Fayl yo'li:** `frontend/src/pages/user/UserPostsPage.tsx`

### 2. Nima uchun kerak
Foydalanuvchi o'zi joylagan barcha Instagram Reels videolarining to'liq ro'yxatini ko'rishi, qidirishi, har bir postning ko'rishlar o'sish tarixini modal oynada grafik shaklida tahlil qilishi va xohlasa keraksiz postni ro'yxatdan o'chirishi uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Umumiy statistika chizig'i (KPI Bar):** Tanlangan postlar bo'yicha jami ko'rishlar, layklar va izohlar.
- **Qidiruv va Filtr paneli:** Qidiruv maydoni (kod yoki matn bo'yicha), status bo'yicha filtr ("Faol postlar", "O'chirilgan postlar", "Barchasi").
- **Postlar Kartalari yoki Jadvali:**
  - Video muqovasi (thumbnail) va Instagram permalink havolasi.
  - Unikal reklama kodi (`code`).
  - Ko'rishlar, layklar va izohlar hisoblagichi.
  - AI tekshiruvi natijasi (yashil qalqon yoki qizil belgi).
  - Keyingi avtomatik tekshiruv vaqti.
  - Tugmalar: "Statistika tarixi" (grafikni ochish), "Hozir tekshirish" (Celery tekshiruvini majburiy chaqirish), "O'chirish".
- **Statistika Tarixi Modali:** Postning vaqt bo'yicha qanday ko'rilganini ko'rsatuvchi Recharts chizma grafigi.
- **Sahifalash (Pagination):** 20 tadan postlarni sahifalar bo'yicha ko'rsatish.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Recharts (`AreaChart`, `Area`, `XAxis`, `YAxis`, `Tooltip`), Lucide (`Eye`, `Heart`, `MessageCircle`, `ExternalLink`, `Search`, `Trash2`, `RefreshCw`, `Clock`, `TrendingUp`, `X`, `Loader2`).
- **Hook va State-lar:**
  - `posts: CampaignPost[]`, `totalCount`, `page`, `loading`.
  - `search`, `statusFilter` (qidiruv 400ms debounce bilan ishlaydi).
  - `historyModalOpen`, `selectedPost`, `postHistory: PostStat[]`, `loadingHistory`.
  - `checkingPostId` — ayni vaqtda tekshirilayotgan post ID si.
- **Axios so'rovlar:**
  - `GET /api/user/posts/?page=...&status=...&search=...`
  - `DELETE /api/user/posts/${postId}/`
  - `GET /api/me/posts/${post.id}/history/`
  - `POST /api/posts/${postId}/check-metrics/`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"Hozir tekshirish" tugmasi:**
   - `apiClient.post('/api/posts/${postId}/check-metrics/')` chaqiriladi.
   - `views.py:PostViewSet.check_metrics` ishga tushadi.
   - Redis orqali bir vaqtning o'zida bir necha marta chaqirilishining oldi olinadi (`lock_metrics_${id}`).
   - Celery `check_post_metrics_task.delay(post.id)` navbatga qo'yiladi.
   - 1.5 soniyadan so'ng postlar qayta yuklanadi va yangi statistika ko'rinadi.
2. **"Statistika tarixi" tugmasi:**
   - Modal ochiladi va `GET /api/me/posts/${post.id}/history/` chaqiriladi.
   - `views.py:me_post_history` ushbu postga tegishli `PostStat` yozuvlarini vaqt bo'yicha tartiblab qaytaradi.
3. **"O'chirish" (Trash) tugmasi:**
   - Brauzer tasdiqlash so'raydi (`confirm`).
   - `DELETE /api/user/posts/${postId}/` orqali post o'chiriladi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_post`: post ma'lumotlari.
- `tracker_poststat`: `checked_at`, `views`, `likes`, `comments_count`.
- `tracker_uniquelink`: `code`, `token`.

### 7. Celery/Redis ishtiroki
- `check_post_metrics_task`: Tugma bosilganda yoki har 5 daqiqada post statistikasini Meta API dan yangilab, `PostStat` jadvaliga yangi qator qo'shadi.
- Redis lock: `lock_metrics_{post_id}` orqali ketma-ket qayta so'rov yuborishdan saqlaydi (timeout 60 soniya).

### 8. Xato holatlari
- **Post topilmasa:** 404 xatosi.
- **Meta API rate limit:** Celery vazifasi xato bermasdan kutish rejimiga o'tadi va 60 soniyadan so'ng qayta urinadi.

### 9. Xavfsizlik
- Foydalanuvchi faqat o'z postlarini ko'ra oladi (`link__user=ig_user`).
- `user_delete_post` funksiyasi begona odamning postini o'chirishga yo'l qo'ymaydi.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/user/UserPostsPage.tsx:106`
- **Muammo:** `setTimeout(async () => { await fetchPosts(); setCheckingPostId(null); }, 1500);` kodi komponent unmounted bo'lgan taqdirda ham ishlab, xotira oqishiga (memory leak) va konsolda ogohlantirishga olib kelishi mumkin.
- **Tuzatish taklifi:** `useEffect` ichida `isMounted` flagi yoki `AbortController` bilan boshqarish lozim.

---

# II. ADMINISTRATOR (ADMIN) OYNALARI

---

## 5. AdminDashboardPage (Administrator Boshqaruv Markazi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Administrator umumiy monitoring va tahlil paneli (`AdminDashboardPage`)
- **Fayl yo'li:** `frontend/src/pages/admin/AdminDashboardPage.tsx`

### 2. Nima uchun kerak
Barcha foydalanuvchilar, videolar, umumiy ko'rishlar, sovrinlar holati, tokenlarning eskirish muddati va eng asosiysi — Instagram API dagi xatoliklarni bir joyda nazorat qilib turish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Ogohlantirish bannerlari:**
  - *Token muddati ogohlantirishi:* Muddati 7 kundan kam qolgan tokenlar soni.
  - *Rate limit ogohlantirishi:* Soatiga 200 ta so'rov limitiga yetgan akkauntlar soni.
- **4 ta asosiy KPI karta:** Jami foydalanuvchilar (ulangan va reauth soni bilan), Jami ko'rishlar, Like va izohlar, Jami berilgan sovrinlar.
- **Postlar holati (Status breakdown):** Joylashtirilgan, O'chirilgan, Xatolik yuz bergan, Jarayonda bo'lgan postlar soni.
- **Kunlik o'sish grafigi:** So'nggi 30 kunlik ko'rishlar va yangi postlar dinamikasi (AreaChart).
- **Eng ko'p ko'rilgan 10 ta post jadvali:** Foydalanuvchi ismi, ko'rishlar soni, sana va Instagramga havola.
- **Instagram API Xatoliklari bloki (Oxirgi 1 soat):** O'chirilgan media, token yaroqsizligi, ruxsat yetishmasligi, rate limit va server xatolari soni.

### 4. Frontend kodi
- **Komponentlar:** Recharts (`AreaChart`, `Area`, `XAxis`, `YAxis`, `Tooltip`, `CartesianGrid`), Lucide (`Users`, `VideoIcon`, `Eye`, `Heart`, `Award`, `AlertTriangle`, `TrendingUp`, `ExternalLink`, `Clock`).
- **Hook va State-lar:**
  - `summary: AdminSummary | null`
  - `dailyStats: AdminDailyStat[]`
  - `topPosts: Post[]`
  - `loading: boolean`
- **Axios so'rovlar:**
  - `GET /api/admin/summary/`
  - `GET /api/admin/stats/daily/`
  - `GET /api/admin/posts/?ordering=-views&page_size=10`

### 5. Har bir tugma bosilganda nima bo'ladi
- Sahifada tashqi havolalar (Reels postini Instagramda ochish) mavjud.
- Yuklanishda 3 ta so'rov parallel yuboriladi (`Promise.all`).
- Backendda `admin_summary` natijasi Redis keshida 60 soniya saqlanadi (`cache.set('admin_summary_cache', data, timeout=60)`). Bu minglab postlar bo'lganda bazani ortiqcha yuklamaslik uchun qilingan.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_instagramuser`, `tracker_post`, `tracker_prize`, `tracker_uniquelink`.
- `Post.objects.aggregate()` orqali jami ko'rishlar va likelar hisoblanadi.
- `TruncDate('posted_at')` orqali 30 kunlik statistika guruhlanadi.

### 7. Celery/Redis ishtiroki
- Redis: `admin_summary` statistikasini 60 soniya keshlaydi.
- Redis: Instagram xatoliklarini (`instagram_errors_last_hour`) ro'yxatga olib turadi.
- Redis: Rate limitga tushgan hisoblarni hisoblaydi.

### 8. Xato holatlari
- **Oddiy foydalanuvchi kirsa:** 403 Forbidden beriladi va `AdminProtectedLayout` uni `/app` ga qaytaradi.
- **Baza bo'sh bo'lsa:** Grafikda "Statistika ma'lumotlari mavjud emas", jadvalda "Postlar topilmadi" deb chiqadi.

### 9. Xavfsizlik
- Faqat `is_staff=True` yoki `is_superuser=True` bo'lgan adminlar kira oladi (`IsAdminRole`).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `tracker/urls.py:92-93`
- **Muammo:** Backend URL sozlamalarida `admin_reset_password` endpointi ketma-ket ikki marta takroran yozilgan:
  ```python
  path('api/admin/reset-password/', admin_reset_password, name='admin_reset_password'),
  path('api/admin/reset-password/', admin_reset_password, name='admin_reset_password'),
  ```
- **Tuzatish taklifi:** Bitta ortiqcha qatorni o'chirib tashlash kerak.

---

## 6. AdminPostsPage (Barcha Postlar va AI Aksiya Sozlamalari)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Administrator postlar boshqaruvi va AI kampaniya sozlamalari sahifasi (`AdminPostsPage`)
- **Fayl yo'li:** `frontend/src/pages/admin/AdminPostsPage.tsx`

### 2. Nima uchun kerak
Barcha foydalanuvchilarning Reels postlarini filtrlash, CSV formatida yuklab olish, sun'iy intellekt (Gemini / Whisper) aksiya qoidalarini va kalit so'zlarini sozlash hamda shubhali postlarni AI orqali qayta tekshiruvdan o'tkazish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Yuqori boshqaruv tugmalari:**
  - "AI Aksiya Sozlamasi" tugmasi (mavzu, brend, kalit so'zlar va beriladigan ballarni tahrirlash modali).
  - "CSV Eksport" tugmasi (barcha postlar statistikasini Excel/CSV fayl qilib yuklab olish).
  - Yangilash tugmasi.
- **Keng qamrovli filtr paneli:** Holat bo'yicha (Tasdiqlangan, Rad etilgan, Joylangan va h.k.), Manba bo'yicha (`site` yoki `self`), Foydalanuvchi yoki kod bo'yicha qidiruv, Sana oralig'i (Boshlanish va Tugash sanalari).
- **Postlar jadvali:** Muqova surati, Foydalanuvchi nomi, Unikal kod, Status badge, Ko'rishlar, Like, Izohlar, Joylangan sana, AI tekshiruv natijasi (AI Verified, Confidence, Manba: Audio/Caption), Amallar (Qayta tekshirish, Qayta urinish, O'chirish, AI Tahlilini ko'rish).
- **AI Tahlil Modali (Inspection Modal):** Videodan ajratib olingan audio matni (transkript), AI nega bu qarorga kelgani tushuntirishi (`ai_explanation`) va "Qayta AI tekshiruvi" tugmasi.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Lucide (`ExternalLink`, `RefreshCw`, `RotateCcw`, `Download`, `AlertTriangle`, `Loader2`, `Eye`, `Heart`, `Search`, `Trash2`, `Sparkles`, `Mic`, `Award`, `CheckCircle2`, `AlertCircle`, `X`).
- **Hook va State-lar:**
  - `posts: CampaignPost[]`, `config: CampaignConfig | null`.
  - `configModalOpen`, `selectedPostForAI`, `savingConfig`, `reverifyingAI`, `exporting`.
- **Axios so'rovlar:**
  - `GET /api/admin/campaign-config/`
  - `PUT /api/admin/campaign-config/`
  - `GET /api/admin/campaign-posts/?...`
  - `POST /api/admin/posts/${id}/re-verify-ai/`
  - `POST /api/posts/${id}/check-metrics/`
  - `POST /api/posts/${id}/retry/`
  - `GET /api/admin/export/posts.csv?...` (responseType: 'blob')
  - `DELETE /api/user/posts/${id}/`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"AI Aksiya Sozlamasini saqlash" tugmasi:**
   - `PUT /api/admin/campaign-config/` chaqiriladi.
   - `views.py:admin_campaign_config` orqali `CampaignConfig` singleton modeli yangilanadi (yangi brend nomi, majburiy so'zlar saqlanadi).
2. **"Qayta AI tekshiruvi" tugmasi:**
   - `POST /api/admin/posts/${postId}/re-verify-ai/` chaqiriladi.
   - `views.py:admin_reverify_post_ai` funksiyasi `ai_verifier.process_and_verify_post_ai(post)` ni ishga tushiradi.
   - Videoning audiosi qayta tahlil qilinadi, yangi kalit so'zlar tekshiriladi, `ai_verified`, `ai_confidence` va `points_awarded` yangilanadi.
3. **"CSV Eksport" tugmasi:**
   - `GET /api/admin/export/posts.csv?...` chaqiriladi.
   - `views.py:admin_export_posts_csv` `StreamingHttpResponse` orqali katta hajmdagi ma'lumotlarni oqimli (stream) ravishda uzatadi va brauzer `posts.csv` faylini yuklab oladi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_campaignconfig`: `topic`, `brand_name`, `required_keywords`, `ai_prompt_instructions`, `points_reward`.
- `tracker_post`: barcha post maydonlari, transkript va AI xulosalari.

### 7. Celery/Redis ishtiroki
- Celery fondagi `verify_post_ai_task` orqali yangi chiqqan postlarni AI orqali tekshirib turadi. Admin sahifasida esa darhol tekshirish imkoniyati ham berilgan.

### 8. Xato holatlari
- Agar CSV eksportda sana noto'g'ri berilsa yoki xato bo'lsa, qizil toast xabari chiqadi.
- Agar AI tekshiruvida video fayl topilmasa, `ai_verified=False` va `ai_detection_source='none'` bo'ladi.

### 9. Xavfsizlik
- Faqat administratorlar (`IsAdminRole`, `IsAdminUser`) kira oladi va AI sozlamalarini o'zgartira oladi.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/admin/AdminPostsPage.tsx:160`
- **Muammo:** Admin sahifasida postni o'chirish uchun foydalanuvchilarning `/api/user/posts/${postId}/` endpointi chaqirilgan. Bu backendda ishlasa-da, arxitekturaviy jihatdan admin amallari admin endpointlari (`/api/admin/posts/...`) orqali bo'lishi to'g'ri hisoblanadi.
- **Tuzatish taklifi:** Admin uchun alohida delete endpoint yaratish yoki umumiy post viewsetidan foydalanish maqsadga muvofiq.

---

## 7. AdminVideosPage (Videolar Kutubxonasi Boshqaruvi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Videolar kutubxonasi va umumiy (default) videolarni boshqarish sahifasi (`AdminVideosPage`)
- **Fayl yo'li:** `frontend/src/pages/admin/AdminVideosPage.tsx`

### 2. Nima uchun kerak
Admin tomonidan tizimga yangi reklama roliklarini yuklash, biror videoni barcha foydalanuvchilar uchun "Umumiy/Default video" sifatida belgilash, videolarni ma'lum bir foydalanuvchiga biriktirish va faolsizlantirish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **"Yangi video yuklash" tugmasi:** Yangi video yuklash modal oynasini ochadi.
- **Videolar jadvali:**
  - Video sarlavhasi va pleyer (video ko'rish tugmasi).
  - Status badge: `ready` (tayyor 9:16), `processing` (tayyorlanmoqda), `failed` (xato).
  - Egasi (Owner): Umumiy video yoki ma'lum bir foydalanuvchiga tegishli.
  - Belgilar: Default (Asosiy) sariq yulduzcha belgisi, Faollik holati (`is_active`).
  - Amallar: "Default qilish" (yulduzcha tugma), "Egaga biriktirish" (User icon), "Faollikni o'zgartirish" (Power icon), "O'chirish" (Trash icon).
- **Egasini biriktirish modali:** Foydalanuvchilar ro'yxatidan tanlab, videoni shaxsiy qilib berish.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Lucide (`Upload`, `Star`, `UserCheck`, `Power`, `Trash2`, `X`, `Loader2`, `ExternalLink`).
- **Hook va State-lar:**
  - `videos: VideoItem[]`, `usersList: InstagramUser[]`.
  - `uploadModalOpen`, `assignModalOpen`, `selectedVideo`, `uploadProgress`, `uploading`.
- **Axios so'rovlar:**
  - `GET /api/videos/?page=...`
  - `GET /api/users/?page_size=100`
  - `POST /api/videos/` (multipart/form-data)
  - `POST /api/videos/${id}/set-default/`
  - `PATCH /api/videos/${id}/`
  - `DELETE /api/videos/${id}/`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"Default qilish" (Set Default) tugmasi:**
   - `POST /api/videos/${id}/set-default/` chaqiriladi.
   - `views.py:VideoViewSet.set_default` ichida `transaction.atomic()` bilan oldingi barcha default videolardan `is_default=False` qilinadi va aynan shu video `is_default=True` bo'ladi.
2. **"Yangi video yuklash" tugmasi:**
   - Fayl va parametrlar yuboriladi -> `VideoViewSet.perform_create`.
   - Video `status='processing'` qilib saqlanadi va darhol `process_video_task.delay(video.id)` ishga tushadi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_video`: `id`, `title`, `file`, `is_default`, `owner_id`, `is_active`, `status`, `processing_error`.

### 7. Celery/Redis ishtiroki
- `process_video_task`: FFmpeg orqali videoni tekshiradi va 9:16 formatga keltiradi.

### 8. Xato holatlari
- Video fayl `.mp4` bo'lmasa yoki 100MB dan katta bo'lsa xato beradi.
- Agar videoni formatlab bo'lmasa, `status='failed'` bo'lib, xato sababi `processing_error` maydonida ko'rsatiladi.

### 9. Xavfsizlik
- Faqat administratorlar video yuklashi, o'chirishi va default qilib belgilashi mumkin (`IsAdminOrReadOnlyOwnerVideo`).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/admin/AdminVideosPage.tsx:78`
- **Muammo:** `if (file.size > 100 * 1024 * 1024)` — mijoz tomonida hajm chegarasi qattiq yozilgan.
- **Tuzatish taklifi:** Hajm limitini server konfiguratsiyasidan olish tavsiya etiladi.

---

## 8. AdminUsersPage (Foydalanuvchilar Ro'yxati va Boshqaruvi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Foydalanuvchilar ro'yxati va parollarni tiklash sahifasi (`AdminUsersPage`)
- **Fayl yo'li:** `frontend/src/pages/admin/AdminUsersPage.tsx`

### 2. Nima uchun kerak
Admin barcha ro'yxatdan o'tgan foydalanuvchilarni ko'rishi, ularning qancha ko'rish va post to'plaganini tahlil qilishi, yangi admin yoki foydalanuvchi qo'shishi va parolini unutgan foydalanuvchining parolini yangilab berishi uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **"Yangi foydalanuvchi yaratish" tugmasi:** Username, parol, ism va "Admin qilish" checkboxiga ega modal oyna.
- **Qidiruv va Saralash:** Ism, login yoki Instagram ID bo'yicha qidiruv; Ko'rishlar, postlar soni yoki ro'yxatdan o'tgan sana bo'yicha tartiblash.
- **Foydalanuvchilar jadvali:**
  - Login va Ism-familiya.
  - Instagram hisob holati (Ulangan, Qayta ulanish kerak, Kutilmoqda).
  - Jami postlar soni, jami ko'rishlar, layklar va izohlar.
  - Oxirgi video joylagan sanasi.
  - Amallar: "Batafsil ko'rish" (User detail sahifasiga o'tish), "Parolni tiklash" (Reset password modali).
- **Parolni tiklash modali:** Yangi parol kiritish formasi.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Lucide (`Search`, `UserPlus`, `KeyRound`, `Eye`, `CheckCircle`, `AlertCircle`, `X`, `Loader2`).
- **Hook va State-lar:**
  - `users: AdminUserItem[]`, `page`, `search`, `statusFilter`, `ordering`.
  - `createModalOpen`, `resetModalOpen`, `selectedUser`, `newPassword`.
- **Axios so'rovlar:**
  - `GET /api/admin/users/?page=...&ordering=...&search=...&status=...`
  - `POST /api/admin/create-user/`
  - `POST /api/users/${selectedUser.id}/reset-password/`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"Foydalanuvchi yaratish" tugmasi:**
   - `POST /api/admin/create-user/` chaqiriladi.
   - `views.py:admin_create_user` orqali `AdminCreateUserSerializer` tekshiradi.
   - Django `User` va `InstagramUser` birgalikda yaratiladi.
2. **"Parolni tiklash" tugmasi:**
   - `POST /api/users/${id}/reset-password/` chaqiriladi.
   - `InstagramUserViewSet.reset_password` foydalanuvchining Django parolini `set_password()` qilib yangilaydi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `auth_user`: foydalanuvchi ma'lumotlari.
- `tracker_instagramuser`: `status`, `ig_user_id`, `name`.
- SQL `annotate()` orqali `posts_count`, `total_views`, `total_likes` bir so'rovda hisoblanadi (N+1 muammosi bartaraf etilgan).

### 7. Celery/Redis ishtiroki
- Ushbu sahifada bevosita Celery vazifalari chaqirilmaydi.

### 8. Xato holatlari
- Band username kiritilsa: `"Bunday username band. Boshqa username tanlang."`
- Parol talablarga mos kelmasa: Django validator xabarlari ko'rsatiladi.

### 9. Xavfsizlik
- Faqat adminlar kira oladi (`IsAdminRole`).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/admin/AdminUsersPage.tsx:107`
- **Muammo:** Parolni tiklash uchun `POST /api/users/${selectedUser.id}/reset-password/` chaqirilmoqda, lekin `tracker/urls.py` da yana alohida `POST /api/admin/reset-password/` ham mavjud. Ikki xil endpoint borligi chalkashlik tug'diradi.
- **Tuzatish taklifi:** Barcha admin parolini tiklash amallarini yagona `/api/admin/reset-password/` ga yo'naltirish lozim.

---

## 9. AdminUserDetailPage (Foydalanuvchi Tafsiloti va Tarixi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Administrator uchun foydalanuvchi to'liq profili va individual statistikasi sahifasi (`AdminUserDetailPage`)
- **Fayl yo'li:** `frontend/src/pages/admin/AdminUserDetailPage.tsx`

### 2. Nima uchun kerak
Tanlangan alohida bir foydalanuvchining butun faoliyatini chuqur o'rganish: uning barcha postlari, ko'rishlar o'sish dinamikasi grafigi va Instagram holatini ko'rish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Orqaga qaytish havolasi:** "Foydalanuvchilar roʻyxatiga qaytish".
- **Foydalanuvchi profili sarlavhasi:** Ismi, username va ID raqami.
- **4 ta statistik karta:** Holati (Ulangan/Kutilmoqda), Jami ko'rishlar, Jami like'lar, Postlar soni.
- **Ko'rishlar O'sishi Dinamikasi Grafigi (LineChart):** Foydalanuvchining vaqt bo'yicha to'plagan ko'rishlari chizig'i.
- **Foydalanuvchining Postlari Jadvali:** Post ID, Status, Ko'rishlar, Like, Izohlar, Joylangan sana, Instagram havolasi va o'chirilgan bo'lsa qachon o'chirilgani sanasi.

### 4. Frontend kodi
- **Komponentlar:** Recharts (`ResponsiveContainer`, `LineChart`, `Line`, `XAxis`, `YAxis`, `Tooltip`, `CartesianGrid`), Lucide (`ArrowLeft`, `VideoIcon`, `ExternalLink`, `TrendingUp`).
- **Hook va State-lar:**
  - `const { id } = useParams<{ id: string }>()` — URL dan foydalanuvchi ID sini olish.
  - `userData: any` — foydalanuvchi to'liq ma'lumotlari.
  - `loading: boolean`.
- **Axios so'rovlar:**
  - `GET /api/admin/users/${id}/`

### 5. Har bir tugma bosilganda nima bo'ladi
- Sahifa ochilishi bilan `apiClient.get('/api/admin/users/${id}/')` chaqiriladi.
- `views.py:admin_user_detail` funksiyasi foydalanuvchining postlarini va ularning barcha `PostStat` yozuvlarini yig'adi, vaqt bo'yicha tartiblab `all_history` ro'yxatini shakllantiradi va qaytaradi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_instagramuser`, `tracker_post`, `tracker_poststat`.

### 7. Celery/Redis ishtiroki
- Ushbu sahifa ma'lumotlarni o'qish (read-only) rejimida ishlaydi.

### 8. Xato holatlari
- Foydalanuvchi ID topilmasa: "Foydalanuvchi topilmadi" xabari ko'rinadi.

### 9. Xavfsizlik
- Faqat administratorlar kira oladi (`IsAdminRole`). Oddiy foydalanuvchilar boshqalarning profiliga kira olmaydi.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/admin/AdminUserDetailPage.tsx:25`
- **Muammo:** `const [userData, setUserData] = useState<any>(null);` — `any` tipidan foydalanilgan, bu TypeScript tip xavfsizligini yo'qotadi va `all_history` mavjud bo'lmaganda xatoni oldindan aniqlashga to'sqinlik qiladi.
- **Tuzatish taklifi:** `AdminUserDetailResponse` interfeysini e'lon qilib, unga qat'iy turlarni biriktirish kerak.

---

## 10. LinksPage (Unikal Havolalar Boshqaruvi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Unikal taklif havolalari (Unique Links) boshqaruvi sahifasi (`LinksPage`)
- **Fayl yo'li:** `frontend/src/pages/LinksPage.tsx`

### 2. Nima uchun kerak
Foydalanuvchilar uchun maxsus bir martalik yoki cheklangan muddatli unikal taklif havolalarini yaratish, ularga video biriktirish, havolalarni nusxalash va ishlamay qolgan havolalarni qayta tiklash (`resend`) uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **"Yangi link yaratish" tugmasi:** Link yaratish modalini ochadi.
- **Filtr:** Status bo'yicha (Barchasi, Pending, Opened, Posted, Failed).
- **Linklar jadvali:**
  - Foydalanuvchi ismi.
  - Unikal havola (`http://.../link/<uuid>/`) va nusxalash tugmasi (`Copy`/`Check`).
  - Biriktirilgan video nomi.
  - Holat nishoni (`pending`, `opened`, `posted`, `failed`).
  - Amal qilish muddati (Expires At).
  - Qayta yuborish tugmasi (`RotateCcw` — faqat `failed` bo'lgan linklar uchun).
- **Link yaratish modali:** Foydalanuvchini tanlash, Video manbasini tanlash (Umumiy video / Kutubxonadagi video / Yangi video yuklash), Amal qilish muddatini kiritish.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Lucide (`Copy`, `Check`, `Plus`, `RotateCcw`, `UploadCloud`).
- **Hook va State-lar:**
  - `links: UniqueLink[]`, `users: InstagramUser[]`, `availableVideos: any[]`.
  - `isModalOpen`, `selectedUserId`, `videoSource`, `selectedVideoId`, `videoFile`, `expiresAt`, `uploadProgress`, `submitting`.
  - `copiedId`, `resendingId`.
- **Axios so'rovlar:**
  - `GET /api/links/?page=...&status=...`
  - `GET /api/users/?page_size=100`
  - `GET /api/videos/?page_size=100`
  - `POST /api/links/` (multipart/form-data)
  - `POST /api/links/${linkId}/resend/`

### 5. Har bir tugma bosilganda nima bo'ladi
1. **"Nusxalash" tugmasi:**
   - Link matni operatsion tizim buferiga yoziladi (`navigator.clipboard.writeText`), yashil "Nusxalandi!" toasti chiqadi.
2. **"Qayta yuborish" (Resend) tugmasi:**
   - `POST /api/links/${linkId}/resend/` chaqiriladi.
   - `views.py:UniqueLinkViewSet.resend` link holatini `pending` ga o'tkazadi va agar unga bog'langan xato post bo'lsa, uni o'chiradi.
3. **"Link yaratish" tugmasi:**
   - Yangi video yuklansa, `Video` obyekti yaratiladi, so'ng unikal 6 xonali `code` va `token` (UUID) bilan `UniqueLink` saqlanadi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_uniquelink`: `id`, `user_id`, `token` (UUID), `code` (6 xonali unikal), `video_id`, `status`, `expires_at`, `created_at`.
- `tracker_video`, `tracker_instagramuser`.

### 7. Celery/Redis ishtiroki
- Foydalanuvchi havolani bosib Instagram orqali ruxsat berganda (`/oauth/callback/`), avtomatik ravishda Celery `publish_reels_task.delay(link.id)` ishga tushadi.

### 8. Xato holatlari
- Foydalanuvchi tanlanmasa: "Iltimos, foydalanuvchini tanlang" toasti.
- Faqat `failed` holatdagi linklarni qayta yuborish mumkin, aks holda backend 400 beradi.

### 9. Xavfsizlik
- Admin barcha linklarni ko'radi va yaratadi.
- Oddiy foydalanuvchi faqat o'z linklarini ko'ra oladi (`IsOwnerOrAdmin`).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/LinksPage.tsx:46`
- **Muammo:** `apiClient.get('/api/videos/?page_size=100')` — agar bazada 100 tadan ortiq video bo'lsa, dropdown ichida faqat dastlabki 100 ta video chiqadi, qolganlarini tanlab bo'lmaydi.
- **Tuzatish taklifi:** Qidiruvli (searchable select) autocomplete komponentini qo'llash kerak.

---

## 11. PrizesPage (Sovrinlar Tarixi)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Sovrinlar va yutuqlar tarixi sahifasi (`PrizesPage`)
- **Fayl yo'li:** `frontend/src/pages/PrizesPage.tsx`

### 2. Nima uchun kerak
Ko'rishlar soni belgilangan marralarga (masalan, 500, 1000, 5000 va h.k.) yetganda foydalanuvchilarga berilgan barcha yutuqlar tarixini nazorat qilish va ko'rish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Sarlavha:** "Sovrinlar Tarixi" va tushuntirish matni.
- **Sovrinlar jadvali:**
  - Sovrin ID si.
  - Foydalanuvchi ismi.
  - Tegishli Post ID si (`#post_id`).
  - Sovrin Marrasi (`milestone`) — sariq nishoncha bilan (masalan, `1,000 ko'rish`).
  - Yuborilgan aniq sana va vaqt.
- **Sahifalash (Pagination):** 50 tadan sahifalash.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`, Lucide (`Award`).
- **Hook va State-lar:**
  - `prizes: Prize[]`, `loading: boolean`, `page: number`, `totalCount: number`.
- **Axios so'rovlar:**
  - `GET /api/prizes/?page=${page}`

### 5. Har bir tugma bosilganda nima bo'ladi
- Sahifa raqami bosilganda `fetchPrizes` chaqiriladi va keyingi 50 ta sovrin ma'lumotlari yuklanadi.
- Backendda `PrizeViewSet` (ReadOnlyModelViewSet) ishlaydi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_prize`: `id`, `post_id`, `milestone`, `sent_at`.
- `tracker_post`, `tracker_uniquelink`, `tracker_instagramuser`.
- Baza darajasida `unique_together = ('post', 'milestone')` cheklovi bor, ya'ni bitta post bitta marra uchun faqat bir marta sovrin olishi kafolatlangan.

### 7. Celery/Redis ishtiroki
- Sovrinlar qo'lda berilmaydi: Har safar Celery `check_post_metrics_task` post ko'rishlarini yangilaganda, agar yangi marra zabt etilgan bo'lsa, `services.py:check_and_award_prizes` funksiyasi avtomatik tarzda `Prize` va unga bog'liq `Notification` yaratadi.

### 8. Xato holatlari
- Hali sovrinlar berilmagan bo'lsa: "Sovrinlar hali berilmagan" xabari chiqadi.

### 9. Xavfsizlik
- Admin barcha sovrinlarni ko'radi, oddiy foydalanuvchi esa o'z profilida faqat o'ziga tegishli sovrinlarni ko'radi (`IsOwnerOrAdmin`).

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/PrizesPage.tsx:31`
- **Muammo:** Dizayn nomuvofiqligi — butun loyiha zamonaviy to'q rangli (dark mode: `bg-slate-950`, `text-white`) uslubda qurilgan bo'lsa-da, ushbu sahifada oq fonli (`bg-white`, `border-slate-200`, `text-slate-900`) ochiq rangli qoliplar ishlatilgan. Bu umumiy vizual uyg'unlikni buzadi.
- **Tuzatish taklifi:** Tailwind klasslarini `bg-slate-950`, `bg-slate-900`, `border-slate-800` va `text-white` ga o'zgartirish kerak.

---

## 12. DataDeletionsPage (Ma'lumotlarni O'chirish So'rovlari)

### 1. Oyna nomi va fayl yo'li
- **Nomi:** Meta orqali kelgan ma'lumotlarni o'chirish so'rovlari sahifasi (`DataDeletionsPage`)
- **Fayl yo'li:** `frontend/src/pages/DataDeletionsPage.tsx`

### 2. Nima uchun kerak
Meta (Facebook/Instagram) platformasining qat'iy qonuniy talabi (GDPR va Platform Policy) bo'yicha: foydalanuvchi o'z Instagram sozlamalaridan bizning ilovamizni o'chirib tashlaganida, uning barcha shaxsiy ma'lumotlarini o'chirish so'rovi kelib tushadi. Ushbu sahifa o'sha so'rovlarni va ularning holatini nazorat qilish uchun kerak.

### 3. Ekranda nimalar ko'rinadi
- **Sarlavha:** "Maʼlumotlarni Oʻchirish Soʻrovlari".
- **So'rovlar jadvali:**
  - Tasdiq kodi (`Confirmation Code` — UUID shaklida).
  - Meta User ID (Instagram foydalanuvchisining raqamli identifikatori).
  - Status nishoni: `Completed` (yashil), `Pending` (sariq), `Failed` (qizil).
  - So'ralgan sana va vaqt.
  - Tafsilotlar (`Details`).
- **Sahifalash (Pagination):** 50 tadan sahifalash.

### 4. Frontend kodi
- **Komponentlar:** `Pagination`.
- **Hook va State-lar:**
  - `requests: DataDeletionRequest[]`, `loading: boolean`, `page: number`, `totalCount: number`.
- **Axios so'rovlar:**
  - `GET /api/data-deletions/?page=${page}`

### 5. Har bir tugma bosilganda nima bo'ladi
- Sahifa ochilganda `apiClient.get('/api/data-deletions/')` chaqiriladi.
- Backendda `DataDeletionRequestViewSet` (ReadOnlyModelViewSet) ma'lumotlarni sanasi bo'yicha kamayish tartibida (`-requested_at`) qaytaradi.
- **So'rov qanday paydo bo'ladi?** Meta serveri bizning `POST /oauth/data-deletion/` manzilimizga imzolangan `signed_request` yuboradi. Backend `services.py:handle_data_deletion_request` orqali foydalanuvchining tokenlari va ma'lumotlarini tozalaydi, tasdiq kodi yaratadi va statusini `completed` qiladi.

### 6. Ishlatiladigan baza jadvallari va maydonlar
- `tracker_datadeletionrequest`: `id`, `confirmation_code`, `user_id`, `status` ('pending', 'completed', 'failed'), `requested_at`, `details`.

### 7. Celery/Redis ishtiroki
- Ushbu ma'lumotlar Meta tomonidan yuboriladigan Webhook orqali to'ldiriladi.

### 8. Xato holatlari
- So'rovlar mavjud bo'lmasa: "Soʻrovlar mavjud emas" matni chiqadi.

### 9. Xavfsizlik
- Faqat administratorlar (`IsAdminRole`) ko'ra oladi. Tashqi foydalanuvchilar esa o'z so'rovining holatini ochiq `/oauth/data-deletion/status/<confirmation_code>/` havolasi orqali tekshirishlari mumkin.

### 10. Sahifadagi muammo (Zaif joy)
- **Fayl:qator:** `frontend/src/pages/DataDeletionsPage.tsx:42`
- **Muammo:** `PrizesPage` kabi bu sahifa ham loyihaning umumiy to'q (dark) foniga mos kelmaydigan oq fon (`bg-white`, `border-slate-200`) klasslari bilan qolib ketgan.
- **Tuzatish taklifi:** Sahifa dizaynini loyiha andozasiga moslab `bg-slate-950` va `bg-slate-900` ga o'tkazish lozim.

---

# III. BUTUN LOYIHA BO'YICHA MA'LUMOT OQIMI SXEMASI

Quyida foydalanuvchi tugmani bosganidan boshlab to ma'lumot bazaga borib, orqaga qaytguncha qaysi papkalar va qatlamlardan o'tishi tasvirlangan:

```
[ FRONTEND QATLAMI ]
  1. frontend/src/pages/ (Foydalanuvchi harakati: tugma bosilishi, forma to'ldirilishi)
         │
         ▼
  2. frontend/src/context/ (AuthContext tokenlarni qo'shadi) & api/client.ts (Axios Interceptors: Bearer JWT)
         │  (HTTP / JSON So'rovi)
         ▼
[ BACKEND QATLAMI ]
  3. config/urls.py  ───► tracker/urls.py (Yo'nalish aniqlanadi: URL -> View funksiyasi)
         │
         ▼
  4. tracker/throttles.py (Rate Limit tekshiriladi: minutiga/soatiga so'rovlar soni oshmaganmi?)
         │
         ▼
  5. tracker/permissions.py (Xavfsizlik tekshiriladi: User tizimga kirganmi? Adminmi? O'zining obyektimi?)
         │
         ▼
  6. tracker/views.py (Asosiy boshqaruvchi: parametrlar qabul qilinadi)
         │
         ├───► tracker/serializers.py (Ma'lumotlar tozaligi va formati tekshiriladi: Validation)
         │
         ├───► tracker/services.py (Murakkab biznes-mantiq: Meta API bilan ishlash, shifrlash)
         │        │
         │        ├───► tracker/crypto.py (Tokenlarni Fernet bilan AES-128 shifrlash/ochish)
         │        └───► tracker/instagram_client.py (Meta Graph API ga haqiqiy so'rov yuborish)
         │
         ├───► tracker/tasks.py [CELERY WORKER & REDIS] (Og'ir ishlar: Video konvertatsiya, Reels yuklash, AI)
         │        │
         │        ├───► tracker/video_utils.py (FFmpeg orqali 9:16 formatlash)
         │        └───► tracker/ai_verifier.py (Whisper/Gemini audio transkripsiya va tekshiruv)
         │
         ▼
  7. tracker/models.py ───► [ PostgreSQL BAZASI ] (Ma'lumotlar jadvallarga yoziladi yoki o'qiladi)
         │
         ▼
  8. Serializers orqali JSON javob shakllanadi ───► Axios ───► React State ───► Ekranda aks etadi!
```

---

# IV. OYNALAR O'RTASIDAGI BOG'LIQLIK (NAVIGATSIYA) XARITASI

```
                  ┌─────────────────────────────────────┐
                  │              LoginPage              │
                  │        (/login orqali kirish)       │
                  └──────────────────┬──────────────────┘
                                     │
                 Roliga qarab yo'naltirish (AuthContext)
                 ┌───────────────────┴───────────────────┐
                 ▼                                       ▼
       [ Foydalanuvchi Paneli ]               [ Administrator Paneli ]
       
   ┌──────────────────────────────┐       ┌──────────────────────────────┐
   │      UserDashboardPage       │       │      AdminDashboardPage      │
   │   (/app - Natijalar, Kpi)    │       │  (/admin-panel - Umumiy Kpi) │
   └─────────────┬────────────────┘       └──────────────┬───────────────┘
                 │                                       │
     ┌───────────┴───────────┐               ┌───────────┼───────────┐
     ▼                       ▼               ▼           ▼           ▼
┌──────────────┐     ┌──────────────┐  ┌───────────┐┌──────────┐┌───────────┐
│UserVideoPage │     │UserPostsPage │  │AdminUsers ││AdminPosts││AdminVideos│
│(/app/video)  │     │(/app/posts)  │  │  Page     ││  Page    ││  Page     │
└──────────────┘     └──────────────┘  └─────┬─────┘└──────────┘└───────────┘
                                             │
                                             ▼
                                      ┌──────────────┐
                                      │AdminUserDetail│
                                      │Page (:id)    │
                                      └──────────────┘
                                             │
                         Qo'shimcha boshqaruv sahifalari:
                         ├── LinksPage (/admin-panel/links)
                         ├── PrizesPage (/admin-panel/prizes)
                         └── DataDeletionsPage (/admin-panel/deletions)
```

---

## 🔍 Ushbu ma'lumotlarni topish uchun foydalanilgan vositalar va manbalar:
1. `read_file` vositasi: Frontend barcha 12 ta sahifasi (`frontend/src/pages/`), `App.tsx`, `api/client.ts`, `AuthContext.tsx`, `types/index.ts` hamda backenddagi `tracker/urls.py`, `config/urls.py`, `tracker/models.py`, `tracker/views.py`, `tracker/serializers.py`, `tracker/permissions.py`, `tracker/tasks.py`, `tracker/throttles.py`, `tracker/services.py`, `tracker/ai_verifier.py` to'liq o'qib chiqildi.
2. `grep_search` vositasi: Barcha `@shared_task` Celery vazifalari, `CELERY_BEAT_SCHEDULE` davriy rejalari, barcha `@api_view` va `viewsets` ro'yxatlari aniq satr raqamlari bilan qidirildi va o'zaro solishtirildi.
