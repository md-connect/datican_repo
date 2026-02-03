# datasets/context_processors.py
from .models import Dataset
from django.urls import reverse

def auth_redirects(request):
    return {
        'default_redirect': reverse('redirect_after_login'),
    }
    
def dataset_filters(request):
    return {
        'modality_choices': Dataset.MODALITY_CHOICES,
        'format_choices': Dataset.FORMAT_CHOICES,
        'dimension_choices': Dataset.DIMENSION_CHOICES,
    }