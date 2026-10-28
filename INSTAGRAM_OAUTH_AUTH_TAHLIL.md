# InstaChecker — Instagram OAuth & Autentifikatsiya Bo'limi Tahlili

Ushbu tahlil hujjati **InstaChecker** loyihasining `config/`, `tracker/` va `frontend/src/` papkalaridagi kod bazasi asosida tayyorlandi. Tizimdagi foydalanuvchini autentifikatsiya qilish, Instagram hisobini ulash (OAuth 2.0), tokenlarni shifrlash va yangilash mexanizmlarining qat'iy kod zanjiri ko'rsatilgan.

---

## 1. KIRISH NUQTALARI

Bu bo'lim quyidagi 7 xil usul orqali ishga tushadi:

| # | Kirish nuqtasi turi | Nima ishga tushiradi | Qaysi funksiya / View ishlaydi | Fayl va qator |
|---|----------------------|-----------------------|--------------------------------|---------------|
| 1 | **Frontend tugma / HTTP GET** | Foydalanuvchi Login sahifasidagi "Instagram orqali davom etish" tugmasini bosganda yoki to'g'ridan-to'g'ri havola orqali kelganda | `instagram_auth_url(request)` | `tracker/views.py:1137` |
| 2 | **Frontend tugma / HTTP POST & GET** | Shaxsiy kabinetda (`UserVideoPage.tsx`) "Instagram akkauntni ulash" tugmasi bosilganda (`/api/user/connect-instagram/`) | `user_connect_instagram(request)` | `tracker/views.py:1045` |
| 3 | **Unikal havola / HTTP GET** | Foydalanuvchiga yuborilgan shaxsiy havola ochilganda (`/link/<uuid:token>/`) | `redirect_to_instagram(request, token)` | `tracker/views.py:1439` |
| 4 | **Tashqi OAuth Callback / HTTP GET** | Meta Instagram serveri avtorizatsiya kodini bizning serverga qaytarganda (`/oauth/callback/`) | `instagram_callback(request)` | `tracker/views.py:1485` |
| 5 | **Frontend Forma / HTTP POST (JWT Login & Sign Up)** | Login formasi (`/api/token/`) yoki Ro'yxatdan o'tish formasi (`/api/register/`) yuborilganda | `LoginView` (Throttle bilan) va `register_user` | `tracker/throttles.py:27`, `tracker/views.py:976` |
| 6 | **Celery Beat Rejali Jadvali** | Har kuni soat 03:00 da avtomatik ishga tushuvchi rejalashtiruvchi (`refresh-expiring-instagram-tokens`) | `refresh_expiring_tokens_task()` | `config/settings.py:240`, `tracker/tasks.py:168` |
| 7 | **Meta Webhook / HTTP POST** | Foydalanuvchi Instagram ilovasida ruxsatni bekor qilganda (`/oauth/deauthorize/`) yoki ma'lumotlarni o'chirishni so'raganda (`/oauth/data-deletion/`) | `instagram_deauthorize` va `instagram_data_deletion` | `tracker/views.py:1628`, `tracker/views.py:1658` |
| 8 | **Django Admin Action & CLI Commands** | Admin paneldan "Tokenni yangilash" tugmasi yoki terminaldan `connect_instagram`, `show_auth_url`, `check_instagram` buyruqlari berilganda | `refresh_token_action`, `Command.handle` | `tracker/admin.py:26`, `tracker/management/commands/` |

---

## 2. KOD ZANJIRI (Chaqiruvlar ketma-ketligi)

### A. To'liq Instagram OAuth 2.0 orqali ulanish oqimi
1. **`frontend/src/pages/LoginPage.tsx:92` yoki `frontend/src/pages/user/UserVideoPage.tsx:214`**: Foydalanuvchi interfeysdagi Instagram tugmasini bosadi va backenddan avtorizatsiya havolasini oladi.
2. **`tracker/views.py:1137` (`instagram_auth_url`)**: Yangi vaqtinchalik `InstagramUser` va `UniqueLink` yaratadi hamda `build_instagram_auth_url` orqali Meta havolasini qaytaradi.
3. **`tracker/services.py:52` -> `tracker/instagram_client.py:139` (`build_auth_url`)**: `client_id`, `redirect_uri`, `scope` va `state=<link.token>` parametrlarini birlashtirib `https://www.instagram.com/oauth/authorize` manzilini yasaydi.
4. **Meta Instagram Oynasi**: Foydalanuvchi hisobiga kirib, so'ralgan ruxsatnomalarga (kontent joylash, statistika ko'rish) rozilik beradi.
5. **`tracker/views.py:1485` (`instagram_callback`)**: Meta serveri foydalanuvchini `code` va `state` parametrlari bilan bizning callback manzilimizga yo'naltiradi; funksiya link holatini tekshiradi va `complete_instagram_oauth` ni chaqiradi.
6. **`tracker/services.py:113` (`complete_instagram_oauth`)**:
   - `UniqueLink` ni `state` bo'yicha bazadan oladi (`tracker/services.py:115`).
   - `exchange_code_for_token(code)` chaqiriladi (`tracker/instagram_client.py:154`): Meta API'ga (`https://api.instagram.com/oauth/access_token`) so'rov yuborilib, 1 soatlik `short_lived_token` va `user_id` olinadi.
   - `get_long_lived_token(short_lived_token)` chaqiriladi (`tracker/instagram_client.py:175`): Graph API (`https://graph.instagram.com/access_token`) orqali short-lived token 60 kunlik `long_lived_token`ga almashtiriladi.
   - `verify_token_permissions(final_token)` chaqiriladi (`tracker/instagram_client.py:210`): Tokenning `content_publish`, `manage_insights` kabi majburiy huquqlari borligi tekshiriladi.
   - `check_instagram_account_type(final_token)` chaqiriladi (`tracker/instagram_client.py:231`): Akkaunt shaxsiy (Personal) emas, balki Professional (Business yoki Creator) ekanligi tasdiqlanadi.
   - Foydalanuvchining Instagram `@username` nomi `https://graph.instagram.com/me` orqali so'rab olinadi (`tracker/services.py:156`).
   - `InstagramUser` maydonlari yangilanadi: `access_token` o'rnatiladi (avtomatik Fernet bilan shifrlanadi), `status='connected'`, `token_expires_at = now + 60 kun` qilib saqlanadi (`tracker/services.py:168-173`).
7. **`tracker/views.py:1542-1560`**: Agar `user.user` (Django User) bo'lmasa, Instagram username asosida yangi Django `User` yaratiladi.
8. **`tracker/views.py:1567-1571`**: Ushbu Django `User` uchun JWT `access` va `refresh` tokenlari generatsiya qilinadi.
9. **`tracker/views.py:1574`**: Reels videoni avtomatik Instagramga yuklash vazifasi fonda ishga tushiriladi: `publish_reels_task.delay(link.id)`.
10. **`tracker/templates/tracker/status.html:86-105`**: Foydalanuvchiga muvaffaqiyat ekrani ko'rsatiladi, ichidagi JavaScript JWT tokenlarni brauzer `localStorage`iga yozadi va 1.2 soniyadan so'ng foydalanuvchini `/app/video?connected=1` sahifasiga yo'naltiradi.

---

### B. Oddiy JWT Login va Ro'yxatdan O'tish oqimi
1. **`frontend/src/pages/LoginPage.tsx:31` (`handleLoginSubmit`)**: Foydalanuvchi login va parolni kiritib yuboradi.
2. **`tracker/throttles.py:27` (`LoginView`)**: So'rov `LoginThrottle` (minutiga 5 ta so'rov cheklovi) orqali tekshiriladi (`tracker/throttles.py:6`).
3. **`tracker/throttles.py:14` (`CustomTokenObtainPairSerializer.validate`)**: Django parolini tekshiradi, foydalanuvchi roli (`admin`/`user`), `username`, `name` va `instagram_user_id` ma'lumotlarini JWT token juftligiga (access, refresh) qo'shib javob qaytaradi.
4. **`frontend/src/context/AuthContext.tsx:78` (`login`)**: Qaytgan tokenlarni `localStorage` ga saqlaydi va `/api/me/` orqali to'liq profil ma'lumotlarini yuklaydi.

---

### C. Fondagi Tokenlarni Avtomatik Yangilash (Celery Beat) oqimi
1. **`config/settings.py:239`**: Celery Beat har kuni soat 03:00 da `refresh_expiring_tokens_task` vazifasini chaqiradi.
2. **`tracker/tasks.py:168` (`refresh_expiring_tokens_task`)**: Muddati 14 kundan kam qolgan barcha `status='connected'` foydalanuvchilarni bazadan filtrlaydi.
3. **`tracker/services.py:68` (`refresh_user_token`)**: Har bir foydalanuvchi uchun `refresh_instagram_access_token` funksiyasini chaqiradi.
4. **`tracker/instagram_client.py:193` (`refresh_access_token`)**: Meta Graph API ga (`https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token`) so'rov yuborib tokenni yangilaydi.
5. **`tracker/services.py:76-80`**: Yangi token bazaga shifrlab yoziladi va `token_expires_at` yana 60 kunga uzaytiriladi.

---

## 3. QAYERDAN NIMA OLINADI (Ma'lumot manbalari)

| Manba | Nima olinadi | Qaysi funksiya oladi | Fayl:qator |
|-------|--------------|----------------------|------------|
| **Frontend Request Body** | `username`, `password`, `name` | `register_user` | `tracker/views.py:983`, `tracker/serializers.py:377` |
| **Frontend Request Body** | `username`, `password` | `CustomTokenObtainPairSerializer.validate` | `tracker/throttles.py:15` |
| **Frontend Request Query** | `code` (avtorizatsiya kodi), `state` (UUID token) | `instagram_callback` | `tracker/views.py:1502-1503` |
| **Frontend Request Query** | `token` (unikal havola UUID) | `redirect_to_instagram` | `tracker/views.py:1439` |
| **PostgreSQL (`tracker_uniquelink`)** | `link` yozuvi, unga bog'langan `user` va `video` | `complete_instagram_oauth` | `tracker/services.py:115` |
| **PostgreSQL (`tracker_instagramuser`)** | `access_token`, `status`, `token_expires_at` | `refresh_expiring_tokens_task` | `tracker/tasks.py:173-176` |
| **PostgreSQL (`auth_user`)** | `username`, paroli xeshi, `is_staff` roli | `CustomTokenObtainPairSerializer.validate` | `tracker/throttles.py:17-18` |
| **Settings / Environment** | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`, `INSTAGRAM_SCOPE` | `build_auth_url`, `exchange_code_for_token` | `tracker/instagram_client.py:146-150, 157-160` |
| **Settings / Environment** | `TOKEN_ENCRYPTION_KEY` (Fernet 32 baytli kalit) | `get_fernet_key` | `tracker/crypto.py:11` |
| **Tashqi API (Meta OAuth)** | `access_token` (short-lived), `user_id` | `exchange_code_for_token` | `tracker/instagram_client.py:166` |
| **Tashqi API (Meta Graph API)** | `access_token` (long-lived), `expires_in` (5184000) | `get_long_lived_token` | `tracker/instagram_client.py:182` |
| **Tashqi API (Meta Graph API)** | Ruxsatnomalar ro'yxati (`data: [{permission, status}]`) | `verify_token_permissions` | `tracker/instagram_client.py:213` |
| **Tashqi API (Meta Graph API)** | `account_type` (`BUSINESS`, `MEDIA_CREATOR`, `PERSONAL`) | `check_account_type` | `tracker/instagram_client.py:234` |
| **Tashqi API (Meta Graph API)** | Instagram `@username` foydalanuvchi nomi | `complete_instagram_oauth` | `tracker/services.py:156` |
| **Tashqi API (Meta Webhook Body)** | `signed_request` (HMAC imzoli foydalanuvchi deavtorizatsiya ma'lumotlari) | `instagram_deauthorize` | `tracker/views.py:1632` |
| **Redis Cache** | Anonim foydalanuvchilar login urinishlari hisoblagichi (Rate limit) | `LoginThrottle` | `tracker/throttles.py:6`, `config/settings.py:183` |
| **Redis Cache (Faqat DRY_RUN)** | Token xatoliklari simulyatsiyasi (`dry_run:sim:token:...`) | `MockInstagramClientAdapter` | `tracker/instagram_client.py:595` |

---

## 4. QAYERGA NIMA YOZILADI (Natijalar)

| Qayerga | Nima yoziladi | Qaysi funksiya yozadi | Fayl:qator |
|---------|--------------|----------------------|------------|
| **`tracker_instagramuser` (DB)** | Yangi foydalanuvchi (`name`, `status='pending'`) | `register_user`, `instagram_auth_url` | `tracker/serializers.py:410`, `tracker/views.py:1145` |
| **`tracker_instagramuser` (DB)** | `access_token` (Fernet shifrlangan), `token_expires_at`, `status='connected'`, `ig_user_id`, `name` | `complete_instagram_oauth` | `tracker/services.py:168-173` |
| **`tracker_instagramuser` (DB)** | Yangilangan `access_token`, yangi `token_expires_at` (+60 kun) | `refresh_user_token` | `tracker/services.py:76-80` |
| **`tracker_instagramuser` (DB)** | `status='needs_reauth'`, `access_token=None` | `handle_deauthorize_request`, `handle_data_deletion_request` | `tracker/services.py:739, 767` |
| **`auth_user` (Django DB)** | Yangi tizim foydalanuvchisi (`username`, xesh parol) | `UserRegisterSerializer.create` | `tracker/serializers.py:405` |
| **`auth_user` (Django DB)** | Instagramdan kirgan user uchun avtomatik yaratilgan akkaunt | `instagram_callback` | `tracker/views.py:1555` |
| **`tracker_uniquelink` (DB)** | Yangi unikal token, 6 xonali kod va video bog'lanmasi | `instagram_auth_url`, `user_connect_instagram` | `tracker/views.py:1150, 1059` |
| **`tracker_uniquelink` (DB)** | `status='opened'` yoki `status='failed'` | `redirect_to_instagram`, `instagram_callback` | `tracker/views.py:1459, 1490` |
| **`tracker_datadeletionrequest` (DB)** | `confirmation_code`, `user_id`, `status='completed'` | `handle_data_deletion_request` | `tracker/services.py:773` |
| **Celery Vazifalar Navbati (Redis)** | `publish_reels_task.delay(link.id)` (video chiqarish vazifasi) | `instagram_callback` | `tracker/views.py:1574` |
| **HTTP Response JSON** | JWT `access`, `refresh`, `role`, `username`, `name` | `LoginView`, `register_user` | `tracker/throttles.py:19`, `tracker/views.py:993` |
| **HTTP Response HTML (`status.html`)** | Brauzer skriptiga uzatiladigan JWT tokenlar va qaytish manzili | `instagram_callback` | `tracker/views.py:1576-1585` |
| **Frontend `localStorage`** | `access_token`, `refresh_token`, `user_role` | Brauzerdagi inline JS skript | `tracker/templates/tracker/status.html:95-97` |

---

## 5. ISHTIROK ETADIGAN FAYLLAR

1. **`tracker/models.py`**:
   - `EncryptedTextField` (L10-28): Fernet algoritmi orqali bazaga yozishdan oldin tokenni shifrlaydi va o'qiyotganda deshifrlaydi.
   - `InstagramUser` (L38-66): Instagram foydalanuvchisining tokeni, statusi va amal qilish muddatini saqlaydi.
   - `UniqueLink` (L146-180): OAuth jarayonidagi CSRF va `state` qiymatini bog'lovchi 6 xonali kod va UUID tokenini saqlaydi.
   - `DataDeletionRequest` (L318-333): Meta qoidalariga binoan foydalanuvchi ma'lumotlarini o'chirish arizalarini saqlaydi.
2. **`tracker/crypto.py`**:
   - `encrypt_token` (L49), `decrypt_token` (L62), `get_fernet` (L26): Simmetrik 256-bitli Fernet shifrlash tizimining asosi; tokenni ma'lumotlar bazasida xavfsiz saqlashni ta'minlaydi.
3. **`tracker/instagram_client.py`**:
   - `RealInstagramClientAdapter` (L134-245): Meta Graph API bilan bevosita muloqot qiluvchi klass.
   - `MockInstagramClientAdapter` (L490-535): Sinov (DRY_RUN) rejimida tashqi tarmoqsiz soxta OAuth javoblarini qaytaradi.
4. **`tracker/services.py`**:
   - `complete_instagram_oauth` (L113): OAuth callbackdan kelgan kodni tekshirib, tokenlarni olib foydalanuvchini faollashtiradi.
   - `refresh_user_token` (L68): Foydalanuvchi tokenini Graph API orqali yangilaydi.
   - `parse_signed_request` (L702): Meta Webhook HMAC-SHA256 imzosini tekshiradi.
5. **`tracker/views.py`**:
   - `instagram_auth_url` (L1137), `user_connect_instagram` (L1045), `redirect_to_instagram` (L1439): Avtorizatsiya havolasini shakllantiruvchi endpointlar.
   - `instagram_callback` (L1485): Meta javobini qabul qilib, JWT yaratuvchi va foydalanuvchini tizimga kirituvchi markaziy oyna.
   - `instagram_deauthorize` (L1628), `instagram_data_deletion` (L1658): Tashqi Meta hodisalarini qayta ishlovchilar.
6. **`tracker/throttles.py`**:
   - `LoginThrottle` (L5), `LoginView` (L27), `CustomTokenObtainPairSerializer` (L14): Login so'rovlariga cheklov qo'yadi va JWT tokeniga qo'shimcha profil parametrlarini kiritadi.
7. **`tracker/tasks.py`**:
   - `refresh_expiring_tokens_task` (L168): Token muddati 14 kundan kam qolganda avtomatik fonda yangilovchi Celery vazifasi.
8. **`config/settings.py`**:
   - JWT muddati (`SIMPLE_JWT`, L190), Celery Beat jadvali (`CELERY_BEAT_SCHEDULE`, L239), Rate Limitlar va Instagram konfiguratsiyasi.
9. **`frontend/src/context/AuthContext.tsx`**:
   - Brauzer xotirasidagi (`localStorage`) tokenlarni boshqaradi, URL parametrlaridan yoki `status.html`dan kelgan tokenlarni qabul qiladi.
10. **`frontend/src/api/client.ts`**:
    - Axios interceptor: har bir API so'rovga `Bearer <token>` qo'shadi va 401 xatosi yuz berganda `/api/token/refresh/` orqali yangi access token oladi.
11. **`tracker/templates/tracker/status.html`**:
    - OAuth yakunlanganida natijani ko'rsatib, JWT tokenlarni xavfsiz tarzda frontend `localStorage`iga joylovchi ko'prik shablon.

---

## 6. SHARTLAR VA TARMOQLANISHLAR

| Shart / Qayerda | Tekshiriladigan qiymat | Natija (Yo'nalish) | Kod joyi |
|-----------------|------------------------|---------------------|----------|
| `redirect_to_instagram` | `link.expires_at < timezone.now()` | 400 Xato: "Link muddati tugagan" | `tracker/views.py:1443` |
| `redirect_to_instagram` | `link.status in ('posted', 'failed')` | 400 Xato: "Link faol emas" | `tracker/views.py:1451` |
| `redirect_to_instagram` | `not settings.INSTAGRAM_APP_ID` | Instagramga yo'naltirmaydi, test sahifasi chiqaradi | `tracker/views.py:1464` |
| `instagram_callback` | `request.GET.get('error')` | Link `status='failed'` bo'ladi, 400 rad etildi sahifasi chiqadi | `tracker/views.py:1487` |
| `instagram_callback` | `not code or not state` | 400 Xato: "Kerakli parametrlar topilmadi" | `tracker/views.py:1505` |
| `complete_instagram_oauth` | `has_perms == False` (ruxsat yetishmasa) | User `status='needs_reauth'`, `InstagramOAuthError` tashlanadi | `tracker/services.py:139` |
| `complete_instagram_oauth` | `acc_type == 'PERSONAL'` (shaxsiy akkaunt) | User `status='needs_reauth'`, 400 xatosi: Professional hisob talab qilinadi | `tracker/services.py:148` |
| `complete_instagram_oauth` | `get_long_lived_token` xatoga uchrasa | Short-lived tokenni 3600 soniya muddat bilan saqlaydi (fallback) | `tracker/services.py:133-135` |
| `refresh_user_token` | `InstagramOAuthError` (Meta tokenni bekor qilgan) | User `status='needs_reauth'` qilinadi | `tracker/services.py:91` |
| `refresh_user_token` | `InstagramNetworkError` (tarmoq uzilishi) | User statusi o'zgarmaydi (`connected` saqlanadi), `False` qaytadi | `tracker/services.py:87` |
| `user_connect_instagram` (POST) | `INSTAGRAM_MODE == 'mock'` yoki `DRY_RUN=True` | Graph API ga bormasdan soxta ulanish o'rnatiladi | `tracker/views.py:1076` |
| `parse_signed_request` | `hmac.compare_digest(sig, expected_sig) == False` | `MetaWebhookError`: Imzo mos kelmadi | `tracker/services.py:730` |

---

## 7. FONDA ISHLASH (Celery / Redis)

1. **Tokenlarni Avtomatik Yangilash (`refresh_expiring_tokens_task`)**:
   - **Vaqti / Rejasi:** Celery Beat orqali har kuni soat 03:00 da (`crontab(hour=3, minute=0)` — `config/settings.py:240`).
   - **Mantiq:** Muddati kelayotgan (oxirgi 14 kun ichida qolgan) barcha tokenlarni Meta Graph API orqali uzaytiradi (`tracker/tasks.py:168`).
   - **Retry siyosati:** Bu rejaviy davriy vazifa bo'lgani sababli ichki retry mexanizmiga ega emas; tarmoq xatosi bo'lsa ertasi kuni soat 03:00 da qayta urinadi.
2. **Post Yuklash Vazifasini Boshlash (`publish_reels_task`)**:
   - **Vaqti:** OAuth muvaffaqiyatli yakunlanishi bilanoq `instagram_callback` ichidan chaqiriladi (`tracker/views.py:1574`).
   - **Retry siyosati:** `bind=True, max_retries=3, default_retry_delay=60` (`tracker/tasks.py:24`). Tarmoq xatolarida 1 daqiqalik kechikish bilan 3 martagacha qayta ishlaydi.
3. **Redis Rate Limit va Throttling**:
   - `LoginThrottle`: Redis keshida anonim foydalanuvchilarning IP bo'yicha login urinishlarini hisoblaydi. Cheklov: **minutiga 5 ta so'rov** (`config/settings.py:183`).

---

## 8. XATO VA CHEKKA HOLATLAR

1. **Foydalanuvchi Instagramda ruxsatni rad etsa (Cancel / Decline):**
   - Meta `error=access_denied` parametri bilan callbackga yo'naltiradi (`tracker/views.py:1487`). Tizim `UniqueLink.status='failed'` qiladi va xatolik sahifasini ko'rsatadi.
2. **Foydalanuvchi shaxsiy (Personal) Instagram akkaunti bilan kirsa:**
   - Meta Reels API faqat Professional (Business/Creator) akkauntlarni qo'llab-quvvatlaydi. `check_account_type` buni aniqlaydi, foydalanuvchiga aniq tushuntirish beriladi va uning statusi `needs_reauth` holatiga o'tkaziladi (`tracker/services.py:148`).
3. **Foydalanuvchi Instagram parolini o'zgartirsa yoki ruxsatni bekor qilsa (Error 190):**
   - Meta avtomatik `signed_request` orqali `/oauth/deauthorize/` ga xabar beradi. Tizim `handle_deauthorize_request` orqali foydalanuvchi tokenini o'chiradi va `status='needs_reauth'` qiladi (`tracker/services.py:739`).
4. **Token yangilashda tarmoq uzilsa (Network Timeout):**
   - Tizim `InstagramNetworkError` ni ushlaydi, foydalanuvchi statusini buzmasdan `connected` holatda qoldiradi va keyingi davriy rejada qayta sinaydi (`tracker/services.py:87`).
5. **Foydalanuvchi ma'lumotlarini o'chirishni talab qilsa (GDPR / Meta Data Deletion):**
   - `/oauth/data-deletion/` chaqiriladi. Tizim `handle_data_deletion_request` orqali tokenni o'chiradi, `name="Deleted User {id}"` qilib anonimlashtiradi va foydalanuvchiga kuzatuv kodi (`confirmation_code`) beradi (`tracker/services.py:748`).

---

## 9. ZAIF JOYLAR VA TUZATISHLAR

### 1. Login Sahifasida Instagram Tugmasining Noto'g'ri Ishlashi (Hardcoded URL & JSON)
- **Fayl va qator:** `frontend/src/pages/LoginPage.tsx:92`
- **Muammo:** 
  ```tsx
  <button onClick={() => window.location.href='http://127.0.0.1:8000/api/auth/instagram/url/'} ...>
  ```
  Birinchidan, `http://127.0.0.1:8000/` qattiq yozilgan bo'lib, serverda (production) ishlamaydi. Ikkinchidan, `/api/auth/instagram/url/` API si to'g'ridan-to'g'ri yo'naltirmaydi, balki JSON qaytaradi (`{"auth_url": "..."}`). Tugma bosilganda foydalanuvchi brauzerida xom JSON matni ochilib qoladi!
- **Tuzatish:** Tugma bosilganda `apiClient.get('/api/auth/instagram/url/')` chaqirilib, qaytgan `res.data.auth_url` ga yo'naltirish kerak (xuddi `UserVideoPage.tsx:220` kabi):
  ```tsx
  const handleInstagramLogin = async () => {
    try {
      const res = await apiClient.get('/api/auth/instagram/url/');
      if (res.data?.auth_url) window.location.href = res.data.auth_url;
    } catch (err) {
      showToast("Instagram havolasini olishda xatolik", "error");
    }
  };
  ```

### 2. Ochiq Endpointda Baza Resurslarini Tiqilib Qolishi (Spam DB Creation)
- **Fayl va qator:** `tracker/views.py:1145-1150` (`instagram_auth_url`)
- **Muammo:** Har safar bu ochiq GET so'rov chaqirilganda, bazada yangi `InstagramUser(name="Instagram Foydalanuvchisi")` va yangi `UniqueLink` yaratiladi. Hech qanday rate limit yoki captcha yo'q. Botlar yoki takroriy so'rovlar bazani o'lik foydalanuvchilar bilan to'ldirib tashlashi mumkin.
- **Tuzatish:** Ushbu endpointga anonim throttle (`scope = 'anon'`) o'rnatish yoki tizimga avtorizatsiyadan o'tgan foydalanuvchi bo'lsa, mavjud `InstagramUser` dan foydalanish.

### 3. Foydalanuvchi Yaratishdagi Poyga Holati (Race Condition)
- **Fayl va qator:** `tracker/views.py:1550-1557` (`instagram_callback`)
- **Muammo:** Instagram orqali birinchi marta kirgan foydalanuvchiga yangi `User` yaratishda:
  ```python
  while User.objects.filter(username__iexact=final_username).exists():
      final_username = f"{base_username}_{counter}"
      counter += 1
  django_user = User.objects.create_user(username=final_username, ...)
  ```
  Agar ikki so'rov bir vaqtda kelsa, `exists()` ikkalasida ham `False` qaytarib, keyingi qatorda `IntegrityError` yuz beradi.
- **Tuzatish:** `try ... except IntegrityError:` bloki orqali xavfsiz yaratish yoki tranzaksiya blokida qulflash.

### 4. Foydalanuvchi Deavtorizatsiya Qilinganida Postlar Monitoringi To'xtamasligi
- **Fayl va qator:** `tracker/services.py:739` (`handle_deauthorize_request`)
- **Muammo:** Foydalanuvchi dasturni Instagramdan uzganida faqat uning `access_token`i `None` qilinadi. Lekin uning avvalgi postlari `Post.next_check_at` bo'yicha navbatda qoladi. Celery vazifasi bu postni tekshirishga borganida tokenni topolmay yoki xato olib resurs sarflaydi.
- **Tuzatish:** Deavtorizatsiyada foydalanuvchiga tegishli faol postlarning tekshiruvini ham bekor qilish (`Post.objects.filter(link__user=user).update(next_check_at=None)`).

---

## 10. XULOSA

Instagram OAuth va Autentifikatsiya bo'limi InstaChecker tizimining asosiy "darvozasi" hisoblanadi. U foydalanuvchining shaxsiy Instagram hisobini Meta Graph API orqali xavfsiz bog'laydi, professional (Business/Creator) akkaunt va kerakli ruxsatnomalarni qat'iy tekshiradi hamda olingan 60 kunlik maxfiy tokenni ma'lumotlar bazasida 256-bitli Fernet kaliti bilan shifrlangan holatda saqlaydi. Tizim uzluksiz ishlashi uchun Celery Beat har kuni muddati yaqinlashgan tokenlarni fonda avtomatik yangilab turadi, login jarayonida esa JWT tokenlar vositasida foydalanuvchi sessiyasi ta'minlanadi.

Ushbu bo'limdagi eng muhim 3 ta fayl:
1. `tracker/instagram_client.py` — Meta OAuth 2.0 va Graph API bilan barcha so'rovlar, ruxsat tekshiruvlari va token almashinuvlarini amalga oshiruvchi markaz.
2. `tracker/services.py` — OAuth jarayonining biznes mantiqini (qabul qilish, ruxsatlarni tekshirish, token yangilash, imzolarni tasdiqlash) boshqaruvchi modul.
3. `tracker/views.py` — Foydalanuvchi so'rovlarini qabul qilib, callback orqali JWT tokenlar yaratuvchi va frontendga xavfsiz uzatuvchi kontrollyor.

Ehtiyot bo'lish kerak bo'lgan asosiy jihat: Meta Graph API qoidalarining qat'iyligi (ruxsatlar to'liq berilishi shartligi, shaxsiy akkauntlarning ishlamasligi) hamda `LoginPage.tsx`dagi qattiq yozilgan manzil tufayli ishlab chiqarish muhitida yuzaga kelishi mumkin bo'lgan ulanish uzilishlaridir.

---

## KOD VA JARAYON ZANJIRI DIAGRAMMASI

```text
[Foydalanuvchi (Frontend)]
         │
         ▼
[LoginPage.tsx / UserVideoPage.tsx] ───> GET /api/auth/instagram/url/
         │
         ▼
[tracker/views.py: instagram_auth_url]
         │
         ▼
[tracker/services.py: build_instagram_auth_url]
         │
         ▼
[tracker/instagram_client.py: build_auth_url] ───> https://www.instagram.com/oauth/authorize
         │
         ▼
[Meta Instagram Avtorizatsiya Oynasi (Foydalanuvchi Roziligi)]
         │
         ▼
[GET /oauth/callback/?code=...&state=...]
         │
         ▼
[tracker/views.py: instagram_callback]
         │
         ▼
[tracker/services.py: complete_instagram_oauth]
         │
         ├──> POST https://api.instagram.com/oauth/access_token (Short-lived Token)
         ├──> GET  https://graph.instagram.com/access_token (Long-lived 60 kunlik Token)
         ├──> GET  https://graph.instagram.com/me/permissions (Ruxsatlarni tekshirish)
         ├──> GET  https://graph.instagram.com/v21.0/me (Akkaunt turini tekshirish: Business/Creator)
         └──> GET  https://graph.instagram.com/me (Instagram @username olish)
         │
         ▼
[tracker/crypto.py: encrypt_token] ───> Fernet bilan shifrlash
         │
         ▼
[Baza: tracker_instagramuser (status='connected', access_token=shifrlangan, token_expires_at=+60 kun)]
         │
         ├──> [Baza: auth_user (Django User yaratish / biriktirish)]
         ├──> [JWT Tokenlar: RefreshToken.for_user(django_user) -> access, refresh]
         └──> [Celery: publish_reels_task.delay(link.id)]
         │
         ▼
[tracker/templates/tracker/status.html]
         │
         ▼
[Brauzer localStorage (access_token, refresh_token saqlanadi)] ───> Yo'naltirish: /app/video?connected=1
```
