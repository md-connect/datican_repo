#!/bin/bash

# Wait for MySQL to be ready (optional but recommended)
echo "Waiting for MySQL to be ready..."
sleep 5

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Start Gunicorn
exec gunicorn datican_repo.wsgi:application --bind 0.0.0.0:$PORT