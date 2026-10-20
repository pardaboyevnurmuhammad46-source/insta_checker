.PHONY: e2e test build up down

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
