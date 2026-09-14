import os

from django import template
from django.conf import settings
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def static_v(path):
    """Like {% static %}, but busts the browser cache when the file changes.

    The development server serves /static/ ahead of the middleware chain, so a
    no-cache header can't be attached there; browsers then hold on to an old
    stylesheet or script long after it changed, which looks exactly like a
    broken feature. Appending the file's modification time fixes that without
    touching the response. In production ManifestStaticFilesStorage already
    puts a content hash in the name, so nothing is appended.
    """
    url = static(path)
    if not settings.DEBUG:
        return url
    try:
        source = finders.find(path)
        if source:
            return "%s?v=%d" % (url, os.path.getmtime(source))
    except (OSError, ValueError):
        pass
    return url
