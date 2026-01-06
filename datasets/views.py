# datasets/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.db.models import Prefetch, Q, Avg, Count
from .models import Dataset, DataRequest, Thumbnail, DatasetRating, UserCollection, DatasetReport
from .forms import DataRequestForm, RatingForm, CollectionForm, ReportForm
import os
from datetime import datetime
from .utils import data_manager_required, director_required
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from django.core.paginator import Paginator
import pandas as pd
import json


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
    if request.user.is_authenticated:
        data_request = DataRequest.objects.filter(
            user=request.user,
            dataset=dataset
        ).first()
        
        if data_request:
            show_request_form = False
    
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

# Helper function for preview data (add this to your views.py)
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
        project_title = request.POST.get('project_title', '').strip()
        project_description = request.POST.get('project_description', '').strip()
        form_submission = request.FILES.get('form_submission')
        
        # Enhanced validation
        errors = []
        if not institution:
            errors.append('Institution is required')
        if not project_title:
            errors.append('Project title is required')
        if not project_description:
            errors.append('Project description is required')
        if not form_submission:
            errors.append('Form submission file is required')
        elif not form_submission.name.endswith('.pdf'):
            errors.append('Form submission must be a PDF file')
        
        
        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'datasets/request_form.html', {
                'dataset': dataset,
                'institution': institution,
                'project_title': project_title,
                'project_description': project_description
            })
        
        try:
            # Create and save DataRequest
            data_request = DataRequest(
                user=request.user,
                dataset=dataset,
                institution=institution,
                project_title=project_title,
                project_description=project_description,
                form_submission=form_submission,
            )
            data_request.save()
            
            user_full_name = getattr(request.user, 'get_full_name', None)
            if callable(user_full_name):
                user_full_name = user_full_name()
            else:
                # Fallback: use first and last name or username
                first_name = getattr(request.user, 'first_name', '')
                last_name = getattr(request.user, 'last_name', '')
                if first_name or last_name:
                    user_full_name = f"{first_name} {last_name}".strip()
                else:
                    user_full_name = request.user.username

            # Send notification emails
            subject = f"New Data Request: {dataset.title}"
            message = f"""
            A new data request has been submitted:
            
            Researcher: {request.user.get_full_name()} ({request.user.email})
            Institution: {institution}
            Dataset: {dataset.title}
            Project Title: {project_title}
            
            Please review the request in the admin panel.
            """
            
            # Send to admins
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [admin[1] for admin in settings.ADMINS],
                fail_silently=True,
            )
            
            # Send confirmation to user
            user_message = f"""
            Thank you for submitting your data request for "{dataset.title}".
            
            Your request is now under review. You'll receive an email notification 
            when there's an update on your request status.
            
            Request ID: {data_request.id}
            Submission Date: {data_request.request_date.strftime('%Y-%m-%d %H:%M')}
            """
            
            send_mail(
                "Data Request Submitted",
                user_message,
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email],
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
    
    remaining_downloads = data_request.max_downloads - data_request.download_count
    
    # Prepare status stages for visualization
    status_stages = [
        {
            'name': 'Submitted',
            'icon': 'clipboard-check',
            'active': True,
            'date': data_request.request_date
        },
        {
            'name': 'Manager Review',
            'icon': 'user-check',
            'active': data_request.status in ['manager_review', 'director_review', 'approved', 'rejected'],
            'date': data_request.manager_comment_date if hasattr(data_request, 'manager_comment_date') else None
        },
        {
            'name': 'Director Review' if data_request.status in ['director_review', 'approved', 'rejected'] else 'Final Approval',
            'icon': 'shield-check',
            'active': data_request.status in ['director_review', 'approved', 'rejected'],
            'date': data_request.approved_date if data_request.status == 'approved' else None
        }
    ]
    
    # Calculate progress percentage
    progress = 0
    if data_request.status == 'pending':
        progress = 33
    elif data_request.status == 'manager_review':
        progress = 66
    else:
        progress = 100
    
    return render(request, 'datasets/request_status.html', {
        'data_request': data_request,
        'can_download': data_request.can_download(),
        'status_stages': status_stages,
        'progress': progress,
        'remaining_downloads': remaining_downloads
    })

@login_required
def download_request_form(request):
    # Path to your form template
    form_path = os.path.join(settings.BASE_DIR, 'static', 'forms', 'Data_Request_Form.pdf')
    if os.path.exists(form_path):
        return FileResponse(open(form_path, 'rb'), as_attachment=True, filename='Data_Request_Form.pdf')
    messages.error(request, 'The request form template is not currently available.')
    return redirect('dataset_list')

# datasets/views.py
@login_required
@data_manager_required
def review_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    # Check if this data manager can review this request
    if data_request.status not in ['pending', 'manager_review']:
        messages.error(request, 'This request is not available for review.')
        return redirect('admin:datasets_datarequest_changelist')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        manager_comment = request.POST.get('manager_comment', '').strip()
        
        if action == 'approve':
            data_request.status = 'director_review'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'recommended'  # Track recommendation
            messages.success(request, 'Request recommended and sent to director for final review.')
            
            # Notify directors
            directors = CustomUser.objects.filter(role='director', is_active=True)
            for director in directors:
                send_mail(
                    "Request Needs Final Approval",
                    f"Request ID: {data_request.id} for '{data_request.project_title}' needs your approval.\n\n"
                    f"Researcher: {data_request.user.first_name} {data_request.user.last_name} ({data_request.user.email})\n"
                    f"Institution: {data_request.institution}\n"
                    f"Manager Notes: {manager_comment}\n"
                    f"Manager Review Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                    f"Please review the request in the admin panel.",
                    settings.DEFAULT_FROM_EMAIL,
                    [director.email],
                    fail_silently=True,
                )
                
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.manager = request.user
            data_request.data_manager_comment = manager_comment
            data_request.manager_review_date = timezone.now()
            data_request.manager_action = 'rejected'  # Track rejection
            messages.success(request, 'Request has been rejected.')
            
            # Notify user
            send_mail(
                "Your Data Request Status",
                f"Your request for '{data_request.dataset.title}' has been reviewed.\n\n"
                f"Status: Rejected\n"
                f"Manager Notes: {manager_comment}\n"
                f"Review Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Request ID: {data_request.id}",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
        
        data_request.save()
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/review_request.html', {
        'data_request': data_request
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
            data_request.director_action = 'approved'  # Track approval
            messages.success(request, 'Request approved successfully!')
            
            # Notify user
            send_mail(
                "Your Data Request Approved",
                f"Your request for '{data_request.dataset.title}' has been approved.\n\n"
                f"Director Notes: {director_comment}\n"
                f"Approval Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Request ID: {data_request.id}\n"
                f"You can now download the dataset from your request status page.",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = director_comment
            data_request.director_action = 'rejected'  # Track rejection
            messages.success(request, 'Request has been rejected.')
            
            # Notify user
            send_mail(
                "Your Data Request Status",
                f"Your request for '{data_request.dataset.title}' has been reviewed.\n\n"
                f"Status: Rejected\n"
                f"Director Notes: {director_comment}\n"
                f"Decision Date: {timezone.now().strftime('%Y-%m-%d %H:%M')}\n\n"
                f"Request ID: {data_request.id}",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
        
        data_request.save()
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/director_review.html', {
        'data_request': data_request
    })

# datasets/views.py
@login_required
@data_manager_required
def manager_recommendations(request):
    """Show data manager's recommended requests"""
    recommendations = DataRequest.objects.filter(
        manager=request.user,
        manager_action='recommended'
    ).select_related('user', 'dataset', 'director')
    
    return render(request, 'datasets/manager_recommendations.html', {
        'recommendations': recommendations
    })

@login_required
@data_manager_required
def manager_rejections(request):
    """Show data manager's rejected requests"""
    rejections = DataRequest.objects.filter(
        manager=request.user,
        manager_action='rejected'
    ).select_related('user', 'dataset', 'director')
    
    return render(request, 'datasets/manager_rejections.html', {
        'rejections': rejections
    })

@login_required
@director_required
def director_approvals(request):
    """Show director's approved requests"""
    approvals = DataRequest.objects.filter(
        director=request.user,
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
        director_action='rejected'
    ).select_related('user', 'dataset', 'manager')
    
    return render(request, 'datasets/director_rejections.html', {
        'rejections': rejections
    })

@login_required
@permission_required('datasets.approve_datarequest', raise_exception=True)
def approve_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.approved_date = timezone.now()
            data_request.director = request.user
            data_request.director_comment = comment
            messages.success(request, 'Request approved successfully!')
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = comment
            messages.success(request, 'Request has been rejected.')
        
        data_request.save()
        data_request.send_status_notification()
        return redirect(reverse('admin:datasets_datarequest_changelist'))
    
    return render(request, 'datasets/admin/approve_request.html', {
        'data_request': data_request
    })

@login_required
def dataset_download(request, pk):
    dataset = get_object_or_404(Dataset, pk=pk)
    data_request = DataRequest.objects.filter(
        user=request.user,
        dataset=dataset,
        status='approved'
    ).first()
    
    if data_request and data_request.can_download():
        # Record the download
        data_request.record_download()
        
        # Increment dataset download count
        dataset.download_count += 1
        dataset.save()
        
        # Serve the file
        file_path = os.path.join(settings.MEDIA_ROOT, dataset.file.name)
        if os.path.exists(file_path):
            response = FileResponse(open(file_path, 'rb'), as_attachment=True)
            
            # Set appropriate Content-Type based on file extension
            ext = os.path.splitext(dataset.file.name)[1].lower()
            if ext == '.csv':
                response['Content-Type'] = 'text/csv'
            elif ext in ['.jpg', '.jpeg']:
                response['Content-Type'] = 'image/jpeg'
            elif ext == '.png':
                response['Content-Type'] = 'image/png'
            elif ext in ['.dcm', '.dicom']:
                response['Content-Type'] = 'application/dicom'
            elif ext in ['.nii', '.gz']:
                response['Content-Type'] = 'application/octet-stream'
            
            return response
    
    return render(request, 'datasets/download_denied.html', status=403)

@login_required
@permission_required('datasets.review_datarequest', raise_exception=True)
def review_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            data_request.status = 'director_review'
            data_request.manager = request.user
            data_request.data_manager_comment = comment
            messages.success(request, 'Request recommended for director approval.')
            
            # Notify directors
            directors = User.objects.filter(groups__name='Directors')
            for director in directors:
                send_mail(
                    "Request Needs Final Approval",
                    f"Request ID: {data_request.id} needs your approval.",
                    settings.DEFAULT_FROM_EMAIL,
                    [director.email],
                    fail_silently=True,
                )
                
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.manager = request.user
            data_request.data_manager_comment = comment
            messages.success(request, 'Request has been rejected.')
            
            # Notify user
            send_mail(
                "Your Data Request Status",
                f"Your request for {data_request.dataset.title} has been rejected.",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
        
        data_request.save()
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/review_request.html', {
        'data_request': data_request
    })
    

@login_required
@permission_required('datasets.approve_datarequest', raise_exception=True)
def approve_request(request, pk):
    data_request = get_object_or_404(DataRequest, pk=pk, status='director_review')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        comment = request.POST.get('comment', '')
        
        if action == 'approve':
            data_request.status = 'approved'
            data_request.approved_date = timezone.now()
            data_request.director = request.user
            data_request.director_comment = comment
            messages.success(request, 'Request approved successfully!')
            
            # Notify user
            send_mail(
                "Your Data Request Approved",
                f"Your request for {data_request.dataset.title} has been approved.",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
            
        elif action == 'reject':
            data_request.status = 'rejected'
            data_request.director = request.user
            data_request.director_comment = comment
            messages.success(request, 'Request has been rejected.')
            
            # Notify user
            send_mail(
                "Your Data Request Status",
                f"Your request for {data_request.dataset.title} has been rejected.",
                settings.DEFAULT_FROM_EMAIL,
                [data_request.user.email],
                fail_silently=True,
            )
        
        data_request.save()
        return redirect('admin:datasets_datarequest_changelist')
    
    return render(request, 'datasets/admin/approve_request.html', {
        'data_request': data_request
    })