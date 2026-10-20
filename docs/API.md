# Instagram Tracker API Inventarizatsiyasi

Ushbu hujjat tizimdagi barcha API endpointlarni o'zida jamlaydi.

| Modul | Endpoint | Metod | Kim chaqira oladi | Input (Kirish) | Output (Chiqish) |
| --- | --- | --- | --- | --- | --- |
| **Auth** | `/api/token/` | POST | Barcha | username, password | access, refresh |
| **Auth** | `/api/token/refresh/` | POST | Barcha | refresh | access, refresh |
| **Auth** | `/api/token/logout/` | POST | Auth user | refresh | message |
| **Auth** | `/api/me/` | GET | Auth user | - | User ma'lumotlari (role, ism) |
| **Auth** | `/api/me/` | PATCH | Auth user | first_name, email | User ma'lumotlari |
| **Auth** | `/api/change-password/` | POST | Auth user | old_password, new_password | message |
| **Admin User** | `/api/admin/users/` | GET | Admin | filtr, pagination | Userlar ro'yxati |
| **Admin User** | `/api/admin/create-user/` | POST | Admin | username, password, role | Yangi User |
| **Admin User** | `/api/admin/users/<id>/` | GET | Admin | - | To'liq tafsilotlar |
| **Admin User** | `/api/admin/users/<id>/` | PATCH | Admin | first_name, status, is_active | Yangilangan user |
| **Admin User** | `/api/admin/reset-password/` | POST | Admin | user_id, new_password | message |
| **Admin User** | `/api/admin/users/<id>/` | DELETE | Admin | - | 204 No Content (Soft delete) |
| **User IG** | `/api/user/connect-instagram/` | GET | Auth user | - | auth_url |
| **User IG** | `/api/user/disconnect-instagram/` | POST | Auth user | - | message |
| **User Post** | `/api/user/publish/` | POST | Auth user | link_id | status, message |
| **User Post** | `/api/user/publish-status/` | GET | Auth user | link_id | can_publish, progress, status |
| **User Post** | `/api/user/retry/` | POST | Auth user | post_id | status, message |
| **Videolar** | `/api/videos/` | GET | Auth user/Admin | filtr, pagination | Videolar ro'yxati |
| **Videolar** | `/api/videos/` | POST | Admin | title, file | Yangi Video |
| **Videolar** | `/api/videos/<id>/` | PATCH | Admin | title, is_active, owner | Yangilangan video |
| **Videolar** | `/api/videos/<id>/` | DELETE | Admin | - | 204 No Content |
| **Linklar** | `/api/links/` | GET | Auth/Admin | filtr, pagination | Linklar ro'yxati |
| **Linklar** | `/api/links/` | POST | Admin | user_id, video_id | Yangi Link |
| **Linklar** | `/api/links/<id>/` | GET | Auth/Admin | - | Link tafsiloti |
| **Linklar** | `/api/links/<id>/resend/` | POST | Admin | - | message |
| **Linklar** | `/api/links/<id>/` | DELETE | Admin | - | 204 No Content |
| **Postlar** | `/api/posts/` | GET | Auth/Admin | filtr, pagination | Postlar ro'yxati |
| **Postlar** | `/api/posts/<id>/` | GET | Auth/Admin | - | Post tafsiloti |
| **Postlar** | `/api/posts/<id>/check-metrics/`| POST | Auth/Admin | - | metrics |
| **Postlar** | `/api/posts/<id>/repost/` | POST | Admin | - | Yangi post/link |
| **Postlar** | `/api/me/posts/<id>/history/` | GET | Auth/Admin | - | Tarix ro'yxati |
| **Statistika** | `/api/me/summary/` | GET | Auth user | - | view/like/comment/milestones |
| **Statistika** | `/api/admin/summary/` | GET | Admin | - | total views, users, errors |
| **Statistika** | `/api/admin/stats/daily/` | GET | Admin | date range | Kunlik statistika |
| **Statistika** | `/api/admin/export/posts.csv`| GET | Admin | - | CSV fayl |
| **Bildirishnoma** | `/api/notifications/` | GET | Auth/Admin | pagination | Ro'yxat |
| **Bildirishnoma** | `/api/notifications/<id>/mark-read/` | POST | Auth/Admin | - | message |
| **Bildirishnoma** | `/api/notifications/mark-all-read/` | POST | Auth/Admin | - | message |
| **Bildirishnoma** | `/api/notifications/unread-count/`| GET | Auth/Admin | - | count |
| **Prizlar** | `/api/prizes/` | GET | Auth/Admin | pagination | Ro'yxat |
| **Deletions** | `/api/data-deletions/` | GET | Admin | pagination | Ro'yxat |
| **Tizim** | `/api/health/` | GET | Public | - | db, redis, status, dry_run |
| **Simulyatsiya (DRY_RUN)** | `/api/dev/simulate-views/` | POST | Admin (DRY_RUN=True) | post_id, views | message, post_id, views, status |
| **Simulyatsiya (DRY_RUN)** | `/api/dev/simulate-delete/` | POST | Admin (DRY_RUN=True) | post_id | message, post_id, status, deleted_detected_at |
| **Simulyatsiya (DRY_RUN)** | `/api/dev/simulate-token-revoked/` | POST | Admin (DRY_RUN=True) | user_id | message, user_id, status |
| **Simulyatsiya (DRY_RUN)** | `/api/dev/simulate-network-error/` | POST | Admin (DRY_RUN=True) | post_id | message, post_id, status |

Ushbu inventarizatsiya asosida barcha endpointlar ishlab chiqiladi va standartlashtiriladi.
