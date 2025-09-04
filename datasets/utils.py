# datasets/utils.py
import pydicom
import nibabel as nib
import numpy as np
from PIL import Image
from io import BytesIO
import os
import gzip
import tempfile
from django.contrib.auth.decorators import user_passes_test


def convert_to_png(file):
    """Convert medical image files (DICOM/NIfTI) to PNG format"""
    # Handle both file paths and file objects
    if hasattr(file, 'temporary_file_path'):
        file_path = file.temporary_file_path()
        is_temp = False
    else:
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.name)[1]) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            file_path = tmp.name
        is_temp = True
    
    try:
        # Check file type and process accordingly
        if file.name.lower().endswith(('.dcm', '.dicom')):
            result = dicom_to_png(file_path)
        elif file.name.lower().endswith(('.nii', '.nii.gz')):
            result = nifti_to_png(file_path)
        else:
            # For non-medical images, just return the original file
            return file
        
        # Clean up temporary file if we created it
        if is_temp:
            os.unlink(file_path)
            
        return result
    except Exception as e:
        # Clean up temporary file if we created it
        if is_temp:
            os.unlink(file_path)
        raise e

def dicom_to_png(file_path):
    """Convert DICOM file to PNG"""
    ds = pydicom.dcmread(file_path)
    pixel_array = ds.pixel_array
    
    # Normalize to 0-255 range
    pixel_array = pixel_array.astype(np.float32)
    if pixel_array.max() - pixel_array.min() > 0:
        pixel_array = (pixel_array - pixel_array.min()) / (pixel_array.max() - pixel_array.min()) * 255.0
    else:
        pixel_array = np.zeros_like(pixel_array)
    pixel_array = pixel_array.astype(np.uint8)
    
    # Create PIL image
    img_pil = Image.fromarray(pixel_array)
    return image_to_buffer(img_pil)

def nifti_to_png(file_path):
    """Convert NIfTI file to PNG"""
    # Handle .nii.gz files
    try:
        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rb') as f:
                nii = nib.FileHolder(fileobj=f)
                img = nib.Nifti1Image.from_file_map({'header': nii, 'image': nii})
        else:
            img = nib.load(file_path)
        
        data = img.get_fdata()
        
        # Get middle slice from the first 3D volume
        if data.ndim == 4:  # 4D data (x,y,z,time)
            # Use first timepoint and middle z-slice
            vol_idx = data.shape[3] // 2
            slice_idx = data.shape[2] // 2
            slice_data = data[:, :, slice_idx, vol_idx]
        elif data.ndim == 3:  # 3D data (x,y,z)
            slice_idx = data.shape[2] // 2
            slice_data = data[:, :, slice_idx]
        else:
            # Use first slice for 2D data
            slice_data = data[:, :, 0] if data.ndim > 2 else data
        
        # Normalize to 0-255 range
        slice_data = slice_data.astype(np.float32)
        if slice_data.max() - slice_data.min() > 0:
            slice_data = (slice_data - slice_data.min()) / (slice_data.max() - slice_data.min()) * 255.0
        else:
            slice_data = np.zeros_like(slice_data)
        slice_data = slice_data.astype(np.uint8)
        
        # Create PIL image
        img_pil = Image.fromarray(slice_data)
        return image_to_buffer(img_pil)
    finally:
        # Clean up temporary files if needed
        pass
def image_to_buffer(img):
    """Convert PIL image to BytesIO buffer"""
    png_buffer = BytesIO()
    img.save(png_buffer, format='PNG')
    png_buffer.seek(0)
    return png_buffer

def is_data_manager(user):
    """Check if user is a data manager or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'data_manager')

def is_director(user):
    """Check if user is a director or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'director')

def is_admin(user):
    """Check if user is an admin or superuser"""
    return user.is_authenticated and (user.is_superuser or user.role == 'admin')

# Create decorators for role-based access
def data_manager_required(view_func=None):
    actual_decorator = user_passes_test(
        is_data_manager,
        login_url='/accounts/login/',
        redirect_field_name=None
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator

def director_required(view_func=None):
    actual_decorator = user_passes_test(
        is_director,
        login_url='/accounts/login/',
        redirect_field_name=None
    )
    if view_func:
        return actual_decorator(view_func)
    return actual_decorator