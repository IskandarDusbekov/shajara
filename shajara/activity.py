"""The audit trail behind the admin panel's "who did what"."""

import logging
import os

from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def client_ip(request):
    if request is None:
        return None
    # Behind nginx the socket peer is nginx itself; the visitor's address
    # arrives in X-Real-IP, which only a trusted local proxy can set.
    if os.environ.get("DJANGO_BEHIND_PROXY", "").strip().lower() in ("1", "true", "yes", "on"):
        forwarded = (request.META.get("HTTP_X_REAL_IP") or "").strip()
        if forwarded:
            return forwarded
    return request.META.get("REMOTE_ADDR") or None


def log_activity(request, action, *, user=None, detail="", tree=None, person=None):
    """Record one action. Never lets a logging problem break the request."""
    from .models import ActivityLog

    if user is None and request is not None and request.user.is_authenticated:
        user = request.user
    try:
        ActivityLog.objects.create(
            user=user, action=action, detail=(detail or "")[:300],
            tree=tree, person=person, ip_address=client_ip(request),
        )
    except Exception:  # pragma: no cover - the audit log must not take a page down
        logger.exception("Could not write activity log entry %s", action)


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    log_activity(request, "login", user=user)


@receiver(user_logged_out)
def _on_logout(sender, request, user, **kwargs):
    if user is not None:
        log_activity(request, "logout", user=user)
        from .presence import go_offline
        go_offline(user)


@receiver(user_login_failed)
def _on_login_failed(sender, credentials, request=None, **kwargs):
    # Only the attempted login name is kept, never the password.
    attempted = (credentials or {}).get("username", "")
    log_activity(request, "login_failed", user=None, detail=f"Kiritilgan nom: {attempted}"[:300])
