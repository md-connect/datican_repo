# core/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

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
    
# FIXED: Use CustomUser model instead of UserProfile
class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'profile_picture']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg'
            }),
            'profile_picture': forms.FileInput(attrs={
                'class': 'w-full px-3 py-2 border rounded-lg'
            }),
        }