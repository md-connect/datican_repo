# datican_repo/middleware.py
from django.conf import settings
from django.contrib.auth import load_backend, BACKEND_SESSION_KEY

class AdminSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if this is an admin request
        if request.path.startswith('/admin/'):
            # Use admin-specific session cookie
            request.COOKIES[settings.SESSION_COOKIE_NAME] = request.COOKIES.get(
                settings.ADMIN_SESSION_COOKIE_NAME, ''
            )
        
        response = self.get_response(request)
        
        # For admin responses, set admin-specific cookie
        if request.path.startswith('/admin/'):
            if hasattr(request, 'session') and request.session.session_key:
                response.set_cookie(
                    settings.ADMIN_SESSION_COOKIE_NAME,
                    request.session.session_key,
                    max_age=settings.SESSION_COOKIE_AGE,
                    domain=settings.SESSION_COOKIE_DOMAIN,
                    path=settings.ADMIN_SESSION_COOKIE_PATH,
                    secure=settings.SESSION_COOKIE_SECURE,
                    httponly=settings.SESSION_COOKIE_HTTPONLY,
                    samesite=settings.SESSION_COOKIE_SAMESITE,
                )
        
        return response