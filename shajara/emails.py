import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .activity import log_activity
from .models import OTP_MAX_ATTEMPTS, OTP_TTL

logger = logging.getLogger(__name__)


def send_otp_email(otp):
    """Send a one-time code as a branded HTML email, with a plain-text
    fallback for clients that don't render HTML. Returns True on success,
    False on failure."""
    if otp.purpose == "verify":
        subject = "e-Shajara — emailni tasdiqlash kodi"
        action = "emailingizni tasdiqlash"
    else:
        subject = "e-Shajara — parolni tiklash kodi"
        action = "parolingizni tiklash"

    context = {
        "username": otp.user.username,
        "code": otp.code,
        "action": action,
        "ttl_minutes": int(OTP_TTL.total_seconds() // 60),
        "max_attempts": OTP_MAX_ATTEMPTS,
    }
    text_body = render_to_string("shajara/emails/otp.txt", context)
    html_body = render_to_string("shajara/emails/otp.html", {**context, "subject": subject})

    try:
        message = EmailMultiAlternatives(subject, text_body, settings.DEFAULT_FROM_EMAIL, [otp.email])
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
        return True
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if settings.EMAIL_HOST_PASSWORD:
            reason = reason.replace(settings.EMAIL_HOST_PASSWORD, "********")
        logger.error("OTP email (%s) to %s failed: %s", otp.purpose, otp.email, reason)
        log_activity(None, "email_failed", user=otp.user, detail=f"{otp.purpose} → {otp.email}: {reason}")
        return False
