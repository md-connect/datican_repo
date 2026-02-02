# datasets/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.http import FileResponse, HttpResponseForbidden, JsonResponse, HttpResponse
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.db.models import Prefetch, Q, Avg, Count, F, Sum, Min, Max
from django.db.models.functions import TruncMonth, TruncYear, TruncDay
from django.db import models
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport
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


User = get_user_model()


def download_request_form(request):
    form_path = os.path.join(settings.STATIC_ROOT, 'forms', 'Dataset_Request_Form_Template.pdf')
    if os.path.exists(form_path):
        response = FileResponse(open(form_path, 'rb'), as_attachment=True)
        response['Content-Type'] = 'application/pdf'
        response['Content-Disposition'] = 'attachment; filename="Dataset_Request_Form_Template.pdf"'
        return response
    messages.error(request, "Dataset Request Form template not found")
    return redirect('dataset_list')


def dataset_list(request):
    # Get filter parameters from request
    modality = request.GET.getlist('modality')
    format = request.GET.getlist('format')
    dimension = request.GET.getlist('dimension')
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
    
    # Apply dimension filter
    if dimension:
        datasets = datasets.filter(dimension__in=dimension)
    
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
            'dimension': dimension,
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
        'dimension_choices': Dataset.DIMENSION_CHOICES,
    }
    
    return render(request, 'datasets/list.html', context)

def dataset_detail(request, pk):
    # Prefetch related thumbnails and optimize queries
    dataset = get_object_or_404(
        Dataset.objects.prefetch_related('thumbnails'), 
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
        
        # Forms
        'rating_form': RatingForm(instance=user_rating_obj) if user_rating_obj else RatingForm(),
        'collection_form': CollectionForm(),
        'report_form': ReportForm(),
    }
    
    return render(request, 'datasets/detail.html', context)

def get_preview_data(dataset, max_rows=100):
    """Extract preview data from CSV/Excel/JSON file"""
    if not hasattr(dataset, 'preview_file') or not dataset.preview_file:
        return None
    
    try:
        # Handle file field properly
        file_obj = dataset.preview_file
        if hasattr(file_obj, 'path'):
            file_path = file_obj.path
        else:
            # For in-memory files or URLs
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_obj.name)[1]) as tmp:
                for chunk in file_obj.chunks():
                    tmp.write(chunk)
                file_path = tmp.name
        
        file_extension = file_obj.name.lower()
        
        if file_extension.endswith('.csv'):
            # Read CSV with pandas
            df = pd.read_csv(file_path, nrows=max_rows)
        elif file_extension.endswith(('.xlsx', '.xls')):
            # Read Excel with pandas
            df = pd.read_excel(file_path, nrows=max_rows)
        elif file_extension.endswith('.json'):
            # Read JSON
            with open(file_path, 'r') as f:
                data = json.load(f)
            # Convert JSON to DataFrame for consistency
            if isinstance(data, list):
                df = pd.DataFrame(data[:max_rows])
            elif isinstance(data, dict):
                # If JSON is a single object
                df = pd.DataFrame([data])
            else:
                return None
        else:
            return None
        
        # Convert DataFrame to list of dictionaries
        rows = df.head(max_rows).to_dict('records')
        
        # Clean NaN values
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
        print(f"Error reading preview file: {e}")
        return None
    finally:
        # Clean up temporary file if created
        if 'tmp' in locals():
            try:
                os.unlink(file_path)
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
    """Get total number of rows in file"""
    try:
        if hasattr(file_obj, 'path'):
            file_path = file_obj.path
        else:
            # Handle in-memory files
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_obj.name)[1]) as tmp:
                for chunk in file_obj.chunks():
                    tmp.write(chunk)
                file_path = tmp.name
        
        file_extension = file_obj.name.lower()
        
        if file_extension.endswith('.csv'):
            # Count CSV rows efficiently
            with open(file_path, 'r', encoding='utf-8') as f:
                return sum(1 for _ in f) - 1  # Subtract header
        elif file_extension.endswith(('.xlsx', '.xls')):
            # Count Excel rows
            df = pd.read_excel(file_path)
            return len(df)
        elif file_extension.endswith('.json'):
            # Count JSON rows
            with open(file_path, 'r') as f:
                data = json.load(f)
            if isinstance(data, list):
                return len(data)
            else:
                return 1
        return 0
    except:
        return 0
    finally:
        # Clean up temporary file if created
        if 'tmp' in locals():
            try:
                os.unlink(file_path)
            except:
                pass

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

# AJAX views for better UX
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

@login_required
def download_request_form(request):
    # Path to your form template
    form_path = os.path.join(settings.BASE_DIR, 'static', 'forms', 'Data_Request_Form.pdf')
    if os.path.exists(form_path):
        return FileResponse(open(form_path, 'rb'), as_attachment=True, filename='Data_Request_Form.pdf')
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
                        settings.DEFAULT_FROM_EMAIL,
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
                    settings.DEFAULT_FROM_EMAIL,
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
                    settings.DEFAULT_FROM_EMAIL,
                    [data_request.manager.email],
                    fail_silently=True,
                )
        
        return redirect('director_review_list')
    
    return render(request, 'datasets/director_review.html', {
        'data_request': data_request
    })

@login_required
def dataset_download(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    
    # Find approved request for this user and dataset
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).order_by('-approved_date').first()
    
    if not data_request:
        messages.error(request, 'You do not have an approved request for this dataset.')
        return redirect('dataset_detail', pk=pk)
    
    if not data_request.can_download():
        messages.error(request, 
            f'You have reached your download limit ({data_request.max_downloads} downloads). '
            f'Please contact support if you need access to the data again.'
        )
        return redirect('request_status', pk=data_request.pk)
    
    # Record the download
    data_request.record_download()
    
    # Increment dataset download count
    dataset.download_count += 1
    dataset.save()
    
    # Send download confirmation email (optional)
    try:
        send_mail(
            f"Dataset Downloaded: {dataset.title}",
            f"You have successfully downloaded the dataset '{dataset.title}'.\n\n"
            f"Download Details:\n"
            f"- Request ID: {data_request.id}\n"
            f"- Download Count: {data_request.download_count} of {data_request.max_downloads}\n"
            f"- Download Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n"
            f"- Dataset: {dataset.title}\n\n"
            f"Please remember to comply with the data use agreement and citation requirements.",
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email],
            fail_silently=True,
        )
    except Exception as e:
        # Log error but don't prevent download
        pass
    
    # Serve the file
    if dataset.file and dataset.file.name:
        file_path = dataset.file.path
        if os.path.exists(file_path):
            response = FileResponse(open(file_path, 'rb'), as_attachment=True)
            
            # Set appropriate filename and Content-Type
            filename = os.path.basename(dataset.file.name)
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            # Set Content-Type based on file extension
            ext = os.path.splitext(filename)[1].lower()
            content_types = {
                '.csv': 'text/csv',
                '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                '.xls': 'application/vnd.ms-excel',
                '.pdf': 'application/pdf',
                '.zip': 'application/zip',
                '.rar': 'application/x-rar-compressed',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.dcm': 'application/dicom',
                '.nii': 'application/octet-stream',
                '.gz': 'application/gzip',
            }
            response['Content-Type'] = content_types.get(ext, 'application/octet-stream')
            
            return response
        else:
            messages.error(request, 'The dataset file is not available. Please contact support.')
            return redirect('dataset_detail', pk=pk)
    else:
        # Check for multiple files in a dataset
        if hasattr(dataset, 'files') and dataset.files.exists():
            # Handle multiple files - could create a ZIP archive
            messages.info(request, 'This dataset contains multiple files. Download functionality for multiple files is under development.')
            return redirect('dataset_detail', pk=pk)
        else:
            messages.error(request, 'No files available for this dataset.')
            return redirect('dataset_detail', pk=pk)

@login_required
def request_status(request, pk):  # Keep as pk
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
    
    # Prepare status stages for visualization (updated for new status flow)
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
    })

@login_required
@director_required
def director_review_list(request):
    """Show all requests pending director review"""
    pending_reviews = DataRequest.objects.filter(
        status='director_review'
    ).select_related('user', 'dataset', 'manager').order_by('manager_review_date')
    
    return render(request, 'datasets/director_review_list.html', {
        'pending_reviews': pending_reviews
    })

# Admin approval view (for superusers)
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

# Resend email functionality
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
    from django.conf import settings
    
    data_request = get_object_or_404(DataRequest, id=request_id, user=request.user)
    
    context = {
        'user': request.user,
        'request': data_request,
        'dataset': data_request.dataset,
        'site_name': getattr(settings, 'SITE_NAME', 'Data Portal'),
        'support_email': getattr(settings, 'SUPPORT_EMAIL', 'support@example.com'),
    }
    
    return render(request, 'emails/requests/acknowledgment.html', context)
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

def test_email_notification(request):
    """Test all email notifications in the system"""
    # Check if user is logged in
    if not request.user.is_authenticated:
        from django.contrib.auth.views import redirect_to_login
        return redirect_to_login(request.get_full_path())
    
    test_results = []
    test_email = request.user.email if request.user.email else "test@example.com"
    
    # Test 1: Basic email
    try:
        send_mail(
            subject='✅ DATICAN - Basic Email Test',
            message=f'This is a basic text email test.\n\n'
                   f'User: {request.user.first_name}\n'
                   f'Email: {test_email}\n'
                   f'Time: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n'
                   f'If you see this in console, basic emails are working!',
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[test_email],
            fail_silently=False,
        )
        test_results.append("✅ Basic email sent successfully")
    except Exception as e:
        test_results.append(f"❌ Basic email failed: {e}")
    
    # Test 2: HTML email
    try:
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        
        html_message = render_to_string('emails/test_email.html', {
            'user': request.user,
            'test_data': f'Test performed at {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}'
        })
        plain_message = strip_tags(html_message)
        
        send_mail(
            subject='✅ DATICAN - HTML Email Test',
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[test_email],
            html_message=html_message,
            fail_silently=False,
        )
        test_results.append("✅ HTML email sent successfully")
    except Exception as e:
        test_results.append(f"❌ HTML email failed: {e}")
    
    # Test 3: Simulate request notification
    try:
        # Try to find a real DataRequest for testing
        from .models import DataRequest
        test_request = DataRequest.objects.first()
        
        if test_request:
            subject = f'🔔 DATICAN - Simulated Notification: {test_request.dataset.title}'
            message = f"""Test Notification Email

    Request Details:
    - Dataset: {test_request.dataset.title}
    - Request ID: {test_request.id}
    - User: {test_request.user.first_name}
    - Status: {test_request.status}
    - Date: {test_request.request_date.strftime("%Y-%m-%d")}

    This is a simulated notification email to test the workflow.
    """
            
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[test_email],
                fail_silently=False,
            )
            test_results.append("✅ Simulated notification sent successfully")
        else:
            test_results.append("⚠️ No DataRequest found for simulation test")
    except Exception as e:
        test_results.append(f"❌ Simulation test failed: {e}")
    
    # System info
    test_results.append(f"📧 Current email backend: {settings.EMAIL_BACKEND}")
    test_results.append(f"👤 Logged in as: {request.user.first_name} ({request.user.email})")
    test_results.append(f"📨 From email: {settings.DEFAULT_FROM_EMAIL}")
    
    return HttpResponse("<br>".join(test_results))

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

# Check functions for user roles
def is_manager(user):
    return user.is_authenticated and user.role == 'data_manager'

def is_director(user):
    return user.is_authenticated and user.role == 'director'

def is_superuser(user):
    return user.is_authenticated and user.is_superuser

@login_required
@data_manager_required
def manager_recommendations(request):
    """Show data manager's recommended requests"""
    # Use status='director_review' instead of manager_action='recommended' for consistency
    recommendations = DataRequest.objects.filter(
        manager=request.user,
        status='director_review'  # CHANGED FROM manager_action='recommended'
    ).select_related('user', 'dataset', 'director')
    
    return render(request, 'datasets/manager_recommendations.html', {
        'recommendations': recommendations
    })

@login_required
@data_manager_required
def manager_rejections(request):
    """Show data manager's rejected requests"""
    # Use status='rejected' and manager_action='rejected' for accuracy
    rejections = DataRequest.objects.filter(
        manager=request.user,
        status='rejected',
        manager_action='rejected'  # Added this to ensure it was manager's rejection
    ).select_related('user', 'dataset')
    
    return render(request, 'datasets/manager_rejections.html', {
        'rejections': rejections
    })

@login_required
@director_required
def director_approvals(request):
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
def director_rejections(request):
    """Show director's rejected requests"""
    rejections = DataRequest.objects.filter(
        director=request.user,
        status='rejected',
        director_action='rejected'
    ).select_related('user', 'dataset', 'manager')
    
    return render(request, 'datasets/director_rejections.html', {
        'rejections': rejections
    })

# Fix the dashboard views to use correct status values:

@login_required
@user_passes_test(is_manager, login_url='/login/')
def manager_dashboard(request):
    # Get pending requests for this manager
    pending_requests = DataRequest.objects.filter(
        status='manager_review',  # This should be the correct status
        manager_id=request.user.id
    ).count()
    
    # Get requests recommended by this manager (sent to director)
    recommended_by_manager = DataRequest.objects.filter(
        status='director_review',
        manager_id=request.user.id
    ).count()
    
    # Get requests rejected by this manager
    rejected_by_manager = DataRequest.objects.filter(
        status='rejected',
        manager_id=request.user.id,
        manager_action='rejected'  # Ensure it was manager's rejection
    ).count()
    
    # Get list of requests recommended by this manager
    manager_recommended_list = DataRequest.objects.filter(
        status='director_review',
        manager_id=request.user.id
    ).select_related('dataset', 'director').order_by('-manager_review_date')[:10]
    
    # Get list of requests rejected by this manager
    manager_rejected_list = DataRequest.objects.filter(
        status='rejected',
        manager_id=request.user.id,
        manager_action='rejected'
    ).select_related('dataset').order_by('-manager_review_date')[:10]
    
    # Get list of director decisions on manager's requests
    director_decisions_for_manager = DataRequest.objects.filter(
        manager_id=request.user.id,
        status__in=['approved', 'rejected']
    ).select_related('dataset', 'director').order_by('-approved_date', '-manager_review_date')[:10]
    
    # Calculate completion rate
    total_assigned = DataRequest.objects.filter(manager_id=request.user.id).count()
    completed = DataRequest.objects.filter(
        manager_id=request.user.id,
        status__in=['director_review', 'approved', 'rejected']
    ).count()
    
    context = {
        'pending_count': pending_requests,
        'recommended_by_manager_count': recommended_by_manager,
        'rejected_by_manager_count': rejected_by_manager,
        'total_assigned': total_assigned,
        'completion_rate': (completed / total_assigned * 100) if total_assigned > 0 else 0,
        
        # Lists for the template
        'manager_recommended_list': manager_recommended_list,
        'manager_rejected_list': manager_rejected_list,
        'director_decisions_list': director_decisions_for_manager,
    }
    return render(request, 'dashboard/manager_dashboard.html', context)

@login_required
@user_passes_test(is_director, login_url='/login/')
def director_dashboard(request):
    # Get requests pending director review
    pending_director_reviews = DataRequest.objects.filter(
        status='director_review'
    ).count()
    
    # Get requests approved by this director
    director_approved = DataRequest.objects.filter(
        status='approved',
        director_id=request.user.id
    ).count()
    
    # Get requests rejected by this director
    director_rejected = DataRequest.objects.filter(
        status='rejected',
        director_id=request.user.id,
        director_action='rejected'
    ).count()
    
    # Get lists for display
    pending_director_list = DataRequest.objects.filter(
        status='director_review'
    ).select_related('user', 'manager', 'dataset').order_by('-manager_review_date')[:10]
    
    director_approved_list = DataRequest.objects.filter(
        status='approved',
        director_id=request.user.id
    ).select_related('user', 'manager', 'dataset').order_by('-approved_date')[:10]
    
    director_rejected_list = DataRequest.objects.filter(
        status='rejected',
        director_id=request.user.id,
        director_action='rejected'
    ).select_related('user', 'manager', 'dataset').order_by('-approved_date')[:10]
    
    context = {
        'pending_director_count': pending_director_reviews,
        'director_approved_count': director_approved,
        'director_rejected_count': director_rejected,
        
        # Lists
        'pending_director_list': pending_director_list,
        'director_approved_list': director_approved_list,
        'director_rejected_list': director_rejected_list,
        
        # Statistics
        'director_total_decisions': director_approved + director_rejected,
        'approval_rate': (director_approved / (director_approved + director_rejected) * 100) if (director_approved + director_rejected) > 0 else 0,
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

# Update the review functions to properly set both status and action fields:

@login_required
@data_manager_required
def manager_review_request(request, pk): 
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    # Check if this data manager can review this request
    if data_request.status not in ['pending', 'manager_review']:
        messages.error(request, 'This request is not available for review.')
        return redirect('review_requests_list')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        manager_comment = request.POST.get('manager_comment', '').strip()
        
        if action == 'recommend':
            data_request.status = 'director_review'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'recommended'  # Set action field
            
            # Find and assign a director
            directors = CustomUser.objects.filter(role='director', is_active=True)
            if directors.exists():
                data_request.director = directors.first()
                messages.success(request, 'Request recommended and sent to director for final review.')
            else:
                # If no director found, keep in manager_review and notify admin
                data_request.status = 'manager_review'
                messages.warning(request, 'Request recommended but no director available. Notified administrators.')
                
                # Notify admin
                admin_users = CustomUser.objects.filter(is_staff=True, is_active=True)
                for admin_user in admin_users:
                    send_mail(
                        "URGENT: No Director Available",
                        f"A data request (#{data_request.id}) needs director approval but no director is available.",
                        settings.DEFAULT_FROM_EMAIL,
                        [admin_user.email],
                        fail_silently=True,
                    )
            
            data_request.save()
            
            # Send email notifications
            if data_request.director:
                EmailService.send_staff_notification(data_request, data_request.director, 'director')
            
            # Send status update to user
            EmailService.send_status_update_email(data_request, 'pending', request.user)
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'rejected'  # Set action field
            
            data_request.save()
            messages.success(request, 'Request has been rejected.')
            
            # Send rejection email to user
            EmailService.send_rejection_email(
                data_request, 
                request.user, 
                manager_comment, 
                'manager'
            )
        
        return redirect('review_requests_list')
    
    return render(request, 'datasets/manager_review.html', {
        'data_request': data_request
    })

@login_required
@director_required  
def director_review_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk, status='director_review')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        director_comment = request.POST.get('director_comment', '').strip()
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.approved_date = timezone.now()
            data_request.director_action = 'approved'  # Set action field
            
            data_request.save()
            messages.success(request, 'Request approved successfully!')
            
            # Send approval email with download link
            EmailService.send_approval_email(data_request)
            
            # Notify data manager about approval
            if data_request.manager:
                send_mail(
                    f"Request #{data_request.id} Approved",
                    f"The data request you recommended has been approved by the director.",
                    settings.DEFAULT_FROM_EMAIL,
                    [data_request.manager.email],
                    fail_silently=True,
                )
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'rejected'  # Set action field
            
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
                    f"The data request you recommended has been rejected by the director.",
                    settings.DEFAULT_FROM_EMAIL,
                    [data_request.manager.email],
                    fail_silently=True,
                )
        
        return redirect('director_review_list')
    
    return render(request, 'datasets/director_review.html', {
        'data_request': data_request
    })

# Update the admin review to be consistent:

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

# Add these missing view functions if they don't exist:

@login_required
@user_passes_test(is_manager, login_url='/login/')
def manager_recommended_requests(request):
    """View for new dashboard - maps to existing manager_recommendations"""
    # Redirect to existing view for consistency
    return manager_recommendations(request)

@login_required
@user_passes_test(is_manager, login_url='/login/')
def manager_rejected_requests(request):
    """View for new dashboard - maps to existing manager_rejections"""
    # Redirect to existing view for consistency
    return manager_rejections(request)

@login_required
@user_passes_test(is_manager, login_url='/login/')
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
@user_passes_test(is_director, login_url='/login/')
def director_approved_requests(request):
    """View for new dashboard - maps to existing director_approvals"""
    # Redirect to existing view for consistency
    return director_approvals(request)

@login_required
@user_passes_test(is_director, login_url='/login/')
def director_rejected_requests(request):
    """View for new dashboard - maps to existing director_rejections"""
    # Redirect to existing view for consistency
    return director_rejections(request)

@login_required
@user_passes_test(is_superuser, login_url='/login/')
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

# Fix the review_requests_list to use correct status:

@login_required
@data_manager_required
def review_requests_list(request):
    """Show all requests pending manager review"""
    pending_requests = DataRequest.objects.filter(
        status__in=['pending', 'manager_review']  # Correct status values
    ).select_related('user', 'dataset').order_by('request_date')
    
    return render(request, 'datasets/review_requests_list.html', {
        'pending_requests': pending_requests
    })

# Fix the all_requests_report function to use correct status values:

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
    
    # Calculate statistics - use correct status values
    total_requests = all_requests.count()
    pending_requests = all_requests.filter(status='pending').count()
    manager_review_requests = all_requests.filter(status='manager_review').count()
    director_review_requests = all_requests.filter(status='director_review').count()
    approved_requests = all_requests.filter(status='approved').count()
    rejected_requests = all_requests.filter(status='rejected').count()
    
    # Approval rate
    approval_rate = 0
    if total_requests > 0:
        approval_rate = (approved_requests / total_requests) * 100
    
    context = {
        'all_requests': all_requests,
        'total_requests': total_requests,
        'pending_requests': pending_requests,
        'manager_review_requests': manager_review_requests,
        'director_review_requests': director_review_requests,
        'approved_requests': approved_requests,
        'rejected_requests': rejected_requests,
        'approval_rate': approval_rate,
        'user_role': request.user.role,
        'is_superuser': request.user.is_superuser,
    }
    
    return render(request, 'datasets/all_requests_report.html', context)
    # Get all requests with detailed information
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