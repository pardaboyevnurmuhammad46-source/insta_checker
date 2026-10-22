.PHONY: e2e test build up down restart logs status connect check-ig run-local worker-local beat-local frontend-dev test-local

# --- Docker boshqaruvi ---
e2e:
	docker compose --profile e2e run --rm newman

test:
	docker compose exec web python manage.py test

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

status:
	docker compose ps

check-ig:
	docker compose exec web python manage.py check_instagram

connect:
	docker compose exec web python manage.py connect_instagram $(filter-out $@,$(MAKECMDGOALS))

# --- Terminalda bevosita (Local / Docker'siz) ishlatish ---
run-local:
	./venv/bin/python manage.py runserver 8000

worker-local:
	./venv/bin/celery -A config worker -l info --concurrency 4

beat-local:
	./venv/bin/celery -A config beat -l info

frontend-dev:
	cd frontend && npm run dev

test-local:
	./venv/bin/python manage.py test tracker

%:
	@:

