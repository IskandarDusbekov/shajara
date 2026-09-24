"""Site-wide SEO helpers: verification codes, <head> snippets, robots.txt
and the sitemap. Everything an admin edits in /boshqaruv/seo/sozlamalar/
ends up in the pages through here."""

import re
from html.parser import HTMLParser

from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import SiteSetting

CODE_RE = re.compile(r"^[A-Za-z0-9_\-.:=]{6,200}$")
GA_RE = re.compile(r"^(G|UA|AW|GT)-[A-Za-z0-9\-]{4,20}$")
METRICA_RE = re.compile(r"^\d{4,12}$")
FILE_PATH_RE = re.compile(r"^(?:\.well-known/)?[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,8}$")


def parse_verification(value):
    """Accept a bare code or the whole <meta name="..." content="CODE"> tag
    the search engine shows, and return just the code."""
    value = (value or "").strip()
    match = re.search(r"content\s*=\s*[\"']([^\"']+)[\"']", value)
    return (match.group(1) if match else value).strip()


class _HeadCheck(HTMLParser):
    ALLOWED = {"meta", "link", "script"}

    def __init__(self):
        super().__init__()
        self.error = None
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED:
            self.error = f"<{tag}> tegiga ruxsat yo'q — faqat meta, link va script."
        self._in_script = tag == "script"

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if data.strip() and not self._in_script:
            self.error = "Teglar orasida oddiy matn bo'lishi mumkin emas."


def check_head_html(value):
    """Return an error message, or "" when the snippet is only meta/link/script tags."""
    checker = _HeadCheck()
    try:
        checker.feed(value or "")
        checker.close()
    except Exception:
        return "HTML noto'g'ri yozilgan."
    return checker.error or ""


def site_setting():
    return SiteSetting.load()


def head_snippets(cfg=None):
    """The search-engine tags, analytics and custom tags for a public <head>."""
    cfg = cfg or site_setting()
    parts = []
    for name, code in (("google-site-verification", cfg.google_verification),
                       ("msvalidate.01", cfg.bing_verification),
                       ("yandex-verification", cfg.yandex_verification)):
        if code and CODE_RE.match(code):
            parts.append(format_html('<meta name="{}" content="{}">', name, code))
    if cfg.block_indexing:
        parts.append(mark_safe('<meta name="robots" content="noindex, nofollow">'))
    if cfg.extra_head_html.strip() and not check_head_html(cfg.extra_head_html):
        parts.append(mark_safe(cfg.extra_head_html.strip()))
    if cfg.ga_measurement_id and GA_RE.match(cfg.ga_measurement_id):
        gid = cfg.ga_measurement_id
        parts.append(format_html(
            '<script async src="https://www.googletagmanager.com/gtag/js?id={0}"></script>'
            "<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}"
            "gtag('js',new Date());gtag('config','{0}');</script>", gid))
    if cfg.yandex_metrica_id and METRICA_RE.match(cfg.yandex_metrica_id):
        mid = cfg.yandex_metrica_id
        parts.append(format_html(
            "<script>(function(m,e,t,r,i,k,a){{m[i]=m[i]||function(){{(m[i].a=m[i].a||[]).push(arguments)}};"
            "m[i].l=1*new Date();k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,"
            "a.parentNode.insertBefore(k,a)}})(window,document,'script','https://mc.yandex.ru/metrika/tag.js','ym');"
            "ym({0},'init',{{clickmap:true,trackLinks:true,accurateTrackBounce:true}});</script>", mid))
    return mark_safe("".join(str(p) for p in parts))


def default_robots(base):
    return "\n".join([
        "User-agent: *",
        "Allow: /$",
        "Allow: /shajaralar/",
        "Allow: /static/",
        "Disallow: /shajara/",
        "Disallow: /boshqaruv/",
        "Disallow: /admin/",
        "Disallow: /taklif/",
        "Disallow: /media/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ])


def robots_body(base, cfg=None):
    cfg = cfg or site_setting()
    if cfg.block_indexing:
        return "User-agent: *\nDisallow: /\n"
    custom = cfg.robots_txt.strip()
    if not custom:
        return default_robots(base)
    if "sitemap:" not in custom.lower():
        custom += f"\n\nSitemap: {base}/sitemap.xml"
    return custom + "\n"


def absolute(base, url):
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return base + (url if url.startswith("/") else "/" + url)


def og_image(base, *candidates):
    for c in candidates:
        if c:
            return absolute(base, c)
    return ""


def env_report():
    """What the deployment is configured with, for the admin's health page."""
    return {
        "debug": settings.DEBUG,
        "site_url": getattr(settings, "SITE_URL", ""),
        "email_backend": settings.EMAIL_BACKEND.rsplit(".", 2)[-2],
        "email_real": settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"),
        "email_host": settings.EMAIL_HOST,
        "email_port": settings.EMAIL_PORT,
        "email_user": settings.EMAIL_HOST_USER,
        "email_tls": settings.EMAIL_USE_TLS,
        "email_ssl": settings.EMAIL_USE_SSL,
        "from_email": settings.DEFAULT_FROM_EMAIL,
    }
