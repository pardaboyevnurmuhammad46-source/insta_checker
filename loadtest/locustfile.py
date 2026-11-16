# import random, io
# from locust import HttpUser, task, between
# from locust.exception import StopUser
#
# class ApiUser(HttpUser):
#     wait_time = between(1, 3)
#
#     def on_start(self):
#         n = random.randint(1, 50)
#         with self.client.post("/api/token/",
#                               json={"username": f"loadtest{n}", "password": "loadtest123"},
#                               name="/api/token/", catch_response=True) as r:
#             if r.status_code != 200:
#                 r.failure(f"login failed: {r.status_code}")
#                 raise StopUser()
#             token = r.json()["access"]
#         self.client.headers.update({"Authorization": f"Bearer {token}"})
#
#     @task(10)
#     def summary(self):
#         self.client.get("/api/me/summary/")
#
#     @task(6)
#     def posts(self):
#         self.client.get("/api/me/posts/")
#
#     @task(4)
#     def notifications(self):
#         self.client.get("/api/me/notifications/")
#
#     @task(2)
#     def publish_status(self):
#         self.client.get("/api/user/publish-status/")
#
#     @task(1)
#     def upload_video(self):
#         fake_video = io.BytesIO(b"\x00" * 2 * 1024 * 1024)  # 2 MB soxta video
#         self.client.post(
#             "/api/user/upload-video/",
#             files={"video": ("test.mp4", fake_video, "video/mp4")},  # "video" maydon nomini tekshiring
#             name="/api/user/upload-video/",
#         )


import io, os, random
from locust import HttpUser, task, between
from locust.exception import StopUser

TOKENS = {}
REAL_MP4 = "loadtest/sample.mp4"   # ixtiyoriy: haqiqiy video (Test B uchun)

class ApiUser(HttpUser):
    wait_time = between(3, 8)

    def on_start(self):
        n = random.randint(1, 1000)
        name = f"loadtest{n}"
        if name not in TOKENS:
            r = self.client.post("/api/token/", json={"username": name, "password": "loadtest123"},
                                 name="/api/token/")
            if r.status_code != 200:
                raise StopUser()
            TOKENS[name] = r.json()["access"]
        self.client.headers["Authorization"] = f"Bearer {TOKENS[name]}"

    # @task(10)
    # def summary(self):
    #     self.client.get("/api/me/summary/")
    #
    # @task(6)
    # def posts(self):
    #     self.client.get("/api/me/posts/")
    #
    # @task(4)
    # def notifications(self):
    #     self.client.get("/api/me/notifications/")
    #
    # @task(2)
    # def publish_status(self):
    #     self.client.get("/api/user/publish-status/")

    @task(10)
    def summary(self): self.client.get("/api/me/summary/")
    @task(6)
    def posts(self): self.client.get("/api/me/posts/")
    @task(4)
    def notifications(self): self.client.get("/api/me/notifications/")
    @task(3)
    def status(self): self.client.get("/api/user/publish-status/")
    @task(2)
    def prizes(self): self.client.get("/api/me/prizes/")


    # @task(1)
    # def upload_video(self):
    #     fake = io.BytesIO(b"\x00" * 2 * 1024 * 1024)
    #     self.client.post("/api/user/upload-video/",
    #                      files={"file": ("test.mp4", fake, "video/mp4")},
    #                      name="/api/user/upload-video/")

    # @task(1)
    # def publish(self):
    #     self.client.post("/api/user/publish/", name="/api/user/publish/")


    @task(1)
    def publish(self):
        with self.client.post("/api/user/publish/",
                              name="/api/user/publish/",
                              catch_response=True) as r:
            if r.status_code in (202, 409, 429):
                r.success()
            else:
                # r.failure(f"publish: {r.status_code} {r.text[:100]}")
                r.failure(f"{r.status_code} {r.text[:120]}")


class UploadUser(ApiUser):
    """Video yuklash va joylash. Faqat Test B/C da ishlating."""
    weight = 0
    wait_time = between(5, 15)
    tasks = []

    @task(3)
    def upload(self):
        if os.path.exists(REAL_MP4):
            data = open(REAL_MP4, "rb").read()
        else:
            data = b"\x00" * 5 * 1024 * 1024   # 5 MB soxta
        self.client.post("/api/user/upload-video/",
                         files={"file": ("t.mp4", io.BytesIO(data), "video/mp4")},
                         name="/api/user/upload-video/")
