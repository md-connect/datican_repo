# datasets/admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport
from django import forms
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from .utilities import can_manage_datasets, is_data_manager, is_director, is_admin
from datasets.utils.email_service import EmailService

@admin.action(description='Send approval emails to selected requests')
def send_approval_emails(modeladmin, request, queryset):
    for data_request in queryset.filter(status='approved'):
        EmailService.send_approval_email(data_request)
    modeladmin.message_user(request, f"Approval emails sent for {queryset.count()} requests.")

@admin.action(description='Send status update emails')
def send_status_update_emails(modeladmin, request, queryset):
    for data_request in queryset:
        EmailService.send_status_update_email(data_request, 'previous', request.user)
    modeladmin.message_user(request, f"Status update emails sent for {queryset.count()} requests.")

class ThumbnailInline(admin.TabularInline):
    model = Thumbnail
    extra = 1
    max_num = 5
    fields = ('image', 'is_primary', 'preview')
    readonly_fields = ('preview',)
    
    def preview(self, instance):
        if instance.image:
            return mark_safe(f'<img src="{instance.image.url}" style="max-height: 100px;" />')
        return "No image"
    preview.short_description = 'Preview'
    
class DatasetAdminForm(forms.ModelForm):
    class Meta:
        model = Dataset
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'preview_file': forms.FileInput(attrs={
                'accept': '.csv,.xlsx,.xls,.json',
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make preview_type field readonly since it's auto-detected
        if 'preview_type' in self.fields:
            self.fields['preview_type'].widget.attrs['readonly'] = True
            self.fields['preview_type'].help_text = 'Auto-detected from preview file'

@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    form = DatasetAdminForm
    inlines = [ThumbnailInline]
    list_display = ['title', 'modality', 'format', 'no_of_subjects', 'upload_date', 'rating', 'thumbnail_preview', 'owner', 'has_preview', 'has_readme']
    list_filter = ['modality', 'format', 'upload_date', 'preview_type']
    search_fields = ['title', 'description', 'body_part']
    readonly_fields = (
        'readme_updated', 
        'readme_file_size', 
        'size', 
        'download_count', 
        'upload_date', 
        'update_date', 
        'thumbnail_preview', 
        'preview_type', 
        'owner',
        'b2_file_id',
        'b2_file_info',
        'file_download_link',
        'preview_download_link',
        'readme_download_link',
    )
    
    # UPDATED: Add preview file section
    fieldsets = (
        ('Basic Information', {
            'fields': ('title', 'description', 'uploaded_by', 'owner')
        }),
        ('Medical Information', {
            'fields': ('modality', 'body_part', 'no_of_subjects')
        }),
        ('File Information', {
            'fields': ('file', 'format')
        }),
        ('Preview File', {
            'fields': ('preview_file', 'preview_type'),
            'description': 'Upload a CSV/Excel/JSON file for data preview (optional). File type will be auto-detected.'
        }),
        ('README Documentation', { 
            'fields': ('readme_file', 'readme_content', 'readme_updated', 'readme_file_size'),
            'description': 'Upload README documentation (MD, TXT, PDF, RST, Markdown)'
        }),
        ('Statistics', {
            'fields': ('rating', 'download_count', 'size'),
        }),
        ('System Information', {
            'fields': ('upload_date', 'update_date'),
            'classes': ('collapse',)
        }),
        ('B2 Cloud Storage', {
            'fields': ('b2_file_id', 'b2_file_info', 'file_download_link'),
            'classes': ('collapse',),
        }),
    )
    
    # Add a property for admin list display
    def has_readme(self, obj):
        return bool(obj.readme_file) or bool(obj.readme_content)
    has_readme.boolean = True
    has_readme.short_description = 'Has README'

    def thumbnail_preview(self, obj):
        primary = obj.thumbnails.filter(is_primary=True).first()
        if primary and primary.image:
            try:
                # Generate signed URL for thumbnail (24h expiry)
                thumb_url = primary.image.storage.url(primary.image.name, expire=86400)
                return mark_safe(f'<img src="{thumb_url}" style="max-height: 100px;" />')
            except Exception:
                return "Error loading thumbnail"
        return "No thumbnail"
    thumbnail_preview.allow_tags = True
    thumbnail_preview.short_description = 'Primary Thumbnail'
    
    def has_preview(self, obj):
        if obj.preview_file:
            return mark_safe(
                f'<span style="color: green;">✓</span> {obj.get_preview_type_display()}'
            )
        return mark_safe('<span style="color: red;">✗</span>')
    has_preview.short_description = 'Preview'
    has_preview.admin_order_field = 'preview_type'
    
    def file_download_link(self, obj):
        """Generate temporary admin download link"""
        if obj.file and obj.file.name:
            try:
                url = obj.get_download_url(expiration=3600)
                return format_html('<a href="{}" target="_blank">📥 Download File (expires in 1 hour)</a>', url)
            except Exception as e:
                return format_html('<span style="color: red;">Error: {}</span>', str(e))
        return "No file"
    file_download_link.short_description = 'Download Link'
    
    def b2_file_info_display(self, obj):
        """Pretty display of B2 file information"""
        if obj.b2_file_id:
            return format_html(
                '<span title="{}">📁 {}</span>',
                obj.b2_file_id,
                obj.b2_file_id.split('/')[-1] if '/' in obj.b2_file_id else obj.b2_file_id
            )
        return "—"
    b2_file_info_display.short_description = 'B2 File'

    def preview_download_link(self, obj):
        if obj.preview_file:
            url = obj.get_preview_url(expiration=3600)
            return format_html('<a href="{}" target="_blank">View Preview</a>', url)
        return "No preview"
    preview_download_link.short_description = 'Preview Link'
    
    def readme_download_link(self, obj):
        if obj.readme_file:
            url = obj.get_readme_url(expiration=3600)
            return format_html('<a href="{}" target="_blank">View README</a>', url)
        return "No README"
    readme_download_link.short_description = 'README Link'

    def save_model(self, request, obj, form, change):
        # First, let the model save handle the file uploads
        super().save_model(request, obj, form, change)
        
        # Then handle preview_type detection
        if 'preview_file' in form.changed_data and obj.preview_file:
            # ... set preview_type code ...
            Dataset.objects.filter(pk=obj.pk).update(preview_type=obj.preview_type)
        
        # Then store B2 file info
        if obj.file and obj.file.name:
            try:
                storage = obj.file.storage
                if hasattr(storage, 'bucket'):
                    obj.b2_file_id = f"{storage.bucket.name}/{obj.file.name}"
                    Dataset.objects.filter(pk=obj.pk).update(
                        b2_file_id=obj.b2_file_id,
                        b2_file_info={'updated_at': timezone.now().isoformat()}
                    )
            except Exception:
                pass

    def has_add_permission(self, request):
        return can_manage_datasets(request.user)
    
    def has_change_permission(self, request, obj=None):
        return can_manage_datasets(request.user)
    
    def has_delete_permission(self, request, obj=None):
        return can_manage_datasets(request.user)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.role == 'data_manager' and not request.user.is_superuser:
            # Data managers can only edit datasets they own
            return qs.filter(owner=request.user.username)
        return qs

# ADD THESE NEW ADMIN CLASSES FOR THE NEW MODELS
@admin.register(DatasetRating)
class DatasetRatingAdmin(admin.ModelAdmin):
    list_display = ['user', 'dataset', 'rating', 'created_at', 'short_comment']
    list_filter = ['rating', 'created_at']
    search_fields = ['user__email', 'dataset__title', 'comment']
    readonly_fields = ['created_at', 'updated_at']
    
    def short_comment(self, obj):
        if obj.comment:
            return obj.comment[:50] + ('...' if len(obj.comment) > 50 else '')
        return "—"
    short_comment.short_description = 'Comment'

@admin.register(UserCollection)
class UserCollectionAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'dataset_count', 'is_public', 'created_at']
    list_filter = ['is_public', 'created_at']
    search_fields = ['name', 'user__email', 'description']
    readonly_fields = ['created_at', 'updated_at']
    filter_horizontal = ['datasets']
    
    def dataset_count(self, obj):
        return obj.datasets.count()
    dataset_count.short_description = '# Datasets'

@admin.register(DatasetReport)
class DatasetReportAdmin(admin.ModelAdmin):
    list_display = ['dataset', 'user', 'report_type', 'status', 'created_at']
    list_filter = ['report_type', 'status', 'created_at']
    search_fields = ['dataset__title', 'user__email', 'description']
    readonly_fields = ['created_at', 'updated_at', 'resolved_at']
    
    fieldsets = (
        ('Report Information', {
            'fields': ('user', 'dataset', 'report_type', 'status')
        }),
        ('Details', {
            'fields': ('description', 'screenshot')
        }),
        ('Admin', {
            'fields': ('admin_notes', 'resolved_at'),
            'classes': ('collapse',)
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def save_model(self, request, obj, form, change):
        if change and obj.status == 'resolved' and not obj.resolved_at:
            obj.resolved_at = timezone.now()
        super().save_model(request, obj, form, change)

# Keep your existing DataRequestAdmin unchanged
@admin.register(DataRequest)
class DataRequestAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'user',
        'dataset_short',
        'project_title_short',
        'colored_status',
        'manager_short',
        'director_short',
        'manager_notes_short',
        'director_notes_short',
        'request_date_short',
        'review_action',  # Add review action column
        'manager_review_date_short',  # Add manager review date
        'approved_date_short',         # Add approval date
    )
    
    list_filter = ('status', 'request_date', 'manager', 'director')
    search_fields = (
        'user__email',
        'dataset__title',
        'project_title',
        'institution',
        'data_manager_comment',
        'director_comment'
    )
    readonly_fields = ('request_date', 'approved_date', 'last_download', 'download_count')
    list_per_page = 20
    list_select_related = ('user', 'dataset', 'manager', 'director')

    def manager_review_date_short(self, obj):
        return obj.manager_review_date.strftime('%Y-%m-%d') if obj.manager_review_date else "—"
    manager_review_date_short.short_description = 'Manager Review'
    manager_review_date_short.admin_order_field = 'manager_review_date'

    def approved_date_short(self, obj):
        return obj.approved_date.strftime('%Y-%m-%d') if obj.approved_date else "—"
    approved_date_short.short_description = 'Approved'
    approved_date_short.admin_order_field = 'approved_date'

    def colored_status_badge(self, obj):
        colors = {
            'pending': 'status-pending',
            'manager_review': 'status-manager_review',
            'director_review': 'status-director_review',
            'approved': 'status-approved',
            'rejected': 'status-rejected',
        }
        return format_html(
            '<span class="status-badge {}">{}</span>',
            colors.get(obj.status, ''),
            obj.get_status_display()
        )
    colored_status_badge.short_description = 'Status'
    colored_status_badge.admin_order_field = 'status'

    # Custom display methods
    def dataset_short(self, obj):
        return obj.dataset.title[:30] + ('...' if len(obj.dataset.title) > 30 else '')
    dataset_short.short_description = 'Dataset'
    dataset_short.admin_order_field = 'dataset__title'

    def project_title_short(self, obj):
        return obj.project_title[:30] + ('...' if len(obj.project_title) > 30 else '')
    project_title_short.short_description = 'Project'
    project_title_short.admin_order_field = 'project_title'

    def colored_status(self, obj):
        colors = {
            'pending': 'gray',
            'manager_review': 'orange',
            'director_review': 'blue',
            'approved': 'green',
            'rejected': 'red'
        }
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display()
        )
    colored_status.short_description = 'Status'
    colored_status.admin_order_field = 'status'

    def manager_short(self, obj):
        return obj.manager.email if obj.manager else "—"
    manager_short.short_description = 'Manager'
    manager_short.admin_order_field = 'manager__email'

    def director_short(self, obj):
        return obj.director.email if obj.director else "—"
    director_short.short_description = 'Director'
    director_short.admin_order_field = 'director__email'

    def manager_notes_short(self, obj):
        if obj.data_manager_comment:
            return format_html(
                '<span title="{}">{}</span>',
                obj.data_manager_comment,
                obj.data_manager_comment[:30] + ('...' if len(obj.data_manager_comment) > 30 else '')
            )
        return "—"
    manager_notes_short.short_description = 'Manager Notes'

    def director_notes_short(self, obj):
        if obj.director_comment:
            return format_html(
                '<span title="{}">{}</span>',
                obj.director_comment,
                obj.director_comment[:30] + ('...' if len(obj.director_comment) > 30 else '')
            )
        return "—"
    director_notes_short.short_description = 'Director Notes'

    def request_date_short(self, obj):
        return obj.request_date.strftime('%Y-%m-%d')
    request_date_short.short_description = 'Requested'
    request_date_short.admin_order_field = 'request_date'

    def approved_date_short(self, obj):
        return obj.approved_date.strftime('%Y-%m-%d') if obj.approved_date else "—"
    approved_date_short.short_description = 'Approved'
    approved_date_short.admin_order_field = 'approved_date'

    def review_action(self, obj):
        """Add review buttons for both managers and directors"""
        if hasattr(self, 'request'):
            if (obj.status in ['pending', 'manager_review'] and 
                self.request.user.role == 'data_manager'):
                return format_html(
                    '<a href="{}" class="button" style="background: #417690; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">Review</a>',
                    reverse('manager_review', args=[obj.pk])
                )
            elif (obj.status == 'director_review' and 
                  self.request.user.role == 'director'):
                return format_html(
                    '<a href="{}" class="button" style="background: #417690; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">Review</a>',
                    reverse('director_review', args=[obj.pk])
                )
        return "—"
    review_action.short_description = 'Action'

    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'dataset', 'status')
        }),
        ('Project Details', {
            'fields': ('project_title', 'institution', 'project_description')
        }),
        ('Documents', {
            'fields': ('form_submission', 'ethical_approval_proof'),
            'classes': ('collapse',)
        }),
        ('Review Comments', {
            'fields': ('data_manager_comment', 'director_comment')
        }),
        ('Tracking', {
            'fields': ('manager', 'director', 'download_count')
        }),
        ('Dates', {
            'fields': ('request_date', 'approved_date', 'last_download', 'manager_review_date')
        })
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        
        # Role-based readonly fields
        if request.user.role == 'data_manager':
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'director_comment', 'director', 'download_count', 'last_download', 
                'approved_date', 'status', 'form_submission', 'ethical_approval_proof'
            ])
        elif request.user.role == 'director':
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'data_manager_comment', 'manager', 'download_count', 'last_download',
                'form_submission', 'ethical_approval_proof'
            ])
        
        return readonly

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        self.request = request  # Store request for use in review_action method
        
        # Role-based filtering
        if request.user.role == 'data_manager' and not request.user.is_superuser:
            return qs.filter(status__in=['pending', 'manager_review'])
        elif request.user.role == 'director' and not request.user.is_superuser:
            return qs.filter(status__in=['manager_review', 'director_review'])
        return qs

    def has_change_permission(self, request, obj=None):
        # Data managers can only change requests in their review state
        if obj and request.user.role == 'data_manager' and not request.user.is_superuser:
            return obj.status in ['pending', 'manager_review']
        return super().has_change_permission(request, obj)

    def response_change(self, request, obj):
        # Redirect to custom review page for data managers
        if request.user.role == 'data_manager' and not request.user.is_superuser:
            if '_review' in request.POST:
                return HttpResponseRedirect(reverse('manager_review', args=[obj.pk]))
        return super().response_change(request, obj)

    def save_model(self, request, obj, form, change):
        if change:
            # Auto-assign manager/director and update dates
            if request.user.role == 'data_manager' and not request.user.is_superuser:
                obj.manager = request.user
                obj.manager_review_date = timezone.now()
            elif request.user.role == 'director' and not request.user.is_superuser:
                obj.director = request.user
                if obj.status == 'approved':
                    obj.approved_date = timezone.now()
        
        super().save_model(request, obj, form, change)