# Insta Checker API

This project provides an API for Instagram tracking and management.

## Setup Instructions (Docker)

1. Rename `.env.example` to `.env` and fill in the required values (e.g. database credentials, Instagram App details).
2. Ensure you have Docker and Docker Compose installed.
3. Build and start the containers:
   ```bash
   docker compose up -d --build
   ```
4. To create a superuser for the admin panel and API:
   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

The application will be running on `http://localhost:8000`. Wait for the migrations and collectstatic to finish (which happens automatically on web startup).

## Running Tests

To test the APIs, use the provided admin user credentials to obtain a JWT token from `/api/token/` and then query the endpoints.

To run Django unit tests:
```bash
docker compose exec web python manage.py test
```