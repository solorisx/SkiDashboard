from django import template
import logging

logger = logging.getLogger(__name__)
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


@register.filter
def format_money(value):
    if value is None:
        return ""

    currency = value.currency
    amount = value.amount

    return f"{currency} {amount:,.2f}"


@register.filter
def icon_to_emoji(icon_class):
    """
    Convert Font Awesome icon classes to emoji for use in emails.
    Falls back to a default trophy emoji if no mapping is found.
    """
    if not icon_class:
        return "🏆"

    # Mapping of Font Awesome classes to emoji
    icon_map = {
        "fa-solid fa-cable-car": "🚡",
        "fa-solid fa-medal": "🥇",
        "fa-solid fa-trophy": "🏆",
        "fa-solid fa-mountain": "⛰️",
        "fa-solid fa-mountain-sun": "🏔️",
        "fa-solid fa-map-location-dot": "📍",
        "fa-solid fa-map-pin": "📌",
        "fa-solid fa-compass": "🧭",
        "fa-solid fa-map": "🗺️",
        "fa-solid fa-crown": "👑",
        "fa-solid fa-calendar-day": "📅",
        "fa-solid fa-calendar-check": "✅",
        "fa-solid fa-calendar-star": "⭐",
        "fa-solid fa-calendar-crown": "👑",
        "fa-solid fa-list": "📋",
        "fa-solid fa-grip": "⚡",
        "fa-solid fa-star": "⭐",
        "fa-solid fa-gem": "💎",
        "fa-solid fa-fire": "🔥",
    }

    # Return mapped emoji or default
    return icon_map.get(icon_class, "🏆")


@register.filter
def json_js(value):
    """Render JSON for inline <script> use, escaping <, > and & so data can't close the tag.

    Accepts an already-serialized JSON string or a Python object to serialize.
    """
    import json
    from django.utils.html import _json_script_escapes
    from django.utils.safestring import mark_safe

    if not isinstance(value, str):
        value = json.dumps(value, default=str)
    return mark_safe(value.translate(_json_script_escapes))
