#!/bin/bash

# Wait for database to be ready
echo "Waiting for database..."
sleep 5

# Run migrations
python manage.py migrate --noinput

# Collect static files
python manage.py collectstatic --noinput

# Start Gunicorn
exec gunicorn datican_repo.wsgi:application --bind 0.0.0.0:$PORT --workers 3
