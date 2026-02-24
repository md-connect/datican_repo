from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
import os
from django.core.files.base import ContentFile
from datasets.utilities import convert_to_png
from django.core.validators import FileExtensionValidator
import markdown
from django.utils.safestring import mark_safe
from .storage import get_preview_storage, get_readme_storage, get_thumbnail_storage, get_request_document_storage
import uuid
import logging
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


logger = logging.getLogger(__name__)

import uuid
import os

def preview_upload_path(instance, filename):
    """Generate upload path for preview files"""
    ext = os.path.splitext(filename)[1].lower()
    unique_id = uuid.uuid4().hex[:8]
    
    # If instance has an ID, use it; otherwise use a temporary ID
    if instance.id:
        folder = str(instance.id)
        file_id = instance.id
    else:
        # Generate a temporary ID using a random string
        temp_id = uuid.uuid4().hex[:8]
        folder = f"temp_{temp_id}"
        file_id = temp_id
    
    # Keep the original filename but add prefix for clarity
    base_name = os.path.splitext(filename)[0][:30]  # Truncate long names
    safe_filename = f"{base_name}_{unique_id}{ext}"
    
    return f"previews/{folder}/{safe_filename}"

def readme_upload_path(instance, filename):
    """Generate upload path for README files"""
    ext = os.path.splitext(filename)[1].lower()
    unique_id = uuid.uuid4().hex[:8]
    
    if instance.id:
        folder = str(instance.id)
        file_id = instance.id
    else:
        temp_id = uuid.uuid4().hex[:8]
        folder = f"temp_{temp_id}"
        file_id = temp_id
    
    # Keep the original filename but add prefix for clarity
    base_name = os.path.splitext(filename)[0][:30]  # Truncate long names
    safe_filename = f"{base_name}_{unique_id}{ext}"
    
    return f"readmes/{folder}/{safe_filename}"

# Keep aliases for backward compatibility
preview_file_path = preview_upload_path
readme_file_path = readme_upload_path


def dataset_file_path(instance, filename):
    """Generate unique file path for dataset files in B2"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    return f"{instance.id}/{filename}"


def thumbnail_file_path(instance, filename):
    """Generate unique path for thumbnail images in local storage"""
    ext = filename.split('.')[-1]
    filename = f"thumb_{uuid.uuid4().hex}.{ext}"
    return f"{instance.dataset_id}/{filename}"

def validate_thumbnail(value):
    """Validate thumbnail file formats"""
    valid_extensions = ['.jpg', '.jpeg', '.png', '.dcm', '.dicom', '.nii', '.nii.gz']
    name = value.name.lower()
    
    # Check all valid extensions
    if not any(name.endswith(ext) for ext in valid_extensions):
        raise ValidationError(
            "Unsupported file format. Supported formats: " +
            "JPG, JPEG, PNG, DICOM, NIfTI"
        )

# Keep the old function name as an alias for backward compatibility
def request_document_path(instance, filename):
    """Legacy function - routes to appropriate new function based on context"""
    # You can check the field name if needed, but for simplicity:
    if hasattr(instance, 'form_submission') and instance._meta.get_field('form_submission').upload_to == request_document_path:
        return form_submission_path(instance, filename)
    else:
        return ethical_approval_path(instance, filename)


def form_submission_path(instance, filename):
    """Path for form submission documents"""
    ext = os.path.splitext(filename)[1].lower()
    unique_id = uuid.uuid4().hex[:8]
    
    # If instance has an ID, use it; otherwise use a temporary ID
    if instance.id:
        folder = str(instance.id)
        file_id = instance.id
    else:
        # Generate a temporary ID using a random string
        temp_id = uuid.uuid4().hex[:8]
        folder = f"temp_{temp_id}"
        file_id = temp_id
    
    return f"request-documents/{folder}/form_{file_id}_{unique_id}{ext}"

def ethical_approval_path(instance, filename):
    """Path for ethical approval documents"""
    ext = os.path.splitext(filename)[1].lower()
    unique_id = uuid.uuid4().hex[:8]
    
    if instance.id:
        folder = str(instance.id)
        file_id = instance.id
    else:
        temp_id = uuid.uuid4().hex[:8]
        folder = f"temp_{temp_id}"
        file_id = temp_id
    
    return f"request-documents/{folder}/ethical_{file_id}_{unique_id}{ext}"


class DatasetFile(models.Model):
    """
    Individual file belonging to a dataset (ForeignKey relationship)
    One dataset can have many files, but each file belongs to exactly one dataset
    """
    # Relationship - THIS IS THE KEY CHANGE
    dataset = models.ForeignKey(
        'Dataset',
        on_delete=models.CASCADE,
        related_name='files',
        help_text="The dataset this file belongs to"
    )
    
    # File information
    filename = models.CharField(max_length=500)
    file_path = models.CharField(
        max_length=500,
        unique=True,  # Prevent duplicate B2 paths
        help_text="Full path in B2 bucket (e.g., datasets/breast-cancer/part1.zip)"
    )
    file_size = models.BigIntegerField(default=0)
    
    # Part information (for multi-part datasets)
    part_number = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Part number (1, 2, 3, etc.)"
    )
    total_parts = models.PositiveIntegerField(
        null=True, 
        blank=True,
        help_text="Total number of parts in this dataset"
    )
    
    # B2 metadata
    b2_etag = models.CharField(max_length=100, blank=True)
    b2_upload_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['part_number', 'filename']
        unique_together = ['dataset', 'part_number']  # Prevent duplicate part numbers
        indexes = [
            models.Index(fields=['dataset', 'part_number']),
            models.Index(fields=['file_path']),
        ]
    
    def __str__(self):
        if self.part_number and self.total_parts:
            return f"{self.filename} (Part {self.part_number}/{self.total_parts})"
        return self.filename
    
    def get_download_url(self, expiration=3600):
        """Generate pre-signed download URL"""
        if not self.file_path:
            return None
        
        s3 = boto3.client(
            's3',
            endpoint_url=settings.B2_ENDPOINT_URL,
            aws_access_key_id=settings.B2_APPLICATION_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            region_name=settings.B2_REGION,
            config=Config(signature_version='s3v4')
        )
        
        try:
            return s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.B2_BUCKET_NAME,
                    'Key': self.file_path
                },
                ExpiresIn=expiration
            )
        except Exception as e:
            logger.error(f"Error generating URL for {self.filename}: {e}")
            return None
    
    def get_file_size_display(self):
        """Human readable size"""
        size = self.file_size
        if not size:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"
    
    def refresh_metadata(self):
        """Fetch current metadata from B2"""
        if not self.file_path:
            return False
        
        s3 = boto3.client(
            's3',
            endpoint_url=settings.B2_ENDPOINT_URL,
            aws_access_key_id=settings.B2_APPLICATION_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            region_name=settings.B2_REGION,
        )
        
        try:
            response = s3.head_object(
                Bucket=settings.B2_BUCKET_NAME,
                Key=self.file_path
            )
            
            self.file_size = response.get('ContentLength', self.file_size)
            self.b2_etag = response.get('ETag', '').strip('"')
            self.b2_upload_date = response.get('LastModified', self.b2_upload_date)
            self.save(update_fields=['file_size', 'b2_etag', 'b2_upload_date'])
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"File not found in B2: {self.file_path}")
            else:
                logger.error(f"Error fetching B2 metadata: {e}")
            return False


class Dataset(models.Model):
    
    MODALITY_CHOICES = [
        ('MRI', 'MRI'),
        ('MG', 'Mammography'),
        ('CT', 'CT Scan'),
        ('X-RAY', 'X-Ray'),
        ('Other', 'Other'),
    ]
    
    FORMAT_CHOICES = [
        ('DICOM', 'DICOM'),
        ('NIfTI', 'NIfTI'),
        ('PNG', 'PNG'),
        ('JPG', 'JPG'),
        ('HDF5', 'HDF5'),
    ]
    DIMENSION_CHOICES = [
        ('2D', '2D'),
        ('3D', '3D'),
        ('4D', '4D'),
    ]

    title = models.CharField(max_length=255)
    description = models.TextField()
    modality = models.CharField(
        max_length=20,
        choices=MODALITY_CHOICES,
        blank=True,
        null=True
    )
    body_part = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="e.g., Brain, Breast, Chest, Abdomen, Knee, etc."
    )
    
    # Keep for backward compatibility, but will be deprecated
    dataset_path = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name="Dataset Path in B2 (Legacy)",
        help_text="Legacy single file path - use DatasetFile model for multi-part"
    )

    format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        blank=True,
        null=True
    )
    no_of_subjects = models.IntegerField(
        default=0,
        help_text="Number of subjects/patients in the dataset"
    )
    upload_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)
    rating = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
        default=0.0
    )
    download_count = models.PositiveIntegerField(default=0)
    owner = models.CharField(
        max_length=100,
        default='DATICAN',
        editable=False)
    
    # Track who actually uploaded it
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Local storage fields (unchanged)
    preview_file = models.FileField(
        upload_to=preview_upload_path,
        storage=get_preview_storage(),
        blank=True,
        null=True,
        help_text="Preview file"
    )
    
    # Preview type field
    PREVIEW_TYPE_CHOICES = [
        ('csv', 'CSV'),
        ('excel', 'Excel'),
        ('json', 'JSON'),
        ('none', 'No Preview'),
    ]
    
    preview_type = models.CharField(
        max_length=10,
        choices=PREVIEW_TYPE_CHOICES,
        default='none',
        blank=True
    )

    readme_file = models.FileField(
        upload_to=readme_upload_path,
        storage=get_readme_storage(),
        blank=True,
        null=True,
        validators=[FileExtensionValidator(
            allowed_extensions=['md', 'txt', 'pdf', 'rst', 'markdown']
        )],
        help_text="Upload README file (Markdown, PDF, or Text)"
    )

    readme_content = models.TextField(
        blank=True,
        help_text="Automatically extracted text from README"
    )
    readme_updated = models.DateTimeField(null=True, blank=True)
    readme_file_size = models.IntegerField(default=0)  
    
    # B2 metadata fields (for legacy single file)
    b2_file_id = models.CharField(max_length=255, null=True, blank=True)
    b2_file_info = models.JSONField(null=True, blank=True)
    b2_file_size = models.BigIntegerField(null=True, blank=True, verbose_name="B2 File Size (bytes)")
    b2_upload_date = models.DateTimeField(null=True, blank=True)
    b2_etag = models.CharField(max_length=100, blank=True, null=True)
    
    # Keep file_type for backward compatibility
    file_type = models.CharField(max_length=100, null=True, blank=True)

    # Helper methods for file management
    def get_all_files(self):
        """Get all files ordered by part number"""
        return self.files.all().order_by('part_number')
    
    def get_file_by_part(self, part_number):
        """Get a specific part file"""
        try:
            return self.files.get(part_number=part_number)
        except DatasetFile.DoesNotExist:
            return None
    
    def get_total_size(self):
        """Calculate total size of all files"""
        total = sum(f.file_size for f in self.files.all())
        # Include legacy file size if exists and no files
        if not total and self.b2_file_size:
            return self.b2_file_size
        return total
    
    def get_file_count(self):
        """Get number of files"""
        count = self.files.count()
        if count == 0 and self.dataset_path:
            return 1  # Legacy single file
        return count
    
    def get_file_size_display(self):
        """Human readable total size"""
        total = self.get_total_size()
        if not total:
            return "Unknown"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if total < 1024.0:
                return f"{total:.1f} {unit}"
            total /= 1024.0
        return f"{total:.1f} TB"
    
    def is_multi_part(self):
        """Check if dataset has multiple parts"""
        return self.files.count() > 1
    
    def get_download_urls(self, user):
        """Get download URLs for all files if user is approved"""
        if not self.is_approved_for_user(user):
            return None
        
        urls = []
        for file in self.get_all_files():
            urls.append({
                'part_number': file.part_number,
                'filename': file.filename,
                'url': file.get_download_url(),
                'size': file.get_file_size_display(),
                'size_bytes': file.file_size
            })
        return urls
    
    def is_approved_for_user(self, user):
        """Check if user has active approval"""
        if not user.is_authenticated:
            return False
        
        return DataRequest.objects.filter(
            dataset=self,
            user=user,
            status='approved'
        ).exists()

    def get_download_url(self, expiration=3600):
        """Legacy method - generate pre-signed download URL for single file"""
        if not self.dataset_path:
            return None
        
        # Configure B2 client
        config = Config(signature_version='s3v4')
        s3 = boto3.client(
            's3',
            endpoint_url=settings.B2_ENDPOINT_URL,
            aws_access_key_id=settings.B2_APPLICATION_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            region_name=settings.B2_REGION,
            config=config
        )
        
        try:
            url = s3.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': settings.B2_BUCKET_NAME,
                    'Key': self.dataset_path
                },
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Error generating download URL: {e}")
            return None
    
    def get_preview_url(self, expiration=3600):
        if self.preview_file:
            return self.preview_file.url
        return None

    def get_readme_url(self, expiration=3600):
        if self.readme_file:
            return self.readme_file.url
        return None

    def refresh_b2_metadata(self):
        """Fetch current metadata from B2 for legacy single file"""
        if not self.dataset_path:
            return False
            
        s3 = boto3.client(
            's3',
            endpoint_url=settings.B2_ENDPOINT_URL,
            aws_access_key_id=settings.B2_APPLICATION_KEY_ID,
            aws_secret_access_key=settings.B2_APPLICATION_KEY,
            region_name=settings.B2_REGION,
        )
        
        try:
            response = s3.head_object(
                Bucket=settings.B2_BUCKET_NAME,
                Key=self.dataset_path
            )
            
            self.b2_file_size = response.get('ContentLength')
            self.b2_etag = response.get('ETag', '').strip('"')
            self.b2_upload_date = response.get('LastModified')
            
            # Auto-detect file type from extension
            ext = os.path.splitext(self.dataset_path)[1].lower()
            type_map = {
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.zip': 'application/zip',
                '.nii': 'application/octet-stream',
                '.dcm': 'application/dicom',
                '.pdf': 'application/pdf',
                '.tar': 'application/x-tar',
                '.gz': 'application/gzip',
                '.tar.gz': 'application/gzip',
            }
            self.file_type = type_map.get(ext, 'application/octet-stream')
            
            self.save(update_fields=['b2_file_size', 'b2_etag', 'b2_upload_date', 'file_type'])
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                logger.warning(f"File not found in B2: {self.dataset_path}")
            else:
                logger.error(f"Error fetching B2 metadata: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error fetching B2 metadata: {e}")
            return False

    @property
    def readme(self):
        """Property to maintain compatibility with template"""
        return self.readme_content
    
    @property
    def has_readme(self):
        """Check if README exists"""
        return bool(self.readme_file) or bool(self.readme_content)

    @property
    def readme_html(self):
        """Convert Markdown to HTML if possible"""
        if not self.readme_content:
            return ""
        
        # Check if it's likely markdown (contains markdown syntax)
        content = self.readme_content
        
        # Simple check for markdown
        has_markdown = any(marker in content for marker in [
            '# ', '## ', '### ', '**', '*', '`', '[', ']('
        ])
        
        if has_markdown:
            try:
                # Convert markdown to HTML
                html = markdown.markdown(
                    content,
                    extensions=['extra', 'codehilite', 'tables']
                )
                return mark_safe(html)
            except:
                # Fallback to plain text
                return mark_safe(content.replace('\n', '<br>'))
        else:
            # Plain text with line breaks
            return mark_safe(content.replace('\n', '<br>'))
            
    def get_user_rating(self, user):
        """Get user's rating for this dataset"""
        try:
            return self.ratings.get(user=user).rating
        except DatasetRating.DoesNotExist:
            return None
    
    def get_average_rating(self):
        """Calculate average rating"""
        ratings = self.ratings.all()
        if ratings:
            total = sum(rating.rating for rating in ratings)
            return total / len(ratings)
        return 0.0
    
    def get_rating_count(self):
        """Get total number of ratings"""
        return self.ratings.count()
    
    def is_in_user_collection(self, user, collection_id=None):
        """Check if dataset is in user's collection"""
        if collection_id:
            return self.collections.filter(id=collection_id, user=user).exists()
        return self.collections.filter(user=user).exists()
    
    def get_user_collections(self, user):
        """Get all collections containing this dataset for the user"""
        return UserCollection.objects.filter(user=user, datasets=self)

    def save(self, *args, **kwargs):
        # Auto-detect file type from extension if not set
        if self.dataset_path and not self.file_type:
            ext = os.path.splitext(self.dataset_path)[1].lower()
            type_map = {
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.zip': 'application/zip',
                '.nii': 'application/octet-stream',
                '.dcm': 'application/dicom',
                '.pdf': 'application/pdf',
            }
            self.file_type = type_map.get(ext, 'application/octet-stream')
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class Thumbnail(models.Model):
    image = models.ImageField(
        upload_to=thumbnail_file_path,
        storage=get_thumbnail_storage(),
        max_length=500,
        verbose_name="Thumbnail Image"
    )

    def get_thumbnail_url(self, expiration=86400):
        """Generate URL for thumbnail"""
        if self.image and self.image.name:
            try:
                return self.image.storage.url(self.image.name, expire=expiration)
            except Exception:
                return None
        return None

    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='thumbnails')
    is_primary = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        # Convert medical images to PNG on save
        if self.image:
            name = self.image.name.lower()
            # Check all valid medical extensions
            if any(name.endswith(ext) for ext in ['.dcm', '.dicom', '.nii', '.nii.gz']):
                try:
                    # Use the correct function name
                    png_buffer = convert_to_png(self.image)
                    
                    base_name = os.path.splitext(os.path.basename(self.image.name))[0]
                    
                    # Handle double extensions like .nii.gz
                    if base_name.endswith('.nii'):
                        base_name = os.path.splitext(base_name)[0]
                    
                    new_name = f"thumbnails/{base_name}.png"
                    # Save as PNG
                    self.image.save(new_name, ContentFile(png_buffer.getvalue()), save=False)
                except Exception as e:
                    # Log error but don't break save
                    print(f"Error converting thumbnail: {e}")
        
        # Ensure only one primary thumbnail per dataset
        if self.is_primary:
            Thumbnail.objects.filter(dataset=self.dataset, is_primary=True).exclude(pk=self.pk).update(is_primary=False)
        
        super().save(*args, **kwargs)


class DataRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('manager_review', 'Manager Review'),
        ('director_review', 'Director Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    # Existing fields...
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Add new specific action fields:
    MANAGER_ACTION_CHOICES = [
        ('pending', 'Pending Review'),
        ('recommended', 'Recommended for Director Review'),
        ('rejected', 'Rejected by Manager'),
        ('requested_changes', 'Requested Changes'),
        ('pending_info', 'Awaiting Additional Information'),
        ('approved', 'Approved (Direct Approval)'),
    ]
    
    manager_action = models.CharField(
        max_length=20,
        choices=MANAGER_ACTION_CHOICES,
        default='pending',
        verbose_name="Manager Decision"
    )
    
    manager_action_date = models.DateTimeField(null=True, blank=True)
    manager_action_notes = models.TextField(blank=True, null=True, verbose_name="Manager Action Notes")
    
    DIRECTOR_ACTION_CHOICES = [
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('returned_to_manager', 'Returned to Manager'),
        ('requested_changes', 'Requested Changes'),
        ('pending_info', 'Awaiting Additional Information'),
    ]
    
    director_action = models.CharField(
        max_length=20,
        choices=DIRECTOR_ACTION_CHOICES,
        default='pending',
        verbose_name="Director Decision"
    )
    
    director_action_date = models.DateTimeField(null=True, blank=True)
    director_action_notes = models.TextField(blank=True, null=True, verbose_name="Director Action Notes")
    
    # Add a field to track overall decision (final decision)
    FINAL_DECISION_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('conditional_approval', 'Conditional Approval'),
        ('returned_for_revision', 'Returned for Revision'),
    ]
    
    final_decision = models.CharField(
        max_length=25,
        choices=FINAL_DECISION_CHOICES,
        default='pending',
        verbose_name="Final Decision"
    )
    
    # Add reason fields for better tracking
    REASON_CHOICES = [
        ('', '-- Select Reason --'),
        ('insufficient_info', 'Insufficient Information'),
        ('ethics_concern', 'Ethics Concern'),
        ('methodology_issue', 'Methodology Issue'),
        ('data_not_suitable', 'Data Not Suitable for Purpose'),
        ('budget_constraints', 'Budget/Resource Constraints'),
        ('timing_issue', 'Timing Issue'),
        ('other', 'Other'),
    ]
    
    manager_rejection_reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        blank=True,
        null=True,
        verbose_name="Rejection Reason (Manager)"
    )
    
    director_rejection_reason = models.CharField(
        max_length=20,
        choices=REASON_CHOICES,
        blank=True,
        null=True,
        verbose_name="Rejection Reason (Director)"
    )
    
    # Add escalation field
    ESCALATION_CHOICES = [
        ('none', 'Not Escalated'),
        ('to_director', 'Escalated to Director'),
        ('to_committee', 'Escalated to Ethics Committee'),
        ('to_legal', 'Escalated to Legal Department'),
    ]
    
    escalation_status = models.CharField(
        max_length=20,
        choices=ESCALATION_CHOICES,
        default='none',
        verbose_name="Escalation Status"
    )
    
    escalation_notes = models.TextField(blank=True, null=True, verbose_name="Escalation Notes")
    
    # Existing fields continue...
    institution = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    ethical_approval_no = models.CharField(max_length=100, blank=True, null=True)
    project_title = models.CharField(max_length=255)
    project_description = models.TextField(max_length=500)
    
    # File uploads (local storage)
    form_submission = models.FileField(
        upload_to=form_submission_path,
        storage=get_request_document_storage(),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Form Submission"
    )
    ethical_approval_proof = models.FileField(
        upload_to=ethical_approval_path,
        storage=get_request_document_storage(),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Ethical Approval Proof"
    )

    def get_document_url(self, doc_type='form', expiration=3600):
        """Generate signed URL for request documents"""
        file_field = self.form_submission if doc_type == 'form' else self.ethical_approval_proof
        if file_field and file_field.name:
            try:
                return file_field.url
            except Exception:
                return None
        return None
    
    # Review fields
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_requests'
    )
    data_manager_comment = models.TextField(blank=True, null=True, verbose_name="Manager Notes")
    manager_review_date = models.DateTimeField(blank=True, null=True)
    
    director = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directed_requests'
    )
    director_comment = models.TextField(blank=True, null=True, verbose_name="Director Notes")
    approved_date = models.DateTimeField(blank=True, null=True)
    
    # Download tracking
    download_count = models.PositiveIntegerField(default=0)
    last_download = models.DateTimeField(blank=True, null=True)
    max_downloads = models.PositiveIntegerField(default=3)
    
    # Add timeline tracking
    submitted_to_manager_date = models.DateTimeField(null=True, blank=True)
    submitted_to_director_date = models.DateTimeField(null=True, blank=True)
    decision_date = models.DateTimeField(null=True, blank=True)
    
    # Add priority field
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('normal', 'Normal'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    priority = models.CharField(
        max_length=10,
        choices=PRIORITY_CHOICES,
        default='normal',
        verbose_name="Priority Level"
    )
    
    # Add SLA tracking
    sla_due_date = models.DateTimeField(null=True, blank=True, verbose_name="SLA Due Date")
    sla_status = models.CharField(
        max_length=20,
        choices=[
            ('on_track', 'On Track'),
            ('at_risk', 'At Risk'),
            ('breached', 'Breached'),
        ],
        default='on_track',
        verbose_name="SLA Status"
    )
    
    class Meta:
        ordering = ['-request_date']
        permissions = [
            ('review_datarequest', 'Can review data requests'),
            ('approve_datarequest', 'Can approve data requests'),
            ('escalate_datarequest', 'Can escalate data requests'),
            ('assign_priority', 'Can assign priority to requests'),
        ]
    
    def __str__(self):
        return f"Request #{self.id} - {self.dataset.title}"
    
    # Add helper methods
    def get_manager_action_display_text(self):
        """Get display text for manager action"""
        action_map = {
            'pending': '🔄 Pending Review',
            'recommended': '✅ Recommended',
            'rejected': '❌ Rejected',
            'requested_changes': '📝 Requested Changes',
            'pending_info': '⏳ Awaiting Information',
            'approved': '✅ Approved',
        }
        return action_map.get(self.manager_action, self.get_manager_action_display())
    
    def get_director_action_display_text(self):
        """Get display text for director action"""
        action_map = {
            'pending': '🔄 Pending Review',
            'approved': '✅ Approved',
            'rejected': '❌ Rejected',
            'returned_to_manager': '↩️ Returned to Manager',
            'requested_changes': '📝 Requested Changes',
            'pending_info': '⏳ Awaiting Information',
        }
        return action_map.get(self.director_action, self.get_director_action_display())
    
    def get_final_decision_display_text(self):
        """Get display text for final decision"""
        decision_map = {
            'pending': '🔄 Pending',
            'approved': '✅ Approved',
            'rejected': '❌ Rejected',
            'conditional_approval': '⚠️ Conditional Approval',
            'returned_for_revision': '↩️ Returned for Revision',
        }
        return decision_map.get(self.final_decision, self.get_final_decision_display())
    
    def get_priority_badge_class(self):
        """Get CSS class for priority badge"""
        classes = {
            'low': 'bg-gray-100 text-gray-800',
            'normal': 'bg-blue-100 text-blue-800',
            'high': 'bg-yellow-100 text-yellow-800',
            'urgent': 'bg-red-100 text-red-800',
        }
        return classes.get(self.priority, 'bg-gray-100 text-gray-800')
    
    def get_status_badge_class(self):
        """Get CSS class for status badge"""
        classes = {
            'pending': 'bg-gray-100 text-gray-800',
            'manager_review': 'bg-yellow-100 text-yellow-800',
            'director_review': 'bg-blue-100 text-blue-800',
            'approved': 'bg-green-100 text-green-800',
            'rejected': 'bg-red-100 text-red-800',
        }
        return classes.get(self.status, 'bg-gray-100 text-gray-800')
    
    def calculate_sla_due_date(self):
        """Calculate SLA due date based on priority"""
        from datetime import timedelta
        
        sla_days = {
            'low': 14,      # 2 weeks
            'normal': 7,    # 1 week
            'high': 3,      # 3 days
            'urgent': 1,    # 1 day
        }
        
        if self.submitted_to_manager_date:
            days = sla_days.get(self.priority, 7)
            self.sla_due_date = self.submitted_to_manager_date + timedelta(days=days)
            self.save()
    
    def update_sla_status(self):
        """Update SLA status based on due date"""
        if not self.sla_due_date:
            self.sla_status = 'on_track'
            return
        
        now = timezone.now()
        time_remaining = self.sla_due_date - now
        
        if time_remaining.total_seconds() > 86400:  # > 1 day
            self.sla_status = 'on_track'
        elif time_remaining.total_seconds() > 0:
            self.sla_status = 'at_risk'
        else:
            self.sla_status = 'breached'
        
        self.save()
    
    def get_processing_time(self):
        """Calculate processing time"""
        if not self.decision_date or not self.request_date:
            return None
        
        processing_time = self.decision_date - self.request_date
        return processing_time.days
    
    def can_download(self):
        return self.status == 'approved' and self.download_count < self.max_downloads
    
    def record_download(self):
        self.download_count += 1
        self.last_download = timezone.now()
        self.save()
    
    def save(self, *args, **kwargs):
        # Auto-calculate SLA dates
        if self.pk is None or 'priority' in self.__dict__:
            self.calculate_sla_due_date()
        
        # Update SLA status
        self.update_sla_status()
        
        # Set submission dates
        if self.status == 'manager_review' and not self.submitted_to_manager_date:
            self.submitted_to_manager_date = timezone.now()
        
        if self.status == 'director_review' and not self.submitted_to_director_date:
            self.submitted_to_director_date = timezone.now()
        
        # Set decision date when final decision is made
        if self.final_decision in ['approved', 'rejected', 'conditional_approval'] and not self.decision_date:
            self.decision_date = timezone.now()
        
        super().save(*args, **kwargs)


# Add this at the bottom of your models.py, after the DataRequest class
from django.db.models.signals import post_save
from django.dispatch import receiver
import os
import shutil

@receiver(post_save, sender=Dataset)
def move_dataset_files(sender, instance, created, **kwargs):
    """Move preview and README files from temp folders to permanent location"""
    if created:
        updated_fields = []
        
        # Fix preview file
        if instance.preview_file and 'temp_' in instance.preview_file.name:
            old_path = instance.preview_file.path
            if os.path.exists(old_path):
                filename = os.path.basename(old_path)
                name, ext = os.path.splitext(filename)
                
                # IMPORTANT: Extract base name WITHOUT the UUID suffix
                # Remove the last 9 chars which are the UUID (_ + 8 hex chars)
                if '_' in name and len(name.split('_')[-1]) == 8:
                    base_name = '_'.join(name.split('_')[:-1])  # Remove UUID
                else:
                    base_name = name
                
                # Generate new filename with dataset ID
                new_filename = f"{base_name}_{instance.id}{ext}"
                new_dir = f"/app/media/previews/{instance.id}"
                new_path = f"{new_dir}/{new_filename}"
                
                os.makedirs(new_dir, exist_ok=True)
                shutil.move(old_path, new_path)
                
                instance.preview_file.name = f"previews/{instance.id}/{new_filename}"
                updated_fields.append('preview_file')
                
                # Auto-detect preview type
                if ext.lower() in ['.csv']:
                    instance.preview_type = 'csv'
                elif ext.lower() in ['.xlsx', '.xls']:
                    instance.preview_type = 'excel'
                elif ext.lower() in ['.json']:
                    instance.preview_type = 'json'
                updated_fields.append('preview_type')
        
        # Fix README file
        if instance.readme_file and 'temp_' in instance.readme_file.name:
            old_path = instance.readme_file.path
            if os.path.exists(old_path):
                filename = os.path.basename(old_path)
                name, ext = os.path.splitext(filename)
                
                # Extract base name without UUID
                if '_' in name and len(name.split('_')[-1]) == 8:
                    base_name = '_'.join(name.split('_')[:-1])
                else:
                    base_name = name
                
                new_filename = f"{base_name}_{instance.id}{ext}"
                new_dir = f"/app/media/readmes/{instance.id}"
                new_path = f"{new_dir}/{new_filename}"
                
                os.makedirs(new_dir, exist_ok=True)
                shutil.move(old_path, new_path)
                
                instance.readme_file.name = f"readmes/{instance.id}/{new_filename}"
                updated_fields.append('readme_file')
        
        if updated_fields:
            instance.save(update_fields=updated_fields)


@receiver(post_save, sender=DataRequest)
def move_request_documents(sender, instance, created, **kwargs):
    """Move request documents from temp folder to permanent location"""
    if created:
        updated_fields = []
        
        # Fix form_submission
        if instance.form_submission and 'temp_' in instance.form_submission.name:
            old_path = instance.form_submission.path
            if os.path.exists(old_path):
                filename = os.path.basename(old_path)
                name, ext = os.path.splitext(filename)
                
                # Extract base name (remove temp prefix and UUID)
                # Expected format: form_temp_a1b2c3_d4e5f6g7.pdf
                # We want: form_123_d4e5f6g7.pdf
                if '_temp_' in name:
                    # Split at _temp_ and keep the part before and after
                    parts = name.split('_temp_')
                    if len(parts) == 2:
                        prefix = parts[0]  # "form"
                        rest = parts[1]    # "a1b2c3_d4e5f6g7"
                        # Keep the last UUID part
                        uuid_part = rest.split('_')[-1] if '_' in rest else rest
                        base_name = f"{prefix}_{instance.id}_{uuid_part}"
                    else:
                        base_name = name
                else:
                    base_name = name
                
                new_filename = f"{base_name}{ext}"
                new_dir = f"/app/media/request-documents/{instance.id}"
                new_path = f"{new_dir}/{new_filename}"
                
                os.makedirs(new_dir, exist_ok=True)
                shutil.move(old_path, new_path)
                
                instance.form_submission.name = f"request-documents/{instance.id}/{new_filename}"
                updated_fields.append('form_submission')
        
        # Fix ethical_approval_proof
        if instance.ethical_approval_proof and 'temp_' in instance.ethical_approval_proof.name:
            old_path = instance.ethical_approval_proof.path
            if os.path.exists(old_path):
                filename = os.path.basename(old_path)
                name, ext = os.path.splitext(filename)
                
                # Extract base name (remove temp prefix and UUID)
                if '_temp_' in name:
                    parts = name.split('_temp_')
                    if len(parts) == 2:
                        prefix = parts[0]  # "ethical"
                        rest = parts[1]    # "a1b2c3_d4e5f6g7"
                        uuid_part = rest.split('_')[-1] if '_' in rest else rest
                        base_name = f"{prefix}_{instance.id}_{uuid_part}"
                    else:
                        base_name = name
                else:
                    base_name = name
                
                new_filename = f"{base_name}{ext}"
                new_dir = f"/app/media/request-documents/{instance.id}"
                new_path = f"{new_dir}/{new_filename}"
                
                os.makedirs(new_dir, exist_ok=True)
                shutil.move(old_path, new_path)
                
                instance.ethical_approval_proof.name = f"request-documents/{instance.id}/{new_filename}"
                updated_fields.append('ethical_approval_proof')
        
        if updated_fields:
            instance.save(update_fields=updated_fields)

class DatasetRating(models.Model):
    """Model for users to rate datasets"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='ratings')
    rating = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
        default=0.0
    )
    comment = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'dataset']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username} rated {self.dataset.title}: {self.rating}"


class UserCollection(models.Model):
    """Model for users to save datasets to collections"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    datasets = models.ManyToManyField(Dataset, related_name='collections', blank=True)
    is_public = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user', 'name']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.username}'s collection: {self.name}"


class DatasetReport(models.Model):
    """Model for reporting issues with datasets"""
    REPORT_TYPES = [
        ('inaccurate', 'Inaccurate Information'),
        ('corrupt', 'Corrupt File'),
        ('copyright', 'Copyright Issue'),
        ('privacy', 'Privacy Concern'),
        ('offensive', 'Offensive Content'),
        ('other', 'Other Issue'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name='reports')
    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField()
    screenshot = models.ImageField(upload_to='reports/', blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    admin_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Report on {self.dataset.title} by {self.user.username if self.user else 'Anonymous'}"