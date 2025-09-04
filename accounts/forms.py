# accounts/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

class CustomUserCreationForm(UserCreationForm):
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
        model = get_user_model()
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
        
        # Remove username field if it exists in the form
        if 'username' in self.fields:
            del self.fields['username']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if get_user_model().objects.filter(email=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        
        # Set username to email if your model requires a username field
        # If your CustomUser model doesn't have username field, remove this
        if hasattr(user, 'username'):
            user.username = self.cleaned_data['email']
        
        if commit:
            user.save()
        return user