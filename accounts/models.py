# accounts/models.py
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager, Group, Permission
from django.db import models
from django.utils.translation import gettext_lazy as _

class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('role', 'admin')  # Default superuser role
        return self.create_user(email, password, **extra_fields)

class CustomUser(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = (
        ('user', 'User'),
        ('admin', 'Admin'),
        ('data_manager', 'Data Manager'),
        ('director', 'Director'),
    )
    
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    
    # Add role field
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default='user',
        verbose_name='Role/User Type'
    )
    
    # Change this to handle both URLs and file uploads
    profile_picture = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="URL or path to profile picture"
    )
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    last_login = models.DateTimeField(blank=True, null=True, verbose_name="last login")
    date_joined = models.DateTimeField(auto_now_add=True, verbose_name="date joined")

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    def get_display_name(self):
        """Return a display name for the user."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email

    def __str__(self):
        return self.email
    
    def save(self, *args, **kwargs):
        # Set is_staff based on role (but don't override for superusers)
        if not self.is_superuser:
            self.is_staff = self.role in ['admin', 'data_manager', 'director']
        super().save(*args, **kwargs)
    
    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()
    
    def get_short_name(self):
        """Return the short name for the user."""
        return self.first_name
    
    def get_role_display(self):
        """Get role display name, considering superuser status"""
        if self.is_superuser:
            role_display = dict(self.ROLE_CHOICES).get(self.role, self.role)
            return f"Superuser ({role_display})"
        return dict(self.ROLE_CHOICES).get(self.role, self.role)
    
    def assign_role_permissions(self):
        """Assign user to appropriate group based on role"""
        if self.is_superuser:
            # Superusers keep all groups
            return
            
        # Clear all groups first
        self.groups.clear()
        
        # Assign to appropriate group based on role
        group_name = None
        if self.role == 'admin':
            group_name = 'Admins'
        elif self.role == 'data_manager':
            group_name = 'Data Managers'
        elif self.role == 'director':
            group_name = 'Directors'
        
        if group_name:
            try:
                group = Group.objects.get(name=group_name)
                self.groups.add(group)
            except Group.DoesNotExist:
                # Group doesn't exist yet, will be created by management command
                pass