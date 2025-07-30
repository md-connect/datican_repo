from django.core.exceptions import ValidationError

def validate_file_extension(value):
    valid_extensions = ['.pdf', '.doc', '.docx']
    if not value.name.lower().endswith(tuple(valid_extensions)):
        raise ValidationError('Unsupported file format. Only PDF and Word documents are allowed.')