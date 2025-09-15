#!/bin/bash

# Wait for MySQL to be ready
if [ -n "$MYSQLHOST" ] || [ -n "$MYSQL_URL" ]; then
    echo "Waiting for MySQL to be ready..."
    sleep 10
fi

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser if not exists (optional)
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin@example.com', 'adminpassword') if not User.objects.filter(email='admin@example.com').exists() else None" | python manage.py shell

# Start Gunicorn
exec gunicorn datican_repo.wsgi:application --bind 0.0.0.0:$PORT --access-logfile -