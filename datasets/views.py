# datasets/views.py
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required, permission_required
from django.http import FileResponse, HttpResponseForbidden
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.urls import reverse
from django.db.models import Prefetch, Q
from .models import Dataset, DataRequest, Thumbnail
from .forms import DataRequestForm
import os
from datetime import datetime
from .utils import data_manager_required, director_required
from django.contrib.auth import get_user_model
from django.utils import timezone


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
    tasks = request.GET.getlist('task')
    attributes = request.GET.getlist('attribute')
    formats = request.GET.getlist('format')
    year = request.GET.get('year')
    search_query = request.GET.get('q')

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
            Q(category__icontains=search_query)
        )

    # Apply other filters
    if tasks:
        datasets = datasets.filter(task__in=tasks)
    
    if attributes:
        attribute_query = Q()
        for attr in attributes:
            attribute_query |= Q(attributes__contains=attr)
        datasets = datasets.filter(attribute_query)
    
    if formats:
        format_query = Q()
        for fmt in formats:
            format_query |= Q(file__endswith=f'.{fmt}')
        datasets = datasets.filter(format_query)
    
    if year:
        try:
            year_int = int(year)
            datasets = datasets.filter(upload_date__year=year_int)
        except ValueError:
            pass  # Ignore invalid year values

    # Pagination
    paginator = Paginator(datasets, 12)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get available years for filter
    available_years = Dataset.objects.dates('upload_date', 'year').order_by('-upload_date__year')
    
    return render(request, 'datasets/list.html', {
        'datasets': page_obj,
        'available_years': available_years,
        'current_filters': {
            'tasks': tasks,
            'attributes': attributes,
            'formats': formats,
            'year': year,
            'q': search_query
        }
    })

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
            # Redirect to status page if request exists
            return redirect('request_status', pk=data_request.pk)
    
    # Check download access only if request exists and is approved
    can_download = False
    if data_request and data_request.status == 'approved':
        can_download = data_request.can_download()
    
    # Get similar datasets with their primary thumbnails
    similar_datasets = Dataset.objects.filter(
        category=dataset.category
    ).exclude(pk=pk).prefetch_related(
        Prefetch('thumbnails', queryset=Thumbnail.objects.filter(is_primary=True), to_attr='primary_thumbnails')
    )[:4]
    
    # Add primary thumbnail to each similar dataset
    for similar in similar_datasets:
        similar.primary_thumbnail = similar.primary_thumbnails[0] if similar.primary_thumbnails else None
    
    return render(request, 'datasets/detail.html', {
        'dataset': dataset,
        'can_download': can_download,
        'data_request': data_request,
        'show_request_form': show_request_form,
        'similar_datasets': similar_datasets,
        'thumbnails': thumbnails,
        'primary_thumbnail': primary_thumbnail
    })

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