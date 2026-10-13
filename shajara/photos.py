"""Old family pictures on a person's page.

Any member of the tree may add pictures — to the person's gallery or to a
story they write — with a caption and the year it was taken. The uploader
and the tree's owner may change the caption or remove the picture.

Every upload is opened and re-encoded here: only real images are kept,
turned upright, shrunk to a sensible size and saved as JPEG without the
camera's metadata (which can hold the place a photo was taken).
"""

from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from .activity import log_activity
from .models import Person, PersonPhoto, Tree
from .tree import can_view_tree, person_ids_in_tree, tree_role

MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_PHOTOS_PER_UPLOAD = 10
MAX_SIDE = 2000
Image.MAX_IMAGE_PIXELS = 60_000_000     # refuse decompression bombs


def clean_image(upload):
    """ContentFile with a re-encoded JPEG, or None if `upload` isn't a usable picture."""
    if not upload or upload.size > MAX_PHOTO_BYTES:
        return None
    try:
        img = Image.open(upload)
        img.verify()
        upload.seek(0)
        img = Image.open(upload)
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, "white")
            rgba = img.convert("RGBA")
            background.paste(rgba, mask=rgba.split()[-1])
            img = background
        img = img.convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        out = BytesIO()
        img.save(out, format="JPEG", quality=86, optimize=True, progressive=True)
        return ContentFile(out.getvalue(), name="photo.jpg")
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return None


def attach_photos(request, person, files, caption="", when="", story=None):
    """Save the uploaded pictures; returns (saved, rejected) counts."""
    saved = rejected = 0
    for upload in list(files)[:MAX_PHOTOS_PER_UPLOAD]:
        content = clean_image(upload)
        if not content:
            rejected += 1
            continue
        photo = PersonPhoto(person=person, story=story, caption=caption[:300], when=when[:60], uploaded_by=request.user)
        photo.image.save("photo.jpg", content, save=True)
        saved += 1
    return saved, rejected


def _target(request, tree_key, pk):
    tree = get_object_or_404(Tree.objects.select_related("root_person"), public_id=tree_key)
    if not can_view_tree(request.user, tree) or tree_role(request.user, tree) is None:
        return None, None, HttpResponseForbidden("Suratni faqat shajara a'zolari qo'sha oladi.")
    if pk not in person_ids_in_tree(tree.root_person):
        return None, None, HttpResponseForbidden("Bu shaxs bu shajaraga tegishli emas.")
    return tree, get_object_or_404(Person, pk=pk), None


def _back(tree, pk, anchor="suratlar"):
    return redirect(reverse("person_detail", args=[tree.url_key, pk]) + f"#{anchor}")


def report(request, saved, rejected):
    if saved:
        messages.success(request, f"{saved} ta surat qo'shildi." if saved > 1 else "Surat qo'shildi.")
    if rejected:
        messages.error(request, f"{rejected} ta fayl qo'shilmadi: u rasm emas yoki 15 MB dan katta.")


@require_POST
@login_required
def photo_add_view(request, tree_key, pk):
    tree, person, denied = _target(request, tree_key, pk)
    if denied:
        return denied
    files = request.FILES.getlist("images")
    if not files:
        messages.error(request, "Avval suratni tanlang.")
        return _back(tree, pk)
    saved, rejected = attach_photos(request, person, files, (request.POST.get("caption") or "").strip(),
                                    (request.POST.get("when") or "").strip())
    if saved:
        log_activity(request, "photo_add", tree=tree, person=person, detail=f"{person.full_name}: {saved} ta")
    report(request, saved, rejected)
    return _back(tree, pk)


def _photo_for_change(request, tree_key, pk, photo_id):
    tree, person, denied = _target(request, tree_key, pk)
    if denied:
        return None, None, None, denied
    photo = get_object_or_404(PersonPhoto, pk=photo_id, person=person)
    if photo.uploaded_by_id != request.user.id and tree_role(request.user, tree) != "owner":
        return None, None, None, HttpResponseForbidden("Suratni faqat uni qo'shgan kishi yoki shajara egasi o'zgartira oladi.")
    return tree, person, photo, None


@require_POST
@login_required
def photo_edit_view(request, tree_key, pk, photo_id):
    tree, person, photo, denied = _photo_for_change(request, tree_key, pk, photo_id)
    if denied:
        return denied
    photo.caption = (request.POST.get("caption") or "").strip()[:300]
    photo.when = (request.POST.get("when") or "").strip()[:60]
    photo.save(update_fields=["caption", "when"])
    log_activity(request, "photo_edit", tree=tree, person=person, detail=person.full_name)
    messages.success(request, "Surat izohi saqlandi.")
    return _back(tree, pk, f"surat-{photo.pk}")


@require_POST
@login_required
def photo_delete_view(request, tree_key, pk, photo_id):
    tree, person, photo, denied = _photo_for_change(request, tree_key, pk, photo_id)
    if denied:
        return denied
    in_story = photo.story_id
    photo.image.delete(save=False)
    photo.delete()
    log_activity(request, "photo_delete", tree=tree, person=person, detail=person.full_name)
    messages.success(request, "Surat o'chirildi.")
    return _back(tree, pk, f"hikoya-{in_story}" if in_story else "suratlar")


def story_photos(story_id_list):
    """{story id: [photos]} for showing pictures inside their stories."""
    out = {}
    for p in PersonPhoto.objects.filter(story_id__in=story_id_list):
        out.setdefault(p.story_id, []).append(p)
    return out
