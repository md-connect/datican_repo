# datasets/models.py
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
from .storage import get_dataset_storage, get_preview_storage, get_readme_storage, get_thumbnail_storage, get_request_document_storage
import uuid
import logging
logger = logging.getLogger(__name__)


def dataset_file_path(instance, filename):
    """Generate unique file path for dataset files in B2"""
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4().hex}.{ext}"
    return f"{instance.id}/{filename}"

def preview_file_path(instance, filename):
    """Generate file path for preview files"""
    ext = filename.split('.')[-1]
    filename = f"preview_{uuid.uuid4().hex}.{ext}"
    return f"{instance.id}/{filename}"

def readme_file_path(instance, filename):
    """Generate file path for README files"""
    ext = filename.split('.')[-1]
    filename = f"readme_{uuid.uuid4().hex}.{ext}"
    return f"{instance.id}/{filename}"

def thumbnail_file_path(instance, filename):
    """Generate unique path for thumbnail images in B2"""
    ext = filename.split('.')[-1]
    filename = f"thumb_{uuid.uuid4().hex}.{ext}"
    return f"{instance.dataset_id}/{filename}"

def request_document_path(instance, filename):
    """Generate unique path for request documents in B2"""
    ext = filename.split('.')[-1]
    filename = f"request_{instance.id}_{uuid.uuid4().hex[:8]}.{ext}"
    return f"requests/{instance.id}/{filename}"

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
    
    file = models.FileField(
        upload_to=dataset_file_path,
        storage=settings.DATASET_STORAGE,
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Dataset File"
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

    # Add this field for preview file
    preview_file = models.FileField(
        upload_to=preview_file_path,
        storage=get_preview_storage(),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Preview File"
    )
    
    # Add preview type field
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
        upload_to=readme_file_path,
        storage=get_readme_storage(),
        null=True,
        blank=True,
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
    
    # Add B2 metadata fields
    b2_file_id = models.CharField(max_length=255, null=True, blank=True)
    b2_file_info = models.JSONField(null=True, blank=True)
    # File size and type - keep these
    size = models.BigIntegerField(null=True, blank=True, verbose_name="File Size (bytes)")
    file_type = models.CharField(max_length=100, null=True, blank=True)

    def get_download_url(self, expiration=300):
        """Generate signed download URL for approved users"""
        if self.file and self.file.name:
            try:
                return self.file.storage.url(self.file.name, expire=expiration)
            except Exception as e:
                logger.error(f"Error generating download URL: {e}")
                return None
        return None
    
    def get_preview_url(self, expiration=3600):
        """Generate signed URL for preview files"""
        if self.preview_file and self.preview_file.name:
            try:
                return self.preview_file.storage.url(self.preview_file.name, expire=expiration)
            except Exception:
                return None
        return None
    
    def get_readme_url(self, expiration=3600):
        """Generate signed URL for README files"""
        if self.readme_file and self.readme_file.name:
            try:
                return self.readme_file.storage.url(self.readme_file.name, expire=expiration)
            except Exception:
                return None
        return None


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
        # Auto-detect file type from extension
        if self.file and not self.file_type:
            ext = os.path.splitext(self.file.name)[1].lower()
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
        """Generate signed URL for thumbnail"""
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
    
    # File uploads
    form_submission = models.FileField(
        upload_to=request_document_path,
        storage=get_request_document_storage(),
        max_length=500,
        null=True,
        blank=True,
        verbose_name="Form Submission"
    )
    ethical_approval_proof = models.FileField(
        upload_to=request_document_path,
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
                return file_field.storage.url(file_field.name, expire=expiration)
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
        
        if time_remaining.days > 1:
            self.sla_status = 'on_track'
        elif time_remaining.days >= 0:
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