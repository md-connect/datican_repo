from django.contrib import admin
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport, DatasetFile
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
# DatasetFile Inline
# --------------------------
class DatasetFileInline(admin.TabularInline):
    model = DatasetFile
    extra = 1
    fields = ['filename', 'file_path', 'part_number', 'total_parts', 'file_size_display', 'download_link_preview']
    readonly_fields = ['file_size_display', 'download_link_preview']
    
    def file_size_display(self, obj):
        return obj.get_file_size_display() if obj.pk else "—"
    file_size_display.short_description = 'Size'
    
    def download_link_preview(self, obj):
        if obj.pk and obj.file_path:
            url = obj.get_download_url(expiration=3600)
            return format_html('<a href="{}" target="_blank">🔗 Link</a>', url)
        return "—"
    download_link_preview.short_description = 'Download'


# --------------------------
# Dataset Admin Form
# --------------------------
class DatasetAdminForm(forms.ModelForm):
    # Keep existing b2_file_key field for backward compatibility
    b2_file_key = forms.CharField(
        max_length=500,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'datasets/your-filename.zip',
            'style': 'width: 600px; font-family: monospace;'
        }),
        help_text="Single file path (for simple datasets)"
    )
    
    # NEW: Multi-file bulk addition
    b2_file_paths = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': '''datasets/breast-cancer/part1.zip
datasets/breast-cancer/part2.zip
datasets/breast-cancer/part3.zip''',
            'style': 'font-family: monospace;'
        }),
        help_text=mark_safe("""
            <div style="padding: 10px; background: #e8f4e8; border-left: 4px solid #2e6b2e;">
                <strong>📦 Add multiple files (one per line):</strong><br>
                Part numbers will be auto-assigned in order.
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

    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
            
            # Handle single file (backward compatibility)
            b2_key = self.cleaned_data.get('b2_file_key')
            if b2_key and not instance.files.exists():
                filename = b2_key.split('/')[-1]
                DatasetFile.objects.create(
                    dataset=instance,
                    filename=filename,
                    file_path=b2_key,
                    part_number=1,
                    total_parts=1
                )
            
            # Handle multiple files
            b2_paths = self.cleaned_data.get('b2_file_paths')
            if b2_paths:
                paths = [p.strip() for p in b2_paths.split('\n') if p.strip()]
                paths.sort()  # Ensure correct order
                
                total_parts = len(paths)
                for idx, path in enumerate(paths, 1):
                    filename = path.split('/')[-1]
                    
                    # Create or update file
                    file_obj, created = DatasetFile.objects.update_or_create(
                        dataset=instance,
                        part_number=idx,
                        defaults={
                            'filename': filename,
                            'file_path': path,
                            'total_parts': total_parts
                        }
                    )
                    
                    # Refresh metadata from B2
                    file_obj.refresh_metadata()
        
        return instance


# --------------------------
# Dataset Admin
# --------------------------
@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    form = DatasetAdminForm
    inlines = [ThumbnailInline, DatasetFileInline]

    list_display = [
        'title', 'modality', 'file_stats', 'no_of_subjects', 'upload_date',
        'rating', 'thumbnail_preview', 'has_preview', 'has_readme'
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
        'total_size_display',
        'file_count_display',
    )

    fieldsets = (
        ('Basic Information', {'fields': ('title', 'description', 'uploaded_by', 'owner')}),
        ('Medical Information', {'fields': ('modality', 'body_part', 'no_of_subjects', 'format')}),
        ('Dataset Files', {
            'fields': ('b2_file_key', 'b2_file_paths', 'total_size_display', 'file_count_display'),
            'classes': ('wide',),
            'description': mark_safe(
                '<div style="padding: 15px; background: #f8f9fa; border-left: 4px solid #007bff;">'
                '<strong>📦 Add files from B2</strong><br>'
                'Option 1: Single file - use the "B2 File Key" field<br>'
                'Option 2: Multiple files - paste paths in the textarea (one per line)'
                '</div>'
            )
        }),
        ('B2 Cloud Storage (Legacy)', {
            'fields': ('dataset_path', 'b2_file_info', 'b2_file_size', 'b2_upload_date', 'b2_download_link'),
            'classes': ('collapse',),
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

    def file_stats(self, obj):
        count = obj.get_file_count()
        if count:
            total_size = obj.get_file_size_display()
            return format_html(
                '<a href="{}">{} file{}</a><br><small>{}</small>',
                reverse('admin:datasets_datasetfile_changelist') + f'?dataset__id__exact={obj.id}',
                count,
                's' if count != 1 else '',
                total_size
            )
        return "No files"
    file_stats.short_description = 'Files'
    
    def total_size_display(self, obj):
        return obj.get_file_size_display()
    total_size_display.short_description = 'Total Size'
    
    def file_count_display(self, obj):
        return obj.get_file_count()
    file_count_display.short_description = 'File Count'

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


# --------------------------
# DatasetFile Admin
# --------------------------
@admin.register(DatasetFile)
class DatasetFileAdmin(admin.ModelAdmin):
    list_display = ['filename', 'dataset_link', 'part_info', 'file_size_display', 
                   'b2_upload_date', 'created_at']
    list_filter = ['dataset', 'created_at']
    search_fields = ['filename', 'file_path', 'dataset__title']
    readonly_fields = ['b2_etag', 'b2_upload_date', 'created_at', 'updated_at', 
                      'download_link', 'file_size_display']
    
    fieldsets = (
        ('Dataset Relationship', {
            'fields': ('dataset',)
        }),
        ('File Information', {
            'fields': ('filename', 'file_path', 'file_size', 'file_size_display')
        }),
        ('Part Information', {
            'fields': ('part_number', 'total_parts'),
            'classes': ('collapse',)
        }),
        ('B2 Metadata', {
            'fields': ('b2_etag', 'b2_upload_date'),
            'classes': ('collapse',)
        }),
        ('Download', {
            'fields': ('download_link',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def dataset_link(self, obj):
        url = reverse('admin:datasets_dataset_change', args=[obj.dataset.id])
        return format_html('<a href="{}">{}</a>', url, obj.dataset.title)
    dataset_link.short_description = 'Dataset'
    dataset_link.admin_order_field = 'dataset__title'
    
    def part_info(self, obj):
        if obj.part_number and obj.total_parts:
            return f"Part {obj.part_number}/{obj.total_parts}"
        return "—"
    part_info.short_description = 'Part'
    
    def file_size_display(self, obj):
        return obj.get_file_size_display()
    file_size_display.short_description = 'Size'
    
    def download_link(self, obj):
        url = obj.get_download_url()
        if url:
            return format_html(
                '<a href="{}" target="_blank" style="background: #28a745; color: white; '
                'padding: 5px 10px; border-radius: 3px; text-decoration: none;">📥 Download</a>',
                url
            )
        return "No link available"
    download_link.short_description = 'Download'
    
    actions = ['refresh_b2_metadata']
    
    def refresh_b2_metadata(self, request, queryset):
        for file_obj in queryset:
            file_obj.refresh_metadata()
        self.message_user(request, f"Refreshed metadata for {queryset.count()} files")
    refresh_b2_metadata.short_description = "Refresh B2 metadata"


# --------------------------
# DatasetRating Admin
# --------------------------
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


# --------------------------
# UserCollection Admin
# --------------------------
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


# --------------------------
# DatasetReport Admin
# --------------------------
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


# --------------------------
# DataRequest Admin
# --------------------------
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