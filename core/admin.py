from django.contrib import admin
from .models import TeamMember

@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['order', 'full_name_list', 'position', 'institution', 'created_at']
    list_display_links = ['full_name_list']
    list_editable = ['order']  # This lets you edit order directly in the list view
    list_filter = ['title', 'institution', 'department']
    search_fields = ['first_name', 'last_name', 'position', 'institution', 'email']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('title', 'first_name', 'last_name', 'professional_titles', 'profile_image')
        }),
        ('Professional Details', {
            'fields': ('position', 'department', 'institution', 'other_info')
        }),
        ('Display Settings', {
            'fields': ('order',),  # Order field here
            'description': 'Control the display order (lower numbers appear first)'
        }),
        ('Contact & Social', {
            'fields': ('email', 'linkedin_url', 'google_scholar_url', 'researchgate_url'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def full_name_list(self, obj):
        return obj.full_name
    full_name_list.short_description = "Name"
    full_name_list.admin_order_field = ['order', 'last_name', 'first_name']