#!/bin/sh
set -ex  # Changed from 'set -e' to 'set -ex' for verbose output

echo "=== START SCRIPT BEGINNING ==="
echo "PORT variable is: ${PORT}"
echo "Current directory: $(pwd)"
echo "Python version: $(python --version)"

echo "=== Running migrations ==="
python manage.py migrate --noinput

echo "=== Migrations complete ==="
echo "=== Checking if gunicorn is installed ==="
which gunicorn
gunicorn --version

echo "=== Starting gunicorn on port ${PORT:-8080} ==="
exec gunicorn config.wsgi:application \
    --bind "0.0.0.0:${PORT:-8080}" \
    --workers 2 \
    --timeout 0 \
    --log-level info \
    --access-logfile - \
    --error-logfile -