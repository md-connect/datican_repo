from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from ..models import DataRequest
from utils.email_service import EmailService

@permission_required('data_app.review_datarequest')
def resend_notification(request, request_id):
    """Resend notification email to staff"""
    data_request = get_object_or_404(DataRequest, id=request_id)
    
    if data_request.manager:
        success = EmailService.send_staff_notification(
            data_request, 
            data_request.manager, 
            'manager'
        )
        
        if success:
            return JsonResponse({'success': True, 'message': 'Notification resent to manager.'})
    
    return JsonResponse({'success': False, 'message': 'Failed to resend notification.'}, status=400)

@login_required
def preview_acknowledgment_email(request, request_id):
    """Preview acknowledgment email (for testing)"""
    data_request = get_object_or_404(DataRequest, id=request_id, user=request.user)
    
    context = {
        'user': request.user,
        'request': data_request,
        'dataset': data_request.dataset,
        'site_name': 'DATICAN Repo',
        'support_email': 'support@datican.org',
    }
    
    return render(request, 'emails/requests/acknowledgment.html', context)