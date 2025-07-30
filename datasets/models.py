# datasets/models.py
from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError
import os
from django.core.files.base import ContentFile
from .utils import convert_to_png

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
    TASK_CHOICES = [
        ('classification', 'Classification'),
        ('regression', 'Regression'),
        ('segmentation', 'Segmentation'),
        ('detection', 'Detection'),
        ('prediction', 'Prediction'),
        ('other', 'Other'),
    ]
    
    ATTRIBUTE_CHOICES = [
        ('image', 'Image'),
        ('multimodal', 'Multimodal'),
    ]
    
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('dcm', 'DICOM'),
        ('nii', 'NIfTI'),
        ('png', 'PNG'),
        ('jpg', 'JPG'),
        ('h5', 'HDF5'),
    ]
    
    title = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=100)
    file = models.FileField(upload_to='datasets/')
    upload_date = models.DateTimeField(auto_now_add=True)
    update_date = models.DateTimeField(auto_now=True)
    size = models.CharField(max_length=20, blank=True)
    rating = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(10.0)],
        default=0.0
    )
    download_count = models.PositiveIntegerField(default=0)
    owner = models.CharField(
        max_length=100,
        default='admin',
        editable=False)
    
    # Track who actually uploaded it
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    
    # New fields for filtering
    task = models.CharField(
        max_length=50, 
        choices=TASK_CHOICES,
        default='other'
    )
    attributes = models.JSONField(
        default=list,
        help_text="List of attributes describing the data"
    )
    format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        blank=True,
        null=True
    )

    def save(self, *args, **kwargs):
        # Auto-calculate size before saving
        if not self.size and self.file:
            size_bytes = self.file.size
            if size_bytes < 1024 * 1024:
                self.size = f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                self.size = f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                self.size = f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        
        # Auto-detect format from file extension if not set
        if self.file and not self.format:
            ext = os.path.splitext(self.file.name)[1][1:].lower()
            if ext in dict(self.FORMAT_CHOICES):
                self.format = ext
            elif ext == 'gz':  # Handle .nii.gz case
                base_ext = os.path.splitext(os.path.splitext(self.file.name)[0])[1][1:].lower()
                if base_ext == 'nii':
                    self.format = 'nii'
        
        super().save(*args, **kwargs)
        
    def __str__(self):
        return self.title

class Thumbnail(models.Model):
    image = models.FileField(
        upload_to='thumbnails/',
        validators=[validate_thumbnail]
    )
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
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE)
    request_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Updated fields to match new form
    institution = models.CharField(max_length=255, blank=True, null=True)
    project_title = models.CharField(max_length=255, blank=True, null=True)
    project_details = models.TextField(blank=True, null=True)
    project_description = models.TextField(max_length=500, blank=True, null=True)  # Approximately 100 words
    
    # File fields
    document = models.FileField(upload_to='requests/documents/')
    form_submission = models.FileField(upload_to='requests/forms/')
    
    # Review fields
    data_manager_comment = models.TextField(blank=True, null=True)
    director_comment = models.TextField(blank=True, null=True)
    approved_date = models.DateTimeField(blank=True, null=True)
    
    # Download tracking
    download_count = models.PositiveIntegerField(default=0)
    last_download = models.DateTimeField(blank=True, null=True)
    max_downloads = models.PositiveIntegerField(default=3)
    
    # Reviewers
    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_requests'
    )
    director = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directed_requests'
    )
    
    class Meta:
        ordering = ['-request_date']
        permissions = [
            ('review_datarequest', 'Can review data requests'),
            ('approve_datarequest', 'Can approve data requests'),
        ]
    
    def __str__(self):
        return f"Request #{self.id} - {self.dataset.title}"
    
    def can_download(self):
        return (
            self.status == 'approved' and 
            self.download_count < self.max_downloads
        )
    
    def record_download(self):
        self.download_count += 1
        self.last_download = timezone.now()
        self.save()
    
    def send_status_notification(self):
        from django.core.mail import send_mail
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        subject = f"Data Request Update: {self.get_status_display()}"
        
        # Email to requester
        html_message = render_to_string('datasets/email/status_update.html', {
            'request': self,
            'user': self.user
        })
        plain_message = strip_tags(html_message)
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [self.user.email],
            html_message=html_message
        )
        
        # Email to managers/directors if needed
        if self.status in ['manager_review', 'director_review']:
            recipients = []
            if self.status == 'manager_review':
                managers = User.objects.filter(groups__name='Data Managers')
                recipients = [m.email for m in managers if m.email]
            elif self.status == 'director_review':
                directors = User.objects.filter(groups__name='Data Directors')
                recipients = [d.email for d in directors if d.email]
            
            if recipients:
                html_message = render_to_string('datasets/email/review_request.html', {
                    'request': self
                })
                plain_message = strip_tags(html_message)
                send_mail(
                    f"Review Required: Data Request #{self.id}",
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    recipients,
                    html_message=html_message
                )