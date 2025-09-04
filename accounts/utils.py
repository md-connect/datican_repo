# accounts/utils.py
def has_role(user, role_name):
    """Check if user has a specific role, considering superuser status"""
    if user.is_superuser:
        return True  # Superusers can do anything
    return user.role == role_name

def is_data_manager(user):
    """Check if user is a data manager or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'data_manager')

def is_director(user):
    """Check if user is a director or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'director')

def is_admin(user):
    """Check if user is an admin or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'admin')