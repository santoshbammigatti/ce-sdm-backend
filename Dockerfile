FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV WEB_CONCURRENCY=2

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

EXPOSE 8080

# Simple startup without config file
CMD python manage.py migrate --noinput && \
    exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:$PORT \
    --workers 2 \
    --timeout 0 \
    --log-level info \
    --access-logfile - \
    --error-logfile -