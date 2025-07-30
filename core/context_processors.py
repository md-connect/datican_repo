from datasets.models import Dataset

def dataset_count(request):
    return {
        'global_dataset_count': Dataset.objects.count()
    }