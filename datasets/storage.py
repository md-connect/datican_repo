# datasets/storage.py
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings
from django.core.files.storage import FileSystemStorage
import hmac
import hashlib
import time
import base64
import urllib.parse

class DatasetStorage(S3Boto3Storage):
    """Storage for private dataset files with HMAC-signed expiring URLs"""
    
    location = "datasets"
    default_acl = "private"
    file_overwrite = False
    custom_domain = settings.AWS_S3_CUSTOM_DOMAIN
    
    def url(self, name, expire=300):
        """
        Generate HMAC-signed URL with expiration
        Format matches Cloudflare Worker validation exactly
        """
        # Full path that Worker will see
        pathname = f"/datasets/{name}"
        
        # Expiration timestamp
        expires = int(time.time()) + expire
        
        # Create message WITHOUT secret (secret is key, not part of message)
        message = f"{pathname}:{expires}".encode('utf-8')
        
        # Generate HMAC signature using secret as KEY
        signature = hmac.new(
            key=settings.DATASET_SECRET_KEY.encode('utf-8'),
            msg=message,
            digestmod=hashlib.sha256
        ).hexdigest()[:32]  # 16 bytes = 32 hex chars
        
        # URL-safe token
        token = f"{expires}:{signature}"
        
        # Build final URL
        base_url = f"https://{self.custom_domain}{pathname}"
        return f"{base_url}?token={urllib.parse.quote(token)}"
    
    def get_signed_download_url(self, name, expire=300):
        """Alias for url() with clearer intent"""
        return self.url(name, expire)

# Local storage classes
class LocalPreviewStorage(FileSystemStorage):
    """Local storage for preview files"""
    def __init__(self):
        super().__init__(
            location=settings.LOCAL_MEDIA_ROOT + '/previews',
            base_url=settings.LOCAL_MEDIA_URL
        )

class LocalReadmeStorage(FileSystemStorage):
    """Local storage for README files"""
    def __init__(self):
        super().__init__(
            location=settings.LOCAL_MEDIA_ROOT + '/readmes',
            base_url=settings.LOCAL_MEDIA_URL
        )

class LocalThumbnailStorage(FileSystemStorage):
    """Local storage for thumbnail images"""
    def __init__(self):
        super().__init__(
            location=settings.LOCAL_MEDIA_ROOT + '/thumbnails',
            base_url=settings.LOCAL_MEDIA_URL + 'thumbnails/'
        )

class LocalRequestDocumentStorage(FileSystemStorage):
    """Local storage for data request documents (form submissions, ethical approval proofs)"""
    def __init__(self):
        super().__init__(
            location=settings.LOCAL_MEDIA_ROOT + '/request-documents',
            base_url=settings.LOCAL_MEDIA_URL
        )

# Factory functions
def get_dataset_storage():
    return DatasetStorage()

def get_preview_storage():
    return LocalPreviewStorage()
    
def get_readme_storage():
    return LocalReadmeStorage()

def get_thumbnail_storage():
    return LocalThumbnailStorage()

def get_request_document_storage():
    """Factory function for request document storage"""
    return LocalRequestDocumentStorage()