# In your existing file (probably adapters.py or similar)
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialApp
from django.contrib.sites.models import Site
from django.conf import settings
from django.core.exceptions import ValidationError
from accounts.models import CustomUser
from allauth.account.adapter import DefaultAccountAdapter
from core.utils import send_welcome_email  # Import your welcome email function
import logging
from urllib.parse import quote
from django.urls import reverse



logger = logging.getLogger(__name__)

class CustomAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Enable signup through your custom views
        return True  # Changed from False to True
    
    def send_confirmation_mail(self, request, emailconfirmation, signup):
        """
        Override to URL-encode the confirmation key in the email
        This prevents email clients from truncating URLs with : characters
        """
        logger.info(f"📧 Custom send_confirmation_mail called for {emailconfirmation.email_address.email}")
        
        # Get the current site
        current_site = Site.objects.get_current()
        
        # Get the original key
        key = emailconfirmation.key
        
        # First, generate the URL with the unencoded key (for reverse)
        unencoded_url = request.build_absolute_uri(
            reverse('account_confirm_email', args=[key])
        )
        
        # Then, replace the key part with the encoded version
        encoded_key = quote(key, safe='')
        activate_url = unencoded_url.replace(key, encoded_key, 1)
        
        logger.info(f"🔗 Encoded URL: {activate_url}")
        
        # Get expiration days - FIXED METHOD NAME
        expiration_days = 1
        
        # Prepare context for the email template
        context = {
            'user': emailconfirmation.email_address.user,
            'activate_url': activate_url,
            'key': encoded_key,
            'expiration_days': expiration_days,
            'site_name': current_site.name,
            'site_domain': current_site.domain,
            'site_url': settings.SITE_URL,
            'support_email': settings.SUPPORT_EMAIL,
        }
        
        # Send the email using your HTML template
        self.send_mail('account/email/email_confirmation', 
                    emailconfirmation.email_address.email, 
                    context)
        
        logger.info(f"✅ Custom confirmation email sent to {emailconfirmation.email_address.email}")
        
class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def get_app(self, request, provider, client_id=None):
        """
        FIX for MultipleObjectsReturned error in MySQL/AllAuth.
        Database shows 1 row but AllAuth sometimes sees multiple due to race conditions.
        """
        try:
            # Get current site
            site = Site.objects.get_current()
            logger.debug(f"CustomSocialAccountAdapter.get_app: provider={provider}, site={site.id}")
            
            # Try the standard query first
            try:
                app = SocialApp.objects.get(provider=provider, sites=site)
                logger.debug(f"✅ Standard query success: app_id={app.id}")
                return app
                
            except SocialApp.MultipleObjectsReturned:
                # This should never happen since database has only 1 row
                logger.error(f"❌ MultipleObjectsReturned for {provider} on site {site.id}")
                
                # Debug: Log what's actually in database
                from django.db import connection
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT sa.id, sa.name, COUNT(*) as count
                        FROM socialaccount_socialapp sa
                        JOIN socialaccount_socialapp_sites sas ON sa.id = sas.socialapp_id
                        WHERE sa.provider = %s AND sas.site_id = %s
                        GROUP BY sa.id, sa.name
                    """, [provider, site.id])
                    results = cursor.fetchall()
                    logger.error(f"RAW SQL shows: {results}")
                
                # Fix: Return first app (there should be only one)
                apps = SocialApp.objects.filter(provider=provider, sites=site)
                logger.warning(f"Returning first of {apps.count()} apps: {apps.first().id}")
                return apps.first()
                
            except SocialApp.DoesNotExist:
                logger.error(f"No {provider} app found for site {site.domain}")
                raise
                
        except Exception as e:
            logger.error(f"Error in CustomSocialAccountAdapter.get_app: {e}", exc_info=True)
            # Fall back to parent implementation
            return super().get_app(request, provider, client_id)

    def pre_social_login(self, request, sociallogin):
        user = sociallogin.user
        if user.id:
            return
        
        email = user.email
        if email:
            try:
                existing_user = CustomUser.objects.get(email=email)
                # Attach this social login to the existing user
                sociallogin.connect(request, existing_user)
            except CustomUser.DoesNotExist:
                pass

    def populate_user(self, request, sociallogin, data):
        user = super().populate_user(request, sociallogin, data)
        extra_data = sociallogin.account.extra_data

        user.email = extra_data.get('email', '')
        user.first_name = extra_data.get('given_name', '')
        user.last_name = extra_data.get('family_name', '')
        
        profile_picture = extra_data.get('picture')  # URL to the profile picture
        if profile_picture:
            user.profile_picture = profile_picture  # This will save the URL

        return user

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        extra_data = sociallogin.account.extra_data

        user.email = user.email or extra_data.get('email', '')
        user.first_name = user.first_name or extra_data.get('given_name', '')
        user.last_name = user.last_name or extra_data.get('family_name', '')

        profile_picture = extra_data.get('picture')
        if profile_picture:
            user.profile_picture = profile_picture

        user.save()
        
        # Check if this is a new user (just created via social login)
        if sociallogin.is_existing is False:
            # This is a first-time Google login (registration)
            logger.info(f"New social signup: {user.email}")
            
            # Google already verified the email, so mark as verified immediately
            email_address = user.emailaddress_set.first()
            if email_address:
                email_address.verified = True
                email_address.save()
                logger.info(f"Email {user.email} marked as verified for social signup")
            
            # Send welcome email directly (no verification needed)
            try:
                send_welcome_email(user, social_signup=True)
                logger.info(f"Welcome email sent to {user.email}")
            except Exception as e:
                logger.error(f"Failed to send welcome email to {user.email}: {e}")
            
            # Optional: Store a flag in session for a success message
            request.session['social_signup_complete'] = True
        
        return user

    def get_connect_redirect_url(self, request, socialaccount):
        """Return URL to redirect to after connecting a social account"""
        return '/'