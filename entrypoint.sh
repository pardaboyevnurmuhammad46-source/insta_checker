#!/bin/sh
#python manage.py migrate --noinput
#python manage.py collectstatic --noinput
#exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120


python manage.py migrate --noinput
python manage.py collectstatic --noinput
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 5 --threads 4 --timeout 30