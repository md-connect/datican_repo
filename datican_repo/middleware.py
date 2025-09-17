# datican_repo/middleware.py
from django.conf import settings

class AdminSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_admin_request = request.path.startswith('/admin/')

        if is_admin_request:
            # Swap to admin-specific session cookie (if it exists)
            admin_cookie = request.COOKIES.get(settings.ADMIN_SESSION_COOKIE_NAME)
            if admin_cookie:
                request.COOKIES[settings.SESSION_COOKIE_NAME] = admin_cookie

        response = self.get_response(request)

        if is_admin_request and hasattr(request, 'session') and request.session.session_key:
            # Store session key into admin-specific cookie
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
