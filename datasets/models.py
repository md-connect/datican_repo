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
    file = models.FileField(upload_to='datasets/')
    dimension = models.CharField(
        max_length=10,
        choices=DIMENSION_CHOICES,
        blank=True,
        null=True
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
    size = models.CharField(max_length=20, blank=True)
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
        upload_to='dataset_previews/',
        blank=True,
        null=True,
        help_text="Upload a CSV/Excel file for preview (optional)"
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
        upload_to='dataset_readmes/%Y/%m/%d/',
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
        
        # Auto-detect preview type from file extension
        if self.preview_file and not self.preview_type:
            file_name = self.preview_file.name.lower()
            if file_name.endswith('.csv'):
                self.preview_type = 'csv'
            elif file_name.endswith(('.xlsx', '.xls')):
                self.preview_type = 'excel'
            elif file_name.endswith('.json'):
                self.preview_type = 'json'
        # Handle README file processing
        if self.readme_file and hasattr(self.readme_file, 'file'):
            try:
                self.readme_file_size = self.readme_file.size
                
                # Extract content for text-based files
                file_extension = os.path.splitext(self.readme_file.name)[1].lower()
                
                if file_extension in ['.md', '.txt', '.rst', '.markdown']:
                    try:
                        # Read and decode the file
                        self.readme_file.seek(0)
                        content_bytes = self.readme_file.read()
                        
                        # Try different encodings
                        for encoding in ['utf-8', 'latin-1', 'cp1252']:
                            try:
                                content = content_bytes.decode(encoding)
                                self.readme_content = content[:50000]  # Limit size
                                break
                            except UnicodeDecodeError:
                                continue
                        
                        # If all encodings fail, store as binary string
                        if not self.readme_content:
                            self.readme_content = "Binary content - cannot preview"
                            
                    except Exception as e:
                        self.readme_content = f"Error reading file: {str(e)}"
                
                elif file_extension == '.pdf':
                    self.readme_content = "PDF file - download to view"
                
                self.readme_updated = timezone.now()
                
            except Exception as e:
                print(f"Error processing README: {str(e)}")
                self.readme_content = f"Error: {str(e)}"

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
    
    # Updated fields
    institution = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True, null=True)  # NEW FIELD
    ethical_approval_no = models.CharField(max_length=100, blank=True, null=True)  # NEW FIELD
    project_title = models.CharField(max_length=255)
    project_description = models.TextField(max_length=500)
    
    # File uploads
    form_submission = models.FileField(upload_to='requests/forms/')
    ethical_approval_proof = models.FileField(  # NEW FIELD
        upload_to='requests/ethical_approvals/',
        blank=True,
        null=True,
        help_text="Upload proof of ethical approval (PDF, JPG, PNG)"
    )
    
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
    manager_action = models.CharField(
        max_length=20,
        choices=(('recommended', 'Recommended'), ('rejected', 'Rejected')),
        blank=True,
        null=True
    )
    
    director = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='directed_requests'
    )
    director_comment = models.TextField(blank=True, null=True, verbose_name="Director Notes")
    approved_date = models.DateTimeField(blank=True, null=True)
    director_action = models.CharField(
        max_length=20,
        choices=(('approved', 'Approved'), ('rejected', 'Rejected')),
        blank=True,
        null=True
    )
    
    # Download tracking
    download_count = models.PositiveIntegerField(default=0)
    last_download = models.DateTimeField(blank=True, null=True)
    max_downloads = models.PositiveIntegerField(default=3)
    
    class Meta:
        ordering = ['-request_date']
        permissions = [
            ('review_datarequest', 'Can review data requests'),
            ('approve_datarequest', 'Can approve data requests'),
        ]
    
    def __str__(self):
        return f"Request #{self.id} - {self.dataset.title}"
    
    def can_download(self):
        return self.status == 'approved' and self.download_count < self.max_downloads
    
    def record_download(self):
        self.download_count += 1
        self.last_download = timezone.now()
        self.save()
    
    def get_form_submission_filename(self):
        """Extract filename from form_submission path"""
        if self.form_submission:
            return os.path.basename(self.form_submission.name)
        return None
    
    def get_ethical_approval_proof_filename(self):  # NEW METHOD
        """Extract filename from ethical_approval_proof path"""
        if self.ethical_approval_proof:
            return os.path.basename(self.ethical_approval_proof.name)
        return None

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