FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy project files
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Expose port (Railway sets this dynamically)
EXPOSE 8080

# Run migrations and start gunicorn
# Important: Use 0.0.0.0 to listen on all interfaces
CMD sh -c "python manage.py migrate --noinput && \
    gunicorn config.wsgi:application \
    --bind 0.0.0.0:\${PORT:-8080} \
    --workers 2 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    --log-level debug"