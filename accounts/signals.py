# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import Group
from .models import CustomUser

@receiver(post_save, sender=CustomUser)
def assign_role_permissions(sender, instance, created, **kwargs):
    """Automatically assign users to appropriate groups based on their role"""
    instance.assign_role_permissions()