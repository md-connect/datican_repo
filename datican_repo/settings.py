"""
Django settings for datican_repo project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Import pymysql for MySQL connection
# import pymysql
# pymysql.install_as_MySQLdb()

# Detect environment
IS_PRODUCTION = os.environ.get('DJANGO_ENV') == 'production'
IS_DEVELOPMENT = not IS_PRODUCTION

# Dataset signed URL secret
DATASET_SECRET_KEY = "e811e2491c080ea559e567d7da0600e007c35c4513a6e56bfee564f3e2382023"  # Use secrets.token_hex(32)
DATASET_TOKEN_EXPIRY = 300  # 5 minutes default

# Resend API Key
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "re_gC4Zo81u_bC9o5HsdsycxjWrU7CF1jhKb")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('SECRET_KEY', "django-insecure-(-hc=)gls3m91b5q(tat_t^2ilpu8#!_(61^tgxh!lcxb&r9x*")

# SECURITY WARNING: don't run with debug turned on in production!


# Host configuration
if IS_PRODUCTION:
    ALLOWED_HOSTS = ['repo.datican.org']
    CSRF_TRUSTED_ORIGINS = ['https://repo.datican.org']
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

else:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '0.0.0.0']
    CSRF_TRUSTED_ORIGINS = ['http://localhost:8000', 'http://127.0.0.1:8000']
    DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "anymail",
    "storages",

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
                'datasets.context_processor.auth_redirects',
                'datasets.context_processor.dataset_filters',
            ],
        },
    },
]

WSGI_APPLICATION = "datican_repo.wsgi.application"

# Database configuration - Docker MySQL
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.environ.get('DB_NAME', 'datican_db'),
        'USER': os.environ.get('DB_USER', 'datican'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'datican123'),
        'HOST': os.environ.get('DB_HOST', 'mysql'),  
        'PORT': os.environ.get('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'charset': 'utf8mb4',
        }
    }
}

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

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
DATA_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 52428800  # 50MB

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Authentication settings
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 3
SOCIALACCOUNT_LOGIN_ON_GET = True  # This skips the intermediate page

# ====================================================
# EMAIL CONFIGURATION FOR RESEND
# ====================================================

# Resend Email Backend
EMAIL_BACKEND = "anymail.backends.resend.EmailBackend"

# Resend API Configuration
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
ANYMAIL = {
    "RESEND_API_KEY": RESEND_API_KEY,
}

# Default email settings
DEFAULT_FROM_EMAIL = "no-reply@datican.org"  # Default Resend test domain
SERVER_EMAIL = DEFAULT_FROM_EMAIL  # For error messages
EMAIL_SUBJECT_PREFIX = "[DATICAN] "

# For debugging
if DEBUG:
    ANYMAIL.update({
        "DEBUG_API_REQUESTS": True,  # Log API requests to console
    })

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'datican_repo': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True,
        },
        'allauth': {
            'handlers': ['console'],
            'level': 'INFO',  # DEBUG for more details
            'propagate': True,
        },
    },
}

# ====================================================
# Application specific settings
# ====================================================
SITE_NAME = 'DATICAN Repository'
SITE_URL = os.environ.get('SITE_URL', 'http://localhost:8000')

# Staff emails (for rejection notifications)
MANAGER_EMAIL = os.environ.get('MANAGER_EMAIL', 'mondayoke93@gmail.com')
DIRECTOR_EMAIL = os.environ.get('DIRECTOR_EMAIL', 'mondayoke93@gmail.com')
CONTACT_EMAIL = os.environ.get('CONTACT_EMAIL', 'support@datican.org')
SUPPORT_EMAIL = os.environ.get('SUPPORT_EMAIL', 'support@datican.org')

# Auth settings
AUTH_USER_MODEL = 'accounts.CustomUser'
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_METHODS = {'email'}  
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none' 

# Session settings
SESSION_COOKIE_AGE = 1209600  
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_SAVE_EVERY_REQUEST = True

# URL settings
LOGIN_URL = '/login/'
LOGOUT_REDIRECT_URL = '/'
LOGIN_REDIRECT_URL = '/redirect-after-login/'
ACCOUNT_LOGOUT_REDIRECT_URL = '/'
ACCOUNT_LOGOUT_ON_GET = True

# Social account settings
SOCIALACCOUNT_ADAPTER = 'core.adapters.CustomSocialAccountAdapter'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = False
SOCIALACCOUNT_QUERY_EMAIL = True

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ.get('GOOGLE_CLIENT_ID'),
            'secret': os.environ.get('GOOGLE_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
        'METHOD': 'oauth2',
        'VERIFIED_EMAIL': True,
    }
}


# Security settings for production only
if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    # Use your verified domain in production
    DEFAULT_FROM_EMAIL = "noreply@repo.datican.org"
else:
    # Development-specific settings
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    # Use Resend test domain in development
    DEFAULT_FROM_EMAIL = "onboarding@resend.dev"


# ====================================================
# BACKBLAZE B2 CLOUD STORAGE CONFIGURATION
# ====================================================

B2_APPLICATION_KEY_ID = os.environ.get('B2_APPLICATION_KEY_ID')
B2_APPLICATION_KEY = os.environ.get('B2_APPLICATION_KEY')
B2_BUCKET_NAME = os.environ.get('B2_BUCKET_NAME', 'datican-repo')
B2_REGION = os.environ.get('B2_REGION', 'eu-central-003')
B2_ENDPOINT_URL = f'https://s3.{B2_REGION}.backblazeb2.com'

AWS_ACCESS_KEY_ID = B2_APPLICATION_KEY_ID
AWS_SECRET_ACCESS_KEY = B2_APPLICATION_KEY
AWS_STORAGE_BUCKET_NAME = B2_BUCKET_NAME
AWS_S3_REGION_NAME = B2_REGION
AWS_S3_ENDPOINT_URL = B2_ENDPOINT_URL
AWS_S3_SIGNATURE_VERSION = 's3v4'
AWS_S3_ADDRESSING_STYLE = 'virtual'
AWS_S3_FILE_OVERWRITE = False
AWS_DEFAULT_ACL = None
AWS_QUERYSTRING_AUTH = True
AWS_QUERYSTRING_EXPIRE = 300
AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
AWS_S3_CUSTOM_DOMAIN = "cdn.repo.datican.org"


B2_DATASETS_LOCATION = 'datasets'
B2_PREVIEWS_LOCATION = 'previews'
B2_THUMBNAILS_LOCATION = 'thumbnails'
B2_README_LOCATION = 'readmes'
B2_REQUEST_DOCS_LOCATION = 'request-documents'

from storages.backends.s3boto3 import S3Boto3Storage
from django.core.files.storage import FileSystemStorage

class DatasetStorage(S3Boto3Storage):
    location = B2_DATASETS_LOCATION
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 300
    custom_domain = None


# Local storage paths
LOCAL_MEDIA_ROOT = '/app/media'
LOCAL_MEDIA_URL = '/media/'

# Custom local storage classes
class LocalThumbnailStorage(FileSystemStorage):
    location = f'{LOCAL_MEDIA_ROOT}/thumbnails'
    base_url = f'{LOCAL_MEDIA_URL}thumbnails/'

class LocalPreviewStorage(FileSystemStorage):
    location = f'{LOCAL_MEDIA_ROOT}/dataset_previews'
    base_url = f'{LOCAL_MEDIA_URL}dataset_previews/'

class LocalReadmeStorage(FileSystemStorage):
    location = f'{LOCAL_MEDIA_ROOT}/dataset_readmes'
    base_url = f'{LOCAL_MEDIA_URL}dataset_readmes/'

class LocalRequestDocumentStorage(FileSystemStorage):
    location = f'{LOCAL_MEDIA_ROOT}/request-documents'
    base_url = f'{LOCAL_MEDIA_URL}request-documents/'

# Instantiate storage classes
DATASET_STORAGE = DatasetStorage()
THUMBNAIL_STORAGE = LocalThumbnailStorage()
PREVIEW_STORAGE = LocalPreviewStorage()
README_STORAGE = LocalReadmeStorage()
REQUEST_DOCUMENT_STORAGE = LocalRequestDocumentStorage()

