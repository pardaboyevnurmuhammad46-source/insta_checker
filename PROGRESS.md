# Loyiha Rivojlanish Jarayoni (PROGRESS)

## [R0] Instagram Haqiqiy Rejimga O'tkazish (graph.instagram.com)
**Sana:** 2026-10-21
**Holat:** Bajarildi

### Bajarilgan ishlar:
1. **Facebook qoldiqlari olib tashlandi:**
   - `config/settings.py` va `.env.example` fayllaridan `FACEBOOK_APP_ID`, `FACEBOOK_APP_SECRET` qoldiqlari butunlay tozalandi.
   - So'rovlar faqat `https://graph.instagram.com` (va avtorizatsiya uchun tegishli Instagram domenlari) ga yo'naltirildi.
2. **Qat'iy muhit tekshiruvi:**
   - `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_ACCESS_TOKEN` kalitlari faqat `os.environ[...]` orqali o'qiladigan qilindi. Kalitlar mavjud bo'lmasa, dastur jim ishlamaydi, aniq `KeyError` bilan to'xtaydi.
3. **Yagona rejim boshqaruvi (`INSTAGRAM_MODE`):**
   - Soxta rejim faqat bitta sozlama bilan (`INSTAGRAM_MODE=real` yoki `mock`) boshqariladi, default qiymat: `real`.
   - `docker-compose.yml` da `web`, `worker`, `beat` xizmatlarida `INSTAGRAM_MODE=${INSTAGRAM_MODE:-real}` o'rnatildi.
   - `tracker/instagram_client.py` dagi `get_instagram_client()` faqat `INSTAGRAM_MODE='mock'` bo'lgandagina soxta klientni qaytaradi. Real rejimda soxta klient hech qachon ishlatilmaydi.
4. **`check_instagram` boshqaruv buyrug'i:**
   - `python manage.py check_instagram` buyrug'i yaratildi.
   - `INSTAGRAM_ACCESS_TOKEN` yordamida `GET https://graph.instagram.com/me?fields=user_id,username,account_type` so'rovini yuboradi.
   - Faqat `username` va `account_type` ni xavfsiz tarzda chiqaradi. Token hech qachon log yoki konsolga chiqmaydi.
   - Xatolik yuz berganda Instagram qaytargan `code` va `message` ni (tokensiz) chiqaradi.
5. **Testlar va izolyatsiya:**
   - Tashqi tarmoqqa chiqib timeout bergan testlar aniqlandi va `requests.get` to'liq mock qilindi.
   - `check_instagram` buyrug'i uchun qamrovli testlar yozildi.
   - Barcha 134 ta test `docker compose exec web python manage.py test` orqali to'liq va muvaffaqiyatli o'tdi.

## [9] Token Shifrlash va Xavfsizlik Tozalash
**Sana:** 2026-10-21
**Holat:** Bajarildi

### Bajarilgan ishlar:
1. **Instagram Tokenlarini Bazada Shifrlash (`cryptography.fernet`):**
   - `tracker/crypto.py` moduli yaratildi. `TOKEN_ENCRYPTION_KEY` muhit o'zgaruvchisi orqali Fernet kaliti deterministik hosil qilinadi/moslashtiriladi.
   - `InstagramUser` modelida `EncryptedTextField` joriy qilindi. Ma'lumotlar bazaga yozilayotganda (`get_prep_value`) avtomatik shifrlanadi, o'qilayotganda (`from_db_value`) esa shaffof tarzda dekodlanadi.
2. **Qaytariladigan (Reverse) Data Migratsiya:**
   - `tracker/migrations/0011_alter_instagramuser_access_token_and_encrypt_existing.py` migratsiyasi yaratildi.
   - Bazadagi mavjud tokenlar ma'lumot yo'qotilmasdan shifrlab chiqildi.
   - Migratsiya to'liq qaytariladigan (`reverse_code=decrypt_existing_tokens`) qilib yozildi va `migrate tracker 0010` hamda `migrate tracker` orqali to'liq sinovdan o'tkazildi.
3. **Sozlamalar va Namunaviy Qiymatlarni Tozalash (`config/settings.py`):**
   - Namunaviy (`django-insecure...`, `1234`) default qiymatlar olib tashlandi.
   - Majburiy parametrlar faqat 5 ta belgilandi: `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `TOKEN_ENCRYPTION_KEY`, `SECRET_KEY`, `DB_PASSWORD`.
   - Qisqa bir qatorda tekshiruv for-sikli orqali mavjud bo'lmaganida aniq `KeyError` berilishi ta'minlandi.
   - `INSTAGRAM_ACCESS_TOKEN` majburiy bo'lmagan holatga keltirildi (`os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')`, faqat `check_instagram` buyrug'ida ixtiyoriy ishlatiladi).
4. **Tokenlar API va Loglardan Himoyalandi:**
   - Tokenlar hech bir serializer yoki API javoblarida qaytarilmasligi tasdiqlandi.
   - `InstagramUserAdmin` dan `access_token` maydoni chiqarib tashlandi (`exclude`).
   - Loglar va istisnolar uchun `mask_sensitive_data` ga yangi token formatlari (`IGAA`, Fernet `gAAAAA`, dry-run) qo'shildi.
5. **Testlar va Validatsiya:**
   - Barcha yangi xususiyatlar uchun `TokenEncryptionAndSecurityTestCase` yozildi.
   - Barcha 143 ta test `docker compose exec web python manage.py test` orqali muvaffaqiyatli o'tdi.

