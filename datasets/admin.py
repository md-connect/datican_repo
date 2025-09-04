# datasets/admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Dataset, DataRequest, Thumbnail
from django import forms
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.http import HttpResponseRedirect





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
        }

@admin.register(Dataset)
class DatasetAdmin(admin.ModelAdmin):
    form = DatasetAdminForm
    inlines = [ThumbnailInline]
    list_display = ('title', 'category', 'owner', 'size', 'upload_date', 'thumbnail_preview')
    readonly_fields = ('size', 'download_count', 'upload_date', 'update_date', 'thumbnail_preview')
    search_fields = ('title', 'description', 'category')
    list_filter = ('category', 'upload_date')
    
    def thumbnail_preview(self, obj):
        primary = obj.thumbnails.filter(is_primary=True).first()
        if primary:
            return f'<img src="{primary.image.url}" style="max-height: 100px;" />'
        return "No thumbnail"
    thumbnail_preview.allow_tags = True
    thumbnail_preview.short_description = 'Primary Thumbnail'
    
    def save_model(self, request, obj, form, change):
        if not change:
            obj.owner = request.user
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
                    reverse('review_request', args=[obj.pk])
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
            'fields': ('form_submission', 'document'),
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
                'approved_date', 'status', 'form_submission', 'document'
            ])
        elif request.user.role == 'director':
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'data_manager_comment', 'manager', 'download_count', 'last_download',
                'form_submission', 'document'
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
                return HttpResponseRedirect(reverse('review_request', args=[obj.pk]))
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
