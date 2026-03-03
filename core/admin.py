from django.contrib import admin
from .models import TeamMember
from django.contrib import admin
from .models import Donation

@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    list_display = ['id', 'full_name', 'email', 'phone_number', 'donation_types', 'created_at', 'is_contacted']
    list_filter = ['donation_type', 'is_contacted', 'created_at']
    search_fields = ['first_name', 'last_name', 'email', 'phone_number', 'message']
    readonly_fields = ['created_at', 'ip_address', 'user_agent']
    list_editable = ['is_contacted']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email', 'phone_number', 'address')
        }),
        ('Donation Details', {
            'fields': ('donation_type', 'message')
        }),
        ('Status', {
            'fields': ('is_contacted', 'contacted_at', 'notes')
        }),
        ('Metadata', {
            'fields': ('created_at', 'ip_address', 'user_agent'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['mark_as_contacted']
    
    def full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"
    full_name.short_description = "Name"
    
    def donation_types(self, obj):
        return obj.get_donation_types_display()
    donation_types.short_description = "Donation Types"
    
    def mark_as_contacted(self, request, queryset):
        queryset.update(is_contacted=True, contacted_at=timezone.now())
    mark_as_contacted.short_description = "Mark selected as contacted"


@admin.register(TeamMember)
class TeamMemberAdmin(admin.ModelAdmin):
    list_display = ['order', 'full_name', 'position', 'created_at']
    list_editable = ['order']
    list_display_links = ['full_name']
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