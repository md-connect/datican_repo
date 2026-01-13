# datasets/decorators.py
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from functools import wraps

def data_manager_required(view_func):
    """
    Decorator for views that checks if the user is a data manager.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has data manager role or permission
        if hasattr(request.user, 'role') and request.user.role == 'data_manager':
            return view_func(request, *args, **kwargs)
        
        # Alternative: Check for permission
        if request.user.has_perm('datasets.review_datarequest'):
            return view_func(request, *args, **kwargs)
        
        # Alternative: Check for group membership
        if request.user.groups.filter(name='Data Managers').exists():
            return view_func(request, *args, **kwargs)
        
        raise PermissionDenied("You must be a data manager to access this page.")
    
    return _wrapped_view

def director_required(view_func):
    """
    Decorator for views that checks if the user is a director.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Check if user has director role or permission
        if hasattr(request.user, 'role') and request.user.role == 'director':
            return view_func(request, *args, **kwargs)
        
        # Alternative: Check for permission
        if request.user.has_perm('datasets.approve_datarequest'):
            return view_func(request, *args, **kwargs)
        
        # Alternative: Check for group membership
        if request.user.groups.filter(name='Directors').exists():
            return view_func(request, *args, **kwargs)
        
        # Alternative: Check for staff status (directors are usually staff)
        if request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        raise PermissionDenied("You must be a director to access this page.")
    
    return _wrapped_view

# Alternative using user_passes_test decorator
def is_data_manager(user):
    return (user.is_authenticated and 
            (hasattr(user, 'role') and user.role == 'data_manager' or
             user.has_perm('datasets.review_datarequest') or
             user.groups.filter(name='Data Managers').exists()))

def is_director(user):
    return (user.is_authenticated and 
            (hasattr(user, 'role') and user.role == 'director' or
             user.has_perm('datasets.approve_datarequest') or
             user.groups.filter(name='Directors').exists() or
             user.is_staff))


def admin_required(view_func):
    """
    Decorator that allows access to directors, data_managers, and superusers
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        
        # Superusers can access everything
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        
        # Check if user qualifies as admin using existing logic
        if (is_director(request.user) or is_data_manager(request.user)):
            return view_func(request, *args, **kwargs)
        
        raise PermissionDenied("Admin access required.")
    
    return _wrapped_view