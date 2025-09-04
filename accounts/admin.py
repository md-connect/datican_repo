from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _
from accounts.models import CustomUser

class CustomUserAdmin(UserAdmin):
    # Display fields in the user list view
    list_display = ('email', 'first_name', 'last_name', 'get_role_display', 'is_staff', 'date_joined')
    
    # Fields that should be read-only in admin
    readonly_fields = ('last_login', 'date_joined')
    
    # Add role to list filter
    list_filter = ('role', 'is_staff', 'is_active')
    
    # Update fieldsets to include role
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'profile_picture')}),
        ('Role & Permissions', {
            'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
            'description': _('Note: Superusers automatically have all permissions regardless of role.')
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    # Update add fieldsets
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'email', 
                'first_name',
                'last_name',
                'password1', 
                'password2',
                'role',
                'is_staff', 
                'is_active'
            ),
        }),
    )
    
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    filter_horizontal = ('groups', 'user_permissions',)
    
    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        
        # Non-superusers can't change superuser status or roles of other users
        if not request.user.is_superuser:
            return readonly_fields + ('is_superuser', 'role', 'groups', 'user_permissions')
        
        # Superusers can't remove their own superuser status
        if obj and obj == request.user:
            return readonly_fields + ('is_superuser',)
            
        return readonly_fields
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Non-superusers can only see users with the same or lower role
        if not request.user.is_superuser:
            if request.user.role == 'admin':
                return qs.exclude(role__in=['admin']).exclude(is_superuser=True)
            elif request.user.role == 'data_manager':
                return qs.filter(role='user')
            elif request.user.role == 'director':
                return qs.filter(role__in=['user', 'data_manager'])
        return qs
    
    def get_role_display(self, obj):
        return obj.get_role_display()
    get_role_display.short_description = 'Role'
    
    def save_model(self, request, obj, form, change):
        """Override save to assign role permissions"""
        super().save_model(request, obj, form, change)
        obj.assign_role_permissions()

admin.site.register(CustomUser, CustomUserAdmin)