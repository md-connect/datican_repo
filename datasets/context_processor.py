# datasets/context_processors.py
from .models import Dataset

def dataset_filters(request):
    return {
        'modality_choices': Dataset.MODALITY_CHOICES,
        'format_choices': Dataset.FORMAT_CHOICES,
        'dimension_choices': Dataset.DIMENSION_CHOICES,
    }