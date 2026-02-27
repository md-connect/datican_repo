from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import CustomAllauthSignupForm, LoginForm, CombinedProfileForm, PasswordChangeForm
from django.contrib.auth.decorators import login_required
from datasets.models import Dataset, Thumbnail
from allauth.socialaccount.models import SocialAccount
from allauth.account.utils import perform_login
from allauth.account import app_settings
from allauth.socialaccount.helpers import complete_social_login
from django.http import HttpResponseRedirect
from django.db.models import Prefetch
from .models import UserProfile
from django.contrib.auth import update_session_auth_hash
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
import requests
from urllib.parse import urlencode
from allauth.account.views import LoginView
from django.urls import reverse
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from allauth.account.views import SignupView
from allauth.account.views import ConfirmEmailView 
from .models import TeamMember


class CustomSignupView(SignupView):
    """Custom signup view that uses Allauth but our custom template"""
    template_name = 'core/signup.html'
    form_class = CustomAllauthSignupForm
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['default_redirect'] = reverse('redirect_after_login')
        return context
    
    def form_valid(self, form):
        # This saves the user and sends verification email
        response = super().form_valid(form)
        
        # Add a message to tell user to check email
        messages.success(
            self.request, 
            'You have successfully registered on DATICAN Repository! '
            'Please check your email to verify your account. '
            'The verification link will expire in 1 hour.'
        )
        
        return response
    
    def get_success_url(self):
        # After signup, redirect to a "please verify" page
        return reverse('account_email_verification_sent')

class CustomLoginView(LoginView):
    """Custom login view that uses Allauth but our custom template"""
    template_name = 'core/login.html'  # Your custom template
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Add your custom context variables
        context['default_redirect'] = reverse('redirect_after_login')
        return context
    
    def form_valid(self, form):
        # Call the parent form_valid to handle login
        response = super().form_valid(form)
        
        # Add any custom logic here if needed
        user = self.request.user
        messages.success(self.request, f'Welcome back, {user.first_name or user.email}!')
        
        return response
    
    def get_success_url(self):
        # Get the 'next' parameter from POST or GET
        next_url = self.request.POST.get('next') or self.request.GET.get('next') or ''
        
        # Validate the next URL
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return next_url
        
        # Otherwise, use our custom redirect_after_login
        return reverse('redirect_after_login')

class CustomConfirmEmailView(ConfirmEmailView):
    """Handles email confirmation and 'verification sent' page."""

    def get(self, request, *args, **kwargs):
        key = kwargs.get("key", None)

        if key:
            # Key provided → normal confirmation
            return super().get(request, *args, **kwargs)

        if request.user.is_authenticated:
            # Already logged in, no key → redirect
            messages.info(request, "Your email is already verified.")
            return redirect("home")

        # Base URL, not logged in → render custom "verification sent" template
        context = {
            "site_name": "DATICAN Repository",
            "site_url": "https://repo.datican.org",
            "support_email": "support@datican.org",
            "expiration_days": 3,  # or settings.EMAIL_CONFIRMATION_EXPIRY_DAYS
        }
        return render(request, "account/verification_sent.html", context)

def google_login(request):
    # Redirect to Google OAuth2
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'response_type': 'code',
        'scope': 'openid email profile',
        'access_type': 'online',
    }
    
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return redirect(auth_url)

def google_callback(request):
    code = request.GET.get('code')
    
    if not code:
        return redirect('login')
    
    # Exchange code for tokens
    token_url = 'https://oauth2.googleapis.com/token'
    token_data = {
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }
    
    token_response = requests.post(token_url, data=token_data)
    token_json = token_response.json()
    access_token = token_json.get('access_token')
    
    # Get user info from Google
    user_info_url = 'https://www.googleapis.com/oauth2/v3/userinfo'
    headers = {'Authorization': f'Bearer {access_token}'}
    user_info_response = requests.get(user_info_url, headers=headers)
    user_info = user_info_response.json()
    
    # Extract user information
    email = user_info.get('email')
    first_name = user_info.get('given_name', '')
    last_name = user_info.get('family_name', '')
    
    # Find or create user
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        username = email.split('@')[0]
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name
        )
        user.save()
    
    # Log the user in
    login(request, user)
    return redirect('home')
    
def home(request):
    featured_datasets = Dataset.objects.order_by('-rating')[:4].prefetch_related(
        Prefetch(
            'thumbnails',
            queryset=Thumbnail.objects.filter(is_primary=True),
            to_attr='primary_thumbnails'
        ),
        Prefetch(
            'thumbnails',
            queryset=Thumbnail.objects.all(),
            to_attr='all_thumbnails'
        )
    )

    for dataset in featured_datasets:
        if dataset.primary_thumbnails:
            dataset.primary_thumbnail = dataset.primary_thumbnails[0]
        elif dataset.all_thumbnails:
            dataset.primary_thumbnail = dataset.all_thumbnails[0]
        else:
            dataset.primary_thumbnail = None

    dataset_count = Dataset.objects.count()

    return render(request, 'home.html', {
        'featured_datasets': featured_datasets,
        'dataset_count': dataset_count,
    })

def partners_view(request):
    """View for partner universities page"""
    return render(request, 'partners.html')

from django.shortcuts import render
from .models import TeamMember

def team_view(request):
    team_members = TeamMember.objects.all().order_by('order', 'first_name')
    
    context = {
        'team_members': team_members,
        'total_members': team_members.count(),
    }
    return render(request, 'team.html', context)


def verification_sent(request):
    """Page shown after registration, asking user to verify email"""
    return render(request, 'core/verification_sent.html')

@login_required
def profile_view(request):
    """
    Combined profile view for updating both User and UserProfile
    """
    # Get or create user profile
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = CombinedProfileForm(
            request.POST, 
            request.FILES,
            user=request.user,
            profile=profile
        )
        
        if form.is_valid():
            try:
                form.save()
                messages.success(request, 'Your profile has been updated successfully!')
                return redirect('profile')
            except Exception as e:
                messages.error(request, f'An error occurred: {str(e)}')
        else:
            # Display form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = CombinedProfileForm(
            user=request.user,
            profile=profile
        )
    
    return render(request, 'core/profile.html', {
        'form': form,
        'profile': profile
    })


@login_required
def logout_view(request):
    logout(request)
    return redirect('home')

def social_login_callback(request):
    if 'socialaccount_state' not in request.session:
        return redirect('login')
    
    # Store next URL in session before processing social login
    next_url = request.GET.get('next', '')
    if next_url:
        request.session['social_login_next'] = next_url
    
    ret = complete_social_login(request)
    
    # Check if this was a new social signup
    if request.session.pop('social_signup_complete', False):
        messages.success(
            request, 
            'Welcome to DATICAN Repository! Please check your email to verify your account. '
            'The verification link will expire in 1 hour.'
        )
        return redirect('account_email_verification_sent')
    
    if isinstance(ret, HttpResponseRedirect):
        # Check if we have a stored next URL
        next_url = request.session.pop('social_login_next', None)
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
            return redirect(next_url)
        return ret
    
    messages.error(request, "Error during social login")
    return redirect('login')
    
@login_required
def change_password(request):
    """Simple password change view"""
    if request.method == 'POST':
        # Get form data directly from request
        old_password = request.POST.get('old_password', '')
        new_password1 = request.POST.get('new_password1', '')
        new_password2 = request.POST.get('new_password2', '')
        
        # Validate the old password first
        if not request.user.check_password(old_password):
            messages.error(request, 'Your current password was entered incorrectly. Please enter it again.')
            return render(request, 'core/change_password.html')
        
        # Check if new passwords match
        if new_password1 != new_password2:
            messages.error(request, 'The two password fields didn\'t match.')
            return render(request, 'core/change_password.html')
        
        # Check password strength (simple validation)
        if len(new_password1) < 8:
            messages.error(request, 'Password must be at least 8 characters long.')
            return render(request, 'core/change_password.html')
        
        if new_password1.isdigit():
            messages.error(request, 'Password cannot be entirely numeric.')
            return render(request, 'core/change_password.html')
        
        # If all validations pass, change the password
        try:
            request.user.set_password(new_password1)
            request.user.save()
            
            # Update session to prevent logout
            update_session_auth_hash(request, request.user)
            
            messages.success(request, 'Your password has been changed successfully!')
            return redirect('profile')
            
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
    
    return render(request, 'core/change_password.html')


@login_required
def password_change_done(request):
    """Password change success page"""
    messages.success(request, 'Your password has been changed successfully!')
    return redirect('profile')