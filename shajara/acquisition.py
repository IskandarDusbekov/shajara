"""Where new accounts come from.

On a visitor's very first page (while still signed out) we work out the
channel that sent them — Instagram, Telegram, Google, a shared invite link,
direct, and so on — from a ?manba=/utm_source= tag or the referring site, and
keep it in the session. When they register, register_view copies it onto their
UserProfile, so the dashboard can show "where users came from".

An explicit ?manba= (or utm_source / ref) tag always wins over the referrer,
because messenger in-app browsers (Instagram, Telegram) often strip it — so our
own share links carry ?manba=instagram and the like.
"""

from urllib.parse import urlparse

# Referring host → channel. First match wins; anything else external is "referral".
_HOST_MAP = [
    ("instagram", ("instagram.", "l.instagram", "ig.me")),
    ("telegram", ("t.me", "telegram.", "web.telegram", "tele.gram")),
    ("facebook", ("facebook.", "fb.com", "fb.me", "l.facebook", "lm.facebook")),
    ("youtube", ("youtube.", "youtu.be")),
    ("tiktok", ("tiktok.", "vm.tiktok")),
    ("google", ("google.", "googleusercontent", "googleadservices")),
    ("yandex", ("yandex.", "ya.ru")),
]

# Values people (or our own links) put in ?manba= / utm_source= / ref=.
_PARAM_MAP = {
    "instagram": "instagram", "ig": "instagram", "insta": "instagram",
    "telegram": "telegram", "tg": "telegram", "tme": "telegram",
    "facebook": "facebook", "fb": "facebook", "messenger": "facebook",
    "youtube": "youtube", "yt": "youtube",
    "tiktok": "tiktok", "tt": "tiktok",
    "google": "google", "yandex": "yandex",
    "invite": "invite", "taklif": "invite",
}

_SKIP_SUFFIXES = (".json", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".xml", ".txt", ".css", ".js", ".webmanifest")


def _from_param(value):
    return _PARAM_MAP.get((value or "").strip().lower(), "")


def _from_host(host):
    for key, needles in _HOST_MAP:
        if any(n in host for n in needles):
            return key
    return "referral"


def classify(request, own_host):
    """(source, detail) for this first visit. `source` is always a SOURCE_CHOICES
    key; `detail` is the raw host or tag, for the record."""
    tag = (request.GET.get("manba") or request.GET.get("utm_source")
           or request.GET.get("ref") or "").strip()
    mapped = _from_param(tag)
    if mapped:
        return mapped, tag[:120]

    if request.path.startswith("/taklif/"):
        return "invite", request.path[:120]

    ref = request.META.get("HTTP_REFERER", "")
    host = urlparse(ref).netloc.lower()
    if host and not (own_host and own_host in host):
        return _from_host(host), host[:120]

    # An unrecognised campaign tag still means they came from somewhere.
    if tag:
        return "referral", tag[:120]
    return "direct", ""


def for_signup(session):
    """(source, detail) captured on the first visit, for register_view to store."""
    return session.get("acq_source", "direct"), session.get("acq_ref", "")[:120]


class AcquisitionMiddleware:
    """Records the first-touch channel in the session, once per signed-out visit."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._capture(request)
        return self.get_response(request)

    def _capture(self, request):
        if request.method != "GET":
            return
        session = getattr(request, "session", None)
        if session is None or "acq_source" in session:
            return
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            return
        path = request.path
        if path.startswith(("/static/", "/media/")) or path.endswith(_SKIP_SUFFIXES):
            return
        own_host = request.get_host().split(":")[0].lower()
        source, detail = classify(request, own_host)
        session["acq_source"] = source
        session["acq_ref"] = detail
        session["acq_landing"] = path[:200]
