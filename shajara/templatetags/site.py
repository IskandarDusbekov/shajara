from django import template

register = template.Library()


@register.simple_tag
def open_tree_links(limit=6):
    """Featured open trees for menus and the footer."""
    from ..public_views import open_trees
    return list(open_trees()[:limit])


@register.simple_tag
def seo_head():
    """Verification codes, analytics and custom tags an admin set for public pages."""
    from ..seo import head_snippets
    return head_snippets()