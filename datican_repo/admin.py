# datica_repo/admin.py 
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

# Unregister the default User admin if it's already registered
admin.site.unregister(User)

# Re-register User with the standard UserAdmin
admin.site.register(User, UserAdmin)