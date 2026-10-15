# Insta Checker — API va Admin Web-Panel

Instagram Reels avtomatik joylash, ko'rishlar (views) statistikasini kuzatish va sovrinlarni avtomatlashtirish tizimi.

## Arxitektura

- **Backend**: Django 6 + Django REST Framework + Celery + Redis + PostgreSQL
- **Frontend**: React (TypeScript) + Vite + Tailwind CSS + Axios + React Router
- **Infratuzilma**: Docker + Docker Compose + Nginx (Reverse Proxy & Static)

---

## 🚀 Ishga tushirish (Docker)

1. **Muhit o'zgaruvchilari**:
   `.env.example` dan nusxa olib `.env` faylini to'ldiring:
   ```bash
   cp .env.example .env
   ```
   Kerakli parametrlar:
   - `DB_NAME`, `DB_USER`, `DB_PASSWORD`
   - `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_REDIRECT_URI`
   - `SITE_URL` (ngrok yoki domen manzili)

2. **Frontendni yig'ish (Build)**:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. **Docker konteynerlarni ishga tushirish**:
   ```bash
   docker compose up -d --build
   ```
   Konteynerlar:
   - `db` (PostgreSQL 15, healthcheck bilan)
   - `redis` (Ichki tarmoqda, portlari tashqariga ochilmagan)
   - `web` (Django Gunicorn, avtomatik migrate va collectstatic bilan)
   - `worker` (Celery worker)
   - `beat` (Celery beat — bitta nusxada)
   - `nginx` (Port 80/8080: Frontend SPA, Media va Backend API reverse proxy)

4. **Superuser yaratish**:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

5. **Panelga kirish**:
   Brauzerda `http://localhost:8080` (yoki sozlangan port) manziliga kiring va admin login/parolini kiriting.

---

## 🔒 Xavfsizlik va Auth

- **JWT Auth**: `/api/token/` va `/api/token/refresh/` orqali ishlaydi.
- **Login Throttling**: Faqat login endpointiga daqiqasiga 5 ta so'rov bilan cheklangan (`5/minute`), Redis orqali taqsimlangan.
- **Maxfiy tokenlar**: `InstagramUser.access_token` API serializer orqali hech qachon tashqariga chiqarilmaydi va yozilmaydi (`has_token: bool` ko'rinishida taqdim etiladi).
- **Fayl xavfsizligi**: Video yuklash faqat `.mp4` format va maksimal 100MB bilan cheklangan (Nginx va DRF darajasida).

---

## 🧪 Testlarni ishga tushirish

```bash
docker compose exec web python manage.py test
```
yoki lokal virtual muhitda:
```bash
python manage.py test
```
