from django.conf import settings
from django.core.mail import send_mail

from .models import OTP_MAX_ATTEMPTS


def send_otp_email(otp):
    """Send a one-time code. Returns True on success, False on failure."""
    if otp.purpose == "verify":
        subject = "e-Shajara — emailni tasdiqlash kodi"
        action = "emailingizni tasdiqlash"
    else:
        subject = "e-Shajara — parolni tiklash kodi"
        action = "parolingizni tiklash"

    body = (
        f"Assalomu alaykum, {otp.user.username}!\n\n"
        f"Sizning {action} uchun bir martalik kodingiz:\n\n"
        f"    {otp.code}\n\n"
        f"Kod 3 daqiqa davomida amal qiladi. Uni {OTP_MAX_ATTEMPTS} martagacha kiritib ko'rishingiz mumkin.\n"
        f"Agar bu so'rovni siz yubormagan bo'lsangiz, ushbu xatni e'tiborsiz qoldiring.\n\n"
        f"— e-Shajara · e-shajara.uz"
    )
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [otp.email], fail_silently=False)
        return True
    except Exception:
        return False
