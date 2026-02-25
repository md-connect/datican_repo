# datasets/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.http import FileResponse, HttpResponseForbidden, JsonResponse, HttpResponse, HttpResponseRedirect, HttpResponseNotFound
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.db.models import Prefetch, Q, Avg, Count, F, Sum, Min, Max
from django.db.models.functions import TruncMonth, TruncYear, TruncDay
from django.db import models
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport, DatasetFile
from .forms import DataRequestForm, RatingForm, CollectionForm, ReportForm
import os
from datetime import datetime, timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.views.decorators.http import require_POST, require_GET
from django.core.exceptions import PermissionDenied
import pandas as pd
import json
from datasets.utils.email_service import EmailService
from accounts.models import CustomUser
from .decorators import data_manager_required, director_required, admin_required
from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from .models import DataRequest
from django.db.models import Count, Q
import logging

logger = logging.getLogger(__name__)

User = get_user_model()

# ==================== HELPER FUNCTIONS ====================

def format_file_size(size_bytes):
    """Format file size in human readable format"""
    if not size_bytes:
        return "Unknown"
    
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


def is_bot_request(request):
    """Check if request is from a bot"""
    user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
    bot_patterns = [
        'bot', 'crawler', 'spider', 'scrape', 'curl', 'wget', 
        'python', 'requests', 'httpie', 'go-http-client',
        'java', 'okhttp', 'ruby', 'scrapy', 'selenium',
        'headless', 'phantomjs', 'puppeteer', 'playwright'
    ]
    return any(pattern in user_agent for pattern in bot_patterns)


# ==================== USER ROLE CHECK FUNCTIONS ====================

def is_manager(user):
    return user.is_authenticated and user.role == 'data_manager'

def is_director(user):
    return user.is_authenticated and user.role == 'director'

def is_superuser(user):
    return user.is_authenticated and user.is_superuser


# ==================== DATASET LISTING AND DETAIL VIEWS ====================

def dataset_list(request):
    # Get filter parameters from request
    modality = request.GET.getlist('modality')
    format = request.GET.getlist('format')
    body_part = request.GET.get('body_part', '').strip()
    min_subjects = request.GET.get('min_subjects')
    max_subjects = request.GET.get('max_subjects')
    min_rating = request.GET.get('min_rating', '0')
    upload_date = request.GET.get('upload_date', 'all')
    popularity = request.GET.get('popularity', 'all')
    sort = request.GET.get('sort', 'newest')
    search_query = request.GET.get('q', '').strip()

    # Start with base queryset
    datasets = Dataset.objects.prefetch_related(
        Prefetch('thumbnails', 
                queryset=Thumbnail.objects.filter(is_primary=True), 
                to_attr='primary_thumbnails')
    )

    # Apply search filter
    if search_query:
        datasets = datasets.filter(
            Q(title__icontains=search_query) |
            Q(description__icontains=search_query) |
            Q(body_part__icontains=search_query) |
            Q(modality__icontains=search_query)
        )

    # Apply modality filter
    if modality:
        datasets = datasets.filter(modality__in=modality)
    
    # Apply format filter
    if format:
        # Handle both uppercase values from choices and case variations
        format_query = Q()
        for fmt in format:
            format_query |= Q(format__iexact=fmt)
        datasets = datasets.filter(format_query)
    
    # Apply body part filter
    if body_part:
        datasets = datasets.filter(body_part__icontains=body_part)
    
    # Apply number of subjects filter
    if min_subjects:
        try:
            datasets = datasets.filter(no_of_subjects__gte=int(min_subjects))
        except ValueError:
            pass
    
    if max_subjects:
        try:
            datasets = datasets.filter(no_of_subjects__lte=int(max_subjects))
        except ValueError:
            pass
    
    # Apply rating filter
    try:
        min_rating_value = float(min_rating)
        if min_rating_value > 0:
            datasets = datasets.filter(rating__gte=min_rating_value)
    except ValueError:
        pass
    
    # Apply upload date filter
    if upload_date != 'all':
        from django.utils import timezone
        from datetime import timedelta
        
        now = timezone.now()
        if upload_date == 'today':
            datasets = datasets.filter(upload_date__date=now.date())
        elif upload_date == 'week':
            week_ago = now - timedelta(days=7)
            datasets = datasets.filter(upload_date__gte=week_ago)
        elif upload_date == 'month':
            month_ago = now - timedelta(days=30)
            datasets = datasets.filter(upload_date__gte=month_ago)
        elif upload_date == 'year':
            year_ago = now - timedelta(days=365)
            datasets = datasets.filter(upload_date__gte=year_ago)
    
    # Apply popularity filter
    if popularity != 'all':
        if popularity == 'trending':
            datasets = datasets.filter(download_count__gte=100)
        elif popularity == 'popular':
            datasets = datasets.filter(download_count__gte=500)
        elif popularity == 'viral':
            datasets = datasets.filter(download_count__gte=1000)
    
    # Apply sorting
    if sort == 'newest':
        datasets = datasets.order_by('-upload_date')
    elif sort == 'oldest':
        datasets = datasets.order_by('upload_date')
    elif sort == 'rating_high':
        datasets = datasets.order_by('-rating')
    elif sort == 'rating_low':
        datasets = datasets.order_by('rating')
    elif sort == 'downloads':
        datasets = datasets.order_by('-download_count')
    elif sort == 'title_asc':
        datasets = datasets.order_by('title')
    elif sort == 'title_desc':
        datasets = datasets.order_by('-title')
    elif sort == 'updated':
        datasets = datasets.order_by('-update_date')
    else:  # relevance or default
        datasets = datasets.order_by('-upload_date')  # Default to newest
    
    # Pagination
    paginator = Paginator(datasets, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get available years for filter (optional, if you want to keep this)
    available_years = Dataset.objects.dates('upload_date', 'year').order_by('-upload_date__year')
    
    # Prepare URL parameters for templates
    url_params = request.GET.copy()
    
    # Create versions without specific parameters
    url_params_no_page = request.GET.copy()
    if 'page' in url_params_no_page:
        url_params_no_page.pop('page')
    
    url_params_no_body_part = request.GET.copy()
    if 'body_part' in url_params_no_body_part:
        url_params_no_body_part.pop('body_part')
    
    # Create URL parameters for removing each modality
    modality_removal_urls = {}
    if 'modality' in request.GET:
        modalities = request.GET.getlist('modality')
        for modality in modalities:
            # Create a copy of GET parameters
            params = request.GET.copy()
            # Get current modalities list
            current_modalities = params.getlist('modality')
            # Remove this specific modality
            if modality in current_modalities:
                current_modalities.remove(modality)
                # Update the parameters
                params.setlist('modality', current_modalities)
            # Store the URL
            modality_removal_urls[modality] = f"?{params.urlencode()}" if params else ""
    
    context = {
        'datasets': page_obj,
        'available_years': available_years,
        'current_filters': {
            'modality': modality,
            'format': format,
            'body_part': body_part,
            'min_subjects': min_subjects,
            'max_subjects': max_subjects,
            'min_rating': min_rating,
            'upload_date': upload_date,
            'popularity': popularity,
            'sort': sort,
            'q': search_query
        },
        # Pass URL parameters
        'url_params': url_params,
        'url_params_no_page': url_params_no_page,
        'url_params_no_body_part': url_params_no_body_part,
        'modality_removal_urls': modality_removal_urls,
        # Pass the choices for the filter template
        'modality_choices': Dataset.MODALITY_CHOICES,
        'format_choices': Dataset.FORMAT_CHOICES,
    }
    
    return render(request, 'datasets/list.html', context)


def dataset_detail(request, pk):
    # Prefetch related thumbnails and optimize queries
    dataset = get_object_or_404(
        Dataset.objects.prefetch_related('thumbnails', 'files'), 
        pk=pk
    )
    
    # Get all thumbnails and find primary
    thumbnails = list(dataset.thumbnails.all())
    primary_thumbnail = next((t for t in thumbnails if t.is_primary), None)
    
    # If no primary set, use first thumbnail
    if not primary_thumbnail and thumbnails:
        primary_thumbnail = thumbnails[0]
    
    # Check for existing request and determine view behavior
    data_request = None
    show_request_form = True
    request_button_text = "Request Access"
    request_button_link = "dataset_request"
    request_button_disabled = False
    
    if request.user.is_authenticated:
        # Get the most recent request for this dataset
        data_request = DataRequest.objects.filter(
            user=request.user,
            dataset=dataset
        ).order_by('-request_date').first()
        
        if data_request:
            show_request_form = False
            
            # Determine button text and link based on request status
            if data_request.status == 'approved':
                if data_request.can_download():
                    request_button_text = "Download Dataset"
                    request_button_link = "request_status"
                else:
                    # Download count exceeded - can request again
                    request_button_text = "Request Access"
                    request_button_link = "dataset_request"
                    show_request_form = True
            elif data_request.status == 'rejected':
                # Rejected - can request again
                request_button_text = "Request Access"
                request_button_link = "dataset_request"
                show_request_form = True
            else:
                # Pending/Under Review
                request_button_text = "View Request Status"
                request_button_link = "request_status"
    
    # Check download access only if request exists and is approved
    can_download = False
    if data_request and data_request.status == 'approved':
        can_download = data_request.can_download()
    
    # Get similar datasets based on format instead of category
    similar_datasets = Dataset.objects.filter(
        format=dataset.format
    ).exclude(pk=pk).prefetch_related(
        Prefetch('thumbnails', queryset=Thumbnail.objects.filter(is_primary=True), to_attr='primary_thumbnails')
    )[:4]
    
    # Add primary thumbnail to each similar dataset
    for similar in similar_datasets:
        similar.primary_thumbnail = similar.primary_thumbnails[0] if similar.primary_thumbnails else None
    
    # ===== NEW FEATURES =====
    
    # Get user's rating if logged in
    user_rating = None
    user_rating_obj = None
    if request.user.is_authenticated:
        try:
            user_rating_obj = DatasetRating.objects.get(user=request.user, dataset=dataset)
            user_rating = user_rating_obj.rating
        except DatasetRating.DoesNotExist:
            pass
    
    # Get user's collections
    user_collections = []
    if request.user.is_authenticated:
        user_collections = UserCollection.objects.filter(user=request.user)
    
    # Check if dataset is in user's collections
    in_collections = []
    if request.user.is_authenticated:
        in_collections = dataset.get_user_collections(request.user) if hasattr(dataset, 'get_user_collections') else []
    
    # Get dataset statistics
    rating_stats = dataset.ratings.aggregate(
        average=Avg('rating'),
        count=Count('id')
    )
    
    # Get preview data if available
    preview_data = None
    preview_columns = []
    preview_rows = []
    preview_error = None
    has_preview = False
    
    if hasattr(dataset, 'preview_file') and dataset.preview_file:
        try:
            preview_data = get_preview_data(dataset, max_rows=10)  # Load only 10 rows initially
            if preview_data:
                preview_columns = preview_data.get('columns', [])
                preview_rows = preview_data.get('rows', [])
                has_preview = True
        except Exception as e:
            preview_error = str(e)
            has_preview = False
    elif dataset.format and dataset.format.lower() in ['csv', 'json']:
        # If no preview file but dataset is CSV/JSON format, try to use the main file
        try:
            if dataset.file and dataset.file.name.lower().endswith(('.csv', '.json')):
                # Create a temporary dataset-like object for preview
                temp_dataset = type('TempDataset', (), {
                    'preview_file': dataset.file,
                    'preview_type': 'csv' if dataset.file.name.lower().endswith('.csv') else 'json'
                })()
                preview_data = get_preview_data(temp_dataset, max_rows=10)
                if preview_data:
                    preview_columns = preview_data.get('columns', [])
                    preview_rows = preview_data.get('rows', [])
                    has_preview = True
        except Exception as e:
            preview_error = str(e)
            has_preview = False
    
    # Get recent reviews
    recent_reviews = DatasetRating.objects.filter(dataset=dataset).select_related('user').order_by('-created_at')[:5]
    
    # ===== MULTI-PART FILE INFORMATION =====
    files = dataset.get_all_files()
    has_multi_part = files.count() > 1
    total_files = files.count() if files.exists() else (1 if dataset.dataset_path else 0)
    total_size_display = dataset.get_file_size_display()
    
    # Prepare file list for template
    file_list = []
    for file in files:
        file_list.append({
            'id': file.id,
            'part_number': file.part_number,
            'filename': file.filename,
            'size': file.file_size,
            'size_display': file.get_file_size_display(),
            'is_last': file.part_number == files.count()
        })
    
    context = {
        # Existing context
        'dataset': dataset,
        'can_download': can_download,
        'data_request': data_request,
        'show_request_form': show_request_form,
        'request_button_text': request_button_text,
        'request_button_link': request_button_link,
        'request_button_disabled': request_button_disabled,
        'similar_datasets': similar_datasets,
        'thumbnails': thumbnails,
        'primary_thumbnail': primary_thumbnail,
        
        # New features context
        'user_rating': user_rating,
        'user_rating_obj': user_rating_obj,
        'user_collections': user_collections,
        'in_collections': in_collections,
        'rating_stats': rating_stats,
        'recent_reviews': recent_reviews,
        
        # Preview context
        'preview_columns': preview_columns,
        'preview_rows': preview_rows,
        'preview_error': preview_error,
        'has_preview': has_preview,
        'preview_type': getattr(dataset, 'preview_type', 'none'),
        
        # Multi-part file context
        'files': file_list,
        'has_multi_part': has_multi_part,
        'total_files': total_files,
        'total_size_display': total_size_display,
        'legacy_single_file': not files.exists() and dataset.dataset_path,
        'legacy_filename': dataset.dataset_path.split('/')[-1] if dataset.dataset_path else None,
        
        # Forms
        'rating_form': RatingForm(instance=user_rating_obj) if user_rating_obj else RatingForm(),
        'collection_form': CollectionForm(),
        'report_form': ReportForm(),
    }
    
    return render(request, 'datasets/detail.html', context)


def get_preview_data(dataset, max_rows=100):
    """Extract preview data from CSV/Excel/JSON file with minimal memory usage"""
    import tempfile
    import pandas as pd
    import json
    import os
    
    if not hasattr(dataset, 'preview_file') or not dataset.preview_file:
        return None
    
    file_obj = dataset.preview_file
    file_extension = file_obj.name.lower()
    
    # For CSV files, we can read directly from the file object without saving
    try:
        if file_extension.endswith('.csv'):
            # Try to read directly from the file object
            if hasattr(file_obj, 'read'):
                file_obj.seek(0)  # Reset pointer to beginning
                df = pd.read_csv(file_obj, nrows=max_rows)
                return {
                    'columns': list(df.columns),
                    'rows': df.head(max_rows).to_dict('records'),
                    'total_rows': len(df),
                    'total_columns': len(df.columns)
                }
        
        # For other formats, fall back to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_obj.name)[1]) as tmp:
            if hasattr(file_obj, 'read'):
                tmp.write(file_obj.read())
            elif hasattr(file_obj, 'path'):
                with open(file_obj.path, 'rb') as f:
                    tmp.write(f.read())
            else:
                for chunk in file_obj.chunks():
                    tmp.write(chunk)
            tmp_path = tmp.name
        
        # Read based on extension
        if file_extension.endswith('.csv'):
            df = pd.read_csv(tmp_path, nrows=max_rows)
        elif file_extension.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(tmp_path, nrows=max_rows)
        elif file_extension.endswith('.json'):
            with open(tmp_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                df = pd.DataFrame(data[:max_rows])
            elif isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                return None
        else:
            return None
        
        # Process and return
        rows = df.head(max_rows).to_dict('records')
        for row in rows:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
        
        return {
            'columns': list(df.columns),
            'rows': rows,
            'total_rows': len(df),
            'total_columns': len(df.columns)
        }
        
    except Exception as e:
        print(f"Preview error: {e}")
        return None
        
    finally:
        # Clean up temp file
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass


@require_GET
def dataset_preview_api(request, pk):
    """API endpoint for loading preview data with pagination"""
    dataset = get_object_or_404(Dataset, pk=pk)
    
    try:
        page = int(request.GET.get('page', 1))
        page_size = int(request.GET.get('page_size', 50))
        
        # Check if we have a preview file
        if not hasattr(dataset, 'preview_file') or not dataset.preview_file:
            # Try to use main file if it's CSV/JSON
            if dataset.file and dataset.file.name.lower().endswith(('.csv', '.json')):
                # Use main file as preview
                preview_file = dataset.file
                preview_type = 'csv' if dataset.file.name.lower().endswith('.csv') else 'json'
            else:
                return JsonResponse({
                    'error': 'No preview file available',
                    'success': False
                })
        else:
            preview_file = dataset.preview_file
            preview_type = getattr(dataset, 'preview_type', 'csv')
        
        start_row = (page - 1) * page_size
        end_row = start_row + page_size
        
        # Read file based on type
        if preview_file:
            if hasattr(preview_file, 'path'):
                file_path = preview_file.path
            else:
                # Handle in-memory files
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(preview_file.name)[1]) as tmp:
                    for chunk in preview_file.chunks():
                        tmp.write(chunk)
                    file_path = tmp.name
            
            file_extension = preview_file.name.lower()
            
            if file_extension.endswith('.csv'):
                # Read specific rows from CSV
                df = pd.read_csv(file_path, skiprows=start_row, nrows=page_size, header=None if start_row > 0 else 0)
                if start_row > 0:
                    # We need to read headers separately
                    df_header = pd.read_csv(file_path, nrows=0)
                    df.columns = df_header.columns
            elif file_extension.endswith(('.xlsx', '.xls')):
                # Read specific rows from Excel
                df = pd.read_excel(file_path, skiprows=start_row, nrows=page_size)
            elif file_extension.endswith('.json'):
                # Read JSON
                with open(file_path, 'r') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    df = pd.DataFrame(data[start_row:end_row])
                else:
                    df = pd.DataFrame([data])
            else:
                return JsonResponse({
                    'error': 'Unsupported file format',
                    'success': False
                })
            
            # Get total rows for pagination
            total_rows = get_total_rows(preview_file)
            
            # Convert to JSON-friendly format
            rows = df.to_dict('records')
            for row in rows:
                for key, value in row.items():
                    if pd.isna(value):
                        row[key] = None
            
            return JsonResponse({
                'success': True,
                'columns': list(df.columns),
                'rows': rows,
                'page': page,
                'page_size': page_size,
                'total_rows': total_rows,
                'total_pages': (total_rows + page_size - 1) // page_size if total_rows > 0 else 1,
                'has_next': (page * page_size) < total_rows,
                'has_previous': page > 1
            })
            
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        })
    finally:
        # Clean up temporary file if created
        if 'tmp' in locals():
            try:
                os.unlink(file_path)
            except:
                pass


def get_total_rows(file_obj):
    """Get total number of rows in file (supports B2)"""
    import tempfile
    import pandas as pd
    import json
    import os
    
    tmp_file = None
    file_path = None
    
    try:
        # Handle B2 files
        if hasattr(file_obj, 'read'):
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_obj.name)[1])
            file_path = tmp_file.name
            tmp_file.write(file_obj.read())
            tmp_file.close()
            file_obj.seek(0)  # Reset pointer
        elif hasattr(file_obj, 'path'):
            file_path = file_obj.path
        else:
            return 0
        
        file_extension = file_obj.name.lower()
        
        if file_extension.endswith('.csv'):
            # Count CSV rows efficiently
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f) - 1  # Subtract header
        elif file_extension.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file_path)
            return len(df)
        elif file_extension.endswith('.json'):
            with open(file_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            else:
                return 1
        return 0
    except Exception as e:
        print(f"Error counting rows: {e}")
        return 0
    finally:
        # Clean up temp file
        if tmp_file and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except:
                pass
                

# ==================== RATING, COLLECTION, REPORT VIEWS ====================

@login_required
@require_POST
def rate_dataset(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Get or create rating
    rating_obj, created = DatasetRating.objects.get_or_create(
        user=request.user,
        dataset=dataset
    )
    
    form = RatingForm(request.POST, instance=rating_obj)
    if form.is_valid():
        form.save()
        
        # Update dataset average rating
        dataset.rating = dataset.get_average_rating()
        dataset.save()
        
        if created:
            messages.success(request, 'Thank you for rating this dataset!')
        else:
            messages.success(request, 'Your rating has been updated!')
    else:
        messages.error(request, 'Please enter a valid rating.')
    
    return redirect('dataset_detail', pk=pk)


@login_required
def save_to_collection(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    
    if request.method == 'POST':
        collection_id = request.POST.get('collection_id')
        action = request.POST.get('action')
        
        if collection_id:
            # Add/remove from existing collection
            try:
                collection = UserCollection.objects.get(id=collection_id, user=request.user)
                if action == 'add':
                    collection.datasets.add(dataset)
                    messages.success(request, f'Added to "{collection.name}" collection!')
                elif action == 'remove':
                    collection.datasets.remove(dataset)
                    messages.success(request, f'Removed from "{collection.name}" collection!')
            except UserCollection.DoesNotExist:
                messages.error(request, 'Collection not found.')
        else:
            # Create new collection
            form = CollectionForm(request.POST)
            if form.is_valid():
                collection = form.save(commit=False)
                collection.user = request.user
                collection.save()
                collection.datasets.add(dataset)
                messages.success(request, f'Created new collection "{collection.name}" and added the dataset!')
            else:
                messages.error(request, 'Please enter a valid collection name.')
    
    return redirect('dataset_detail', pk=pk)


@login_required
@require_POST
def report_dataset(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    
    form = ReportForm(request.POST, request.FILES)
    if form.is_valid():
        report = form.save(commit=False)
        report.user = request.user
        report.dataset = dataset
        report.save()
        
        messages.success(request, 'Thank you for reporting this issue. We will review it shortly.')
    else:
        messages.error(request, 'Please provide valid report details.')
    
    return redirect('dataset_detail', pk=pk)


@login_required
def toggle_collection(request, pk):
    """AJAX view to toggle dataset in collection"""
    dataset = get_object_or_404(Dataset, pk=pk)
    collection_id = request.GET.get('collection_id')
    
    try:
        collection = UserCollection.objects.get(id=collection_id, user=request.user)
        
        if dataset in collection.datasets.all():
            collection.datasets.remove(dataset)
            added = False
        else:
            collection.datasets.add(dataset)
            added = True
        
        return JsonResponse({
            'success': True,
            'added': added,
            'collection_name': collection.name,
            'in_collection': dataset.is_in_user_collection(request.user, collection_id)
        })
    except UserCollection.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Collection not found'})


# ==================== DATA REQUEST VIEWS ====================

@login_required
def download_request_form(request):
    # Path to your form template
    form_path = os.path.join(settings.BASE_DIR, 'static', 'forms', 'Data_Request_Form.docx')
    if os.path.exists(form_path):
        return FileResponse(open(form_path, 'rb'), as_attachment=True, filename='Data_Request_Form.docx')
    messages.error(request, 'The request form template is not currently available.')
    return redirect('dataset_list')


@login_required
def dataset_request(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Check for existing pending request
    existing_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status__in=['pending', 'manager_review', 'director_review']
    ).first()
    
    if existing_request:
        messages.info(request, 'You already have a pending request for this dataset.')
        return redirect('request_status', pk=existing_request.pk)
    
    if request.method == 'POST':
        # Process form data
        institution = request.POST.get('institution', '').strip()
        phone_number = request.POST.get('phone_number', '').strip()
        ethical_approval_no = request.POST.get('ethical_approval_no', '').strip()
        project_title = request.POST.get('project_title', '').strip()
        project_description = request.POST.get('project_description', '').strip()
        form_submission = request.FILES.get('form_submission')
        ethical_approval_proof = request.FILES.get('ethical_approval_proof')
        
        # Enhanced validation
        errors = []
        if not institution:
            errors.append('Institution is required')
        if not phone_number:
            errors.append('Phone number is required')
        if not project_title:
            errors.append('Project title is required')
        if not project_description:
            errors.append('Project description is required')
        if not form_submission:
            errors.append('Form submission file is required')
        elif not form_submission.name.lower().endswith('.pdf'):
            errors.append('Form submission must be a PDF file')
        
        # Optional validation for ethical approval proof
        if ethical_approval_proof:
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            file_ext = os.path.splitext(ethical_approval_proof.name.lower())[1]
            if file_ext not in allowed_extensions:
                errors.append('Ethical approval proof must be PDF, JPG, or PNG format')
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'datasets/request_form.html', {
                'dataset': dataset,
                'institution': institution,
                'phone_number': phone_number,
                'ethical_approval_no': ethical_approval_no,
                'project_title': project_title,
                'project_description': project_description
            })
        
        try:
            # Create and save DataRequest
            data_request = DataRequest(
                user=request.user,
                dataset=dataset,
                institution=institution,
                phone_number=phone_number if phone_number else None,
                ethical_approval_no=ethical_approval_no if ethical_approval_no else None,
                project_title=project_title,
                project_description=project_description,
                form_submission=form_submission,
                ethical_approval_proof=ethical_approval_proof if ethical_approval_proof else None,
            )
            data_request.save()
            
            # Send acknowledgment email using EmailService
            EmailService.send_acknowledgment_email(data_request)
            
            # Find and assign a data manager
            managers = User.objects.filter(role='data_manager', is_active=True)
            if managers.exists():
                data_request.manager = managers.first()
                data_request.save()
                
                # Send notification to manager
                EmailService.send_staff_notification(data_request, data_request.manager, 'manager')
            else:
                # If no manager found, send to admin as fallback
                admin_users = CustomUser.objects.filter(is_staff=True, is_active=True)
                for admin_user in admin_users:
                    send_mail(
                        "URGENT: No Data Manager Available",
                        f"A new data request (#{data_request.id}) was submitted but no data manager is available to review it.",
                        "no-reply@datican.org",
                        [admin_user.email],
                        fail_silently=True,
                    )
            
            # Render success page
            return render(request, 'datasets/request_submitted.html', {
                'dataset': dataset,
                'data_request': data_request
            })
            
        except Exception as e:
            messages.error(request, f'An error occurred: {str(e)}')
            return render(request, 'datasets/request_form.html', {
                'dataset': dataset,
                'institution': institution,
                'phone_number': phone_number,
                'ethical_approval_no': ethical_approval_no,
                'project_title': project_title,
                'project_description': project_description
            })
    
    return render(request, 'datasets/request_form.html', {
        'dataset': dataset
    })


@login_required
def request_status(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    # Check if user has permission to view this request
    can_view = (
        data_request.user == request.user or  # User owns the request
        request.user.is_superuser or          # Superuser can view all
        request.user.role in ['data_manager', 'director']  # Managers and directors can view
    )
    
    if not can_view:
        return HttpResponseForbidden()
    
    # Calculate remaining downloads (ensure it's not negative)
    remaining_downloads = max(0, data_request.max_downloads - data_request.download_count)
    
    # Determine button text and styling for the template
    if data_request.status == 'approved':
        if data_request.can_download():
            request_button_text = "Download Dataset"
            request_button_class = "bg-green-600 hover:bg-green-700"
            request_button_icon = "download"
        else:
            request_button_text = "Request Access Again"
            request_button_class = "bg-accent hover:bg-accent/90"
            request_button_icon = "file-text"
    elif data_request.status == 'rejected':
        request_button_text = "Submit New Request"
        request_button_class = "bg-accent hover:bg-accent/90"
        request_button_icon = "file-text"
    else:
        request_button_text = "View Request Status"
        request_button_class = "bg-blue-600 hover:bg-blue-700"
        request_button_icon = "clock"
    
    # Prepare status stages for visualization
    status_stages = [
        {
            'name': 'Submitted',
            'icon': 'clipboard-check',
            'active': True,
            'date': data_request.request_date,
            'status_class': 'completed',
            'description': 'Your request has been submitted'
        },
        {
            'name': 'Manager Review',
            'icon': 'user-check',
            'active': data_request.status in ['manager_review', 'director_review', 'approved', 'rejected'],
            'date': data_request.manager_review_date if data_request.manager_review_date else None,
            'status_class': 'completed' if data_request.status in ['manager_review', 'director_review', 'approved', 'rejected'] else 'pending',
            'description': data_request.data_manager_comment or 'Pending manager review'
        },
        {
            'name': 'Director Review',
            'icon': 'shield-check',
            'active': data_request.status in ['director_review', 'approved', 'rejected'],
            'date': data_request.approved_date if data_request.status in ['approved', 'rejected'] else None,
            'status_class': 'approved' if data_request.status == 'approved' else 'rejected' if data_request.status == 'rejected' else 'pending',
            'description': data_request.director_comment or ('Approved' if data_request.status == 'approved' else 'Rejected' if data_request.status == 'rejected' else 'Pending director review')
        }
    ]
    
    # Calculate current stage for progress tracking
    current_stage = 1
    if data_request.status in ['manager_review', 'director_review', 'approved', 'rejected']:
        current_stage = 2
    if data_request.status in ['director_review', 'approved', 'rejected']:
        current_stage = 3
    
    # Check if user can submit a new request
    can_request_again = False
    if data_request.status == 'approved':
        can_request_again = not data_request.can_download()  # Can request again if downloads exceeded
    elif data_request.status == 'rejected':
        can_request_again = True  # Can request again if rejected
    
    # Get download history if any
    download_history = []
    if data_request.download_count > 0:
        download_history = [
            {
                'count': i + 1,
                'date': data_request.last_download if i == data_request.download_count - 1 else None
            }
            for i in range(data_request.download_count)
        ]
    
    # Get file information for this dataset
    dataset = data_request.dataset
    files = dataset.get_all_files()
    
    # Prepare file list for template
    file_list = []
    for file in files:
        file_list.append({
            'id': file.id,
            'part_number': file.part_number,
            'filename': file.filename,
            'size': file.file_size,
            'size_display': file.get_file_size_display(),
            'total_parts': file.total_parts,
            'is_last': file.part_number == files.count()
        })
    
    return render(request, 'datasets/request_status.html', {
        'data_request': data_request,
        'can_download': data_request.can_download(),
        'status_stages': status_stages,
        'remaining_downloads': remaining_downloads,
        'current_stage': current_stage,
        'total_stages': len(status_stages),
        'request_button_text': request_button_text,
        'request_button_class': request_button_class,
        'request_button_icon': request_button_icon,
        'can_request_again': can_request_again,
        'download_history': download_history,
        'max_downloads': data_request.max_downloads,
        'download_count': data_request.download_count,
        # File information
        'files': file_list,
        'has_multi_part': files.count() > 1,
        'total_files': files.count(),
        'total_size_display': dataset.get_file_size_display(),
        'legacy_single_file': not files.exists() and dataset.dataset_path,
        'legacy_filename': dataset.dataset_path.split('/')[-1] if dataset.dataset_path else None,
    })


# ==================== MANAGER REVIEW VIEWS ====================

@login_required
@data_manager_required
def manager_review_request(request, pk): 
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        manager_comment = request.POST.get('manager_comment', '').strip()
        rejection_reason = request.POST.get('rejection_reason', '')
        manager_action_notes = request.POST.get('manager_action_notes', '').strip()
        
        if action == 'recommend':
            data_request.status = 'director_review'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'recommended'
            data_request.manager_action_notes = manager_action_notes
            data_request.manager_action_date = timezone.now()
            
            # Find and assign a director
            directors = CustomUser.objects.filter(role='director', is_active=True)
            if directors.exists():
                data_request.director = directors.first()
                messages.success(request, 'Request recommended and sent to director for final review.')
            else:
                data_request.status = 'manager_review'
                messages.warning(request, 'Request recommended but no director available.')
            
            data_request.save()
            
            # Send notifications
            if data_request.director:
                EmailService.send_staff_notification(data_request, data_request.director, 'director')
            
            EmailService.send_status_update_email(data_request, 'pending', request.user)
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'rejected'
            data_request.manager_action_notes = manager_action_notes
            data_request.manager_action_date = timezone.now()
            data_request.manager_rejection_reason = rejection_reason
            data_request.final_decision = 'rejected'
            
            data_request.save()
            messages.success(request, 'Request has been rejected.')
            
            EmailService.send_rejection_email(
                data_request, 
                request.user, 
                manager_comment, 
                'manager'
            )
            
        elif action == 'request_changes':
            data_request.status = 'pending'  # Send back to user
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'requested_changes'
            data_request.manager_action_notes = manager_action_notes
            data_request.manager_action_date = timezone.now()
            
            data_request.save()
            messages.success(request, 'Changes requested from user.')
            
            # Send email requesting changes
            EmailService.send_change_request_email(data_request, request.user, manager_action_notes)
            
        elif action == 'await_info':
            data_request.status = 'pending'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'pending_info'
            data_request.manager_action_notes = manager_action_notes
            data_request.manager_action_date = timezone.now()
            
            data_request.save()
            messages.success(request, 'Request marked as awaiting additional information.')
            
            EmailService.send_info_request_email(data_request, request.user, manager_action_notes)
        
        return redirect('review_requests_list')
    
    # Add rejection reasons to context
    return render(request, 'datasets/manager_review.html', {
        'data_request': data_request,
        'rejection_reasons': DataRequest.REASON_CHOICES,
    })


@login_required
@data_manager_required
def manager_review_list(request):
    """List all requests pending manager review"""
    # Get all requests that need manager review
    pending_requests = DataRequest.objects.filter(
        Q(status='pending') |
        Q(status='manager_review') |
        Q(status='needs_revision')
    ).select_related('user', 'dataset').order_by('-request_date')
    
    # Separate by status for better organization
    new_requests = DataRequest.objects.filter(
        status='pending'
    ).select_related('user', 'dataset').order_by('-request_date')
    
    in_review_requests = DataRequest.objects.filter(
        status='manager_review',
        manager=request.user  # Only show requests assigned to this manager
    ).select_related('user', 'dataset').order_by('-manager_review_date')
    
    needs_revision_requests = DataRequest.objects.filter(
        status='needs_revision'
    ).select_related('user', 'dataset').order_by('-manager_review_date')
    
    context = {
        'pending_requests': pending_requests,
        'new_requests': new_requests,
        'in_review_requests': in_review_requests,
        'needs_revision_requests': needs_revision_requests,
        'total_count': pending_requests.count(),
    }
    return render(request, 'datasets/request_review_list.html', context)


@login_required
@data_manager_required
def review_requests_list(request):
    """Show all requests pending manager review"""
    pending_requests = DataRequest.objects.filter(
        status__in=['pending', 'manager_review']
    ).select_related('user', 'dataset').order_by('request_date')
    
    return render(request, 'datasets/review_requests_list.html', {
        'pending_requests': pending_requests
    })


# ==================== DIRECTOR REVIEW VIEWS ====================

@login_required
@director_required
def director_review(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk, status='director_review')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        director_comment = request.POST.get('director_comment', '').strip()
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.approved_date = timezone.now()
            data_request.director_action = 'approved'
            
            data_request.save()
            messages.success(request, 'Request approved successfully!')
            
            # Send approval email with download link
            EmailService.send_approval_email(data_request)
            
            # Notify data manager about approval
            if data_request.manager:
                send_mail(
                    f"Request #{data_request.id} Approved",
                    f"The data request you recommended has been approved by the director.\n\n"
                    f"Request ID: {data_request.id}\n"
                    f"Dataset: {data_request.dataset.title}\n"
                    f"Researcher: {data_request.user.get_full_name()}\n"
                    f"Approval Date: {data_request.approved_date.strftime('%Y-%m-%d %H:%M')}\n"
                    f"Director Notes: {director_comment}",
                    "no-reply@datican.org",
                    [data_request.manager.email],
                    fail_silently=True,
                )
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'rejected'
            
            data_request.save()
            messages.success(request, 'Request has been rejected.')
            
            # Send rejection email to user
            EmailService.send_rejection_email(
                data_request, 
                request.user, 
                director_comment, 
                'director'
            )
            
            # Notify data manager about rejection
            if data_request.manager:
                send_mail(
                    f"Request #{data_request.id} Rejected",
                    f"The data request you recommended has been rejected by the director.\n\n"
                    f"Request ID: {data_request.id}\n"
                    f"Dataset: {data_request.dataset.title}\n"
                    f"Researcher: {data_request.user.get_full_name()}\n"
                    f"Rejection Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n"
                    f"Director Notes: {director_comment}",
                    "no-reply@datican.org",
                    [data_request.manager.email],
                    fail_silently=True,
                )
        
        return redirect('director_review_list')
    
    return render(request, 'datasets/director_review.html', {
        'data_request': data_request
    })


@login_required
@director_required
def director_review_list(request):
    """List all requests pending director review"""
    # Get all requests that need director review
    pending_requests = DataRequest.objects.filter(
        Q(status='director_review') |
        Q(manager_action='recommended', director_action='pending')
    ).select_related('user', 'manager', 'dataset').order_by('-submitted_to_director_date', '-request_date')
    
    context = {
        'pending_requests': pending_requests,
        'pending_count': pending_requests.count(),
    }
    return render(request, 'datasets/director_review_list.html', context)


@login_required
@user_passes_test(is_director, login_url='/login/')
def director_review_request(request, pk):
    """View for directors to review OR view approved requests"""
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    # Check if this request is already approved
    if data_request.director_action == 'approved' or data_request.status == 'approved':
        # Show read-only view for approved requests
        return render(request, 'datasets/director_review.html', {
            'data_request': data_request,
            'rejection_reasons': DataRequest.REASON_CHOICES,
        })
    
    # If NOT approved, then do the review checks
    # Check if manager has recommended it
    if data_request.manager_action != 'recommended':
        messages.error(request, 'This request has not been recommended by a manager for director review.')
        return redirect('director_dashboard')
    
    # Check if director hasn't already acted on it
    if data_request.director_action != 'pending':
        messages.warning(request, f'You have already taken action on this request: {data_request.get_director_action_display()}')
        return redirect('director_dashboard')
    
    # Check status
    if data_request.status not in ['director_review', 'manager_review']:
        messages.error(request, f'This request is not in a reviewable status. Current status: {data_request.get_status_display()}')
        return redirect('director_dashboard')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        director_comment = request.POST.get('director_comment', '').strip()
        rejection_reason = request.POST.get('rejection_reason', '')
        director_action_notes = request.POST.get('director_action_notes', '').strip()
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.approved_date = timezone.now()
            data_request.director_action = 'approved'
            data_request.director_action_notes = director_action_notes
            data_request.director_action_date = timezone.now()
            data_request.final_decision = 'approved'
            
            data_request.save()
            messages.success(request, 'Request approved successfully!')
            
            # Send approval email with download link
            EmailService.send_approval_email(data_request)
            
            # Notify data manager about approval
            if data_request.manager:
                send_mail(
                    f"Request #{data_request.id} Approved",
                    f"The data request you recommended has been approved by the director.",
                    "no-reply@datican.org",
                    [data_request.manager.email],
                    fail_silently=True,
                )
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'rejected'
            data_request.director_action_notes = director_action_notes
            data_request.director_action_date = timezone.now()
            data_request.director_rejection_reason = rejection_reason
            data_request.final_decision = 'rejected'
            
            data_request.save()
            messages.success(request, 'Request has been rejected.')

            # Send rejection email
            EmailService.send_rejection_email(data_request)

        elif action == 'return_to_manager':
            data_request.status = 'manager_review'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'returned_to_manager'
            data_request.director_action_notes = director_action_notes
            data_request.director_action_date = timezone.now()
            
            data_request.save()
            messages.success(request, 'Request returned to manager for further review.')

            # Notify data manager about return
            if data_request.manager:
                send_mail(
                    f"Request #{data_request.id} Returned to Manager",
                    f"The data request you recommended has been returned to you for further review.",
                    "no-reply@datican.org",
                    [data_request.manager.email],
                    fail_silently=True,
                )

        elif action == 'request_changes':
            data_request.status = 'pending'  # Return to user
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'requested_changes'
            data_request.director_action_notes = director_action_notes
            data_request.director_action_date = timezone.now()
            
            data_request.save()
            messages.success(request, 'Changes requested from user.')
            
            # Send email requesting changes
            EmailService.send_changes_requested_email(data_request)
        
        return redirect('director_dashboard')
    
    return render(request, 'datasets/director_review.html', {
        'data_request': data_request,
        'rejection_reasons': DataRequest.REASON_CHOICES,
    })


# ==================== ADMIN REVIEW VIEWS ====================

@login_required
@permission_required('datasets.review_datarequest', raise_exception=True)
def admin_review_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('admin_comment', '').strip()
        
        if action == 'approve':
            # Admin can directly approve
            data_request.status = 'approved'
            data_request.director = request.user
            data_request.director_comment = f"Admin approval: {comment}"
            data_request.approved_date = timezone.now()
            data_request.director_action = 'approved'
            
            # If no manager assigned, assign admin as manager too
            if not data_request.manager:
                data_request.manager = request.user
                data_request.data_manager_comment = f"Admin processed: {comment}"
                data_request.manager_action = 'recommended'
                data_request.manager_review_date = timezone.now()
            
            data_request.save()
            messages.success(request, '✅ Request approved via admin override.')
            
            # Send approval email
            EmailService.send_approval_email(data_request)
            
        elif action == 'forward':
            # Forward to director for normal review
            data_request.status = 'director_review'
            if not data_request.manager:
                data_request.manager = request.user
                data_request.data_manager_comment = f"Admin forwarded: {comment}"
                data_request.manager_action = 'recommended'
                data_request.manager_review_date = timezone.now()
            
            # Find a director if not already assigned
            if not data_request.director:
                directors = CustomUser.objects.filter(role='director', is_active=True)
                if directors.exists():
                    data_request.director = directors.first()
            
            data_request.save()
            messages.success(request, '📤 Request forwarded to director.')
            
            # Notify director if assigned
            if data_request.director:
                EmailService.send_staff_notification(data_request, data_request.director, 'director')
            
        elif action == 'reject':
            data_request.status = 'rejected'
            if not data_request.manager:
                data_request.manager = request.user
            data_request.data_manager_comment = f"Admin rejected: {comment}"
            data_request.manager_action = 'rejected'
            data_request.manager_review_date = timezone.now()
            
            data_request.save()
            messages.success(request, '❌ Request rejected via admin override.')
            
            # Send rejection email
            EmailService.send_rejection_email(
                data_request, 
                request.user, 
                comment, 
                'admin'
            )
        
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/admin_review.html', {
        'data_request': data_request,
        'is_admin': True,
    })


@login_required
@permission_required('datasets.approve_datarequest', raise_exception=True)
def approve_request(request, pk):
    """Admin/superuser approval view (bypasses normal workflow)"""
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.approved_date = timezone.now()
            data_request.director = request.user
            data_request.director_comment = f"Admin override: {comment}"
            data_request.director_action = 'approved'
            
            data_request.save()
            messages.success(request, 'Request approved via admin override.')
            
            # Send approval email
            EmailService.send_approval_email(data_request)
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = f"Admin override: {comment}"
            data_request.director_action = 'rejected'
            
            data_request.save()
            messages.success(request, 'Request rejected via admin override.')
            
            # Send rejection email
            EmailService.send_rejection_email(
                data_request, 
                request.user, 
                comment, 
                'admin'
            )
        
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/admin_approve_request.html', {
        'data_request': data_request
    })


# ==================== DASHBOARD VIEWS ====================

@login_required
def redirect_after_login(request):
    """Redirect users based on their role after login"""
    user = request.user
    
    if user.is_superuser:
        return redirect('admin_dashboard')
    elif user.role == 'director':
        return redirect('director_dashboard')
    elif user.role == 'data_manager':
        return redirect('manager_dashboard')
    else:
        # Regular users go to dataset list
        return redirect('dataset_list')


@login_required
@user_passes_test(is_manager, login_url='/login/')
def manager_dashboard(request):
    # Get ALL pending requests for this manager
    pending_requests = DataRequest.objects.filter(
        manager_id=request.user.id
    ).filter(
        Q(status__in=['pending', 'manager_review']) | 
        Q(manager_action='pending')
    ).distinct().count()
    
    # Get requests with different manager actions
    recommended_by_manager = DataRequest.objects.filter(
        manager_id=request.user.id,
        manager_action='recommended'
    ).count()
    
    rejected_by_manager = DataRequest.objects.filter(
        manager_id=request.user.id,
        manager_action='rejected'
    ).count()
    
    requested_changes = DataRequest.objects.filter(
        manager_id=request.user.id,
        manager_action='requested_changes'
    ).count()
    
    awaiting_info = DataRequest.objects.filter(
        manager_id=request.user.id,
        manager_action='pending_info'
    ).count()
    
    # Get breakdown of manager actions
    manager_action_breakdown = DataRequest.objects.filter(
        manager_id=request.user.id
    ).exclude(manager_action='pending').values('manager_action').annotate(
        count=Count('id')
    ).order_by('-count')
    
    context = {
        'pending_count': pending_requests,
        'recommended_by_manager_count': recommended_by_manager,
        'rejected_by_manager_count': rejected_by_manager,
        'requested_changes_count': requested_changes,
        'awaiting_info_count': awaiting_info,
        'manager_action_breakdown': manager_action_breakdown,
    }
    return render(request, 'dashboard/manager_dashboard.html', context)


@login_required
@user_passes_test(is_director, login_url='/login/')
def director_dashboard(request):
    # Get ALL pending requests for director review
    pending_director_reviews = DataRequest.objects.filter(
        Q(status='director_review') |  # Status is director_review
        Q(manager_action='recommended', director_action='pending')  # OR manager recommended but director hasn't acted
    ).count()
    
    # Get requests approved by this director
    director_approved = DataRequest.objects.filter(
        director_id=request.user.id,
        director_action='approved'
    ).count()
    
    # Get requests rejected by this director
    director_rejected = DataRequest.objects.filter(
        director_id=request.user.id,
        director_action='rejected'
    ).count()
    
    # Calculate approval rate
    director_total_decisions = director_approved + director_rejected
    approval_rate = (director_approved / director_total_decisions * 100) if director_total_decisions > 0 else 0
    
    # Get system-wide stats
    total_approved = DataRequest.objects.filter(status='approved').count()
    total_requests = DataRequest.objects.count()
    
    # Calculate average review time (in days)
    approved_requests = DataRequest.objects.filter(
        director_id=request.user.id,
        director_action='approved'
    ).exclude(approved_date__isnull=True).exclude(submitted_to_director_date__isnull=True)
    
    total_days = 0
    count = 0
    for req in approved_requests:
        if req.approved_date and req.submitted_to_director_date:
            review_time = (req.approved_date - req.submitted_to_director_date).total_seconds() / 86400  # Convert to days
            total_days += review_time
            count += 1
    
    avg_review_time = round(total_days / count, 1) if count > 0 else 2.3  # Default to 2.3 days
    
    # Get pending requests from last 30 days
    thirty_days_ago = timezone.now() - timedelta(days=30)
    pending_30_days = DataRequest.objects.filter(
        Q(status='director_review') |
        Q(manager_action='recommended', director_action='pending'),
        submitted_to_director_date__gte=thirty_days_ago
    ).count()
    
    # Get lists for display
    pending_director_list = DataRequest.objects.filter(
        Q(status='director_review') |
        Q(manager_action='recommended', director_action='pending')
    ).select_related('user', 'manager', 'dataset').order_by('-submitted_to_director_date', '-request_date')[:10]
    
    director_approved_list = DataRequest.objects.filter(
        director_id=request.user.id,
        director_action='approved'
    ).select_related('user', 'manager', 'dataset').order_by('-approved_date')[:10]
    
    director_rejected_list = DataRequest.objects.filter(
        director_id=request.user.id,
        director_action='rejected'
    ).select_related('user', 'manager', 'dataset').order_by('-approved_date')[:10]
    
    context = {
        'pending_director_count': pending_director_reviews,
        'director_approved_count': director_approved,
        'director_rejected_count': director_rejected,
        'director_total_decisions': director_total_decisions,
        'approval_rate': approval_rate,
        'total_approved': total_approved,
        'total_requests': total_requests,
        'avg_review_time': avg_review_time,
        'pending_30_days': pending_30_days,
        
        # Lists
        'pending_requests_list': pending_director_list,
        'approved_requests_list': director_approved_list,
        'rejected_requests_list': director_rejected_list,
    }
    return render(request, 'dashboard/director_dashboard.html', context)


@login_required
@user_passes_test(is_superuser, login_url='/login/')
def admin_dashboard(request):
    # Fix status names - use actual status values from your model
    total_requests = DataRequest.objects.count()
    pending_review = DataRequest.objects.filter(status='pending').count()
    manager_review = DataRequest.objects.filter(status='manager_review').count()
    director_review = DataRequest.objects.filter(status='director_review').count()
    approved = DataRequest.objects.filter(status='approved').count()
    rejected = DataRequest.objects.filter(status='rejected').count()
    
    total_users = User.objects.count()
    managers = User.objects.filter(role='data_manager').count()
    directors = User.objects.filter(role='director').count()
    
    # Recent activity
    last_week = timezone.now() - timedelta(days=7)
    recent_requests = DataRequest.objects.filter(
        request_date__gte=last_week
    ).count()
    
    # Calculate regular users
    regular_users = total_users - managers - directors
    
    context = {
        'total_requests': total_requests,
        'pending_review': pending_review,
        'manager_review': manager_review,
        'director_review': director_review,
        'approved': approved,
        'rejected': rejected,
        'total_users': total_users,
        'managers': managers,
        'directors': directors,
        'regular_users': regular_users,
        'recent_requests': recent_requests,
        'completion_rate': ((approved + rejected) / total_requests * 100) if total_requests > 0 else 0,
    }
    return render(request, 'dashboard/admin_dashboard.html', context)


# ==================== REPORT VIEWS ====================

@admin_required
def all_requests_report(request):
    """
    Comprehensive report of all data requests for admins only
    """
    if not request.user.is_authenticated:
        return redirect('login')
    
    # Check admin permissions
    if request.user.role not in ['director', 'data_manager'] and not request.user.is_superuser:
        messages.error(request, "Access denied. Admin privileges required.")
        return redirect('dataset_list')
    
    # Get all data requests with related data
    all_requests = DataRequest.objects.all().select_related(
        'user', 'dataset', 'manager', 'director'
    ).order_by('-request_date')
    
    # Filter based on user role
    if request.user.role == 'director' or request.user.is_superuser:
        # Director and superusers see everything
        pass  # already have all_requests
    elif request.user.role == 'data_manager':
        # Managers see requests they've reviewed or are pending
        all_requests = all_requests.filter(
            Q(status__in=['manager_review', 'director_review', 'approved', 'rejected']) |
            Q(manager=request.user)
        )
    else:
        # Regular users should have been redirected already
        return redirect('dataset_list')
    
    # Calculate statistics
    total_requests = all_requests.count()
    pending_requests = all_requests.filter(status__in=['pending', 'manager_review', 'director_review']).count()
    approved_requests = all_requests.filter(status='approved').count()
    rejected_requests = all_requests.filter(status='rejected').count()
    
    # Approval rate
    approval_rate = 0
    if total_requests > 0:
        approval_rate = (approved_requests / total_requests) * 100
    
    # Status distribution
    status_counts = all_requests.values('status').annotate(count=Count('id')).order_by('status')
    
    # Monthly trends (last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    monthly_stats = all_requests.filter(
        request_date__gte=six_months_ago
    ).annotate(
        month=TruncMonth('request_date')
    ).values('month').annotate(
        total=Count('id'),
        approved=Count('id', filter=Q(status='approved')),
        rejected=Count('id', filter=Q(status='rejected'))
    ).order_by('month')
    
    # Manager performance (for directors and superusers)
    manager_stats = None
    if request.user.role == 'director' or request.user.is_superuser:
        manager_stats = DataRequest.objects.filter(
            manager__isnull=False
        ).values(
            'manager__email',
            'manager__first_name',
            'manager__last_name',
            'manager__role'
        ).annotate(
            total_reviewed=Count('id'),
            recommended=Count('id', filter=Q(manager_action='recommended')),
            rejected=Count('id', filter=Q(manager_action='rejected')),
            pending=Count('id', filter=Q(manager_action__isnull=True) & Q(status='manager_review'))
        ).order_by('-total_reviewed')
    
    # Director performance (for superusers or self-review)
    director_stats = None
    if request.user.is_superuser or request.user.role == 'director':
        director_stats = DataRequest.objects.filter(
            director__isnull=False
        ).values(
            'director__email',
            'director__first_name',
            'director__last_name'
        ).annotate(
            total_reviewed=Count('id'),
            approved=Count('id', filter=Q(director_action='approved')),
            rejected=Count('id', filter=Q(director_action='rejected')),
            pending=Count('id', filter=Q(director_action__isnull=True) & Q(status='director_review'))
        ).order_by('-total_reviewed')
    
    # Overall system performance
    avg_processing_time = None
    if request.user.role == 'director' or request.user.is_superuser:
        # Calculate average time from request to approval
        approved_with_dates = DataRequest.objects.filter(
            status='approved',
            request_date__isnull=False,
            approved_date__isnull=False
        )
        if approved_with_dates.exists():
            # This is a simplified calculation
            total_days = sum([
                (req.approved_date - req.request_date).days 
                for req in approved_with_dates
                if req.approved_date > req.request_date
            ], 0)
            avg_processing_time = total_days / approved_with_dates.count() if approved_with_dates.count() > 0 else 0
    
    context = {
        'all_requests': all_requests,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'approval_rate': approval_rate,
        'status_counts': status_counts,
        'monthly_stats': monthly_stats,
        'manager_stats': manager_stats,
        'director_stats': director_stats,
        'avg_processing_time': avg_processing_time,
        'user_role': request.user.role,
        'is_superuser': request.user.is_superuser,
    }
    
    return render(request, 'datasets/all_requests_report.html', context)


@login_required
def my_requests(request):
    """Show all requests made by the current user"""
    user_requests = DataRequest.objects.filter(user=request.user).select_related(
        'dataset', 'manager', 'director'
    ).order_by('-request_date')
    
    context = {
        'user_requests': user_requests,
        'total_requests': user_requests.count(),
        'approved_requests': user_requests.filter(status='approved').count(),
        'pending_requests': user_requests.filter(status__in=['pending', 'manager_review', 'director_review']).count(),
        'rejected_requests': user_requests.filter(status='rejected').count(),
    }
    
    return render(request, 'datasets/my_requests.html', context)


# ==================== LEGACY DOWNLOAD VIEWS ====================

@login_required
def dataset_download(request, pk):
    """
    Legacy download view - redirects to multi-part download
    Maintained for backward compatibility
    """
    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Check if multi-part or single file
    if dataset.files.exists():
        # Multi-part - redirect to status page which has download buttons
        data_request = DataRequest.objects.filter(
            user=request.user,
            dataset=dataset,
            status='approved'
        ).first()
        
        if data_request:
            return redirect('request_status', pk=data_request.pk)
        else:
            return redirect('dataset_detail', pk=pk)
    else:
        # Legacy single file
        return redirect('dataset_download_b2', pk=pk)


@login_required
@require_GET
def dataset_download_b2(request, pk):
    """
    Generate a signed B2 URL and redirect the user.
    Requires approved DataRequest with remaining downloads.
    """
    # Basic bot detection
    if is_bot_request(request):
        logger.warning(f"Blocked potential bot download attempt: {request.META.get('HTTP_USER_AGENT', '')}")
        return HttpResponseForbidden("Automated downloads are not allowed.")

    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Find approved request for this user and dataset
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).order_by('-approved_date').first()
    
    # Authorization check
    if not data_request:
        messages.error(request, 'You do not have an approved request for this dataset.')
        return redirect('dataset_detail', pk=pk)
    
    if not data_request.can_download():
        messages.error(request, 
            f'You have reached your download limit ({data_request.max_downloads} downloads). '
            f'Please contact support if you need access to the data again.'
        )
        return redirect('request_status', pk=data_request.pk)
    
    try:
        # Generate signed URL (valid for 5 minutes)
        download_url = dataset.get_download_url(expiration=300)
        
        if not download_url:
            messages.error(request, 'The dataset file is not available. Please contact support.')
            return redirect('dataset_detail', pk=pk)
        
        # Record the download
        data_request.record_download()
        
        # Increment dataset download count
        dataset.download_count += 1
        dataset.save(update_fields=['download_count'])
        
        # Log the download
        logger.info(f"User {request.user.email} downloaded dataset {dataset.id} (Request #{data_request.id})")
        
        # Send download confirmation email (async recommended)
        try:
            from .utils.email_service import EmailService
            EmailService.send_download_confirmation(data_request, dataset)
        except Exception as e:
            logger.error(f"Failed to send download confirmation email: {e}")
        
        # Redirect to the signed URL
        return HttpResponseRedirect(download_url)
        
    except Exception as e:
        logger.error(f"Download failed for dataset {dataset.id}: {str(e)}")
        messages.error(request, 'Download failed. Please try again or contact support.')
        return redirect('dataset_detail', pk=pk)


# ==================== MULTI-PART DATASET DOWNLOAD VIEWS ====================

@login_required
@require_GET
def get_dataset_files_api(request, dataset_id):
    """
    API endpoint to get all files for a dataset (requires approval)
    Returns JSON with list of files and download URLs
    """
    dataset = get_object_or_404(Dataset, id=dataset_id)
    
    # Check if user has approved request
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    if not data_request:
        return JsonResponse({
            'success': False,
            'error': 'Not approved',
            'requires_approval': True
        }, status=403)
    
    if not data_request.can_download():
        return JsonResponse({
            'success': False,
            'error': 'Download limit reached',
            'download_count': data_request.download_count,
            'max_downloads': data_request.max_downloads
        }, status=403)
    
    files = dataset.get_all_files()
    
    # Handle legacy single file
    if not files.exists() and dataset.dataset_path:
        # Record this download attempt (will be counted when actual download happens)
        return JsonResponse({
            'success': True,
            'dataset_id': dataset.id,
            'dataset_title': dataset.title,
            'total_files': 1,
            'total_size': dataset.b2_file_size,
            'total_size_display': dataset.get_file_size_display(),
            'is_multi_part': False,
            'files': [
                {
                    'part_number': 1,
                    'filename': dataset.dataset_path.split('/')[-1],
                    'size': dataset.b2_file_size,
                    'size_display': dataset.get_file_size_display(),
                    'download_url': dataset.get_download_url(expiration=3600),
                    'expires_in': '1 hour'
                }
            ]
        })
    
    # Multi-part files
    file_list = []
    for file in files:
        file_list.append({
            'part_number': file.part_number,
            'filename': file.filename,
            'size': file.file_size,
            'size_display': file.get_file_size_display(),
            'download_url': file.get_download_url(expiration=3600),
            'expires_in': '1 hour'
        })
    
    return JsonResponse({
        'success': True,
        'dataset_id': dataset.id,
        'dataset_title': dataset.title,
        'total_files': len(file_list),
        'total_size': dataset.get_total_size(),
        'total_size_display': dataset.get_file_size_display(),
        'is_multi_part': len(file_list) > 1,
        'files': file_list
    })


@login_required
def download_dataset_part(request, dataset_id, part_number):
    """
    Redirect to signed URL for a specific dataset part
    Records the download and tracks usage
    """
    # Basic bot detection
    if is_bot_request(request):
        logger.warning(f"Blocked potential bot download attempt: {request.META.get('HTTP_USER_AGENT', '')}")
        return HttpResponseForbidden("Automated downloads are not allowed.")
    
    dataset = get_object_or_404(Dataset, id=dataset_id)
    
    # Find approved request for this user and dataset
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    # Authorization check
    if not data_request:
        messages.error(request, 'You do not have an approved request for this dataset.')
        return redirect('dataset_detail', pk=dataset_id)
    
    if not data_request.can_download():
        messages.error(request, 
            f'You have reached your download limit ({data_request.max_downloads} downloads). '
            f'Please contact support if you need access again.'
        )
        return redirect('request_status', pk=data_request.pk)
    
    try:
        # Handle legacy single file
        if part_number == 1 and dataset.dataset_path and not dataset.files.exists():
            download_url = dataset.get_download_url(expiration=300)  # 5 minutes
            filename = dataset.dataset_path.split('/')[-1]
        else:
            # Get specific part
            file = dataset.get_file_by_part(part_number)
            if not file:
                messages.error(request, f'Part {part_number} not found.')
                return redirect('dataset_detail', pk=dataset_id)
            
            download_url = file.get_download_url(expiration=300)  # 5 minutes
            filename = file.filename
        
        if not download_url:
            messages.error(request, 'The file is not available. Please contact support.')
            return redirect('dataset_detail', pk=dataset_id)
        
        # Record the download
        data_request.record_download()
        
        # Increment dataset download count
        dataset.download_count += 1
        dataset.save(update_fields=['download_count'])
        
        # Log the download
        logger.info(f"User {request.user.email} downloaded {filename} from dataset {dataset.id} (Request #{data_request.id})")
        
        # Send download confirmation email (optional)
        try:
            from .utils.email_service import EmailService
            EmailService.send_download_confirmation(data_request, dataset, filename)
        except Exception as e:
            logger.error(f"Failed to send download confirmation email: {e}")
        
        # Redirect to the signed URL
        return HttpResponseRedirect(download_url)
        
    except Exception as e:
        logger.error(f"Download failed for dataset {dataset.id} part {part_number}: {str(e)}")
        messages.error(request, 'Download failed. Please try again or contact support.')
        return redirect('dataset_detail', pk=dataset_id)


@login_required
@require_GET
def download_dataset_script(request, dataset_id):
    """
    Generate a bash script for downloading all parts of a dataset
    """
    dataset = get_object_or_404(Dataset, id=dataset_id)
    
    # Check if user has approved request
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    if not data_request:
        return HttpResponseForbidden("You don't have an approved request for this dataset.")
    
    if not data_request.can_download():
        return HttpResponseForbidden("You have reached your download limit.")
    
    files = dataset.get_all_files()
    
    script_lines = ['#!/bin/bash', '# Download script for ' + dataset.title, '']
    script_lines.append(f'# Request ID: {data_request.id}')
    script_lines.append(f'# User: {request.user.email}')
    script_lines.append('')
    
    if not files.exists() and dataset.dataset_path:
        # Legacy single file
        url = dataset.get_download_url(expiration=86400)  # 24 hour expiry
        filename = dataset.dataset_path.split('/')[-1]
        script_lines.append(f'echo "Downloading {filename}..."')
        script_lines.append(f'wget -O "{filename}" "{url}"')
        script_lines.append('')
        script_lines.append('echo "Download complete!"')
    else:
        # Multi-part files
        script_lines.append('# Download all parts sequentially')
        script_lines.append('')
        
        for file in files:
            url = file.get_download_url(expiration=86400)  # 24 hour expiry
            script_lines.append(f'echo "Downloading {file.filename} (Part {file.part_number}/{file.total_parts})..."')
            script_lines.append(f'wget -O "{file.filename}" "{url}"')
            script_lines.append('')
        
        if files.count() > 1:
            script_lines.append('echo "All parts downloaded successfully!"')
            script_lines.append('')
            script_lines.append('# Check if files are split archives and combine if needed')
            script_lines.append('if [[ "$(file part1.zip)" == *"Zip archive data"* ]]; then')
            script_lines.append('    echo "Detected ZIP files. Combining parts..."')
            script_lines.append('    cat part*.zip > combined_dataset.zip')
            script_lines.append('    echo "Created combined_dataset.zip"')
            script_lines.append('fi')
    
    script = '\n'.join(script_lines)
    
    response = HttpResponse(script, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="download_dataset_{dataset_id}.sh"'
    
    return response


@login_required
@require_GET
def get_part_download_url_api(request, dataset_id, part_number):
    """
    API endpoint to get a signed URL for a specific part (for AJAX)
    Returns JSON with the download URL without redirecting
    """
    dataset = get_object_or_404(Dataset, id=dataset_id)
    
    # Check authorization
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    if not data_request:
        return JsonResponse({
            'success': False,
            'error': 'Not authorized'
        }, status=403)
    
    if not data_request.can_download():
        return JsonResponse({
            'success': False,
            'error': 'Download limit reached',
            'download_count': data_request.download_count,
            'max_downloads': data_request.max_downloads
        }, status=403)
    
    try:
        # Handle legacy single file
        if part_number == 1 and dataset.dataset_path and not dataset.files.exists():
            download_url = dataset.get_download_url(expiration=3600)
            filename = dataset.dataset_path.split('/')[-1]
            file_size = dataset.b2_file_size
        else:
            file = dataset.get_file_by_part(part_number)
            if not file:
                return JsonResponse({
                    'success': False,
                    'error': f'Part {part_number} not found'
                }, status=404)
            
            download_url = file.get_download_url(expiration=3600)
            filename = file.filename
            file_size = file.file_size
        
        if not download_url:
            return JsonResponse({
                'success': False,
                'error': 'File not available'
            }, status=404)
        
        # Don't record download here - that happens when user actually clicks download
        # The download will be recorded in download_dataset_part view
        
        return JsonResponse({
            'success': True,
            'part_number': part_number,
            'filename': filename,
            'size': file_size,
            'size_display': format_file_size(file_size),
            'download_url': download_url,
            'expires_in': '1 hour'
        })
        
    except Exception as e:
        logger.error(f"Error generating download URL: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_GET
def get_dataset_parts_list(request, dataset_id):
    """
    Get list of parts for a dataset (for AJAX loading in templates)
    """
    dataset = get_object_or_404(Dataset, id=dataset_id)
    
    # Check if user has approved request (optional - you might want to show list but not URLs)
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    files = dataset.get_all_files()
    
    if not files.exists() and dataset.dataset_path:
        # Legacy single file
        return JsonResponse({
            'success': True,
            'dataset_id': dataset.id,
            'dataset_title': dataset.title,
            'total_parts': 1,
            'total_size': dataset.b2_file_size,
            'total_size_display': dataset.get_file_size_display(),
            'is_multi_part': False,
            'has_access': data_request is not None and data_request.can_download() if data_request else False,
            'parts': [
                {
                    'part_number': 1,
                    'filename': dataset.dataset_path.split('/')[-1],
                    'size': dataset.b2_file_size,
                    'size_display': dataset.get_file_size_display(),
                }
            ]
        })
    
    parts_list = []
    for file in files:
        parts_list.append({
            'part_number': file.part_number,
            'filename': file.filename,
            'size': file.file_size,
            'size_display': file.get_file_size_display(),
        })
    
    return JsonResponse({
        'success': True,
        'dataset_id': dataset.id,
        'dataset_title': dataset.title,
        'total_parts': len(parts_list),
        'total_size': dataset.get_total_size(),
        'total_size_display': dataset.get_file_size_display(),
        'is_multi_part': len(parts_list) > 1,
        'has_access': data_request is not None and data_request.can_download() if data_request else False,
        'parts': parts_list
    })


@login_required
@require_POST
def record_download_api(request, request_id):
    """
    API endpoint to record a download (for AJAX tracking)
    """
    try:
        data_request = get_object_or_404(DataRequest, id=request_id, user=request.user)
        
        if data_request.status != 'approved':
            return JsonResponse({
                'success': False,
                'error': 'Request not approved'
            }, status=403)
        
        if not data_request.can_download():
            return JsonResponse({
                'success': False,
                'error': 'Download limit reached',
                'download_count': data_request.download_count,
                'max_downloads': data_request.max_downloads
            }, status=403)
        
        data_request.download_count += 1
        data_request.last_download = timezone.now()
        data_request.save()
        
        # Increment dataset download count
        dataset = data_request.dataset
        dataset.download_count += 1
        dataset.save(update_fields=['download_count'])
        
        return JsonResponse({
            'success': True,
            'download_count': data_request.download_count,
            'remaining': data_request.max_downloads - data_request.download_count
        })
        
    except DataRequest.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Request not found'
        }, status=404)
    except Exception as e:
        logger.error(f"Error recording download: {e}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


# ==================== REQUEST DOCUMENT VIEWS ====================
@login_required
def request_document_download(request, pk, doc_type):
    data_request = get_object_or_404(DataRequest, pk=pk)

    if data_request.user != request.user and not request.user.is_staff:
        return HttpResponseForbidden()

    file_field = data_request.form_submission if doc_type == 'form' else data_request.ethical_approval_proof

    if not file_field:
        return HttpResponseNotFound("Document not found.")

    # file_field.name is like "request-documents/3/form_3_8bc1ccd6.pdf"
    # We need to extract the path after "request-documents/"
    # Method 1: Use the full name with the protected prefix
    internal_path = f"/protected-request-documents/{file_field.name.replace('request-documents/', '')}"

    # Method 2: More explicit - construct from parts
    # filename = os.path.basename(file_field.name)
    # internal_path = f"/protected-request-docs/{data_request.id}/{filename}"

    response = HttpResponse()
    response['X-Accel-Redirect'] = internal_path
    response['Content-Type'] = 'application/octet-stream'
    response['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_field.name)}"'
    return response


@login_required
def get_readme_url(request, pk):
    """Generate signed URL for README file"""
    dataset = get_object_or_404(Dataset, pk=pk)
    
    if not dataset.readme_file:
        return JsonResponse({'error': 'No README file available'}, status=404)
    
    try:
        readme_url = dataset.get_readme_url(expiration=3600)
        return JsonResponse({'url': readme_url})
    except Exception as e:
        logger.error(f"README access failed for dataset {dataset.id}: {e}")
        return JsonResponse({'error': 'README unavailable'}, status=500)


@login_required
def preview_dataset_file(request, pk):
    """
    Generate signed URL for preview file
    Less restrictive - any authenticated user can view previews
    """
    dataset = get_object_or_404(Dataset, pk=pk)
    
    if not dataset.preview_file:
        return JsonResponse({'error': 'No preview file available'}, status=404)
    
    try:
        preview_url = dataset.get_preview_url(expiration=3600)
        return HttpResponseRedirect(preview_url)
    except Exception as e:
        logger.error(f"Preview failed for dataset {dataset.id}: {e}")
        return JsonResponse({'error': 'Preview unavailable'}, status=500)


# ==================== ADDITIONAL MANAGER/DIRECTOR VIEWS ====================

@login_required
@data_manager_required
def manager_recommended_requests(request):
    """View for manager's recommended requests"""
    recommendations = DataRequest.objects.filter(
        manager=request.user,
        manager_action='recommended'
    ).select_related('user', 'dataset', 'director')
    
    return render(request, 'datasets/manager_recommendations.html', {
        'recommendations': recommendations
    })


@login_required
@data_manager_required
def manager_recommendations(request):
    """Alias for manager_recommended_requests"""
    return manager_recommended_requests(request)


@login_required
@data_manager_required
def manager_rejected_requests(request):
    """Show data manager's rejected requests"""
    rejections = DataRequest.objects.filter(
        manager=request.user,
        manager_action='rejected'
    ).select_related('user', 'dataset')
    
    return render(request, 'datasets/manager_rejections.html', {
        'rejections': rejections
    })


@login_required
@data_manager_required
def manager_rejections(request):
    """Alias for manager_rejected_requests"""
    return manager_rejected_requests(request)


@login_required
@data_manager_required
def director_decisions_for_manager(request):
    """Show director decisions on requests reviewed by this manager"""
    # Get all requests where manager reviewed AND director made a decision
    director_decisions = DataRequest.objects.filter(
        manager=request.user,
        status__in=['approved', 'rejected'],  # Director decided
        director_action__isnull=False  # Director took action
    ).select_related('user', 'dataset', 'director').order_by('-approved_date')
    
    context = {
        'requests': director_decisions,
        'title': 'Director Decisions on Your Requests',
        'subtitle': 'Final decisions made by the director on requests you reviewed'
    }
    return render(request, 'dashboard/request_list.html', context)


@login_required
@director_required
def director_approved_requests(request):
    """Show director's approved requests"""
    approvals = DataRequest.objects.filter(
        director=request.user,
        status='approved',
        director_action='approved'
    ).select_related('user', 'dataset', 'manager')
    
    return render(request, 'datasets/director_approvals.html', {
        'approvals': approvals
    })


@login_required
@director_required
def director_approvals(request):
    """Alias for director_approved_requests"""
    return director_approved_requests(request)


@login_required
@director_required
def director_rejected_requests(request):
    """Show director's rejected requests"""
    rejections = DataRequest.objects.filter(
        director=request.user,
        status='rejected',
        director_action='rejected'
    ).select_related('user', 'dataset', 'manager')
    
    return render(request, 'datasets/director_rejections.html', {
        'rejections': rejections
    })


@login_required
@director_required
def director_rejections(request):
    """Alias for director_rejected_requests"""
    return director_rejected_requests(request)


@login_required
@admin_required
def admin_all_requests(request):
    """Show all requests for admin/superuser"""
    all_requests = DataRequest.objects.select_related(
        'user', 'dataset', 'manager', 'director'
    ).order_by('-request_date')
    
    # Filtering capability
    status_filter = request.GET.get('status', '')
    manager_filter = request.GET.get('manager', '')
    director_filter = request.GET.get('director', '')
    
    if status_filter:
        all_requests = all_requests.filter(status=status_filter)
    if manager_filter:
        all_requests = all_requests.filter(manager_id=manager_filter)
    if director_filter:
        all_requests = all_requests.filter(director_id=director_filter)
    
    # Get filter options for the template
    managers = User.objects.filter(role='data_manager')
    directors = User.objects.filter(role='director')
    
    context = {
        'requests': all_requests,
        'title': 'All Data Requests',
        'subtitle': 'Complete overview of all data requests in the system',
        'managers': managers,
        'directors': directors,
        'current_status': status_filter,
        'current_manager': manager_filter,
        'current_director': director_filter,
    }
    return render(request, 'dashboard/admin_requests.html', context)


# ==================== EMAIL FUNCTIONALITY ====================

@login_required
@permission_required('datasets.review_datarequest', raise_exception=True)
def resend_notification(request, request_id):
    """Resend notification email for a request"""
    from .models import DataRequest
    from .utils.email_service import EmailService
    
    data_request = get_object_or_404(DataRequest, id=request_id)
    
    success = False
    message = ""
    
    if data_request.status == 'pending' and data_request.manager:
        success = EmailService.send_staff_notification(data_request, data_request.manager, 'manager')
        message = 'Manager notification resent.'
    elif data_request.status == 'approved':
        success = EmailService.send_approval_email(data_request)
        message = 'Approval email resent.'
    elif data_request.status == 'director_review' and data_request.director:
        success = EmailService.send_staff_notification(data_request, data_request.director, 'director')
        message = 'Director notification resent.'
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, 'Failed to resend email or no email type applicable.')
    
    return redirect('admin:datasets_datarequest_changelist')


@login_required
def preview_acknowledgment_email(request, request_id):
    """Preview acknowledgment email (for testing)"""
    from .models import DataRequest    
    data_request = get_object_or_404(DataRequest, id=request_id, user=request.user)
    
    context = {
        'user': request.user,
        'request': data_request,
        'dataset': data_request.dataset,
        'site_name': getattr(settings, 'SITE_NAME', 'Data Portal'),
        'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@datican.org'),
    }
    
    return render(request, 'emails/requests/acknowledgment.html', context)


@login_required
@permission_required('datasets.review_datarequest', raise_exception=True)
def resend_email(request, pk, email_type):
    """Resend specific email for a request"""
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    success = False
    if email_type == 'acknowledgment':
        success = EmailService.send_acknowledgment_email(data_request)
        message = 'Acknowledgment email resent.'
    elif email_type == 'approval':
        success = EmailService.send_approval_email(data_request)
        message = 'Approval email resent.'
    elif email_type == 'notification':
        if data_request.manager:
            success = EmailService.send_staff_notification(data_request, data_request.manager, 'manager')
            message = 'Manager notification resent.'
    
    if success:
        messages.success(request, message)
    else:
        messages.error(request, 'Failed to resend email.')
    
    return redirect(request.META.get('HTTP_REFERER', 'review_requests_list'))