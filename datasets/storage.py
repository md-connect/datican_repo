# datasets/storage.py
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from storages.backends.s3boto3 import S3Boto3Storage
import logging
import mimetypes

logger = logging.getLogger(__name__)

class B2StorageMixin:
    """Mixin for common B2 storage functionality"""
    
    def __init__(self, *args, **kwargs):
        """Validate B2 configuration on initialization"""
        super().__init__(*args, **kwargs)
        self._validate_settings()
    
    def _validate_settings(self):
        """Ensure all required B2 settings are configured"""
        required_settings = [
            ('AWS_ACCESS_KEY_ID', 'B2 Application Key ID'),
            ('AWS_SECRET_ACCESS_KEY', 'B2 Application Key'),
            ('AWS_STORAGE_BUCKET_NAME', 'B2 Bucket Name'),
            ('AWS_S3_ENDPOINT_URL', 'B2 Endpoint URL'),
        ]
        
        missing = []
        for setting, description in required_settings:
            if not getattr(settings, setting, None):
                missing.append(f"{setting} ({description})")
        
        if missing:
            raise ImproperlyConfigured(
                f"Missing required B2 settings:\n  " + "\n  ".join(missing)
            )
    
    def url(self, name, expire=None):
        """Generate signed URL with custom expiration"""
        if expire is None:
            expire = getattr(self, 'querystring_expire', 300)
        
        try:
            # Store current expiration, generate URL, then restore
            original_expire = self.querystring_expire
            self.querystring_expire = expire
            url = super().url(name)
            self.querystring_expire = original_expire
            return url
        except Exception as e:
            logger.error(f"Error generating signed URL for {name}: {e}")
            raise
    
    def verify_bucket(self):
        """Verify bucket exists and is accessible"""
        try:
            self.connection.head_bucket(Bucket=self.bucket_name)
            return True
        except Exception as e:
            logger.error(f"Bucket verification failed for {self.bucket_name}: {e}")
            return False
    
    def get_file_info(self, name):
        """Get metadata about a file in storage"""
        try:
            return self.connection.head_object(
                Bucket=self.bucket_name,
                Key=self._normalize_name(name)
            )
        except Exception as e:
            logger.error(f"Failed to get file info for {name}: {e}")
            return None

class DatasetStorage(B2StorageMixin, S3Boto3Storage):
    """Storage for dataset files"""
    location = settings.B2_DATASETS_LOCATION
    file_overwrite = False  # Never overwrite existing files
    querystring_auth = True  # Force signed URLs
    querystring_expire = 300  # 5 minutes
    custom_domain = None  # Force signed URLs
    
    def _save(self, name, content):
        """Auto-detect content type on save"""
        if hasattr(content, 'content_type') and content.content_type:
            self.object_parameters['ContentType'] = content.content_type
        else:
            # Guess content type from filename
            content_type, _ = mimetypes.guess_type(name)
            if content_type:
                self.object_parameters['ContentType'] = content_type
        
        return super()._save(name, content)
    
    def get_available_name(self, name, max_length=None):
        """Prevent automatic renaming of existing files"""
        if self.exists(name):
            raise ValidationError(
                f"A file with the name '{name}' already exists. "
                f"File overwriting is disabled for security."
            )
        return super().get_available_name(name, max_length)

class DatasetPreviewStorage(B2StorageMixin, S3Boto3Storage):
    """Storage for preview files"""
    location = settings.B2_PREVIEWS_LOCATION
    file_overwrite = True  # Previews can be updated
    querystring_auth = True
    querystring_expire = 3600  # 1 hour
    custom_domain = None

class ThumbnailStorage(B2StorageMixin, S3Boto3Storage):
    """Storage for thumbnail images"""
    location = settings.B2_THUMBNAILS_LOCATION
    file_overwrite = True
    querystring_auth = True
    querystring_expire = 86400  # 24 hours
    custom_domain = None
    
    def _save(self, name, content):
        """Ensure thumbnails are saved as web-friendly format"""
        self.object_parameters['ContentType'] = 'image/jpeg'
        return super()._save(name, content)

class ReadmeStorage(B2StorageMixin, S3Boto3Storage):
    """Storage for README files"""
    location = settings.B2_README_LOCATION
    file_overwrite = False  # READMEs shouldn't be overwritten
    querystring_auth = True
    querystring_expire = 3600  # 1 hour
    custom_domain = None

class RequestDocumentStorage(B2StorageMixin, S3Boto3Storage):
    """Storage for request documents"""
    location = settings.B2_REQUEST_DOCS_LOCATION
    file_overwrite = False  # Never overwrite submitted documents
    querystring_auth = True
    querystring_expire = 3600  # 1 hour
    custom_domain = None

# Singleton instances
dataset_storage = DatasetStorage()
preview_storage = DatasetPreviewStorage()
thumbnail_storage = ThumbnailStorage()
readme_storage = ReadmeStorage()
request_document_storage = RequestDocumentStorage()

def get_dataset_storage():
    """Get DatasetStorage singleton instance"""
    return dataset_storage

def get_preview_storage():
    """Get DatasetPreviewStorage singleton instance"""
    return preview_storage

def get_thumbnail_storage():
    """Get ThumbnailStorage singleton instance"""
    return thumbnail_storage

def get_readme_storage():
    """Get ReadmeStorage singleton instance"""
    return readme_storage

def get_request_document_storage():
    """Get RequestDocumentStorage singleton instance"""
    return request_document_storage

# Optional: Verify bucket connection on startup
try:
    if not dataset_storage.verify_bucket():
        logger.warning(f"⚠️ B2 bucket '{settings.AWS_STORAGE_BUCKET_NAME}' is not accessible")
    else:
        logger.info(f"✅ Connected to B2 bucket: {settings.AWS_STORAGE_BUCKET_NAME}")
except Exception as e:
    logger.error(f"❌ Failed to connect to B2: {e}")