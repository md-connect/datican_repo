"""
Django settings for datican_repo project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Import pymysql for MySQL connection
import pymysql
pymysql.install_as_MySQLdb()

# Detect environment - FIXED
IS_RAILWAY = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_STATIC_URL') or os.environ.get('MYSQLHOST'))
IS_PRODUCTION = os.environ.get('DJANGO_ENV') == 'production' or IS_RAILWAY
IS_DEVELOPMENT = not IS_PRODUCTION

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', "django-insecure-(-hc=)gls3m91b5q(tat_t^2ilpu8#!_(61^tgxh!lcxb&r9x*")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# Host configuration - SIMPLIFIED
if IS_RAILWAY:
    # Allow all Railway domains
    ALLOWED_HOSTS = ['*']
    CSRF_TRUSTED_ORIGINS = ['https://*.up.railway.app']
    
    # Add specific domain if available
    railway_domain = os.environ.get('RAILWAY_STATIC_URL', '').replace('https://', '').replace('http://', '')
    if railway_domain:
        ALLOWED_HOSTS.append(railway_domain)
        ALLOWED_HOSTS.append(f'.{railway_domain}')
        CSRF_TRUSTED_ORIGINS.append(f'https://{railway_domain}')
        
elif IS_PRODUCTION:
    ALLOWED_HOSTS = ['repo.datican.org', '93.127.206.235']
    CSRF_TRUSTED_ORIGINS = ['https://repo.datican.org']
else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    
    # Allauth apps
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    
    # Your custom apps
    'accounts',
    'core.apps.CoreConfig',
    'datasets',
]

# Session cookie names
SESSION_COOKIE_NAME = 'main_site_sessionid'
SESSION_COOKIE_PATH = '/'

# Admin-specific settings
ADMIN_SESSION_COOKIE_NAME = 'admin_sessionid'
ADMIN_SESSION_COOKIE_PATH = '/admin/'

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # Add whitenoise for static files
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    'datican_repo.middleware.AdminSessionMiddleware',
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "datican_repo.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.admin_stats",
            ],
        },
    },
]

WSGI_APPLICATION = "datican_repo.wsgi.application"

# Database configuration - WITH DEBUGGING
print("=== DATABASE CONFIG DEBUG ===")
print(f"MYSQLHOST: {os.environ.get('MYSQLHOST')}")
print(f"MYSQL_URL: {os.environ.get('MYSQL_URL')}")
print(f"MYSQLDATABASE: {os.environ.get('MYSQLDATABASE')}")

if os.environ.get('MYSQLHOST'):
    print("Using MYSQLHOST configuration")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ.get('MYSQLDATABASE', 'railway'),
            'USER': os.environ.get('MYSQLUSER', 'root'),
            'PASSWORD': os.environ.get('MYSQLPASSWORD', ''),
            'HOST': os.environ.get('MYSQLHOST', 'mysql.railway.internal'),
            'PORT': os.environ.get('MYSQLPORT', '3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            }
        }
    }
elif os.environ.get('MYSQL_URL'):
    print("Using MYSQL_URL configuration")
    DATABASES = {
        'default': dj_database_url.config(
            default=os.environ.get('MYSQL_URL'),
            conn_max_age=600,
            conn_health_checks=True,
            engine='django.db.backends.mysql',
        )
    }
else:
    print("Using SQLite fallback")
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# File upload settings
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 2

# Email configuration
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Use console backend for now

# Auth settings
AUTH_USER_MODEL = 'accounts.CustomUser'
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_METHODS = {'email'}  
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none' 

# URL settings
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_ON_GET = True

# Social account settings
SOCIALACCOUNT_ADAPTER = 'core.adapters.CustomSocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = False
SOCIALACCOUNT_QUERY_EMAIL = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'METHOD': 'oauth2',
        'VERIFIED_EMAIL': True,
    }
}

# Security settings - TEMPORARILY DISABLE SSL REDIRECT FOR DEBUGGING
if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = False  # Set to False temporarily for debugging
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
elif IS_RAILWAY:
    # Railway-specific settings - disable SSL redirect temporarily
    SECURE_SSL_REDIRECT = False  # CRITICAL: Set to False to fix redirect loop
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
else:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False