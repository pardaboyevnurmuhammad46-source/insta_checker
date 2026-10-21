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
