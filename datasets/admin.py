from django.contrib import admin
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport
from django import forms
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect
from .utilities import can_manage_datasets, is_data_manager, is_director, is_admin
from datasets.utils.email_service import EmailService
import boto3
from botocore.exceptions import ClientError
from django.conf import settings

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

# --------------------------
# Thumbnail inline
# --------------------------
class ThumbnailInline(admin.TabularInline):
    model = Thumbnail
    extra = 1
    max_num = 5
    fields = ('image', 'is_primary', 'preview')
    readonly_fields = ('preview',)

    def preview(self, instance):
        if instance.image:
            try:
                thumb_url = instance.image.storage.url(instance.image.name, expire=86400)
                return format_html('<img src="{}" style="max-height: 100px;" />', thumb_url)
            except Exception:
                return "Error"
        return "No image"
    preview.short_description = 'Preview'


# --------------------------
# Dataset Admin Form
# --------------------------
class DatasetAdminForm(forms.ModelForm):
    # Only keep B2 path input (optional)
    b2_file_key = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'datasets/your-filename.zip',
            'style': 'width: 600px; font-family: monospace;'
        }),
        help_text=mark_safe("""
            <div style="padding: 10px; background: #e8f4e8; border-left: 4px solid #2e6b2e;">
                <strong>📤 How to upload large files:</strong><br>
                1. Upload via CLI: <code>b2 upload-file --threads 10 datican-repo yourfile.zip datasets/yourfile.zip</code><br>
                2. Copy the path to the field above<br>
                3. Save - Django will verify the file exists
            </div>
        """)
    )

    class Meta:
        model = Dataset
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'preview_file': forms.FileInput(attrs={'accept': '.csv,.xlsx,.xls,.json'}),
        }

    def clean_b2_file_key(self):
        """Validate that the path exists in B2 (only if changed)"""
        path = self.cleaned_data.get('b2_file_key')
        if not path or (self.instance and self.instance.dataset_path == path):
            return path
        # Optional: Add B2 existence check here if desired
        return path


# --------------------------
# Dataset Admin
# --------------------------
@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    form = DatasetAdminForm
    inlines = [ThumbnailInline]

    list_display = [
        'title', 'modality', 'format', 'no_of_subjects', 'upload_date',
        'rating', 'thumbnail_preview', 'owner', 'has_preview', 'has_readme', 'b2_path_short'
    ]
    list_filter = ['modality', 'format', 'upload_date', 'preview_type']
    search_fields = ['title', 'description', 'body_part', 'dataset_path']

    readonly_fields = (
        'readme_updated',
        'readme_file_size',
        'uploaded_by',
        'b2_file_size',
        'b2_upload_date',
        'b2_etag',
        'download_count',
        'upload_date',
        'update_date',
        'thumbnail_preview',
        'preview_type',
        'owner',
        'b2_file_id',
        'b2_file_info',
        'b2_download_link',
        'preview_download_link',
        'readme_download_link',
        'b2_path_display',
    )

    fieldsets = (
        ('Basic Information', {'fields': ('title', 'description', 'uploaded_by', 'owner')}),
        ('Medical Information', {'fields': ('modality', 'body_part', 'no_of_subjects', 'format')}),
        ('B2 Cloud Storage (Large Files)', {
            'fields': ('b2_file_key', 'b2_file_info', 'b2_file_size', 'b2_upload_date', 'b2_download_link'),
            'classes': ('wide',),
            'description': mark_safe(
                '<div style="padding: 15px; background: #f8f9fa; border-left: 4px solid #007bff;">'
                '<strong>📦 Upload Large Datasets Directly to B2</strong><br>'
                'Upload using B2 CLI, copy path above, save, and Django will display metadata.'
                '</div>'
            )
        }),
        ('Preview File', {
            'fields': ('preview_file', 'preview_type'),
            'description': 'Upload CSV/Excel/JSON file for preview (optional). Type auto-detected.'
        }),
        ('README Documentation', {'fields': ('readme_file', 'readme_content', 'readme_updated', 'readme_file_size')}),
        ('Statistics', {'fields': ('rating', 'download_count')}),
        ('System Information', {'fields': ('upload_date', 'update_date'), 'classes': ('collapse',)}),
        ('Legacy B2 Fields', {'fields': ('b2_file_id',), 'classes': ('collapse',)}),
    )

    # --------------------------
    # Admin Display Methods
    # --------------------------
    def thumbnail_preview(self, obj):
        primary = obj.thumbnails.filter(is_primary=True).first()
        if primary and primary.image:
            try:
                thumb_url = primary.image.storage.url(primary.image.name, expire=86400)
                return format_html('<img src="{}" style="max-height: 50px;" />', thumb_url)
            except Exception:
                return "Error"
        return "—"
    thumbnail_preview.short_description = 'Thumbnail'

    def has_readme(self, obj):
        return bool(obj.readme_file) or bool(obj.readme_content)
    has_readme.boolean = True
    has_readme.short_description = 'Has README'

    def has_preview(self, obj):
        if obj.preview_file:
            return format_html('<span style="color: green;">✓</span> {}', obj.get_preview_type_display())
        return mark_safe('<span style="color: red;">✗</span>')
    has_preview.short_description = 'Preview'
    has_preview.admin_order_field = 'preview_type'

    def b2_path_short(self, obj):
        if obj.dataset_path:
            filename = obj.dataset_path.split('/')[-1]
            return format_html(
                '<span title="{}">📁 {}</span>',
                obj.dataset_path,
                filename[:30] + '...' if len(filename) > 30 else filename
            )
        return "—"
    b2_path_short.short_description = 'Dataset File'

    def b2_path_display(self, obj):
        if obj.dataset_path:
            return format_html('<code style="background: #f0f0f0; padding: 3px 6px; border-radius: 3px;">{}</code>', obj.dataset_path)
        return "—"
    b2_path_display.short_description = 'B2 Path'

    def b2_file_info(self, obj):
        """Display B2 metadata"""
        if not obj.dataset_path:
            return "—"
        size = obj.get_file_size_display() if obj.b2_file_size else "Unknown size"
        uploaded = obj.b2_upload_date or "Unknown date"
        return f"Size: {size} | Uploaded: {uploaded}"
    b2_file_info.short_description = "B2 File Info"

    def b2_download_link(self, obj):
        if obj.dataset_path:
            try:
                url = obj.get_download_url(expiration=3600)
                file_size = obj.get_file_size_display()
                return format_html(
                    '<a href="{}" target="_blank" style="background: #28a745; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">📥 Download ({})</a>',
                    url, file_size
                )
            except Exception as e:
                return format_html('<span style="color: red;">Error: {}</span>', str(e))
        return "No file"
    b2_download_link.short_description = 'Download Link'

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

    # --------------------------
    # Permissions
    # --------------------------
    def has_add_permission(self, request):
        return can_manage_datasets(request.user)

    def has_change_permission(self, request, obj=None):
        return can_manage_datasets(request.user)

    def has_delete_permission(self, request, obj=None):
        return can_manage_datasets(request.user)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if hasattr(request.user, 'role') and request.user.role == 'data_manager' and not request.user.is_superuser:
            return qs.filter(owner=request.user.username)
        return qs

    def save_model(self, request, obj, form, change):
        # Automatically set uploaded_by on creation
        if not change or not obj.uploaded_by:
            obj.uploaded_by = request.user
            
        b2_key = form.cleaned_data.get('b2_file_key')
        if b2_key and not obj.dataset_path:
            obj.dataset_path = b2_key
        super().save_model(request, obj, form, change)
        if obj.dataset_path and not obj.b2_file_size:
            obj.refresh_b2_metadata()

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
        'approved_date_short',
        'review_action',
        'manager_review_date_short',
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
    
    readonly_fields = (
        'request_date', 'approved_date', 'last_download', 'download_count'
    )
    list_per_page = 20
    list_select_related = ('user', 'dataset', 'manager', 'director')

    fieldsets = (
        ('Request Information', {'fields': ('user', 'dataset', 'status')}),
        ('Project Details', {'fields': ('project_title', 'institution', 'project_description')}),
        ('Documents', {'fields': ('form_submission', 'ethical_approval_proof'), 'classes': ('collapse',)}),
        ('Review Comments', {'fields': ('data_manager_comment', 'director_comment')}),
        ('Tracking', {'fields': ('manager', 'director', 'download_count')}),
        ('Dates', {'fields': ('request_date', 'approved_date', 'last_download', 'manager_review_date')}),
    )

    # --------------------------
    # Custom Display Methods
    # --------------------------
    def dataset_short(self, obj):
        return obj.dataset.title[:30] + ('...' if len(obj.dataset.title) > 30 else '')
    dataset_short.short_description = 'Dataset'
    dataset_short.admin_order_field = 'dataset__title'

    def project_title_short(self, obj):
        return obj.project_title[:30] + ('...' if len(obj.project_title) > 30 else '')
    project_title_short.short_description = 'Project'
    project_title_short.admin_order_field = 'project_title'

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

    def manager_review_date_short(self, obj):
        return obj.manager_review_date.strftime('%Y-%m-%d') if obj.manager_review_date else "—"
    manager_review_date_short.short_description = 'Manager Review'
    manager_review_date_short.admin_order_field = 'manager_review_date'

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

    # --------------------------
    # Review Action Button
    # --------------------------
    def review_action(self, obj):
        if hasattr(self, 'request'):
            user_role = getattr(self.request.user, 'role', None)
            if user_role == 'data_manager' and obj.status in ['pending', 'manager_review']:
                return format_html(
                    '<a href="{}" class="button" style="background: #417690; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">Review</a>',
                    reverse('manager_review', args=[obj.pk])
                )
            elif user_role == 'director' and obj.status == 'director_review':
                return format_html(
                    '<a href="{}" class="button" style="background: #417690; color: white; padding: 5px 10px; border-radius: 3px; text-decoration: none;">Review</a>',
                    reverse('director_review', args=[obj.pk])
                )
        return "—"
    review_action.short_description = 'Action'

    # --------------------------
    # Role-based readonly fields
    # --------------------------
    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        role = getattr(request.user, 'role', None)

        if role == 'data_manager':
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'director_comment', 'director', 'download_count', 'last_download', 
                'approved_date', 'status', 'form_submission', 'ethical_approval_proof'
            ])
        elif role == 'director':
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'data_manager_comment', 'manager', 'download_count', 'last_download',
                'form_submission', 'ethical_approval_proof'
            ])
        return readonly

    # --------------------------
    # Store request for review_action
    # --------------------------
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        self.request = request  # store for review_action
        role = getattr(request.user, 'role', None)

        if role == 'data_manager' and not request.user.is_superuser:
            return qs.filter(status__in=['pending', 'manager_review'])
        elif role == 'director' and not request.user.is_superuser:
            return qs.filter(status__in=['manager_review', 'director_review'])
        return qs

    # --------------------------
    # Permission-based change
    # --------------------------
    def has_change_permission(self, request, obj=None):
        if obj and getattr(request.user, 'role', None) == 'data_manager' and not request.user.is_superuser:
            return obj.status in ['pending', 'manager_review']
        return super().has_change_permission(request, obj)

    # --------------------------
    # Redirect after change
    # --------------------------
    def response_change(self, request, obj):
        if getattr(request.user, 'role', None) == 'data_manager' and not request.user.is_superuser:
            if '_review' in request.POST:
                return HttpResponseRedirect(reverse('manager_review', args=[obj.pk]))
        return super().response_change(request, obj)

    # --------------------------
    # Auto-assign manager/director on save
    # --------------------------
    def save_model(self, request, obj, form, change):
        role = getattr(request.user, 'role', None)
        if change and role:
            if role == 'data_manager' and not request.user.is_superuser:
                obj.manager = request.user
                obj.manager_review_date = timezone.now()
            elif role == 'director' and not request.user.is_superuser:
                obj.director = request.user
                if obj.status == 'approved':
                    obj.approved_date = timezone.now()
        super().save_model(request, obj, form, change)
