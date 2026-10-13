from django import template

from ..tree import tree_role as _tree_role

register = template.Library()


@register.simple_tag
def tree_role(tree, user):
    """{% tree_role tree request.user as role %} — "owner", "muharrir", "kuzatuvchi" or None."""
    if not tree or not getattr(tree, "pk", None):
        return None
    return _tree_role(user, tree)


UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust",
             "sentabr", "oktabr", "noyabr", "dekabr"]


@register.filter
def uz_date(value):
    """{{ d|uz_date }} — «13-oktabr 2026» (the site speaks Uzbek whatever the locale)."""
    if not value:
        return ""
    if hasattr(value, "astimezone") and getattr(value, "tzinfo", None):
        from django.utils import timezone
        value = timezone.localtime(value)
    return f"{value.day}-{UZ_MONTHS[value.month - 1]} {value.year}"
