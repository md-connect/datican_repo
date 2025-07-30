from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from .models import UserProfile
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model


User = get_user_model()

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()
    
@receiver(user_signed_up)
def populate_profile(sociallogin, user, **kwargs):
    data = sociallogin.account.extra_data
    picture = data.get('picture')
    name = data.get('name', '').split()
    first_name = name[0] if name else ''
    last_name = name[1] if len(name) > 1 else ''
    
    user.first_name = first_name
    user.last_name = last_name
    user.save()

    UserProfile.objects.get_or_create(user=user, defaults={
        'avatar': picture,
        # You can save institution later via profile edit
    })
