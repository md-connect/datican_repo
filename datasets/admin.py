# datasets/admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Dataset, DataRequest, Thumbnail
from django import forms
from django.utils import timezone



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
        'approved_date_short'
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
            '<span style="color: {}">{}</span>',
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

    # Rest of your existing configuration remains the same...
    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'dataset', 'status')
        }),
        ('Project Details', {
            'fields': ('project_title', 'institution', 'project_description')
        }),
        ('Review Comments', {
            'fields': ('data_manager_comment', 'director_comment')
        }),
        ('Tracking', {
            'fields': ('manager', 'director', 'download_count')
        }),
        ('Dates', {
            'fields': ('request_date', 'approved_date', 'last_download')
        })
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        
        if request.user.groups.filter(name='Data Managers').exists():
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'director_comment', 'director', 'download_count', 'last_download', 'approved_date'
            ])
        elif request.user.groups.filter(name='Directors').exists():
            readonly.extend([
                'user', 'dataset', 'project_title', 'institution', 'project_description',
                'data_manager_comment', 'manager', 'download_count', 'last_download'
            ])
        
        return readonly

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.groups.filter(name='Data Managers').exists():
            return qs.filter(status__in=['pending', 'manager_review'])
        elif request.user.groups.filter(name='Directors').exists():
            return qs.filter(status__in=['manager_review', 'director_review'])
        return qs

    def save_model(self, request, obj, form, change):
        if change:
            if request.user.groups.filter(name='Data Managers').exists():
                obj.manager = request.user
                if obj.status == 'manager_review':
                    obj.status = 'director_review'
            elif request.user.groups.filter(name='Directors').exists():
                obj.director = request.user
                if obj.status == 'director_review':
                    obj.approved_date = timezone.now()
        super().save_model(request, obj, form, change)