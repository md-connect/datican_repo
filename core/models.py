# core/models.py
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
import os
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator

User = get_user_model()

def user_avatar_path(instance, filename):
    """Generate path for user avatar"""
    ext = filename.split('.')[-1].lower()
    filename = f'user_{instance.user.id}_avatar.{ext}'
    return os.path.join('avatars', filename)

class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE,
        related_name='profile'
    )
    avatar = models.ImageField(
        upload_to=user_avatar_path,
        default='avatars/default_avatar.png',
        validators=[FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'gif'])],
        blank=True
    )
    bio = models.TextField(blank=True, max_length=1000)
    organization = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=100, blank=True)
    position = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'
    
    def __str__(self):
        return f"{self.user.email}'s Profile"
    
    @property
    def has_complete_profile(self):
        """Check if user has filled in essential profile info"""
        return all([
            self.bio,
            self.organization,
            self.position
        ])

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a profile for new users"""
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save user profile when user is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()

class TeamMember(models.Model):
    """Model for team members displayed on the Our Team page"""
    
    TITLE_CHOICES = [
        ('Mr.', 'Mr.'),
        ('Mrs.', 'Mrs.'),
        ('Dr.', 'Dr.'),
        ('Assoc. Prof.', 'Associate Prof.'),
        ('Prof.', 'Prof.'),
    ]
    
    title = models.CharField(
        max_length=20,
        choices=TITLE_CHOICES,
        default='Mr.',
        help_text="Title (e.g., Dr., Prof.)"
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    professional_titles = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Additional professional titles (e.g., PhD, MD, MSc)"
    )
    position = models.CharField(
        max_length=255,
        help_text="Job position or role (e.g., Principal Investigator, Data Scientist)"
    )
    department = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Department or unit"
    )
    institution = models.CharField(
        max_length=255,
        help_text="University, organization, or affiliation"
    )
    other_info = models.TextField(
        blank=True,
        null=True,
        help_text="Additional information like research interests, bio, etc."
    )
    
    # ORDER FIELD - This is what you asked for
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order (lower numbers appear first)"
    )
    
    # Optional fields for enhancement
    profile_image = models.ImageField(
        upload_to='team/',
        blank=True,
        null=True,
        help_text="Profile photo (optional)"
    )
    email = models.EmailField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    google_scholar_url = models.URLField(blank=True, null=True)
    researchgate_url = models.URLField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'last_name', 'first_name']  # Sort by order first, then name
        verbose_name = "Team Member"
        verbose_name_plural = "Team Members"
    
    def __str__(self):
        return f"{self.get_title_display()} {self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        """Return the full name with title"""
        return f"{self.get_title_display()} {self.first_name} {self.last_name}"
    
    @property
    def short_name(self):
        """Return first name and last initial"""
        if self.last_name:
            return f"{self.first_name} {self.last_name[0]}."
        return self.first_name