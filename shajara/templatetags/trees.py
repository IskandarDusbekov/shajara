from django import template

from ..tree import tree_role as _tree_role

register = template.Library()


@register.simple_tag
def tree_role(tree, user):
    """{% tree_role tree request.user as role %} — "owner", "muharrir", "kuzatuvchi" or None."""
    if not tree or not getattr(tree, "pk", None):
        return None
    return _tree_role(user, tree)
