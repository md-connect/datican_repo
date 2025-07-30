# datasets/admin.py
from django.contrib import admin
from django.utils.safestring import mark_safe
from .models import Dataset, DataRequest, Thumbnail
from django import forms



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
    list_display = ('id', 'user', 'dataset', 'project_title', 'institution', 'status', 'request_date')
    list_filter = ('status', 'request_date')
    search_fields = ('user__username', 'dataset__title', 'project_title', 'institution')
    readonly_fields = ('request_date', 'approved_date', 'last_download')
    list_per_page = 20
    
    fieldsets = (
        ('Request Information', {
            'fields': ('user', 'dataset', 'status')
        }),
        ('Project Details', {
            'fields': ('project_title', 'institution', 'project_details', 'project_description')
        }),
        ('Documents', {
            'fields': ('form_submission', 'document')
        }),
        ('Review & Tracking', {
            'fields': ('data_manager_comment', 'director_comment', 
                      'download_count', 'last_download', 'manager', 'director')
        }),
        ('Dates', {
            'fields': ('request_date', 'approved_date')
        })
    )