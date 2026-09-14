"""Pictures of the tree.

The picture itself is drawn in the browser from the live map (tree-export.js),
so it matches exactly what the reader arranged. The server's part:

  - give every picture a check code and a QR mark before it is drawn,
  - keep a small preview of the tree (uploaded by the owner or an editor),
    which invite links show in messenger previews and on the invite page.
"""

import json
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError
from reportlab.graphics import renderSVG

from .activity import log_activity
from .book import long_date, qr_drawing
from .models import Tree, TreeInvite
from .tree import can_edit_tree, can_view_tree, compute_levels
from .views import record_export

MAX_PREVIEW_BYTES = 5 * 1024 * 1024
MAX_PREVIEW_SIDE = 4000


def qr_svg(url, size=120):
    """A QR code as an inline <svg> element (no XML prolog)."""
    markup = renderSVG.drawToString(qr_drawing(url, size))
    start = markup.find("<svg")
    return markup[start:] if start >= 0 else ""


@require_POST
@login_required
def picture_record_view(request, tree_key):
    tree = get_object_or_404(Tree.objects.select_related("owner", "root_person"), public_id=tree_key)
    if not can_view_tree(request.user, tree):
        return JsonResponse({"error": "Bu shajara sizga ko'rinmaydi."}, status=403)
    try:
        kind = json.loads(request.body.decode("utf-8") or "{}").get("kind")
    except (ValueError, UnicodeDecodeError, AttributeError):
        kind = None
    if kind not in ("png", "svg"):
        return JsonResponse({"error": "Noto'g'ri format."}, status=400)

    levels, _, _ = compute_levels(tree.root_person)
    record = record_export(request, tree, kind, len(levels), len(set(levels.values())))
    verify_url = request.build_absolute_uri(reverse("verify_export", args=[record.code]))
    log_activity(request, "tree_export", tree=tree, detail=f"{kind.upper()} rasm: {tree.name} ({record.pretty_code})")
    return JsonResponse({
        "code": record.pretty_code,
        "verify_url": verify_url,
        "qr_svg": qr_svg(verify_url),
        "compiler": tree.owner.get_full_name() or tree.owner.username,
        "date": long_date(timezone.localdate()),
        "people": record.people_count,
        "generations": record.generations,
        "kind_label": "TA‘LIMIY SHAJARA" if tree.is_learning else "OILAVIY SHAJARA",
        "subtitle": " · ".join(x for x in (tree.subject, tree.era) if x) if tree.is_learning else "",
    })


@require_POST
@login_required
def preview_upload_view(request, tree_key):
    """Store the share preview. Only real, reasonably sized PNGs are kept."""
    tree = get_object_or_404(Tree, public_id=tree_key)
    if not can_edit_tree(request.user, tree):
        return JsonResponse({"error": "forbidden"}, status=403)
    upload = request.FILES.get("image")
    if not upload or upload.size > MAX_PREVIEW_BYTES:
        return JsonResponse({"error": "Rasm topilmadi yoki juda katta."}, status=400)
    try:
        img = Image.open(upload)
        img.verify()
        upload.seek(0)
        img = Image.open(upload)
        if img.format != "PNG" or max(img.size) > MAX_PREVIEW_SIDE:
            raise ValueError
        img.load()
    except (UnidentifiedImageError, ValueError, OSError):
        return JsonResponse({"error": "Rasm formati noto'g'ri."}, status=400)

    # Re-encode: never serve the uploaded bytes as they came.
    out = BytesIO()
    img.convert("RGB").save(out, format="PNG", optimize=True)
    old = tree.preview_image.name if tree.preview_image else None
    tree.preview_image.save("preview.png", ContentFile(out.getvalue()), save=False)
    tree.preview_updated_at = timezone.now()
    tree.save(update_fields=["preview_image", "preview_updated_at"])
    if old and old != tree.preview_image.name:
        tree.preview_image.storage.delete(old)
    return JsonResponse({"ok": True})


def invite_preview_view(request, token):
    """The tree picture behind an invite link — what Telegram and other
    messengers show when the link is pasted. Public, but only while the
    invite is alive."""
    invite = get_object_or_404(TreeInvite.objects.select_related("tree"), token=token)
    tree = invite.tree
    if not invite.is_active or not tree.preview_image:
        raise Http404
    try:
        handle = tree.preview_image.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(handle, content_type="image/png")
    response["Cache-Control"] = "private, max-age=600"
    return response


@login_required
def tree_preview_view(request, tree_key):
    """The same picture for people inside the platform (overview page)."""
    tree = get_object_or_404(Tree, public_id=tree_key)
    if not can_view_tree(request.user, tree):
        return HttpResponseForbidden()
    if not tree.preview_image:
        raise Http404
    try:
        handle = tree.preview_image.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404
    response = FileResponse(handle, content_type="image/png")
    response["Cache-Control"] = "private, max-age=600"
    return response
