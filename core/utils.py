from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils.html import strip_tags

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