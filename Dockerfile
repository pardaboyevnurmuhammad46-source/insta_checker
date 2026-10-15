FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --upgrade pip && pip install -r requirements.txt
RUN pip install gunicorn

COPY . /app/

# create a script to run migrations and start gunicorn
RUN echo '#!/bin/sh\npython manage.py migrate --noinput\npython manage.py collectstatic --noinput\nexec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3' > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]