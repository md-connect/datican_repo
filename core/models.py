# core/models.py
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
import os
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.validators import EmailValidator
from django.utils import timezone

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
        ('Ms.', 'Ms.'),
        ('Dr.', 'Dr.'),
        ('Prof.', 'Prof.'),
        ('Assoc. Prof.', 'Associate Prof.'),
    ]
    
    title = models.CharField(max_length=20, choices=TITLE_CHOICES, default='Mr.')
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    position = models.CharField(max_length=255, help_text="Job position or role")
    bio = models.TextField(help_text="Short biography")
    
    # Profile image
    profile_image = models.ImageField(upload_to='team/', blank=True, null=True)
    
    # Social links
    google_scholar_url = models.URLField(blank=True, null=True)
    linkedin_url = models.URLField(blank=True, null=True)
    researchgate_url = models.URLField(blank=True, null=True)
    twitter_url = models.URLField(blank=True, null=True)  # Optional
    github_url = models.URLField(blank=True, null=True)   # Optional
    
    # Display order
    order = models.PositiveIntegerField(default=0, help_text="Display order (lower numbers appear first)")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'first_name', 'last_name']
        verbose_name = "Team Member"
        verbose_name_plural = "Team Members"
    
    def __str__(self):
        return f"{self.get_title_display()} {self.first_name} {self.last_name}"
    
    @property
    def full_name(self):
        return f"{self.get_title_display()} {self.first_name} {self.last_name}"

class Donation(models.Model):
    DONATION_TYPE_CHOICES = [
        ('financial', 'Financial Donation'),
        ('data', 'Data Donation'),
    ]
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(validators=[EmailValidator()])
    phone_number = models.CharField(max_length=20)
    address = models.TextField(blank=True, null=True, help_text="Optional")
    
    # Donation Type
    donation_type = models.JSONField(default=list, help_text="Selected donation types")
    
    # Message
    message = models.TextField(help_text="Description of how you'd like to help")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True, null=True)
    
    # Status
    is_contacted = models.BooleanField(default=False)
    contacted_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True, help_text="Internal notes")
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Donation"
        verbose_name_plural = "Donations"
    
    def __str__(self):
        return f"Donation from {self.first_name} {self.last_name} - {self.created_at.strftime('%Y-%m-%d')}"
    
    def get_donation_types_display(self):
        if not self.donation_type:
            return "Not specified"
        types = []
        for dt in self.donation_type:
            for choice in self.DONATION_TYPE_CHOICES:
                if choice[0] == dt:
                    types.append(choice[1])
        return ", ".join(types)