# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from .models import UserProfile
from django.contrib.auth.forms import PasswordChangeForm, SetPasswordForm
from django.contrib.auth import password_validation

User = get_user_model()

class SignUpForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg'})
    )
    last_name = forms.CharField(
        max_length=30, 
        required=True,
        widget=forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg'})
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary focus:border-primary'})
    )

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Customize password field widgets
        self.fields['password1'].widget = forms.PasswordInput(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary focus:border-primary'
        })
        self.fields['password2'].widget = forms.PasswordInput(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary focus:border-primary'
        })
        
        # Remove username field if it exists
        if 'username' in self.fields:
            del self.fields['username']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        # If your CustomUser model has a username field but you want to use email
        if hasattr(user, 'username'):
            user.username = self.cleaned_data['email']  # Set username to email
        
        if commit:
            user.save()
            # Create UserProfile for the new user
            UserProfile.objects.get_or_create(user=user)
        return user

class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary focus:border-primary'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-primary focus:border-primary'
        })
    )

class CombinedProfileForm(forms.Form):
    """Combined form that handles both User and UserProfile models"""
    # User fields
    first_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'First Name'
        })
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Last Name'
        })
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Email Address'
        })
    )
    
    # UserProfile fields
    avatar = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'accept': 'image/*'
        })
    )
    bio = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 4,
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors resize-none',
            'placeholder': 'Tell us about yourself, your research interests, etc.'
        })
    )
    organization = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'e.g., University of Cambridge, Google AI, etc.'
        })
    )
    location = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'e.g., London, UK'
        })
    )
    position = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'e.g., Research Scientist, PhD Student, etc.'
        })
    )
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.profile = kwargs.pop('profile', None)
        super().__init__(*args, **kwargs)
        
        # Initialize with existing data
        if self.user:
            self.fields['first_name'].initial = self.user.first_name
            self.fields['last_name'].initial = self.user.last_name
            self.fields['email'].initial = self.user.email
        
        if self.profile:
            self.fields['avatar'].initial = self.profile.avatar
            self.fields['bio'].initial = self.profile.bio
            self.fields['organization'].initial = self.profile.organization
            self.fields['location'].initial = self.profile.location
            self.fields['position'].initial = self.profile.position
    
    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if avatar:
            # Validate file size (5MB limit)
            if avatar.size > 5 * 1024 * 1024:
                raise ValidationError("Profile picture must be less than 5MB.")
            
            # Validate file type
            valid_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif']
            if avatar.content_type not in valid_types:
                raise ValidationError("Please upload a valid image file (JPG, PNG, GIF).")
        
        return avatar
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if self.user and User.objects.filter(email=email).exclude(id=self.user.id).exists():
            raise ValidationError("A user with this email already exists.")
        return email
    
    def save(self):
        """Save both User and UserProfile"""
        # Save User
        if self.user:
            self.user.first_name = self.cleaned_data['first_name']
            self.user.last_name = self.cleaned_data['last_name']
            self.user.email = self.cleaned_data['email']
            self.user.save()
        
        # Save UserProfile
        if self.profile:
            # Handle avatar separately to avoid deleting when not provided
            avatar = self.cleaned_data.get('avatar')
            if avatar is not None:  # Only update if a new avatar was provided
                self.profile.avatar = avatar
            
            self.profile.bio = self.cleaned_data.get('bio', '')
            self.profile.organization = self.cleaned_data.get('organization', '')
            self.profile.location = self.cleaned_data.get('location', '')
            self.profile.position = self.cleaned_data.get('position', '')
            self.profile.save()
        
        return self.user, self.profile

class CustomPasswordChangeForm(PasswordChangeForm):
    """Custom password change form with better styling"""
    old_password = forms.CharField(
        label="Current Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'current-password',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Enter your current password'
        }),
    )
    
    new_password1 = forms.CharField(
        label="New Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Enter new password'
        }),
        help_text=password_validation.password_validators_help_text_html(),
    )
    
    new_password2 = forms.CharField(
        label="Confirm New Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Confirm new password'
        }),
    )

class CustomSetPasswordForm(SetPasswordForm):
    """Custom set password form for password reset"""
    new_password1 = forms.CharField(
        label="New Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Enter new password'
        }),
        help_text=password_validation.password_validators_help_text_html(),
    )
    
    new_password2 = forms.CharField(
        label="Confirm New Password",
        strip=False,
        widget=forms.PasswordInput(attrs={
            'autocomplete': 'new-password',
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors',
            'placeholder': 'Confirm new password'
        }),
    )