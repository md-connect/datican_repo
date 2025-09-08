# core/context_processors.py
from django.db.models import Count
from datasets.models import Dataset, DataRequest
from accounts.models import CustomUser

def admin_stats(request):
    if request.path.startswith('/admin/'):
        return {
            'datasets_count': Dataset.objects.count(),
            'pending_requests_count': DataRequest.objects.filter(status='pending').count(),
            'users_count': CustomUser.objects.count(),
            'approved_requests_count': DataRequest.objects.filter(status='approved').count(),
        }
    return {}