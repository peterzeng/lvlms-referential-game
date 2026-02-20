from django import template
import json
import html

register = template.Library()

@register.filter
def load_json(value):
    """Load JSON string as Python object"""
    try:
        return json.loads(value) if value else []
    except (json.JSONDecodeError, TypeError):
        return []

@register.filter
def get_item(dictionary, key):
    """Get item from dictionary"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    elif isinstance(dictionary, list):
        # If it's a list, try to find items with the key
        return [item.get(key) for item in dictionary if isinstance(item, dict) and key in item]
    return None

@register.filter
def in_list(value, lst):
    """Check if value is in list"""
    try:
        if isinstance(lst, str):
            lst = json.loads(lst)
        return value in lst
    except:
        return False

@register.filter
def yesno(value, options="yes,no"):
    """Convert boolean to yes/no strings"""
    try:
        if isinstance(options, str) and ',' in options:
            yes_val, no_val = options.split(',', 1)
        else:
            yes_val, no_val = "yes", "no"
        
        return yes_val.strip() if value else no_val.strip()
    except:
        return "yes" if value else "no"

@register.filter
def make_list(value):
    """Convert a string into a list of its characters (similar to Django's make_list)"""
    if value is None:
        return []
    return list(str(value))

@register.filter
def json_script(value, element_id):
    """Create a script tag with JSON data (similar to Django's json_script)"""
    import json
    from django.utils.safestring import mark_safe
    
    if value is None:
        json_str = 'null'
    else:
        try:
            # If it's already a string that looks like JSON, use it as-is
            if isinstance(value, str):
                # Try to parse it to validate it's valid JSON
                json.loads(value)
                json_str = value
            else:
                # Convert to JSON string
                json_str = json.dumps(value)
        except (json.JSONDecodeError, TypeError):
            json_str = 'null'
    
    # Escape for HTML
    json_str = json_str.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    
    script_tag = f'<script id="{element_id}" type="application/json">{json_str}</script>'
    return mark_safe(script_tag)

@register.filter
def safe(value):
    """Mark a string as safe for HTML output (similar to Django's safe)"""
    from django.utils.safestring import mark_safe
    return mark_safe(str(value)) if value is not None else ''

@register.filter
def length(value):
    """Return the length of a value (similar to Django's length)"""
    try:
        return len(value)
    except (TypeError, AttributeError):
        return 0

@register.filter
def pluralize(value, suffix="s"):
    """Add plural suffix if value != 1 (similar to Django's pluralize)"""
    try:
        if value == 1:
            return ""
        else:
            return suffix
    except (TypeError, ValueError):
        return suffix

@register.filter
def floatformat(value, decimal_places=1):
    """Format a float to specified decimal places (similar to Django's floatformat)"""
    try:
        if value is None:
            return ''
        float_val = float(value)
        if isinstance(decimal_places, str):
            decimal_places = int(decimal_places)
        return f"{float_val:.{decimal_places}f}"
    except (ValueError, TypeError):
        return str(value) if value is not None else ''

@register.filter
def date(value, format_string="%Y-%m-%d"):
    """Format a date/datetime (simplified version of Django's date)"""
    try:
        if value is None:
            return ''
        
        # Handle different date/time formats
        if hasattr(value, 'strftime'):
            # It's a datetime/date object
            return value.strftime(format_string)
        elif isinstance(value, str):
            # Try to parse string as datetime
            from datetime import datetime
            try:
                dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
                return dt.strftime(format_string)
            except:
                return value
        else:
            return str(value)
    except (ValueError, TypeError, AttributeError):
        return str(value) if value is not None else ''

@register.filter
def escapejs(value):
    """Escapes string for use in JavaScript"""
    if value is None:
        return ''
    value = str(value)
    value = value.replace('\\', '\\\\')
    value = value.replace('"', '\\"')
    value = value.replace("'", "\\'")
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('\t', '\\t')
    value = html.escape(value)
    return value