"""Historical maps: upload an old map, pin dated places on it, draw the
routes between them (campaigns, caravans, migrations) and replay them along
a timeline.

Pages are ordinary views; everything the editor changes goes through a small
JSON API, so the map page never reloads while someone is working on it.
"""

import json
import re
from io import BytesIO

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from PIL import Image, UnidentifiedImageError

from .activity import log_activity
from .models import (
    PLACE_KIND_CHOICES, ROUTE_KIND_CHOICES, VISIBILITY_CHOICES, HistoricalMap, MapPlace, MapRoute, Person,
    year_label,
)
from .tree import can_view_tree, compute_levels, trees_for_user

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_SIDE = 9000
MIN_YEAR, MAX_YEAR = -4000, 2100
PLACE_KINDS = dict(PLACE_KIND_CHOICES)
ROUTE_KINDS = dict(ROUTE_KIND_CHOICES)
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# ----------------------------------------------------------------- access --

def can_view_map(user, hmap):
    return hmap.is_public or hmap.owner_id == user.id or user.is_staff


def can_edit_map(user, hmap):
    return hmap.owner_id == user.id


def get_map(request, key):
    hmap = get_object_or_404(HistoricalMap.objects.select_related("owner", "tree"), public_id=key)
    if not can_view_map(request.user, hmap):
        raise Http404
    return hmap


# ------------------------------------------------------------------ forms --

class MapForm(forms.ModelForm):
    class Meta:
        model = HistoricalMap
        fields = ["title", "era", "description", "sources", "visibility", "tree"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "pf-input", "placeholder": "Masalan: Amir Temur yurishlari"}),
            "era": forms.TextInput(attrs={"class": "pf-input", "placeholder": "Masalan: 1370–1405"}),
            "description": forms.Textarea(attrs={"class": "pf-input", "rows": 3,
                                                 "placeholder": "Xarita nimani ko'rsatadi, qaysi mavzuga tegishli"}),
            "sources": forms.Textarea(attrs={"class": "pf-input", "rows": 3,
                                             "placeholder": "Har bir manbani yangi qatordan yozing"}),
            "visibility": forms.Select(attrs={"class": "pf-input"}, choices=VISIBILITY_CHOICES),
            "tree": forms.Select(attrs={"class": "pf-input"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tree"].queryset = trees_for_user(user) if user else self.fields["tree"].queryset.none()
        self.fields["tree"].required = False
        self.fields["tree"].empty_label = "— bog'lanmagan —"


class MapImageForm(forms.Form):
    image = forms.ImageField(label="Xarita rasmi")

    def clean_image(self):
        f = self.cleaned_data["image"]
        if f.size > MAX_IMAGE_BYTES:
            raise forms.ValidationError("Rasm 20 MB dan katta bo'lmasin.")
        try:
            img = Image.open(f)
            img.load()
        except (UnidentifiedImageError, OSError):
            raise forms.ValidationError("Bu rasm fayli emas yoki buzilgan.")
        if max(img.size) > MAX_IMAGE_SIDE:
            raise forms.ValidationError(f"Rasm tomoni {MAX_IMAGE_SIDE} pikseldan oshmasin.")
        f.seek(0)
        return f


def store_image(hmap, upload):
    """Re-encode the upload (never keep the raw bytes) and fill in its size."""
    img = Image.open(upload)
    img.load()
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    out = BytesIO()
    if has_alpha:
        img.save(out, format="PNG", optimize=True)
        name = "map.png"
    else:
        img.convert("RGB").save(out, format="JPEG", quality=90, optimize=True)
        name = "map.jpg"
    old = hmap.image.name if hmap.image else None
    hmap.image.save(name, ContentFile(out.getvalue()), save=False)
    hmap.image_width, hmap.image_height = img.size
    return old


# ------------------------------------------------------------------ pages --

@login_required
def maps_list_view(request):
    mine = (HistoricalMap.objects.filter(owner=request.user)
            .annotate(n_places=Count("places", distinct=True), n_routes=Count("routes", distinct=True)))
    public = (HistoricalMap.objects.filter(visibility="public").exclude(owner=request.user)
              .select_related("owner")
              .annotate(n_places=Count("places", distinct=True), n_routes=Count("routes", distinct=True))
              .order_by("-is_sample", "-updated_at"))
    q = (request.GET.get("q") or "").strip()
    if q:
        cond = Q(title__icontains=q) | Q(era__icontains=q) | Q(description__icontains=q) | Q(places__name__icontains=q)
        mine, public = mine.filter(cond).distinct(), public.filter(cond).distinct()
    return render(request, "shajara/maps_list.html", {"mine": mine, "public": public, "q": q})


@login_required
def map_create_view(request):
    form = MapForm(request.POST or None, user=request.user)
    image_form = MapImageForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and image_form.is_valid():
        hmap = form.save(commit=False)
        hmap.owner = request.user
        store_image(hmap, image_form.cleaned_data["image"])
        hmap.save()
        log_activity(request, "map_create", tree=hmap.tree, detail=hmap.title)
        messages.success(request, "Xarita yuklandi. Endi «Joy qo'shish» bilan xaritaga voqealarni belgilang.")
        return redirect("map_detail", key=hmap.url_key)
    return render(request, "shajara/map_form.html", {"form": form, "image_form": image_form, "creating": True})


@login_required
def map_settings_view(request, key):
    hmap = get_map(request, key)
    if not can_edit_map(request.user, hmap):
        return HttpResponseForbidden("Faqat xarita egasi o'zgartira oladi.")
    if request.method == "POST" and request.POST.get("action") == "delete":
        title = hmap.title
        storage, name = hmap.image.storage, hmap.image.name
        hmap.delete()
        if name:
            storage.delete(name)
        log_activity(request, "map_delete", detail=title)
        messages.success(request, f"«{title}» xaritasi o'chirildi.")
        return redirect("maps")
    form = MapForm(request.POST or None, instance=hmap, user=request.user)
    image_form = MapImageForm(request.POST or None, request.FILES or None)
    if request.method == "POST":
        new_image = bool(request.FILES.get("image"))
        if form.is_valid() and (not new_image or image_form.is_valid()):
            hmap = form.save(commit=False)
            old = store_image(hmap, image_form.cleaned_data["image"]) if new_image else None
            hmap.save()
            if old and old != hmap.image.name:
                hmap.image.storage.delete(old)
            log_activity(request, "map_update", tree=hmap.tree, detail=hmap.title)
            messages.success(request, "Xarita saqlandi.")
            return redirect("map_detail", key=hmap.url_key)
    return render(request, "shajara/map_form.html", {"form": form, "image_form": image_form, "hmap": hmap})


def place_json(p):
    return {
        "id": p.id, "name": p.name, "kind": p.kind, "x": p.x, "y": p.y, "year": p.year, "year_end": p.year_end,
        "description": p.description, "person": p.person_id,
        "person_name": p.person.full_name if p.person_id else "",
    }


def route_json(r):
    return {
        "id": r.id, "name": r.name, "kind": r.kind, "color": r.color, "year_start": r.year_start,
        "year_end": r.year_end, "description": r.description, "stops": r.stops,
    }


@login_required
def map_detail_view(request, key):
    hmap = get_map(request, key)
    can_edit = can_edit_map(request.user, hmap)
    people = []
    tree = hmap.tree if hmap.tree_id and can_view_tree(request.user, hmap.tree) else None
    if tree:
        _, found, _ = compute_levels(tree.root_person)
        people = sorted(({"id": p.id, "name": p.full_name, "years": p.display_year or ""} for p in found.values()),
                        key=lambda x: x["name"])
    data = {
        "map": {"key": hmap.public_id, "title": hmap.title, "width": hmap.image_width, "height": hmap.image_height,
                "image": reverse("map_image", args=[hmap.public_id])},
        "places": [place_json(p) for p in hmap.places.select_related("person")],
        "routes": [route_json(r) for r in hmap.routes.all()],
        "kinds": PLACE_KIND_CHOICES, "routeKinds": ROUTE_KIND_CHOICES,
        "people": people, "canEdit": can_edit,
        "api": {
            "place": reverse("map_place_save", args=[hmap.public_id]),
            "route": reverse("map_route_save", args=[hmap.public_id]),
        },
    }
    response = render(request, "shajara/map_detail.html", {
        "hmap": hmap, "can_edit": can_edit, "map_data": data, "linked_tree": tree,
    })
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def map_image_view(request, key):
    hmap = get_map(request, key)
    try:
        handle = hmap.image.open("rb")
    except (FileNotFoundError, ValueError, OSError):
        raise Http404
    ctype = "image/png" if hmap.image.name.lower().endswith(".png") else "image/jpeg"
    response = FileResponse(handle, content_type=ctype)
    response["Cache-Control"] = "private, max-age=3600"
    return response


# -------------------------------------------------------------------- API --

def _json_body(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _year(value, field):
    if value in (None, ""):
        return None
    try:
        year = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field}: yil butun son bo'lsin (miloddan avvalgisi manfiy, masalan -329).")
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"{field}: yil {MIN_YEAR}…{MAX_YEAR} oralig'ida bo'lsin.")
    return year


def _text(value, limit):
    return str(value or "").strip()[:limit]


def _editable_map(request, key):
    hmap = get_object_or_404(HistoricalMap, public_id=key)
    if not can_edit_map(request.user, hmap):
        return None
    return hmap


@require_POST
@login_required
def map_place_save_view(request, key):
    """Create (no id), update (id) or delete ({"id": .., "delete": true}) a place."""
    hmap = _editable_map(request, key)
    if not hmap:
        return JsonResponse({"error": "Faqat xarita egasi tahrirlay oladi."}, status=403)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Noto'g'ri so'rov."}, status=400)

    place = None
    if data.get("id"):
        place = get_object_or_404(MapPlace, pk=data["id"], map=hmap)
        if data.get("delete"):
            pid = place.id
            place.delete()
            # the routes that went through it skip it now
            for route in hmap.routes.all():
                kept = [s for s in route.stops if s.get("place") != pid]
                if kept != route.stops:
                    route.stops = kept
                    route.save(update_fields=["stops"])
            return JsonResponse({"ok": True, "deleted": pid, "routes": [route_json(r) for r in hmap.routes.all()]})

    try:
        name = _text(data.get("name"), 120) or (place.name if place else "")
        if not name:
            raise ValueError("Joy nomini yozing.")
        kind = data.get("kind") or (place.kind if place else "shahar")
        if kind not in PLACE_KINDS:
            raise ValueError("Noma'lum joy turi.")
        x, y = float(data.get("x", place.x if place else -1)), float(data.get("y", place.y if place else -1))
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError("Joy xarita ichida bo'lishi kerak.")
        year = _year(data.get("year"), "Yil") if "year" in data or not place else place.year
        year_end = _year(data.get("year_end"), "Tugagan yil") if "year_end" in data or not place else place.year_end
        if year is not None and year_end is not None and year_end < year:
            raise ValueError("Tugagan yil boshlangan yildan oldin bo'lmasin.")
    except (TypeError, ValueError) as e:
        return JsonResponse({"error": str(e)}, status=400)

    person = place.person if place else None
    if "person" in data:
        person = None
        if data["person"]:
            tree = hmap.tree
            if not tree or int(data["person"]) not in compute_levels(tree.root_person)[0]:
                return JsonResponse({"error": "Shaxs bog'langan shajarada topilmadi."}, status=400)
            person = Person.objects.get(pk=int(data["person"]))

    place = place or MapPlace(map=hmap)
    place.name, place.kind, place.x, place.y = name, kind, x, y
    place.year, place.year_end, place.person = year, year_end, person
    if "description" in data or not place.pk:
        place.description = _text(data.get("description"), 4000)
    place.save()
    hmap.save(update_fields=["updated_at"])
    return JsonResponse({"ok": True, "place": place_json(place)})


@require_POST
@login_required
def map_route_save_view(request, key):
    hmap = _editable_map(request, key)
    if not hmap:
        return JsonResponse({"error": "Faqat xarita egasi tahrirlay oladi."}, status=403)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Noto'g'ri so'rov."}, status=400)

    route = None
    if data.get("id"):
        route = get_object_or_404(MapRoute, pk=data["id"], map=hmap)
        if data.get("delete"):
            rid = route.id
            route.delete()
            return JsonResponse({"ok": True, "deleted": rid})
    try:
        name = _text(data.get("name"), 150) or (route.name if route else "")
        if not name:
            raise ValueError("Yo'nalish nomini yozing.")
        kind = data.get("kind") or (route.kind if route else "harbiy")
        if kind not in ROUTE_KINDS:
            raise ValueError("Noma'lum yo'nalish turi.")
        color = data.get("color") or (route.color if route else "#b3261e")
        if not HEX.match(color):
            raise ValueError("Rang #RRGGBB ko'rinishida bo'lsin.")
        valid_ids = set(hmap.places.values_list("id", flat=True))
        stops = route.stops if route else []
        if "stops" in data:
            if not isinstance(data["stops"], list) or len(data["stops"]) > 200:
                raise ValueError("Bekatlar ro'yxati noto'g'ri.")
            stops = []
            for stop in data["stops"]:
                pid = int(stop.get("place")) if isinstance(stop, dict) else int(stop)
                if pid not in valid_ids:
                    raise ValueError("Bekat bu xaritadagi joy emas.")
                stops.append({"place": pid, "year": _year(stop.get("year") if isinstance(stop, dict) else None, "Bekat yili")})
        year_start = _year(data.get("year_start"), "Boshlangan yil") if "year_start" in data or not route else route.year_start
        year_end = _year(data.get("year_end"), "Tugagan yil") if "year_end" in data or not route else route.year_end
    except (TypeError, ValueError) as e:
        return JsonResponse({"error": str(e)}, status=400)

    route = route or MapRoute(map=hmap)
    route.name, route.kind, route.color, route.stops = name, kind, color, stops
    route.year_start, route.year_end = year_start, year_end
    if "description" in data or not route.pk:
        route.description = _text(data.get("description"), 4000)
    route.save()
    hmap.save(update_fields=["updated_at"])
    return JsonResponse({"ok": True, "route": route_json(route)})
