# datasets/templatetags/url_helpers.py
from django import template

register = template.Library()

@register.simple_tag
def remove_url_param(url_params, param_to_remove, value_to_remove=None):
    """
    Remove a parameter from URL parameters.
    If value_to_remove is specified, only remove that specific value for multi-value params.
    """
    params = url_params.copy()
    
    if value_to_remove:
        # For multi-value parameters (like modality)
        values = params.getlist(param_to_remove)
        if value_to_remove in values:
            values.remove(value_to_remove)
            params.setlist(param_to_remove, values)
    else:
        # Remove the entire parameter
        params.pop(param_to_remove, None)
    
    return params.urlencode() if params else ''