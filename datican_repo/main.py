#!/usr/bin/env python
"""
Railpack entry point for Datican application
"""
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'datican_repo.settings')
    
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    
    # For production deployment
    if len(sys.argv) == 1:
        # Run gunicorn programmatically
        try:
            from gunicorn.app.wsgiapp import run
            sys.argv = ["gunicorn", "datican_repo.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
            sys.exit(run())
        except ImportError:
            # Fallback to Django development server
            execute_from_command_line([sys.argv[0], "runserver", "0.0.0.0:8000"])
    else:
        # Normal management commands
        execute_from_command_line(sys.argv)