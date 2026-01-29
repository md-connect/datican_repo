# core/models.py
from django.db import models
from django.conf import settings
from django.core.validators import FileExtensionValidator
import os

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
        return f"{self.user.username}'s Profile"
    
    @property
    def has_complete_profile(self):
        """Check if user has filled in essential profile info"""
        return all([
            self.bio,
            self.organization,
            self.position
        ])

# Signals to create/update profile automatically
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

User = get_user_model()

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