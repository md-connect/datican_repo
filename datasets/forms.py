
from django import forms
from .models import DataRequest, DatasetRating, UserCollection, DatasetReport
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
import re

class DataRequestForm(forms.ModelForm):
    class Meta:
        model = DataRequest
        fields = [
            'institution',
            'phone_number',
            'ethical_approval_no',
            'project_title', 
            'project_description',
            'form_submission',
            'ethical_approval_proof'
        ]
    
    def clean_phone_number(self):
        """Validate phone number format"""
        phone_number = self.cleaned_data.get('phone_number', '').strip()
        
        if not phone_number:
            return phone_number  # Allow empty since it's optional
        
        # Basic validation - at least 10 digits
        digits_only = re.sub(r'\D', '', phone_number)
        if len(digits_only) < 10:
            raise forms.ValidationError("Phone number must contain at least 10 digits.")
        
        if len(digits_only) > 15:
            raise forms.ValidationError("Phone number is too long.")
        
        return phone_number
    
    def clean_ethical_approval_no(self):
        """Validate ethical approval number format"""
        approval_no = self.cleaned_data.get('ethical_approval_no', '').strip()
        
        if not approval_no:
            return approval_no  # Allow empty since it's optional
        
        if len(approval_no) > 50:
            raise forms.ValidationError("Ethical approval number is too long (max 50 characters).")
        
        return approval_no
    
    def clean_form_submission(self):
        """Validate form submission file"""
        form_file = self.cleaned_data.get('form_submission')
        
        if not form_file:
            raise forms.ValidationError("Completed request form is required.")
        
        # Check file size (25MB limit)
        max_size = 25 * 1024 * 1024  # 25MB
        if form_file.size > max_size:
            raise forms.ValidationError(f"File size must be less than 25MB. Current size: {form_file.size / (1024*1024):.1f}MB")
        
        # Check file extension
        if not form_file.name.lower().endswith('.pdf'):
            raise forms.ValidationError("Only PDF files are allowed for the request form.")
        
        return form_file
    
    def clean_ethical_approval_proof(self):
        """Validate ethical approval proof file"""
        proof_file = self.cleaned_data.get('ethical_approval_proof')
        
        if proof_file:
            # Check file size (25MB limit)
            max_size = 25 * 1024 * 1024  # 25MB
            if proof_file.size > max_size:
                raise forms.ValidationError(f"File size must be less than 25MB. Current size: {proof_file.size / (1024*1024):.1f}MB")
            
            # Check file extension
            allowed_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
            file_ext = proof_file.name.lower()
            if not any(file_ext.endswith(ext) for ext in allowed_extensions):
                raise forms.ValidationError(f"File type not supported. Allowed: PDF, JPG, PNG")
        
        return proof_file
    
    def clean_project_description(self):
        """Validate project description length"""
        description = self.cleaned_data.get('project_description', '').strip()
        
        if not description:
            raise forms.ValidationError("Project description is required.")
        
        # Check word count (approximately 100 words)
        words = description.split()
        if len(words) > 100:
            raise forms.ValidationError(f"Project description must be 100 words or less. Current: {len(words)} words.")
        
        return description

class RatingForm(forms.ModelForm):
    rating = forms.FloatField(
        widget=forms.NumberInput(attrs={
            'type': 'range',
            'min': '0',
            'max': '10',
            'step': '0.5',
            'class': 'w-full'
        }),
        validators=[MinValueValidator(0.0), MaxValueValidator(10.0)]
    )
    
    class Meta:
        model = DatasetRating
        fields = ['rating', 'comment']
        widgets = {
            'comment': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full border rounded p-2',
                'placeholder': 'Share your thoughts about this dataset (optional)'
            })
        }

class CollectionForm(forms.ModelForm):
    class Meta:
        model = UserCollection
        fields = ['name', 'description', 'is_public']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full border rounded p-2',
                'placeholder': 'Collection name'
            }),
            'description': forms.Textarea(attrs={
                'rows': 2,
                'class': 'w-full border rounded p-2',
                'placeholder': 'Describe this collection (optional)'
            }),
        }

class ReportForm(forms.ModelForm):
    class Meta:
        model = DatasetReport
        fields = ['report_type', 'description', 'screenshot']
        widgets = {
            'report_type': forms.Select(attrs={
                'class': 'w-full border rounded p-2'
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'class': 'w-full border rounded p-2',
                'placeholder': 'Please describe the issue in detail...'
            }),
        }
    