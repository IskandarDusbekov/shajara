"""Old family pictures on a person's page.

Any member of the tree may add pictures — to the person's gallery or to a
story they write — with a caption and the year it was taken. The uploader
and the tree's owner may change the caption or remove the picture.

Every upload is opened and re-encoded here: only real images are kept,
turned upright, shrunk to a sensible size and saved as JPEG without the
camera's metadata (which can hold the place a photo was taken).

Pictures of people are never served from /media/ directly (nginx refuses
those folders): each request goes through a view that checks the visitor
may see the tree, so a copied link is useless to anyone outside the family.
"""

from io import BytesIO
import pillow_heif
pillow_heif.register_heif_opener() # HEIC formatini qo'shib beradi

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image, ImageOps, UnidentifiedImageError

from .activity import log_activity
from .models import Person, PersonPhoto, PersonStory, Tree
from .tree import can_view_tree, person_ids_in_tree, tree_role

MAX_PHOTO_BYTES = 15 * 1024 * 1024
MAX_PHOTOS_PER_UPLOAD = 10
MAX_PHOTOS_PER_PERSON = 20      # a person's page is a family album, not a photo dump
MAX_PHOTOS_PER_DAY = 60         # one account, all trees, last 24 hours
MAX_SIDE = 2000
Image.MAX_IMAGE_PIXELS = 60_000_000     # refuse decompression bombs


def clean_image(upload):
    """ContentFile with a re-encoded JPEG, or None if `upload` isn't a usable picture."""
    if not upload or upload.size > MAX_PHOTO_BYTES:
        return None
    try:
        upload.seek(0)
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


def room_for(request, person):
    """How many more pictures may be added to `person` by this user right now."""
    from datetime import timedelta
    from django.utils import timezone
    left_here = MAX_PHOTOS_PER_PERSON - PersonPhoto.objects.filter(person=person).count()
    today = PersonPhoto.objects.filter(uploaded_by=request.user,
                                       created_at__gte=timezone.now() - timedelta(days=1)).count()
    return max(0, min(MAX_PHOTOS_PER_UPLOAD, left_here, MAX_PHOTOS_PER_DAY - today))


def attach_photos(request, person, files, caption="", when="", story=None):
    """Save the uploaded pictures within the limits; returns (saved, rejected) counts.
    Files past the limit count as rejected and request.photo_limit_hit is set."""
    saved = rejected = 0
    files = list(files)
    room = room_for(request, person)
    if len(files) > room:
        request.photo_limit_hit = True
        rejected += len(files) - room
        files = files[:room]
    for upload in files:
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
    if getattr(request, "photo_limit_hit", False):
        messages.error(request, f"Cheklov: bir kishiga ko'pi bilan {MAX_PHOTOS_PER_PERSON} ta surat, bir yuklashda "
                                f"{MAX_PHOTOS_PER_UPLOAD} ta, bir kunda {MAX_PHOTOS_PER_DAY} ta. Ortiqchasi qo'shilmadi — "
                                "eng yaxshilarini tanlang yoki keraksizini o'chiring.")
    elif rejected:
        messages.error(request, f"{rejected} ta fayl qo'shilmadi: u rasm emas yoki 15 MB dan katta "
                                "(iPhone'da «Eng mos» formatni tanlang yoki suratni JPG qilib yuboring).")


@require_POST
@login_required
def photo_add_view(request, tree_key, pk):
    tree, person, denied = _target(request, tree_key, pk)
    if denied:
        return denied
    # a picture for one of the person's stories: its author or the tree's owner adds it
    story = None
    if request.POST.get("story"):
        story = get_object_or_404(PersonStory, pk=request.POST.get("story"), person=person)
        if story.author_id != request.user.id and tree_role(request.user, tree) != "owner":
            return HttpResponseForbidden("Hikoyaga suratni uning muallifi yoki shajara egasi biriktiradi.")
    back = f"hikoya-{story.pk}" if story else "suratlar"
    files = request.FILES.getlist("images")
    if not files:
        messages.error(request, "Avval suratni tanlang.")
        return _back(tree, pk, back)
    saved, rejected = attach_photos(request, person, files, (request.POST.get("caption") or "").strip(),
                                    (request.POST.get("when") or (story.when if story else "")).strip(), story=story)
    if saved:
        log_activity(request, "photo_add", tree=tree, person=person, detail=f"{person.full_name}: {saved} ta")
    report(request, saved, rejected)
    return _back(tree, pk, back)


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


def _private_file(field):
    """Hand a stored picture out to someone already checked; never cached by shared proxies."""
    try:
        handle = field.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404
    response = FileResponse(handle, content_type="image/jpeg" if field.name.endswith(".jpg") else None)
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    response["Content-Disposition"] = "inline"
    return response


def _viewable_person(request, tree_key, pk):
    """The person, if the visitor may see this tree and the person belongs to it — else 404,
    so a stranger can't even learn that the picture exists."""
    tree = Tree.objects.select_related("root_person").filter(public_id=tree_key).first()
    if not tree or not can_view_tree(request.user, tree) or pk not in person_ids_in_tree(tree.root_person):
        raise Http404
    return tree


def person_avatar_view(request, tree_key, pk):
    _viewable_person(request, tree_key, pk)
    person = get_object_or_404(Person, pk=pk)
    if not person.photo:
        raise Http404
    return _private_file(person.photo)


def photo_file_view(request, tree_key, photo_id):
    """The picture itself; with ?yuklash=1 it is saved as a file named after the person."""
    photo = get_object_or_404(PersonPhoto.objects.select_related("person"), pk=photo_id)
    _viewable_person(request, tree_key, photo.person_id)
    response = _private_file(photo.image)
    if request.GET.get("yuklash"):
        from django.utils.text import slugify
        name = slugify(photo.person.full_name) or "surat"
        response["Content-Disposition"] = f'attachment; filename="{name}-{slugify(photo.when) or photo.pk}.jpg"'
    return response


def story_photos(story_id_list):
    """{story id: [photos]} for showing pictures inside their stories."""
    out = {}
    for p in PersonPhoto.objects.filter(story_id__in=story_id_list):
        out.setdefault(p.story_id, []).append(p)
    return out
