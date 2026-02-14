"""
Docker production settings for datican_repo
"""
from .settings import *

# Override database settings for Docker
DATABASES['default']['HOST'] = os.environ.get('DB_HOST', 'mysql')
DATABASES['default']['PORT'] = os.environ.get('DB_PORT', '3306')
DATABASES['default']['OPTIONS']['charset'] = 'utf8mb4'


# Docker-specific static/media paths
STATIC_ROOT = '/app/staticfiles'
MEDIA_ROOT = '/app/media'

# Security settings for production
DEBUG = os.environ.get('DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = os.environ.get(
    'ALLOWED_HOSTS', 'localhost,127.0.0.1,django'
).split(',')

CSRF_TRUSTED_ORIGINS = os.environ.get(
    'CSRF_TRUSTED_ORIGINS', 'https://repo.datican.org,http://repo.datican.org,http://http://209.38.247.225:8000,http://localhost:8000,http://127.0.0.1:8000'
).split(',')

# Enable SSL settings now that you have HTTPS
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True


# ====================================================
# BACKBLAZE B2 CLOUD STORAGE CONFIGURATION
# ====================================================


B2_APPLICATION_KEY_ID = os.environ.get('003bc74213ce5f30000000001', '')
B2_APPLICATION_KEY = os.environ.get('K003gOvlJyEdZR6oBHkCXk1ltARFOO8', '')
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

B2_DATASETS_LOCATION = 'datasets'
B2_PREVIEWS_LOCATION = 'previews'
B2_THUMBNAILS_LOCATION = 'thumbnails'
B2_README_LOCATION = 'readmes'
B2_REQUEST_DOCS_LOCATION = 'request-documents'

from storages.backends.s3boto3 import S3Boto3Storage

class DatasetStorage(S3Boto3Storage):
    location = B2_DATASETS_LOCATION
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 300
    custom_domain = None

class DatasetPreviewStorage(S3Boto3Storage):
    location = B2_PREVIEWS_LOCATION
    file_overwrite = True
    querystring_auth = True
    querystring_expire = 3600

class ThumbnailStorage(S3Boto3Storage):
    location = B2_THUMBNAILS_LOCATION
    file_overwrite = True
    querystring_auth = True
    querystring_expire = 86400

class ReadmeStorage(S3Boto3Storage):
    location = B2_README_LOCATION
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 3600

class RequestDocumentStorage(S3Boto3Storage):
    location = B2_REQUEST_DOCS_LOCATION
    file_overwrite = False
    querystring_auth = True
    querystring_expire = 3600

DATASET_STORAGE = DatasetStorage()
DATASET_PREVIEW_STORAGE = DatasetPreviewStorage()
THUMBNAIL_STORAGE = ThumbnailStorage()
README_STORAGE = ReadmeStorage()
REQUEST_DOCUMENT_STORAGE = RequestDocumentStorage()