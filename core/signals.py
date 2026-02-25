from allauth.account.signals import user_signed_up
from django.dispatch import receiver
from .models import UserProfile
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from allauth.account.signals import email_confirmed
from core.utils import send_welcome_email
from django.core.mail import send_mail
from django.template.loader import render_to_string



User = get_user_model()

@receiver(email_confirmed)
def handle_email_confirmation(sender, request, email_address, **kwargs):
    """
    Send welcome email when a user confirms their email address
    """
    user = email_address.user
    send_welcome_email(user, social_signup=False)

@receiver(email_confirmed)
def send_welcome_email(sender, request, email_address, **kwargs):
    user = email_address.user
    subject = f"Welcome to {settings.SITE_NAME}! 🎉"
    
    context = {
        'user': user,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'support_email': settings.SUPPORT_EMAIL,
    }
    
    html_message = render_to_string('account/email/welcome_email.html', context)
    send_mail(
        subject=subject,
        message='',  # Plain text version optional
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )
    
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
