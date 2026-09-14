"""Who is on the site right now.

Every page a signed-in person loads stamps UserProfile.last_seen. The stamp
is written at most once a minute per session, so presence costs one small
UPDATE a minute per active visitor rather than one per request.
"""

import time

from django.utils import timezone

from .models import ONLINE_WINDOW, UserProfile

TOUCH_EVERY = 60  # seconds
_SESSION_KEY = "_seen_at"


def online_since():
    return timezone.now() - ONLINE_WINDOW


def touch(user):
    now = timezone.now()
    if not UserProfile.objects.filter(user=user).update(last_seen=now):
        UserProfile.objects.get_or_create(user=user, defaults={"last_seen": now, "tour_done": True})


class PresenceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        # Static files and the live-count polling itself do not count as being on the site.
        if user is not None and user.is_authenticated and not request.path.endswith(".json"):
            session = request.session
            last = session.get(_SESSION_KEY, 0)
            if time.time() - last >= TOUCH_EVERY:
                touch(user)
                session[_SESSION_KEY] = time.time()
        return response


def go_offline(user):
    UserProfile.objects.filter(user=user).update(last_seen=online_since() - ONLINE_WINDOW)
