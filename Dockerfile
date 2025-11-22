FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies including gunicorn
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Expose port (Railway sets this dynamically)
EXPOSE 8080

# Run migrations and start gunicorn
CMD python manage.py migrate --noinput && \
    gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 60