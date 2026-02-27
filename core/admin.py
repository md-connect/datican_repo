from django.contrib import admin
from .models import TeamMember

@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['order', 'full_name', 'position', 'created_at']
    list_editable = ['order']
    list_filter = ['position']
    search_fields = ['first_name', 'last_name', 'position', 'bio']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('title', 'first_name', 'last_name', 'profile_image')
        }),
        ('Professional', {
            'fields': ('position', 'bio')
        }),
        ('Social Links', {
            'fields': ('linkedin_url', 'google_scholar_url', 'researchgate_url', 'twitter_url', 'github_url'),
            'classes': ('collapse',)
        }),
        ('Display Settings', {
            'fields': ('order',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )