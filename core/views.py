from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import SignUpForm, LoginForm, CombinedProfileForm, PasswordChangeForm
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
# views.py
from django.conf import settings
from django.shortcuts import redirect
from django.contrib.auth import login
from django.contrib.auth.models import User
import requests
from urllib.parse import urlencode

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

# core/views.py (update your signup_view)
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    next_url = request.GET.get('next', '')
    
    if request.method == 'POST':
        form = SignUpForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            
            # Handle redirect to next page
            next_url = request.POST.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect(next_url)
            return redirect('home')
        else:
            # Add form errors to messages
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = SignUpForm()
    
    return render(request, 'core/signup.html', {'form': form, 'next_url': next_url})

def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    # Handle both GET and POST
    next_url = request.GET.get('next') or request.POST.get('next') or ''

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            if user is not None:
                login(request, user)

                # Redirect to next_url if it's valid
                if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                    return redirect(next_url)
                return redirect('home')
            else:
                form.add_error(None, 'Invalid credentials')
    else:
        form = LoginForm()

    return render(request, 'core/login.html', {'form': form, 'next_url': next_url})

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