from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.conf import settings
from django.core.exceptions import ValidationError
from accounts.models import CustomUser
from allauth.account.adapter import DefaultAccountAdapter

class CustomAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Disable allauth's regular signup since we're using our custom view
        return False

class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
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
        return user