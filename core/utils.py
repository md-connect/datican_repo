from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)

def send_donation_acknowledgment(donation):
    """Send acknowledgment email to the donor"""
    subject = f"Thank You for Your Interest in Supporting DATICAN"
    
    context = {
        'donation': donation,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'support_email': settings.SUPPORT_EMAIL,
    }
    
    try:
        html_message = render_to_string('core/emails/donation_acknowledgment.html', context)
        text_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[donation.email],
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        logger.info(f"Donation acknowledgment email sent to {donation.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send donation acknowledgment email: {e}")
        return False

def send_donation_notification_to_staff(donation):
    """Send notification about new donation to director and data manager"""
    subject = f"New Donation Interest from {donation.first_name} {donation.last_name}"
    
    context = {
        'donation': donation,
        'site_name': settings.SITE_NAME,
        'admin_url': f"{settings.SITE_URL}/admin/core/donation/{donation.id}/change/",
    }
    
    # Get staff emails
    staff_emails = []
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    # Get director emails
    directors = User.objects.filter(role='director', is_active=True).values_list('email', flat=True)
    staff_emails.extend(directors)
    
    # Get data manager emails
    managers = User.objects.filter(role='data_manager', is_active=True).values_list('email', flat=True)
    staff_emails.extend(managers)
    
    # Add admin emails as fallback
    if not staff_emails:
        admins = User.objects.filter(is_staff=True, is_active=True).values_list('email', flat=True)
        staff_emails.extend(admins)
    
    if not staff_emails:
        staff_emails = [settings.SUPPORT_EMAIL]
    
    try:
        html_message = render_to_string('core/emails/donation_staff_notification.html', context)
        text_message = strip_tags(html_message)
        
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=list(set(staff_emails)),  # Remove duplicates
        )
        email.attach_alternative(html_message, "text/html")
        email.send()
        logger.info(f"Donation staff notification sent to {len(staff_emails)} recipients")
        return True
    except Exception as e:
        logger.error(f"Failed to send donation staff notification: {e}")
        return False
        
def send_welcome_email(user, social_signup=False):
    """
    Send welcome email to newly verified users
    """
    subject = f"Welcome to {settings.SITE_NAME}! 🎉"
    
    context = {
        'user': user,
        'site_name': settings.SITE_NAME,
        'site_url': settings.SITE_URL,
        'support_email': settings.SUPPORT_EMAIL,
        'social_signup': social_signup,
    }
    
    # Render HTML content
    html_message = render_to_string('account/email/welcome_email.html', context)
    plain_message = strip_tags(html_message)  # Fallback for plain text
    
    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )