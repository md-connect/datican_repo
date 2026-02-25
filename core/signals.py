from allauth.account.signals import user_signed_up, email_confirmed
from django.dispatch import receiver
from .models import UserProfile
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

@receiver(email_confirmed)
def handle_email_confirmation(sender, request, email_address, **kwargs):
    """
    Send welcome email when a user confirms their email address
    """
    user = email_address.user
    logger.info(f"✅ email_confirmed signal triggered for {email_address.email}")
    
    subject = f"Welcome to {settings.SITE_NAME}! 🎉"
    
    context = {
        'user': user,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'support_email': settings.SUPPORT_EMAIL,
    }
    
    try:
        html_message = render_to_string('account/email/welcome_email.html', context)
        text_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        logger.info(f"Welcome email sent to {user.email}")
    except Exception as e:
        logger.error(f"Failed to send welcome email to {user.email}: {e}")

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """
    Create or get user profile when user is saved.
    Uses get_or_create to avoid duplicate key errors.
    """
    profile, created = UserProfile.objects.get_or_create(user=instance)
    if created:
        logger.info(f"User profile created for {instance.email}")
    else:
        logger.info(f"User profile already exists for {instance.email}")

@receiver(user_signed_up)
def populate_profile(sender, request, user, sociallogin=None, **kwargs):
    """
    Handle user signup - populates profile based on signup type.
    For social logins (Google), populate from Google data.
    For email signups, just ensure profile exists.
    """
    # Always ensure profile exists (though post_save should handle this)
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Only process social login data if this is a social signup
    if sociallogin and sociallogin.account.provider == 'google':
        data = sociallogin.account.extra_data
        picture = data.get('picture')
        
        # Set name from Google data
        user.first_name = data.get('given_name', '')
        user.last_name = data.get('family_name', '')
        user.save()
        
        # Update profile with avatar
        if picture:
            profile.avatar = picture
            profile.save()
        
        logger.info(f"Google signup processed for {user.email}")
    else:
        logger.info(f"Email signup processed for {user.email}")