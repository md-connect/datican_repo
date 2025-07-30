from django.db import models
from django.conf import settings

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    avatar = models.ImageField(upload_to='avatars/', default='default_avatar.png')
    bio = models.TextField(blank=True)
    organization = models.TextField(blank=True)
    location = models.TextField(blank=True)
    position = models.TextField(blank=True)
    
    def __str__(self):
        return self.user.username
