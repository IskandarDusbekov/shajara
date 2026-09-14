import json
import math

from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from .activity import log_activity
from .emails import send_otp_email
from .forms import (
    AcceptRequestForm, CommentForm, ConnectionRequestForm, EmailForm, LoginForm,
    OTPForm, PasswordResetRequestForm, PersonForm, RegionForm, RegisterForm, SetNewPasswordForm,
    StoryForm, TreeCreateForm, TreeImportForm, TreeSettingsForm,
)
from .models import (
    ConnectionRequest, EmailOTP, Family, Person, QuizAttempt, Tree, TreeGratitude, TreeMember, UserProfile,
)
from .tree import (
    attach_existing, can_delete_in_tree, can_edit_in_tree, can_edit_tree, can_view_tree, compute_levels,
    tree_role,
    export_tree_json, get_or_create_child_family, get_or_create_spouse_family,
    group_people_by_level, import_tree_json, level_label, person_ids_in_tree,
    sibling_groups,
)

User = get_user_model()

RELATION_TITLES = {
    "ota": "Otasini qo'shish",
    "ona": "Onasini qo'shish",
    "farzand": "Farzand qo'shish",
    "akauka": "Aka/uka, opa/singil qo'shish",
    "turmush": "Turmush o'rtog'ini qo'shish",
}


# ---------------------------------------------------------------- helpers --

def get_viewable_tree(request, tree_key):
    tree = get_object_or_404(Tree, public_id=tree_key)
    if not can_view_tree(request.user, tree):
        return None
    return tree


def note_staff_view(request, tree):
    """Staff can open private trees to review data; each such look is logged."""
    if tree.owner_id != request.user.id and not tree.is_public and request.user.is_staff:
        log_activity(request, "admin_view_private", tree=tree, detail=request.path[:300])


def get_editable_tree(request, tree_key):
    """The tree, if the user may build it: the owner or an editor member."""
    tree = get_object_or_404(Tree, public_id=tree_key)
    if not can_edit_tree(request.user, tree):
        return None
    return tree


def get_owned_tree(request, tree_key):
    """The tree, if the user owns it — settings, deleting, sharing, backups."""
    tree = get_object_or_404(Tree, public_id=tree_key)
    if tree.owner_id != request.user.id:
        return None
    return tree


def safe_next(request):
    """A same-site address to return to after signing in or up (e.g. an invite)."""
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()},
                                                   require_https=request.is_secure()):
        return target
    return ""


def private_response(response):
    """A tree page may hold family data, so keep it out of every shared cache
    (proxies, CDNs, the browser's back/forward store)."""
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response["Pragma"] = "no-cache"
    return response


def families_json_for(families):
    return [
        {
            "id": f.id, "father_id": f.father_id, "mother_id": f.mother_id,
            "child_ids": [c.id for c in f.children.all()],
        }
        for f in families.values()
    ]


# ------------------------------------------------------------------- auth --

def landing_view(request):
    if request.user.is_authenticated:
        return redirect("my_trees")
    public_qs = Tree.objects.filter(visibility="public")
    ranked = (
        public_qs.select_related("root_person")
        .annotate(num_gratitude=Count("gratitudes", distinct=True))
        .order_by("-num_gratitude", "-created_at")
    )
    return render(request, "shajara/landing.html", {
        "public_count": public_qs.count(),
        "learning_count": public_qs.filter(kind="talimiy").count(),
        "people_count": Person.objects.count(),
        "family_count": Tree.objects.filter(kind="oilaviy").count(),
        "featured_learning": ranked.filter(kind="talimiy")[:4],
    })


def register_view(request):
    if request.user.is_authenticated:
        return redirect("my_trees")
    initial_role = request.GET.get("rol", "")
    form = RegisterForm(request.POST or None, initial={"role": initial_role})
    next_url = safe_next(request)
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        user = User(
            username=cd["username"], first_name=cd["first_name"],
            last_name=cd["last_name"], email=cd.get("email", ""),
        )
        user.set_password(cd["password1"])
        user.save()
        UserProfile.objects.create(user=user, region=cd.get("region", ""), role=cd.get("role", ""))
        log_activity(request, "register", user=user,
                     detail=f"{user.get_full_name()} ({user.email or 'emailsiz'}){' · ' + cd['role'] if cd.get('role') else ''}")
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        if user.email:
            # Confirm the address straight away, while the person is still here;
            # the page that follows lets them skip it and come back later.
            otp = EmailOTP.issue(user, user.email, "verify")
            if send_otp_email(otp):
                messages.success(request, f"Tasdiqlash kodi {user.email} manziliga yuborildi.")
            else:
                messages.error(request, "Kodni yuborib bo'lmadi. Keyinroq profilingizdan qayta urinib ko'ring.")
            request.session["after_verify"] = next_url or ""
            return redirect("email_verify")
        return redirect(next_url or "my_trees")
    return render(request, "shajara/register.html", {"form": form, "next": next_url})


# ------------------------------------------------- email verification (OTP) --

def _get_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


@login_required
@require_POST
def tour_done_view(request):
    """The first-run guide was finished or dismissed — don't start it again."""
    UserProfile.objects.update_or_create(user=request.user, defaults={"tour_done": True})
    return JsonResponse({"ok": True})


@login_required
def email_setup_view(request):
    """Set/change email and send a 6-digit verification code."""
    profile = _get_profile(request.user)
    if profile.email_verified:
        messages.info(request, "Emailingiz allaqachon tasdiqlangan.")
        return redirect("profile")

    form = EmailForm(request.POST or None, user=request.user, initial={"email": request.user.email})
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"]
        request.user.email = email
        request.user.save(update_fields=["email"])
        otp = EmailOTP.issue(request.user, email, "verify")
        sent = send_otp_email(otp)
        if sent:
            messages.success(request, f"Tasdiqlash kodi {email} manziliga yuborildi.")
        else:
            messages.error(request, "Kodni yuborishda xatolik. Keyinroq urinib ko'ring.")
        return redirect("email_verify")
    return render(request, "shajara/email_setup.html", {"form": form})


@login_required
def email_verify_view(request):
    profile = _get_profile(request.user)
    if profile.email_verified:
        return redirect("profile")

    otp = EmailOTP.objects.filter(user=request.user, purpose="verify", consumed=False).first()
    if not otp:
        return redirect("email_setup")

    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        result = _check_otp(otp, form.cleaned_data["code"])
        if result == "ok":
            profile.email_verified = True
            profile.save(update_fields=["email_verified"])
            log_activity(request, "email_verified", detail=otp.email)
            messages.success(request, "Email muvaffaqiyatli tasdiqlandi! Endi parolni tiklash mumkin.")
            after = request.session.pop("after_verify", None)
            if after is not None:
                return redirect(after or "my_trees")
            return redirect("profile")
        messages.error(request, result)
        if "muddati" in result or "urinish" in result:
            return redirect("email_setup")
    return render(request, "shajara/otp_verify.html", {
        "form": form, "otp": otp, "title": "Emailni tasdiqlash",
        "subtitle": f"{otp.email} manziliga yuborilgan 6 xonali kodni kiriting.",
        "resend_url": "email_setup",
        "skip_url": request.session.get("after_verify") or reverse("my_trees"),
    })


def _check_otp(otp, code):
    """Validate a submitted code against an OTP row. Returns 'ok' or an error message."""
    if otp.consumed:
        return "Bu kod allaqachon ishlatilgan."
    if otp.is_expired:
        otp.consumed = True
        otp.save(update_fields=["consumed"])
        return "Kod muddati tugagan. Yangi kod so'rang."
    if otp.attempts >= 3:
        otp.consumed = True
        otp.save(update_fields=["consumed"])
        return "Urinishlar soni tugadi. Yangi kod so'rang."
    if otp.code != code:
        otp.attempts += 1
        otp.save(update_fields=["attempts"])
        left = otp.attempts_left
        if left <= 0:
            otp.consumed = True
            otp.save(update_fields=["consumed"])
            return "Kod noto'g'ri. Urinishlar tugadi, yangi kod so'rang."
        return f"Kod noto'g'ri. {left} ta urinish qoldi."
    otp.consumed = True
    otp.save(update_fields=["consumed"])
    return "ok"


class ShajaraLoginView(LoginView):
    template_name = "shajara/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


# ------------------------------------------------ password reset (OTP) --

def password_reset_request_view(request):
    """Step 1: user types username or email; we send an OTP to their verified email."""
    if request.user.is_authenticated:
        return redirect("my_trees")
    form = PasswordResetRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login_val = form.cleaned_data["login"].strip()
        user = User.objects.filter(Q(username__iexact=login_val) | Q(email__iexact=login_val)).first()
        profile = getattr(user, "profile", None) if user else None
        # Always behave the same to avoid leaking which accounts exist.
        if user and user.email and profile and profile.email_verified:
            otp = EmailOTP.issue(user, user.email, "reset")
            send_otp_email(otp)
            request.session["reset_user_id"] = user.id
        request.session["reset_email_hint"] = _mask_email(user.email) if user and user.email else ""
        messages.info(
            request,
            "Agar bunday tasdiqlangan email mavjud bo'lsa, unga tiklash kodi yuborildi.",
        )
        return redirect("password_reset_verify")
    return render(request, "shajara/password_reset_request.html", {"form": form})


def password_reset_verify_view(request):
    if request.user.is_authenticated:
        return redirect("my_trees")
    user_id = request.session.get("reset_user_id")
    otp = None
    if user_id:
        otp = EmailOTP.objects.filter(user_id=user_id, purpose="reset", consumed=False).first()

    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if not otp:
            messages.error(request, "Kod topilmadi yoki muddati tugagan. Qaytadan boshlang.")
            return redirect("password_reset")
        result = _check_otp(otp, form.cleaned_data["code"])
        if result == "ok":
            request.session["reset_verified_user_id"] = otp.user_id
            request.session.pop("reset_user_id", None)
            return redirect("password_reset_new")
        messages.error(request, result)
        if "muddati" in result or "urinish" in result:
            return redirect("password_reset")
    return render(request, "shajara/otp_verify.html", {
        "form": form, "otp": otp,
        "title": "Parolni tiklash",
        "subtitle": "Emailingizga yuborilgan 6 xonali kodni kiriting.",
        "email_hint": request.session.get("reset_email_hint", ""),
        "resend_url": "password_reset",
    })


def password_reset_new_view(request):
    if request.user.is_authenticated:
        return redirect("my_trees")
    user_id = request.session.get("reset_verified_user_id")
    user = User.objects.filter(pk=user_id).first() if user_id else None
    if not user:
        messages.error(request, "Avval kodni tasdiqlang.")
        return redirect("password_reset")

    form = SetNewPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["password1"])
        user.save(update_fields=["password"])
        log_activity(request, "password_reset", user=user)
        request.session.pop("reset_verified_user_id", None)
        request.session.pop("reset_email_hint", None)
        messages.success(request, "Parol yangilandi! Endi yangi parol bilan kiring.")
        return redirect("login")
    return render(request, "shajara/password_reset_new.html", {"form": form})


def _mask_email(email):
    if not email or "@" not in email:
        return email
    name, domain = email.split("@", 1)
    if len(name) <= 2:
        masked = name[0] + "*"
    else:
        masked = name[0] + "*" * (len(name) - 2) + name[-1]
    return f"{masked}@{domain}"


# --------------------------------------------------------------- my trees --

@login_required
def my_trees_view(request):
    """Start page: the trees you own and the ones relatives, teachers or
    classmates let you into, with hints that fit who you said you are."""
    kind = request.GET.get("tur", "")
    owned = (
        Tree.objects.filter(owner=request.user).select_related("root_person")
        .annotate(num_members=Count("members", distinct=True)).order_by("-created_at")
    )
    shared = (
        Tree.objects.filter(members__user=request.user).select_related("root_person", "owner")
        .annotate(num_members=Count("members", distinct=True)).order_by("-created_at")
    )
    roles = dict(TreeMember.objects.filter(user=request.user).values_list("tree_id", "role"))
    if kind in ("oilaviy", "talimiy"):
        owned, shared = owned.filter(kind=kind), shared.filter(kind=kind)
    shared = list(shared)
    for t in shared:
        t.my_role = roles.get(t.id)
    profile = _get_profile(request.user)
    return render(request, "shajara/my_trees.html", {
        "trees": owned, "shared_trees": shared, "kind": kind, "profile": profile,
        "has_any": Tree.objects.filter(owner=request.user).exists() or bool(roles),
    })


@login_required
def tree_create_view(request):
    kind = request.GET.get("tur")
    if kind not in ("oilaviy", "talimiy"):
        kind = "talimiy" if _get_profile(request.user).is_learner else "oilaviy"
    form = TreeCreateForm(request.POST or None, initial={"kind": kind})
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        learning = cd["kind"] == "talimiy"
        person = Person.objects.create(
            first_name=cd["first_name"], last_name=cd["last_name"],
            gender=cd["gender"], added_by=request.user,
        )
        tree = Tree.objects.create(
            owner=request.user, root_person=person, kind=cd["kind"],
            name=cd["tree_name"], description=cd["description"], visibility=cd["visibility"],
            subject=cd["subject"] if learning else "", era=cd["era"] if learning else "",
        )
        log_activity(request, "tree_create", tree=tree, person=person, detail=tree.name)
        return redirect("index", tree_key=tree.url_key)
    return render(request, "shajara/tree_create.html", {
        "form": form, "kind": form.data.get("kind", kind) if form.is_bound else kind,
    })


@login_required
def tree_import_create_view(request):
    form = TreeImportForm(request.POST or None, request.FILES or None)
    error = None
    if request.method == "POST" and form.is_valid():
        upload = form.cleaned_data["backup_file"]
        try:
            data = json.loads(upload.read().decode("utf-8"))
            if "people" not in data or "root_key" not in data:
                raise ValueError("Fayl formati noto'g'ri.")
            with transaction.atomic():
                root_person = import_tree_json(request.user, data)
                if not root_person:
                    raise ValueError("Fayldagi bosh odam topilmadi.")
                tree = Tree.objects.create(
                    owner=request.user, root_person=root_person, kind=form.cleaned_data["kind"],
                    name=form.cleaned_data["tree_name"], visibility=form.cleaned_data["visibility"],
                )
            log_activity(request, "tree_import", tree=tree,
                         detail=f"{tree.name}: {len(data.get('people', []))} ta shaxs")
            return redirect("index", tree_key=tree.url_key)
        except (ValueError, KeyError, UnicodeDecodeError) as e:
            error = f"Fayl o'qib bo'lmadi: {e}"

    return render(request, "shajara/tree_import.html", {"form": form, "error": error})


@login_required
def tree_settings_view(request, tree_key):
    tree = get_owned_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Sizda bu shajara sozlamalarini o'zgartirish huquqi yo'q.")

    form = TreeSettingsForm(request.POST or None, instance=tree)
    if request.method == "POST" and form.is_valid():
        form.save()
        log_activity(request, "tree_update", tree=tree,
                     detail=f"{tree.name} ({tree.get_visibility_display()})")
        messages.success(request, "Shajara sozlamalari saqlandi.")
        return redirect("tree_overview", tree_key=tree.url_key)
    return render(request, "shajara/tree_settings.html", {"form": form, "tree": tree})


@require_POST
@login_required
def tree_delete_view(request, tree_key):
    tree = get_owned_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Sizda bu shajarani o'chirish huquqi yo'q.")
    name = tree.name
    log_activity(request, "tree_delete", detail=name)
    tree.delete()
    messages.success(request, f'"{name}" shajarasi o\'chirildi.')
    return redirect("my_trees")


@login_required
def tree_overview_view(request, tree_key):
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")

    gave_gratitude = TreeGratitude.objects.filter(tree=tree, user=request.user).exists()
    comment_qs = tree.comments.select_related("author").order_by("-created_at")
    paginator = Paginator(comment_qs, 8)
    page_obj = paginator.get_page(request.GET.get("page"))
    role = tree_role(request.user, tree)
    levels, _, _ = compute_levels(tree.root_person)
    best = (
        QuizAttempt.objects.filter(tree=tree, user=request.user).order_by("-score", "-created_at").first()
    )
    return private_response(render(request, "shajara/tree_overview.html", {
        "tree": tree, "is_owner": role == "owner", "role": role,
        "can_edit": role in ("owner", "muharrir"),
        "people_count": len(levels),
        "generations": (max(levels.values()) - min(levels.values()) + 1) if levels else 0,
        "members": tree.members.select_related("user"),
        "best_attempt": best,
        "gave_gratitude": gave_gratitude,
        "comments": page_obj,
        "page_obj": page_obj,
        "comment_form": CommentForm(),
    }))


@require_POST
@login_required
def toggle_gratitude_view(request, tree_key):
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    obj, created = TreeGratitude.objects.get_or_create(tree=tree, user=request.user)
    if not created:
        obj.delete()
    else:
        log_activity(request, "gratitude", tree=tree, detail=tree.name)
    return redirect("tree_overview", tree_key=tree.url_key)


@require_POST
@login_required
def add_comment_view(request, tree_key):
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    form = CommentForm(request.POST)
    if form.is_valid():
        tree.comments.create(author=request.user, text=form.cleaned_data["text"])
        log_activity(request, "comment_add", tree=tree, detail=form.cleaned_data["text"][:120])
    return redirect("tree_overview", tree_key=tree.url_key)


@login_required
def public_trees_view(request):
    """The library: public learning trees first, family trees on their own tab."""
    kind = request.GET.get("tur", "talimiy")
    if kind not in ("oilaviy", "talimiy"):
        kind = "talimiy"
    q = (request.GET.get("q") or "").strip()
    base = Tree.objects.filter(visibility="public")
    trees = base.filter(kind=kind).select_related("root_person", "owner")
    if q:
        trees = trees.filter(
            Q(name__icontains=q) | Q(subject__icontains=q) | Q(era__icontains=q)
            | Q(description__icontains=q) | Q(root_person__first_name__icontains=q)
        )
    trees = (
        trees.annotate(num_gratitude=Count("gratitudes", distinct=True), num_comments=Count("comments", distinct=True))
        .order_by("-num_gratitude", "-num_comments", "-created_at")
    )
    return render(request, "shajara/public_trees.html", {
        "trees": trees, "kind": kind, "q": q,
        "learning_total": base.filter(kind="talimiy").count(),
        "family_total": base.filter(kind="oilaviy").count(),
    })


@login_required
def profile_view(request):
    trees = Tree.objects.filter(owner=request.user)
    profile = _get_profile(request.user)
    region_form = RegionForm(request.POST or None, initial={"region": profile.region, "role": profile.role})
    if request.method == "POST" and region_form.is_valid():
        profile.region = region_form.cleaned_data["region"]
        profile.role = region_form.cleaned_data["role"]
        profile.save(update_fields=["region", "role"])
        messages.success(request, "Profilingiz saqlandi.")
        return redirect("profile")
    return render(request, "shajara/profile.html", {
        "region_form": region_form, "profile_region": profile.get_region_display() if profile.region else "",
        "trees_count": trees.count(),
        "shared_count": request.user.tree_memberships.count(),
        "profile": profile,
        "public_count": trees.filter(visibility="public").count(),
        "stories_count": request.user.stories_written.count(),
        "sent_count": request.user.sent_requests.count(),
        "accepted_count": request.user.sent_requests.filter(status="accepted").count(),
    })


# ------------------------------------------------------------------- tree --

@login_required
def index_view(request, tree_key):
    """The tree map. Everyone who may see the tree gets the same board; only
    the owner also gets the add-a-relative shortcuts."""
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    note_staff_view(request, tree)

    root = tree.root_person
    levels, people, families = compute_levels(root)
    rows = group_people_by_level(people, levels)
    rows_list = [
        {"level": lvl, "label": level_label(lvl, root.full_name), "groups": sibling_groups(rows[lvl], families)}
        for lvl in sorted(rows.keys())
    ]

    return private_response(render(request, "shajara/tree.html", {
        "tree": tree, "root": root, "rows": rows_list,
        "families_json": families_json_for(families),
        "can_edit": can_edit_tree(request.user, tree),
        "saved_layout": tree.layout or {},
    }))


MAX_LAYOUT_CARDS = 5000


@login_required
@require_POST
def tree_layout_view(request, tree_key):
    """Saves (or, with an empty set, clears) the card arrangement the owner
    made on the map. Only people who belong to the tree are kept."""
    tree = get_editable_tree(request, tree_key)
    if not tree:
        return JsonResponse({"ok": False, "error": "Faqat shajara egasi tartibni saqlay oladi."}, status=403)
    try:
        raw = json.loads(request.body.decode("utf-8") or "{}").get("positions")
    except (ValueError, AttributeError, UnicodeDecodeError):
        raw = None
    if not isinstance(raw, dict) or len(raw) > MAX_LAYOUT_CARDS:
        return JsonResponse({"ok": False, "error": "Noto'g'ri ma'lumot."}, status=400)

    def number(n):
        return isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and abs(n) < 1e6

    members = person_ids_in_tree(tree.root_person) if raw else set()
    clean = {}
    for key, value in raw.items():
        if not (isinstance(key, str) and key.isdigit() and int(key) in members):
            continue
        if isinstance(value, list) and len(value) == 2 and all(number(n) for n in value):
            clean[key] = [round(value[0], 1), round(value[1], 1)]

    tree.layout = clean
    tree.save(update_fields=["layout"])
    log_activity(request, "tree_layout", tree=tree,
                 detail=f"{len(clean)} ta karta" if clean else "avtomatik tartibga qaytarildi")
    return JsonResponse({"ok": True, "saved": len(clean)})


def preview_redirect_view(request, tree_key):
    """The old "sof ko'rinish" address; that page is now the map itself."""
    return redirect("index", tree_key=tree_key, permanent=True)


def record_export(request, tree, kind, people_count=0, generations=0):
    """Write the check record a PDF or picture carries; returns it."""
    from .models import ExportRecord
    return ExportRecord.objects.create(
        tree=tree, tree_name=tree.name, tree_kind=tree.kind, root_name=tree.root_person.full_name,
        kind=kind, created_by=request.user, people_count=people_count, generations=generations,
        contributors=1 + tree.members.filter(role="muharrir").count(),
    )


@login_required
def tree_pdf_view(request, tree_key):
    """The tree as a printable book (see book.py). Anyone who can see the
    tree may take it home; each copy gets its own check code."""
    from .book import build_book

    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    note_staff_view(request, tree)

    levels, _, _ = compute_levels(tree.root_person)
    record = record_export(request, tree, "pdf", len(levels), len(set(levels.values())))
    contributors = [
        (m.user.get_full_name() or f"@{m.user.username}", "Muharrir")
        for m in tree.members.filter(role="muharrir").select_related("user")
    ]
    pdf, _ = build_book(
        tree, code=record.pretty_code,
        verify_url=request.build_absolute_uri(reverse("verify_export", args=[record.code])),
        tree_url=request.build_absolute_uri(reverse("tree_overview", args=[tree.url_key])),
        contributors=contributors, sources=tree.source_list,
    )
    response = HttpResponse(pdf, content_type="application/pdf")
    slug = slugify(tree.name) or "shajara"
    disposition = "inline" if request.GET.get("korish") else "attachment"
    response["Content-Disposition"] = f'{disposition}; filename="{slug}-kitob.pdf"'
    log_activity(request, "tree_export", tree=tree, detail=f"PDF kitob: {tree.name} ({record.pretty_code})")
    return private_response(response)


def verify_export_view(request, code):
    """Public check page behind the QR code on every book and picture."""
    from .models import ExportRecord
    record = ExportRecord.objects.select_related("created_by", "tree").filter(code=code.upper().replace("-", "")[-10:]).first()
    return render(request, "shajara/verify.html", {"record": record, "code": code}, status=200 if record else 404)


@login_required
def tree_export_view(request, tree_key):
    tree = get_owned_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Faqat shajara egasi JSON zaxira sifatida yuklab olishi mumkin.")

    data = export_tree_json(tree.root_person)
    data["tree_name"] = tree.name
    response = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json")
    slug = slugify(tree.name) or "shajara"
    response["Content-Disposition"] = f'attachment; filename="{slug}.json"'
    log_activity(request, "tree_export", tree=tree, detail=f"JSON: {tree.name}")
    return private_response(response)


@login_required
def person_detail_view(request, tree_key, pk):
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    person = get_object_or_404(Person, pk=pk)
    if pk not in person_ids_in_tree(tree.root_person):
        return HttpResponseForbidden("Bu shaxs bu shajaraga tegishli emas.")
    note_staff_view(request, tree)

    levels, _, _ = compute_levels(tree.root_person)
    father, mother = None, None
    if person.child_family_id:
        fam = person.child_family
        father, mother = fam.father, fam.mother

    marriages = []
    for fam, spouse in person.spouses():
        marriages.append({"family": fam, "spouse": spouse, "children": list(fam.children.all())})

    can_edit = can_edit_in_tree(request.user, tree, person)
    return private_response(render(request, "shajara/person_detail.html", {
        "tree": tree, "root": tree.root_person, "person": person,
        "person_level": level_label(levels.get(pk, 0), tree.root_person.full_name),
        "can_edit": can_edit,
        "can_delete": can_delete_in_tree(request.user, tree, person) and not person.rooted_trees.exists(),
        "father": father, "mother": mother,
        "marriages": marriages,
        "siblings": person.siblings(),
        "stories": person.stories.select_related("author"),
        "story_form": StoryForm(),
    }))


@require_POST
@login_required
def add_story_view(request, tree_key, pk):
    tree = get_viewable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    person = get_object_or_404(Person, pk=pk)
    if pk not in person_ids_in_tree(tree.root_person):
        return HttpResponseForbidden("Bu shaxs bu shajaraga tegishli emas.")
    form = StoryForm(request.POST)
    if form.is_valid():
        person.stories.create(author=request.user, text=form.cleaned_data["text"])
        log_activity(request, "story_add", tree=tree, person=person, detail=person.full_name)
    return redirect("person_detail", tree_key=tree.url_key, pk=pk)


@login_required
def person_edit_view(request, tree_key, pk):
    tree = get_editable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Sizda bu shaxsni tahrirlash huquqi yo'q.")
    person = get_object_or_404(Person, pk=pk)
    if not can_edit_in_tree(request.user, tree, person):
        return HttpResponseForbidden("Sizda bu shaxsni tahrirlash huquqi yo'q.")

    form = PersonForm(request.POST or None, request.FILES or None, instance=person)
    if request.method == "POST" and form.is_valid():
        form.save()
        changed = ", ".join(form.changed_data) or "o'zgarishsiz"
        log_activity(request, "person_edit", tree=tree, person=person, detail=f"{person.full_name}: {changed}")
        return redirect("person_detail", tree_key=tree.url_key, pk=pk)

    return render(request, "shajara/person_form.html", {
        "form": form, "form_title": "Tahrirlash", "ask_gender": True,
        "cancel_tree_key": tree.url_key, "cancel_pk": pk, "tree": tree, "subject_person": person,
    })


@require_POST
@login_required
def person_delete_view(request, tree_key, pk):
    tree = get_editable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Sizda bu shaxsni o'chirish huquqi yo'q.")
    person = get_object_or_404(Person, pk=pk)
    if not can_delete_in_tree(request.user, tree, person):
        return HttpResponseForbidden("Sizda bu shaxsni o'chirish huquqi yo'q.")
    rooted = person.rooted_trees.first()
    if rooted:
        messages.error(
            request,
            f"{person.full_name}ni o'chirib bo'lmaydi — bu shaxs \"{rooted.name}\" "
            "shajarasining bosh shaxsi.",
        )
        return redirect("person_detail", tree_key=tree.url_key, pk=pk)

    full_name = person.full_name
    related_family_ids = list(
        Family.objects.filter(Q(father=person) | Q(mother=person)).values_list("id", flat=True)
    )
    if person.child_family_id:
        related_family_ids.append(person.child_family_id)

    log_activity(request, "person_delete", tree=tree, detail=full_name)
    person.delete()

    for fid in related_family_ids:
        fam = Family.objects.filter(pk=fid).first()
        if fam and not fam.father_id and not fam.mother_id and not fam.children.exists():
            fam.delete()

    messages.success(request, f"{full_name} o'chirildi.")
    return redirect("index", tree_key=tree.url_key)


@login_required
def add_relative_view(request, tree_key):
    tree = get_editable_tree(request, tree_key)
    if not tree:
        return HttpResponseForbidden("Sizda bu shajaraga qarindosh qo'shish huquqi yo'q.")

    try:
        anchor_id = int(request.GET.get("anchor") or request.POST.get("anchor"))
    except (TypeError, ValueError):
        return HttpResponseForbidden("Noto'g'ri so'rov.")
    anchor = get_object_or_404(Person, pk=anchor_id)
    if not can_edit_in_tree(request.user, tree, anchor):
        return HttpResponseForbidden("Sizda bu joyga qarindosh qo'shish huquqi yo'q.")

    relation = request.GET.get("relation") or request.POST.get("relation")
    if relation not in RELATION_TITLES:
        return HttpResponseForbidden("Noto'g'ri so'rov.")

    family_raw = request.GET.get("family") or request.POST.get("family") or ""
    family_id = int(family_raw) if family_raw.isdigit() else None
    ask_gender = relation in ("farzand", "akauka", "turmush")

    form = PersonForm(request.POST or None, request.FILES or None)
    if not ask_gender:
        form.fields.pop("gender", None)

    error = None
    if request.method == "POST" and form.is_valid():
        new_person = form.save(commit=False)
        new_person.added_by = request.user

        if relation in ("ota", "ona"):
            new_person.gender = "erkak" if relation == "ota" else "ayol"
            fam = get_or_create_child_family(anchor)
            slot_taken = fam.father_id if relation == "ota" else fam.mother_id
            if slot_taken:
                error = "Bu joy allaqachon band."
            else:
                new_person.save()
                if relation == "ota":
                    fam.father = new_person
                else:
                    fam.mother = new_person
                fam.save()

        elif relation == "farzand":
            if family_id:
                fam = get_object_or_404(Family, pk=family_id)
                if fam.father_id != anchor.id and fam.mother_id != anchor.id:
                    return HttpResponseForbidden("Noto'g'ri so'rov.")
            else:
                fam = anchor.parent_families().first()
                if not fam:
                    fam = Family.objects.create()
                    if anchor.gender == "erkak":
                        fam.father = anchor
                    else:
                        fam.mother = anchor
                    fam.save()
            new_person.child_family = fam
            new_person.save()

        elif relation == "akauka":
            fam = get_or_create_child_family(anchor)
            new_person.child_family = fam
            new_person.save()

        elif relation == "turmush":
            fam = get_or_create_spouse_family(anchor)
            slot_taken = fam.mother_id if anchor.gender == "erkak" else fam.father_id
            if slot_taken:
                error = "Bu joy allaqachon band."
            else:
                new_person.save()
                if anchor.gender == "erkak":
                    fam.mother = new_person
                else:
                    fam.father = new_person
                fam.save()

        if not error:
            log_activity(
                request, "person_add", tree=tree, person=new_person,
                detail=f"{new_person.full_name} — {anchor.full_name}ning {RELATION_TITLES[relation].split()[0].lower()}",
            )
            return redirect("person_detail", tree_key=tree.url_key, pk=anchor.id)

    return render(request, "shajara/person_form.html", {
        "form": form, "form_title": RELATION_TITLES[relation], "ask_gender": ask_gender,
        "cancel_tree_key": tree.url_key, "cancel_pk": anchor.id,
        "error": error, "is_add": True, "tree_key": tree.url_key,
        "anchor_id": anchor.id, "relation": relation, "family_id": family_id,
        "tree": tree, "anchor": anchor,
    })


# --------------------------------------------------------------- linking --

@login_required
def search_users_view(request):
    q = (request.GET.get("q") or "").strip()
    results = []
    if q:
        results = list(
            User.objects.filter(username__icontains=q)
            .exclude(pk=request.user.pk)
            .order_by("username")[:20]
        )
    return render(request, "shajara/search.html", {"query": q, "results": results})


@login_required
def send_request_view(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect("search_users")

    form = ConnectionRequestForm(request.POST or None, owner=request.user)
    if request.method == "POST" and form.is_valid():
        tree = form.cleaned_data["tree"]
        if ConnectionRequest.objects.filter(
            from_tree=tree, to_user=target, status="pending"
        ).exists():
            messages.error(request, "Bu foydalanuvchiga shu shajara orqali so'rov allaqachon yuborilgan.")
            return redirect("search_users")
        ConnectionRequest.objects.create(
            from_user=request.user, from_tree=tree, to_user=target,
            message=form.cleaned_data["message"],
        )
        log_activity(request, "request_send", tree=tree, detail=f"{target.username}ga «{tree.name}» orqali")
        messages.success(request, f"{target.username}ga so'rov yuborildi.")
        return redirect("search_users")

    return render(request, "shajara/send_request.html", {"form": form, "target": target})


@login_required
def requests_view(request):
    my_requests = ConnectionRequest.objects.filter(to_user=request.user).select_related("from_user", "from_tree")
    return render(request, "shajara/requests.html", {"my_requests": my_requests})


@require_POST
@login_required
def decline_request_view(request, pk):
    req = get_object_or_404(ConnectionRequest, pk=pk, to_user=request.user, status="pending")
    req.status = "declined"
    req.responded_at = timezone.now()
    req.save()
    log_activity(request, "request_decline", detail=f"{req.from_user.username} so'rovi")
    return redirect("requests")


@login_required
def accept_request_view(request, pk):
    req = get_object_or_404(ConnectionRequest, pk=pk, to_user=request.user, status="pending")
    my_trees = list(Tree.objects.filter(owner=request.user))
    tree_ids_by_person = {}
    all_person_ids = set()
    for t in my_trees:
        for pid in person_ids_in_tree(t.root_person):
            tree_ids_by_person[pid] = t
            all_person_ids.add(pid)

    form = AcceptRequestForm(request.POST or None, tree_person_ids=all_person_ids)
    error = None
    if request.method == "POST" and form.is_valid():
        anchor = form.cleaned_data["anchor"]
        relation = form.cleaned_data["relation"]
        requester_root = req.from_tree.root_person if req.from_tree else None
        if not requester_root:
            error = "So'rov yuborgan shajara topilmadi."
        elif requester_root.id in all_person_ids:
            error = "Bu odamlar allaqachon bir shajarada."
        else:
            ok, err = attach_existing(requester_root, anchor, relation)
            if ok:
                req.status = "accepted"
                req.responded_at = timezone.now()
                req.save()
                anchor_tree = tree_ids_by_person.get(anchor.id)
                log_activity(request, "request_accept", tree=anchor_tree, person=anchor,
                             detail=f"{req.from_user.username}: «{req.from_tree.name}» → {anchor.full_name}")
                return redirect("person_detail", tree_key=anchor_tree.url_key, pk=requester_root.id)
            error = err

    return render(request, "shajara/accept_flow.html", {"req": req, "form": form, "error": error})
