from django import template

register = template.Library()

@register.filter
def divide(value, arg):
    try:
        if value is None:
            return 0
        return value / arg
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def multiply(value, arg):
    try:
        if value is None:
            return 0
        return value * arg
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def subtract(value, arg):
    try:
        return value - arg
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def add(value, arg):
    try:
        return value + arg
    except (ValueError, ZeroDivisionError):
        return 0
    
@register.filter
def round_to(value, arg):
    try:
        if value is None:
            return 0
        return round(value, arg)
    except (ValueError, ZeroDivisionError):
        return 0