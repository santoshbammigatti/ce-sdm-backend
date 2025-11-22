FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Expose port
EXPOSE ${PORT:-8080}

# Run migrations and start gunicorn with explicit port
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi:application \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    --log-level info