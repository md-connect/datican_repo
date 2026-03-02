# datasets/templatetags/dataset_extras.py
import os
from django import template

register = template.Library()

@register.filter
def basename(value):
    """Get the basename of a file path"""
    if value:
        return os.path.basename(str(value))
    return value

@register.filter
def get_item(dictionary, key):
    """Template filter to get dictionary item by key"""
    if dictionary and key in dictionary:
        return dictionary.get(key)
    return None

