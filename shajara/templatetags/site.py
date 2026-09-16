from django import template

register = template.Library()


@register.simple_tag
def open_tree_links(limit=6):
    """Featured open trees for menus and the footer."""
    from ..public_views import open_trees
    return list(open_trees()[:limit])
