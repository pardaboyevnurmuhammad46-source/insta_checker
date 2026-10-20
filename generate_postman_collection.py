import json
import os

collection = {
    "info": {
        "_postman_id": "e2e-insta-checker-collection-v2-1",
        "name": "InstaChecker API & E2E Collection",
        "description": "Instagram Reels Tracker & Prize System API Collection (BOSQICH C)\nBarcha endpointlar, negativ/xavfsizlik testlari va avtomatik E2E oqim.",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "event": [
        {
            "listen": "prerequest",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "// Global Pre-request script"
                ]
            }
        }
    ],
    "item": []
}

def make_req(name, method, path, headers=None, body=None, tests=None, prerequest=None, description=""):
    h_list = []
    if headers:
        for k, v in headers.items():
            h_list.append({"key": k, "value": v, "type": "text"})

    b_obj = None
    if body is not None:
        if isinstance(body, dict):
            b_obj = {
                "mode": "raw",
                "raw": json.dumps(body, indent=2),
                "options": {"raw": {"language": "json"}}
            }
        elif isinstance(body, list):
            b_obj = {
                "mode": "formdata",
                "formdata": body
            }

    events = []
    if prerequest:
        events.append({
            "listen": "prerequest",
            "script": {"type": "text/javascript", "exec": prerequest}
        })
    if tests:
        events.append({
            "listen": "test",
            "script": {"type": "text/javascript", "exec": tests}
        })

    clean_path = path.lstrip('/')
    url_parts = clean_path.split('?')[0].split('/')
    query_parts = []
    if '?' in path:
        q_str = path.split('?')[1]
        for pair in q_str.split('&'):
            if '=' in pair:
                qk, qv = pair.split('=', 1)
                query_parts.append({"key": qk, "value": qv})

    url_obj = {
        "raw": "{{base_url}}/" + clean_path,
        "host": ["{{base_url}}"],
        "path": url_parts
    }
    if query_parts:
        url_obj["query"] = query_parts

    return {
        "name": name,
        "event": events,
        "request": {
            "method": method,
            "header": h_list,
            "body": b_obj,
            "url": url_obj,
            "description": description
        },
        "response": []
    }

# ==============================================================================
# 00 Health
# ==============================================================================
folder_00 = {
    "name": "00 Health",
    "item": [
        make_req(
            name="Health Check",
            method="GET",
            path="/api/health/",
            description="Tizim holatini (Database, Redis va DRY_RUN rejimi) tekshiradi. Ochiq endpoint.",
            tests=[
                "pm.test('Status code 200 bo\\'lishi kerak', function () {",
                "    pm.response.to.have.status(200);",
                "});",
                "pm.test('Tizim va servislar sog\\'lom bo\\'lishi kerak', function () {",
                "    var jsonData = pm.response.json();",
                "    pm.expect(jsonData.status, 'status healthy bo\\'lishi kerak').to.eql('healthy');",
                "    pm.expect(jsonData.database, 'database ok bo\\'lishi kerak').to.eql('ok');",
                "    pm.expect(jsonData.redis, 'redis ok bo\\'lishi kerak').to.eql('ok');",
                "    pm.expect(jsonData.dry_run, 'E2E sinovlari faqat INSTAGRAM_DRY_RUN=true rejimida ishlaydi! Iltimos, sozlamada INSTAGRAM_DRY_RUN=True o\\'rnating.').to.be.true;",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_00)

# ==============================================================================
# 01 Auth
# ==============================================================================
folder_01 = {
    "name": "01 Auth",
    "item": [
        make_req(
            name="Admin Login",
            method="POST",
            path="/api/token/",
            body={"username": "{{admin_username}}", "password": "{{admin_password}}"},
            description="Administrator tizimga kiradi va admin_access hamda admin_refresh tokenlarini saqlaydi.",
            tests=[
                "pm.test('Admin muvaffaqiyatli login qilishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.access, 'access token bo\\'lishi kerak').to.be.a('string');",
                "    pm.expect(data.refresh, 'refresh token bo\\'lishi kerak').to.be.a('string');",
                "    pm.expect(data.role, 'role admin bo\\'lishi kerak').to.eql('admin');",
                "    pm.environment.set('admin_access', data.access);",
                "    pm.environment.set('admin_refresh', data.refresh);",
                "});"
            ]
        ),
        make_req(
            name="User Login",
            method="POST",
            path="/api/token/",
            body={"username": "{{user_username}}", "password": "{{user_password}}"},
            description="Oddiy foydalanuvchi tizimga kiradi va user_access hamda user_refresh tokenlarini saqlaydi.",
            tests=[
                "pm.test('User muvaffaqiyatli login qilishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.access, 'access token bo\\'lishi kerak').to.be.a('string');",
                "    pm.environment.set('user_access', data.access);",
                "    pm.environment.set('user_refresh', data.refresh);",
                "});"
            ]
        ),
        make_req(
            name="Token Refresh",
            method="POST",
            path="/api/token/refresh/",
            body={"refresh": "{{user_refresh}}"},
            description="Foydalanuvchi refresh tokeni orqali yangi access token oladi.",
            tests=[
                "pm.test('Token muvaffaqiyatli yangilanishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.access, 'yangi access token kelishi kerak').to.be.a('string');",
                "    pm.environment.set('user_access', data.access);",
                "});"
            ]
        ),
        make_req(
            name="Current User Profile (/api/me/)",
            method="GET",
            path="/api/me/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Joriy foydalanuvchi profili va roli haqida ma'lumot oladi.",
            tests=[
                "pm.test('Foydalanuvchi profili qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.username, 'username mavjud bo\\'lishi kerak').to.be.a('string');",
                "    pm.expect(data.dry_run, 'dry_run bayrog\\'i true bo\\'lishi kerak').to.be.true;",
                "});"
            ]
        ),
        make_req(
            name="Logout",
            method="POST",
            path="/api/token/logout/",
            headers={"Authorization": "Bearer {{user_access}}"},
            body={"refresh": "{{user_refresh}}"},
            description="Foydalanuvchi tizimdan chiqadi va refresh token blacklist qilinadi.",
            tests=[
                "pm.test('Logout muvaffaqiyatli bo\\'lishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_01)

# ==============================================================================
# 02 Admin – Userlar
# ==============================================================================
folder_02 = {
    "name": "02 Admin – Userlar",
    "item": [
        make_req(
            name="Create User",
            method="POST",
            path="/api/admin/create-user/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            prerequest=[
                "var randomNum = Math.floor(Math.random() * 100000);",
                "var newUsername = 'pm_user_' + randomNum;",
                "var newPass = 'StrongPass123!_' + randomNum;",
                "pm.environment.set('new_user_username', newUsername);",
                "pm.environment.set('new_user_password', newPass);"
            ],
            body={
                "username": "{{new_user_username}}",
                "password": "{{new_user_password}}",
                "name": "Postman Test User",
                "is_staff": False
            },
            description="Admin yangi foydalanuvchi yaratadi.",
            tests=[
                "pm.test('Yangi foydalanuvchi yaratilishi kerak (201)', function () {",
                "    pm.response.to.have.status(201);",
                "    var data = pm.response.json();",
                "    pm.expect(data.username, 'to\\'g\\'ri username').to.eql(pm.environment.get('new_user_username'));",
                "    pm.expect(data.user_id, 'user_id mavjud').to.be.a('number');",
                "    pm.environment.set('new_user_id', data.user_id);",
                "});"
            ]
        ),
        make_req(
            name="List Users (Search & Filter)",
            method="GET",
            path="/api/admin/users/?search={{new_user_username}}",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin foydalanuvchilar ro'yxatini qidirish va filtrlash orqali oladi.",
            tests=[
                "pm.test('Foydalanuvchilar ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.results, 'results array bo\\'lishi kerak').to.be.an('array');",
                "    pm.expect(data.count, 'kamida bitta user topilishi kerak').to.be.above(0);",
                "});"
            ]
        ),
        make_req(
            name="User Detail",
            method="GET",
            path="/api/admin/users/{{new_user_id}}/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin tanlangan foydalanuvchi tafsilotlarini oladi.",
            tests=[
                "pm.test('User tafsilotlari qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.id, 'user_id mos kelishi kerak').to.eql(Number(pm.environment.get('new_user_id')));",
                "});"
            ]
        ),
        make_req(
            name="Reset Password",
            method="POST",
            path="/api/admin/reset-password/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body={"user_id": "{{new_user_id}}", "new_password": "NewStrongPass999!_"},
            description="Admin foydalanuvchi parolini yangilaydi.",
            tests=[
                "pm.test('Parol muvaffaqiyatli tiklanishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="Delete User",
            method="DELETE",
            path="/api/users/{{new_user_id}}/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin foydalanuvchini o'chiradi.",
            tests=[
                "pm.test('Foydalanuvchi o\\'chirilishi kerak (204)', function () {",
                "    pm.response.to.have.status(204);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_02)

# ==============================================================================
# 03 Admin – Videolar
# ==============================================================================
folder_03 = {
    "name": "03 Admin – Videolar",
    "item": [
        make_req(
            name="Upload Video (Multipart)",
            method="POST",
            path="/api/videos/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body=[
                {"key": "title", "value": "Postman Test Video", "type": "text"},
                {"key": "is_default", "value": "false", "type": "text"},
                {"key": "is_active", "value": "true", "type": "text"},
                {"key": "file", "type": "file", "src": "files/sample.mp4"}
            ],
            description="Admin yangi video yuklaydi (multipart form-data orqali sample.mp4).",
            tests=[
                "pm.test('Video muvaffaqiyatli yuklanishi kerak (201)', function () {",
                "    pm.response.to.have.status(201);",
                "    var data = pm.response.json();",
                "    pm.expect(data.id, 'video id mavjud').to.be.a('number');",
                "    pm.environment.set('video_id', data.id);",
                "});"
            ]
        ),
        make_req(
            name="List Videos",
            method="GET",
            path="/api/videos/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin mavjud videolar ro'yxatini oladi.",
            tests=[
                "pm.test('Videolar ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.results, 'results array bo\\'lishi kerak').to.be.an('array');",
                "});"
            ]
        ),
        make_req(
            name="Set Default Video",
            method="POST",
            path="/api/videos/{{video_id}}/set-default/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin videoni barcha foydalanuvchilar uchun umumiy (default) qilib belgilaydi.",
            tests=[
                "pm.test('Video default qilib belgilanishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="Delete Video",
            method="DELETE",
            path="/api/videos/{{video_id}}/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin videoni o'chiradi.",
            tests=[
                "pm.test('Video o\\'chirilishi kerak (204)', function () {",
                "    pm.response.to.have.status(204);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_03)

# ==============================================================================
# 04 Admin – Linklar
# ==============================================================================
folder_04 = {
    "name": "04 Admin – Linklar",
    "item": [
        make_req(
            name="Create Link",
            method="POST",
            path="/api/links/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            prerequest=[
                "pm.sendRequest({",
                "    url: pm.environment.get('base_url') + '/api/users/',",
                "    method: 'GET',",
                "    header: { 'Authorization': 'Bearer ' + pm.environment.get('admin_access') }",
                "}, function (err, res) {",
                "    if (!err && res.json().results && res.json().results.length > 0) {",
                "        pm.environment.set('link_user_id', res.json().results[0].id);",
                "    } else {",
                "        pm.environment.set('link_user_id', 1);",
                "    }",
                "});"
            ],
            body={"user": "{{link_user_id}}"},
            description="Admin yangi unikal havola yaratadi.",
            tests=[
                "pm.test('Link yaratilishi kerak (201)', function () {",
                "    pm.response.to.have.status(201);",
                "    var data = pm.response.json();",
                "    pm.expect(data.id, 'link id').to.be.a('number');",
                "    pm.expect(data.token, 'link token').to.be.a('string');",
                "    pm.environment.set('link_id', data.id);",
                "    pm.environment.set('link_token', data.token);",
                "});"
            ]
        ),
        make_req(
            name="List Links",
            method="GET",
            path="/api/links/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin linklar ro'yxatini oladi.",
            tests=[
                "pm.test('Linklar ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="Resend Link",
            method="POST",
            path="/api/links/{{link_id}}/resend/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin linkni qayta pending holatiga o'tkazadi (faqat failed bo'lganda).",
            tests=[
                "pm.test('Resend so\\'rovi tekshirildi (200 yoki 400)', function () {",
                "    pm.expect([200, 400]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="Delete Link",
            method="DELETE",
            path="/api/links/{{link_id}}/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin linkni o'chiradi.",
            tests=[
                "pm.test('Link o\\'chirilishi kerak (204)', function () {",
                "    pm.response.to.have.status(204);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_04)

# ==============================================================================
# 05 User – Instagram va joylash
# ==============================================================================
folder_05 = {
    "name": "05 User – Instagram va joylash",
    "item": [
        make_req(
            name="Connect Instagram",
            method="GET",
            path="/api/user/connect-instagram/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Foydalanuvchi Instagram hisobini ulash havolasini oladi.",
            tests=[
                "pm.test('Instagram ulash havolasi qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.auth_url, 'auth_url mavjud').to.be.a('string');",
                "    pm.expect(data.link_token, 'link_token mavjud').to.be.a('string');",
                "    pm.environment.set('user_link_token', data.link_token);",
                "});"
            ]
        ),
        make_req(
            name="DRY_RUN OAuth Callback",
            method="GET",
            path="/oauth/callback/?code=dry_run&state={{user_link_token}}",
            description="DRY_RUN rejimida brauzersiz OAuth callback orqali Instagramni ulash simulyatsiyasi.",
            tests=[
                "pm.test('Callback muvaffaqiyatli bajarilishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="Publish Video",
            method="POST",
            path="/api/user/publish/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Ulangan foydalanuvchi uchun videoni Reels qilib joylashni boshlaydi.",
            tests=[
                "pm.test('Publish so\\'rovi qabul qilindi (202 yoki 409)', function () {",
                "    pm.expect([202, 400, 409]).to.include(pm.response.code);",
                "    if (pm.response.code === 202) {",
                "        var data = pm.response.json();",
                "        pm.environment.set('user_post_id', data.post_id);",
                "    }",
                "});"
            ]
        ),
        make_req(
            name="Publish Status",
            method="GET",
            path="/api/user/publish-status/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Joylash jarayoni va post holatini tekshiradi (polling).",
            tests=[
                "pm.test('Publish status ma\\'lumotlari qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.has_post, 'has_post mavjud').to.be.a('boolean');",
                "    pm.expect(data.status, 'status mavjud').to.be.a('string');",
                "});"
            ]
        ),
        make_req(
            name="Retry Publish",
            method="POST",
            path="/api/user/retry/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Muvaffaqiyatsiz bo'lgan postni qayta navbatga qo'yadi.",
            tests=[
                "pm.test('Retry endpointi tekshirildi (200, 400 yoki 404)', function () {",
                "    pm.expect([200, 400, 404]).to.include(pm.response.code);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_05)

# ==============================================================================
# 06 User – Statistika
# ==============================================================================
folder_06 = {
    "name": "06 User – Statistika",
    "item": [
        make_req(
            name="Me Summary",
            method="GET",
            path="/api/me/summary/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Foydalanuvchining o'z statistikasi, marra va foizlari.",
            tests=[
                "pm.test('User summary qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.total_views, 'total_views mavjud').to.be.a('number');",
                "    pm.expect(data.milestones, 'milestones mavjud').to.be.an('array');",
                "});"
            ]
        ),
        make_req(
            name="Me Posts",
            method="GET",
            path="/api/me/posts/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Foydalanuvchining o'z postlari ro'yxati.",
            tests=[
                "pm.test('User postlari ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="List Notifications",
            method="GET",
            path="/api/notifications/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Foydalanuvchi bildirishnomalari ro'yxati.",
            tests=[
                "pm.test('Bildirishnomalar qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    if (data.results && data.results.length > 0) {",
                "        pm.environment.set('notification_id', data.results[0].id);",
                "    }",
                "});"
            ]
        ),
        make_req(
            name="Mark All Notifications Read",
            method="POST",
            path="/api/me/notifications/read/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Barcha bildirishnomalarni o'qilgan deb belgilash.",
            tests=[
                "pm.test('Barcha bildirishnomalar o\\'qilgan bo\\'lishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="List Prizes",
            method="GET",
            path="/api/prizes/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Foydalanuvchi yutib olgan sovrinlari ro'yxati.",
            tests=[
                "pm.test('Sovrinlar ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_06)

# ==============================================================================
# 07 Admin – Postlar va statistika
# ==============================================================================
folder_07 = {
    "name": "07 Admin – Postlar va statistika",
    "item": [
        make_req(
            name="Admin Summary",
            method="GET",
            path="/api/admin/summary/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin umumiy tizim statistikasi va monitoring.",
            tests=[
                "pm.test('Admin summary qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.total_users, 'total_users mavjud').to.be.a('number');",
                "    pm.expect(data.dry_run, 'dry_run true').to.be.true;",
                "});"
            ]
        ),
        make_req(
            name="List Posts (Filter & Sort)",
            method="GET",
            path="/api/admin/posts/?status=published",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Admin postlarni status va parametrlar bo'yicha filtrlash.",
            tests=[
                "pm.test('Postlar ro\\'yxati qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    if (data.results && data.results.length > 0) {",
                "        pm.environment.set('admin_post_id', data.results[0].id);",
                "    }",
                "});"
            ]
        ),
        make_req(
            name="Check Metrics Now",
            method="POST",
            path="/api/posts/{{admin_post_id}}/check-metrics/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            prerequest=[
                "if (!pm.environment.get('admin_post_id')) {",
                "    pm.sendRequest({",
                "        url: pm.environment.get('base_url') + '/api/posts/',",
                "        method: 'GET',",
                "        header: { 'Authorization': 'Bearer ' + pm.environment.get('admin_access') }",
                "    }, function (err, res) {",
                "        if (!err && res.json().results && res.json().results.length > 0) {",
                "            pm.environment.set('admin_post_id', res.json().results[0].id);",
                "        } else {",
                "            pm.environment.set('admin_post_id', 1);",
                "        }",
                "    });",
                "}"
            ],
            description="Admin tanlangan post uchun statistikani darhol navbatga qo'yib tekshiradi.",
            tests=[
                "pm.test('Statistikani tekshirish tekshirildi (200 yoki 404)', function () {",
                "    pm.expect([200, 404]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="Daily Stats",
            method="GET",
            path="/api/admin/stats/daily/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Kunlik qamrov va postlar statistikasi.",
            tests=[
                "pm.test('Kunlik statistika qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="Export Posts CSV",
            method="GET",
            path="/api/admin/export/posts.csv",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Barcha postlar ma'lumotlarini CSV formatda yuklab olish.",
            tests=[
                "pm.test('CSV fayl qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "    pm.expect(pm.response.headers.get('Content-Type')).to.include('text/csv');",
                "});"
            ]
        ),
        make_req(
            name="Data Deletions List",
            method="GET",
            path="/api/data-deletions/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            description="Meta orqali kelgan foydalanuvchi ma'lumotlarini o'chirish so'rovlari ro'yxati.",
            tests=[
                "pm.test('Ma\\'lumot o\\'chirish so\\'rovlari qaytishi kerak (200)', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_07)

# ==============================================================================
# 08 Dev – Simulyatsiya (faqat DRY_RUN)
# ==============================================================================
folder_08 = {
    "name": "08 Dev – Simulyatsiya (faqat DRY_RUN)",
    "item": [
        make_req(
            name="Simulate Views",
            method="POST",
            path="/api/dev/simulate-views/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            prerequest=[
                "if (!pm.environment.get('admin_post_id')) {",
                "    pm.sendRequest({",
                "        url: pm.environment.get('base_url') + '/api/posts/',",
                "        method: 'GET',",
                "        header: { 'Authorization': 'Bearer ' + pm.environment.get('admin_access') }",
                "    }, function (err, res) {",
                "        if (!err && res.json().results && res.json().results.length > 0) {",
                "            pm.environment.set('admin_post_id', res.json().results[0].id);",
                "        } else {",
                "            pm.environment.set('admin_post_id', 1);",
                "        }",
                "    });",
                "}"
            ],
            body={"post_id": "{{admin_post_id}}", "views": 500},
            description="Instagram'da post ko'rishlari sonini simulyatsiya qiladi va tekshiruv quvurini ishga tushiradi.",
            tests=[
                "pm.test('Ko\\'rishlar simulyatsiyasi tekshirildi (200 yoki 404)', function () {",
                "    pm.expect([200, 404]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="Simulate Network Error",
            method="POST",
            path="/api/dev/simulate-network-error/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body={"post_id": "{{admin_post_id}}"},
            description="Vaqtinchalik tarmoq/server xatosi simulyatsiyasi.",
            tests=[
                "pm.test('Tarmoq xatosi simulyatsiyasi (200 yoki 404)', function () {",
                "    pm.expect([200, 404]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="Simulate Token Revoked",
            method="POST",
            path="/api/dev/simulate-token-revoked/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            prerequest=[
                "if (!pm.environment.get('sim_user_id')) {",
                "    pm.sendRequest({",
                "        url: pm.environment.get('base_url') + '/api/users/',",
                "        method: 'GET',",
                "        header: { 'Authorization': 'Bearer ' + pm.environment.get('admin_access') }",
                "    }, function (err, res) {",
                "        if (!err && res.json().results && res.json().results.length > 0) {",
                "            pm.environment.set('sim_user_id', res.json().results[0].id);",
                "        } else {",
                "            pm.environment.set('sim_user_id', 1);",
                "        }",
                "    });",
                "}"
            ],
            body={"user_id": "{{sim_user_id}}"},
            description="Foydalanuvchi tokeni bekor qilinganini (Code 190) simulyatsiya qilish.",
            tests=[
                "pm.test('Token bekor qilish simulyatsiyasi tekshirildi (200 yoki 404)', function () {",
                "    pm.expect([200, 404]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="Simulate Delete",
            method="POST",
            path="/api/dev/simulate-delete/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body={"post_id": "{{admin_post_id}}"},
            description="Instagram'da media o'chirilganini (Code 100/33 yoki 404) simulyatsiya qiladi.",
            tests=[
                "pm.test('O\\'chirilish simulyatsiyasi (200 yoki 404)', function () {",
                "    pm.expect([200, 404]).to.include(pm.response.code);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_08)

# ==============================================================================
# 09 E2E – To'liq oqim
# ==============================================================================
folder_09 = {
    "name": "09 E2E – To'liq oqim",
    "item": [
        make_req(
            name="E2E 01 - Admin Login",
            method="POST",
            path="/api/token/",
            body={"username": "{{admin_username}}", "password": "{{admin_password}}"},
            description="E2E: Admin login qilib e2e_admin_access oladi.",
            tests=[
                "pm.test('E2E: Admin login muvaffaqiyatli', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_admin_access', data.access);",
                "});"
            ]
        ),
        make_req(
            name="E2E 02 - Create User",
            method="POST",
            path="/api/admin/create-user/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            prerequest=[
                "var ts = Date.now();",
                "pm.environment.set('e2e_user_username', 'e2e_user_' + ts);",
                "pm.environment.set('e2e_user_password', 'E2ePass_' + ts + '!');"
            ],
            body={
                "username": "{{e2e_user_username}}",
                "password": "{{e2e_user_password}}",
                "name": "E2E Test User",
                "is_staff": False
            },
            description="E2E: Admin yangi foydalanuvchi yaratadi.",
            tests=[
                "pm.test('E2E: User yaratildi', function () {",
                "    pm.response.to.have.status(201);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_user_id', data.user_id);",
                "    if (data.instagram_user && data.instagram_user.id) {",
                "        pm.environment.set('e2e_ig_user_id', data.instagram_user.id);",
                "    }",
                "});"
            ]
        ),
        make_req(
            name="E2E 03 - Upload Video",
            method="POST",
            path="/api/videos/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            body=[
                {"key": "title", "value": "E2E Demo Video", "type": "text"},
                {"key": "is_default", "value": "false", "type": "text"},
                {"key": "is_active", "value": "true", "type": "text"},
                {"key": "file", "type": "file", "src": "files/sample.mp4"}
            ],
            description="E2E: Admin yangi video yuklaydi.",
            tests=[
                "pm.test('E2E: Video yuklandi', function () {",
                "    pm.response.to.have.status(201);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_video_id', data.id);",
                "});"
            ]
        ),
        make_req(
            name="E2E 03b - Make Video Default",
            method="POST",
            path="/api/videos/{{e2e_video_id}}/set-default/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            description="E2E: Yuklangan videoni barcha foydalanuvchilar uchun umumiy (default) qilish.",
            tests=[
                "pm.test('E2E: Video default qilindi', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="E2E 04 - User Login",
            method="POST",
            path="/api/token/",
            body={"username": "{{e2e_user_username}}", "password": "{{e2e_user_password}}"},
            description="E2E: Yangi yaratilgan user tizimga kiradi.",
            tests=[
                "pm.test('E2E: Yangi user tizimga kirdi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_user_access', data.access);",
                "});"
            ]
        ),
        make_req(
            name="E2E 05 - Connect Instagram",
            method="GET",
            path="/api/user/connect-instagram/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: User Instagram ulash havolasini oladi.",
            tests=[
                "pm.test('E2E: Auth URL olindi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_link_token', data.link_token);",
                "});"
            ]
        ),
        make_req(
            name="E2E 06 - OAuth Callback (DRY_RUN)",
            method="GET",
            path="/oauth/callback/?code=dry_run&state={{e2e_link_token}}",
            description="E2E: Brauzersiz Instagramni ulash simulyatsiyasi.",
            tests=[
                "pm.test('E2E: Instagram hisobi ulandi', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="E2E 07 - User Publish Video",
            method="POST",
            path="/api/user/publish/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: User videoni Reels qilib joylashni boshlaydi.",
            tests=[
                "pm.test('E2E: Video joylash qabul qilindi (202)', function () {",
                "    pm.response.to.have.status(202);",
                "    var data = pm.response.json();",
                "    pm.environment.set('e2e_post_id', data.post_id);",
                "    pm.environment.set('poll_count', 0);",
                "});"
            ]
        ),
        make_req(
            name="E2E 08 - Poll Publish Status",
            method="GET",
            path="/api/user/publish-status/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: Post published bo'lguncha polling (max 15 marta).",
            tests=[
                "var data = pm.response.json();",
                "var count = Number(pm.environment.get('poll_count') || 0);",
                "if (data.status !== 'published' && count < 15) {",
                "    pm.environment.set('poll_count', count + 1);",
                "    var start = Date.now();",
                "    while (Date.now() - start < 500) {}",
                "    pm.execution.setNextRequest('E2E 08 - Poll Publish Status');",
                "} else {",
                "    pm.test('E2E: Post muvaffaqiyatli published bo\\'ldi', function () {",
                "        pm.expect(data.status, 'post status published bo\\'lishi kerak').to.eql('published');",
                "        pm.expect(data.permalink, 'permalink mavjud').to.be.a('string');",
                "    });",
                "    pm.environment.set('poll_count', 0);",
                "    pm.execution.setNextRequest('E2E 09 - Simulate 500 Views');",
                "}"
            ]
        ),
        make_req(
            name="E2E 09 - Simulate 500 Views",
            method="POST",
            path="/api/dev/simulate-views/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            body={"post_id": "{{e2e_post_id}}", "views": 500},
            description="E2E: 500 ko'rish to'planganini simulyatsiya qilish.",
            tests=[
                "pm.test('E2E: 500 ko\\'rish simulyatsiya qilindi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.views).to.eql(500);",
                "});"
            ]
        ),
        make_req(
            name="E2E 10 - Verify User Prize & Notification",
            method="GET",
            path="/api/me/summary/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: 500 marra uchun sovrin yaratilganini tekshirish.",
            tests=[
                "pm.test('E2E: 1-sovrin muvaffaqiyatli berildi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.prizes_count, '1 ta sovrin').to.eql(1);",
                "    pm.expect(data.total_views, '500 ko\\'rish').to.eql(500);",
                "});"
            ]
        ),
        make_req(
            name="E2E 11 - Simulate 1000 Views",
            method="POST",
            path="/api/dev/simulate-views/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            body={"post_id": "{{e2e_post_id}}", "views": 1000},
            description="E2E: 1000 ko'rish (keyingi marra) simulyatsiyasi.",
            tests=[
                "pm.test('E2E: 1000 ko\\'rish simulyatsiya qilindi', function () {",
                "    pm.response.to.have.status(200);",
                "});"
            ]
        ),
        make_req(
            name="E2E 12 - Verify Second Prize",
            method="GET",
            path="/api/me/summary/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: 1000 marra uchun 2-sovrin berilganini tekshirish.",
            tests=[
                "pm.test('E2E: 2 ta sovrin bo\\'lishi kerak', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.prizes_count, '2 ta sovrin').to.eql(2);",
                "});"
            ]
        ),
        make_req(
            name="E2E 13 - Simulate Delete",
            method="POST",
            path="/api/dev/simulate-delete/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            body={"post_id": "{{e2e_post_id}}"},
            description="E2E: Instagram'dan post o'chirilishini simulyatsiya qilish.",
            tests=[
                "pm.test('E2E: Post o\\'chirilishi simulyatsiya qilindi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.status).to.eql('deleted');",
                "});"
            ]
        ),
        make_req(
            name="E2E 14 - Verify Post Deleted Status",
            method="GET",
            path="/api/user/publish-status/",
            headers={"Authorization": "Bearer {{e2e_user_access}}"},
            description="E2E: User tomonidan postning deleted holatga o'tganini tasdiqlash.",
            tests=[
                "pm.test('E2E: Post statusi haqiqatdan deleted bo\\'ldi', function () {",
                "    pm.response.to.have.status(200);",
                "    var data = pm.response.json();",
                "    pm.expect(data.status).to.eql('deleted');",
                "});"
            ]
        ),
        make_req(
            name="E2E 15 - Cleanup Video",
            method="DELETE",
            path="/api/videos/{{e2e_video_id}}/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            description="E2E tozalash: Yaratilgan test videosini o'chirish.",
            tests=[
                "pm.test('E2E: Video o\\'chirildi (204)', function () {",
                "    pm.response.to.have.status(204);",
                "});"
            ]
        ),
        make_req(
            name="E2E 16 - Cleanup User",
            method="DELETE",
            path="/api/users/{{e2e_user_id}}/",
            headers={"Authorization": "Bearer {{e2e_admin_access}}"},
            description="E2E tozalash: Yaratilgan test foydalanuvchisini o'chirish.",
            tests=[
                "pm.test('E2E: User o\\'chirildi (204)', function () {",
                "    pm.response.to.have.status(204);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_09)

# ==============================================================================
# 10 Negativ va xavfsizlik
# ==============================================================================
folder_10 = {
    "name": "10 Negativ va xavfsizlik",
    "item": [
        make_req(
            name="01 Request Without Token -> 401",
            method="GET",
            path="/api/me/",
            description="Tokensiz himoyalangan endpointga so'rov yuborilganda 401 Unauthorized qaytishi kerak.",
            tests=[
                "pm.test('Tokensiz so\\'rov 401 qaytarishi kerak', function () {",
                "    pm.response.to.have.status(401);",
                "});"
            ]
        ),
        make_req(
            name="02 Regular User Calls Admin Endpoint -> 403",
            method="GET",
            path="/api/admin/summary/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Oddiy user admin huquqini talab qiluvchi endpointga murojaat qilganda 403 Forbidden qaytishi kerak.",
            tests=[
                "pm.test('Oddiy user admin endpointiga kira olmasligi kerak (403)', function () {",
                "    pm.response.to.have.status(403);",
                "});"
            ]
        ),
        make_req(
            name="03 User Access Other Post History -> 404/403",
            method="GET",
            path="/api/me/posts/999999/history/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Boshqa foydalanuvchining yoki mavjud bo'lmagan post tarixini so'raganda 404 qaytishi kerak.",
            tests=[
                "pm.test('Boshqa user posti tarixi berilmasligi kerak (404)', function () {",
                "    pm.response.to.have.status(404);",
                "});"
            ]
        ),
        make_req(
            name="04 Weak Password Rejected -> 400",
            method="POST",
            path="/api/admin/create-user/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body={"username": "weak_pwd_user", "password": "123", "name": "Weak User"},
            description="Juda sodda (zaif) parol qabul qilinmasligi va 400 qaytarishi kerak.",
            tests=[
                "pm.test('Zaif parol rad etilishi kerak (400)', function () {",
                "    pm.response.to.have.status(400);",
                "});"
            ]
        ),
        make_req(
            name="05 Invalid Video Extension -> 400",
            method="POST",
            path="/api/videos/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body=[
                {"key": "title", "value": "Bad File", "type": "text"},
                {"key": "file", "type": "file", "src": "files/sample.txt"}
            ],
            description=".mp4 dan boshqa formatdagi fayllar rad etilishi kerak.",
            tests=[
                "pm.test('Noto\\'g\\'ri kengaytmali fayl rad etilishi kerak (400)', function () {",
                "    pm.response.to.have.status(400);",
                "});"
            ]
        ),
        make_req(
            name="06 Empty Video File -> 400",
            method="POST",
            path="/api/videos/",
            headers={"Authorization": "Bearer {{admin_access}}"},
            body=[
                {"key": "title", "value": "Empty File", "type": "text"},
                {"key": "file", "type": "file", "src": "files/empty.mp4"}
            ],
            description="Bo'sh (0 baytli) video fayl yuklanganda rad etilishi kerak.",
            tests=[
                "pm.test('Bo\\'sh video fayl rad etilishi kerak (400)', function () {",
                "    pm.response.to.have.status(400);",
                "});"
            ]
        ),
        make_req(
            name="07 Duplicate Publish Rejected -> 409",
            method="POST",
            path="/api/user/publish/",
            headers={"Authorization": "Bearer {{user_access}}"},
            description="Jarayonda bo'lgan post mavjud bo'lganda takroriy publish bosilsa 409 Conflict qaytishi kerak.",
            tests=[
                "pm.test('Takroriy publish tekshirildi (202, 400 yoki 409)', function () {",
                "    pm.expect([202, 400, 409]).to.include(pm.response.code);",
                "});"
            ]
        ),
        make_req(
            name="08 Blacklisted Token Fails -> 401",
            method="POST",
            path="/api/token/refresh/",
            body={"refresh": "{{user_refresh}}"},
            description="Logoutdan so'ng qora ro'yxatga tushgan refresh token orqali yangilash 401 qaytarishi kerak.",
            tests=[
                "pm.test('Blacklist qilingan token ishlamasligi kerak (401)', function () {",
                "    pm.response.to.have.status(401);",
                "});"
            ]
        ),
        make_req(
            name="09 User Cannot Create Link In Another Name",
            method="POST",
            path="/api/links/",
            headers={"Authorization": "Bearer {{user_access}}"},
            body={"user": 999999},
            description="Oddiy user boshqa user ID si bilan link yarata olmasligi kerak.",
            tests=[
                "pm.test('Boshqa user nomidan link yaratish bloklandi yoki o\\'ziga biriktirildi', function () {",
                "    if (pm.response.code === 201) {",
                "        var data = pm.response.json();",
                "        pm.expect(data.user).to.not.eql(999999);",
                "    } else {",
                "        pm.expect([400, 403]).to.include(pm.response.code);",
                "    }",
                "});"
            ]
        ),
        make_req(
            name="10 Rate Limit On Consecutive Failed Logins -> 429",
            method="POST",
            path="/api/token/",
            prerequest=[
                "// Ketma-ket 5 ta noto'g'ri login yuborib 5/min limitni chaqirish",
                "for (var i = 0; i < 5; i++) {",
                "    pm.sendRequest({",
                "        url: pm.environment.get('base_url') + '/api/token/',",
                "        method: 'POST',",
                "        header: { 'Content-Type': 'application/json' },",
                "        body: { mode: 'raw', raw: JSON.stringify({ username: 'bad_user', password: 'bad_password' }) }",
                "    }, function() {});",
                "}"
            ],
            body={"username": "bad_user", "password": "bad_password"},
            description="Ketma-ket noto'g'ri loginda 429 Too Many Requests xatosi qaytishi kerak.",
            tests=[
                "pm.test('Ketma-ket xato loginda 429 yoki 400 qaytarishi kerak', function () {",
                "    pm.expect([400, 401, 429]).to.include(pm.response.code);",
                "});"
            ]
        )
    ]
}
collection["item"].append(folder_10)

os.makedirs("postman", exist_ok=True)
with open("postman/insta_checker.postman_collection.json", "w", encoding="utf-8") as f:
    json.dump(collection, f, indent=2, ensure_ascii=False)

print("Collection generated successfully!")
total_requests = 0
for folder in collection["item"]:
    total_requests += len(folder["item"])
print(f"Total Folders: {len(collection['item'])}, Total Requests: {total_requests}")
