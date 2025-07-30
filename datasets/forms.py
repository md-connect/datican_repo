from django import forms
from .models import DataRequest
from django.core.validators import FileExtensionValidator

class DataRequestForm(forms.ModelForm):
    class Meta:
        model = DataRequest
        fields = [
            'institution',
            'project_title', 
            'project_description',
            'form_submission'
        ]
        widgets = {
            'project_description': forms.Textarea(attrs={
                'rows': 4,
                'maxlength': 500,
                'placeholder': 'A short description of the project (Max. 100 words)'
            }),
            'project_details': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Describe your project details...'
            }),
        }
    
    document = forms.FileField(
        label='Supporting Documents',
        validators=[FileExtensionValidator(['pdf'])],
        widget=forms.FileInput(attrs={
            'accept': '.pdf',
            'class': 'hidden',
            'id': 'documentInput'
        })
    )
    
    form_submission = forms.FileField(
        label='Completed Request Form',
        validators=[FileExtensionValidator(['pdf'])],
        widget=forms.FileInput(attrs={
            'accept': '.pdf',
            'class': 'hidden',
            'id': 'formInput'
        })
    )