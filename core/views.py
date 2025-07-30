from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from .forms import SignUpForm, LoginForm, ProfileForm
from django.contrib.auth.decorators import login_required
from datasets.models import Dataset, Thumbnail
from allauth.socialaccount.models import SocialAccount
from allauth.account.utils import perform_login
from allauth.account import app_settings
from allauth.socialaccount.helpers import complete_social_login
from django.http import HttpResponseRedirect
from django.db.models import Prefetch

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

    
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('home')
        
    next_url = request.GET.get('next', '')
    
    if request.method == 'POST':
        form = SignUpForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            
            # Handle redirect to next page
            next_url = request.POST.get('next', '')
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts=None):
                return redirect(next_url)
            return redirect('home')
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
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=request.user.profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your profile has been updated!')
            return redirect('profile')
    else:
        form = ProfileForm(instance=request.user.profile)
    
    return render(request, 'core/profile.html', {'form': form})

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