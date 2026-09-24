"""The staff-only management panel (/boshqaruv/).

Non-staff get a plain 404, so the panel does not advertise itself.
"""

import json
import os
from collections import Counter, defaultdict
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .activity import log_activity
from .matching import FamilyGraph, run_matching
from .merge import MergeConflict, execute_merge, preview_merge
from .models import (
    ACTIVITY_CHOICES, ActivityLog, ConnectionRequest, Family, MatchCandidate, MatchRun,
    MergeRecord, Person, PersonStory, QuizAttempt, Tree, TreeComment, TreeMember, UserProfile,
)

User = get_user_model()
ACTION_LABELS = dict(ACTIVITY_CHOICES)


def staff_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff:
            raise Http404
        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        return response
    return wrapped


def _page(request, qs, per_page):
    return Paginator(qs, per_page).get_page(request.GET.get("page"))


def _querystring(request, drop=("page",)):
    params = request.GET.copy()
    for key in drop:
        params.pop(key, None)
    return params.urlencode()


def _daily_series(qs, field, days):
    """[{date, count, pct}] for the last `days` days, zero-filled."""
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = (qs.filter(**{f"{field}__date__gte": start})
            .annotate(day=TruncDate(field)).values("day").annotate(n=Count("id")))
    counts = {r["day"]: r["n"] for r in rows}
    series = [{"date": start + timedelta(days=i), "count": counts.get(start + timedelta(days=i), 0)}
              for i in range(days)]
    peak = max((s["count"] for s in series), default=0) or 1
    for s in series:
        s["pct"] = round(s["count"] / peak * 100)
    return series


def _component_sizes(graph):
    return Counter(graph.component.values())


# ------------------------------------------------------------ dashboard --

@staff_required
def dashboard(request):
    now = timezone.now()
    graph = FamilyGraph()
    sizes = _component_sizes(graph)
    in_trees = sum(sizes[c] for c in graph.trees_by_component)

    stats = {
        "users": User.objects.count(),
        "users_new_30": User.objects.filter(date_joined__gte=now - timedelta(days=30)).count(),
        "users_active_7": ActivityLog.objects.filter(created_at__gte=now - timedelta(days=7))
                          .exclude(user=None).values("user").distinct().count(),
        "trees": Tree.objects.count(),
        "trees_public": Tree.objects.filter(visibility="public").count(),
        "trees_learning": Tree.objects.filter(kind="talimiy").count(),
        "shared_members": TreeMember.objects.count(),
        "quiz_attempts": QuizAttempt.objects.count(),
        "persons": len(graph.people),
        "families": Family.objects.count(),
        "orphans": len(graph.people) - in_trees,
        "stories": PersonStory.objects.count(),
        "comments": TreeComment.objects.count(),
        "requests_pending": ConnectionRequest.objects.filter(status="pending").count(),
        "matches_pending": MatchCandidate.objects.filter(status="pending").count(),
        "matches_high": MatchCandidate.objects.filter(status="pending", score__gte=85).count(),
        "merges": MergeRecord.objects.count(),
    }

    top_actions = (ActivityLog.objects.filter(created_at__gte=now - timedelta(days=30))
                   .values("action").annotate(n=Count("id")).order_by("-n")[:8])
    peak = max((a["n"] for a in top_actions), default=0) or 1
    top_actions = [{"label": ACTION_LABELS.get(a["action"], a["action"]), "n": a["n"],
                    "pct": round(a["n"] / peak * 100)} for a in top_actions]

    top_users = (User.objects.annotate(tree_count=Count("trees", distinct=True),
                                       person_count=Count("added_people", distinct=True))
                 .filter(Q(tree_count__gt=0) | Q(person_count__gt=0))
                 .order_by("-person_count", "-tree_count")[:6])

    u = get_unified(AUTO_MERGE_SCORE)
    regions = region_insights.build(u, AUTO_MERGE_SCORE)
    stats["online"] = regions["totals"]["online"]
    stats["users_known_pct"] = regions["totals"]["users_known_pct"]
    region_rank = sorted((regions["rows"][n] for n in REGION_NAMES), key=lambda r: (-r["users"], -r["trees"], r["name"]))
    peak_users = max((r["users"] for r in region_rank), default=0) or 1
    for r in region_rank:
        r["pct"] = round(r["users"] / peak_users * 100)

    alerts = []
    if not settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"):
        alerts.append(("warn", "Email xatlar yuborilmayapti: server konsol rejimida (.env da EMAIL_HOST_USER yo'q).",
                       reverse("boshqaruv:system")))
    failed_mail = ActivityLog.objects.filter(action="email_failed", created_at__gte=now - timedelta(days=7)).count()
    if failed_mail:
        alerts.append(("bad", f"So'nggi 7 kunda {failed_mail} ta tasdiqlash/parol kodi yuborilmadi.",
                       f"{reverse('boshqaruv:activity')}?action=email_failed"))
    if not settings.DEBUG:
        from .models import SeoFile, SiteSetting
        cfg = SiteSetting.objects.filter(pk=1).first()
        has_google = bool(cfg and cfg.google_verification) or SeoFile.objects.filter(path__startswith="google", is_active=True).exists()
        if not has_google:
            alerts.append(("info", "Google Search Console tasdiqlash kodi kiritilmagan — sayt qidiruvda tezroq chiqishi uchun qo'shing.",
                           reverse("boshqaruv:seo_settings")))

    return render(request, "shajara/boshqaruv/dashboard.html", {
        "alerts": alerts,
        "section": "dashboard", "stats": stats, "region_rank": region_rank[:8], "region_totals": regions["totals"],
        "map_data": {"rows": regions["rows"], "links": regions["links"], "marriages": regions["marriages"],
                     "metric": "users", "compact": True,
                     "metrics": [{"key": k, "label": label} for k, label, _ in MAP_METRICS],
                     "live_url": reverse("boshqaruv:map_live"), "page_url": reverse("boshqaruv:map")},
        "signups": _daily_series(User.objects.all(), "date_joined", 30),
        "activity_days": _daily_series(ActivityLog.objects.all(), "created_at", 14),
        "top_actions": top_actions,
        "top_users": top_users,
        "recent": ActivityLog.objects.select_related("user", "tree")[:12],
        "last_run": MatchRun.objects.first(),
        "top_matches": MatchCandidate.objects.filter(status="pending")
                       .select_related("person_a", "person_b")[:5],
    })


# ---------------------------------------------------------------- users --

USER_SORTS = {
    "joined": "-date_joined", "login": "-last_login", "trees": "-tree_count",
    "persons": "-person_count", "activity": "-activity_count", "name": "username",
}


def _csv_cell(value):
    """Keep spreadsheet apps from running =formulas typed into a user's name."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def _users_csv(request, qs):
    import csv

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="foydalanuvchilar-{timezone.localdate():%Y%m%d}.csv"'
    response.write("﻿")
    writer = csv.writer(response)
    writer.writerow(["ID", "Login", "Ism", "Familya", "Email", "Email tasdiqlangan", "Viloyat", "Rol",
                     "Ro'yxatdan o'tgan", "Oxirgi kirish", "Shajaralar", "Shaxslar", "Faol", "Admin"])
    for u in qs.iterator():
        profile = getattr(u, "profile", None)
        writer.writerow([_csv_cell(x) for x in (
            u.pk, u.username, u.first_name, u.last_name, u.email,
            "ha" if profile and profile.email_verified else "yo'q",
            profile.region if profile else "", profile.role if profile else "",
            timezone.localtime(u.date_joined).strftime("%Y-%m-%d %H:%M"),
            timezone.localtime(u.last_login).strftime("%Y-%m-%d %H:%M") if u.last_login else "",
            u.tree_count, u.person_count, "ha" if u.is_active else "yo'q", "ha" if u.is_staff else "yo'q",
        )])
    log_activity(request, "admin_user_update", detail="Foydalanuvchilar CSV yuklab olindi")
    return response


@staff_required
def user_list(request):
    q = (request.GET.get("q") or "").strip()
    status = request.GET.get("status", "all")
    sort = request.GET.get("sort", "joined")

    qs = User.objects.select_related("profile").annotate(
        tree_count=Count("trees", distinct=True),
        person_count=Count("added_people", distinct=True),
        activity_count=Count("activity", distinct=True),
        last_seen=Max("activity__created_at"),
    )
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(first_name__icontains=q)
                       | Q(last_name__icontains=q) | Q(email__icontains=q))
    if status == "online":
        from .presence import online_since
        qs = qs.filter(profile__last_seen__gte=online_since())
    elif status == "active":
        qs = qs.filter(is_active=True)
    elif status == "blocked":
        qs = qs.filter(is_active=False)
    elif status == "staff":
        qs = qs.filter(is_staff=True)
    elif status == "verified":
        qs = qs.filter(profile__email_verified=True)
    elif status == "unverified":
        qs = qs.exclude(profile__email_verified=True)
    qs = qs.order_by(USER_SORTS.get(sort, "-date_joined"), "username")

    if request.GET.get("eksport") == "csv":
        return _users_csv(request, qs)

    return render(request, "shajara/boshqaruv/users.html", {
        "section": "users", "page": _page(request, qs, 25), "q": q, "status": status, "sort": sort,
        "qs": _querystring(request), "total": qs.count(),
    })


@staff_required
def user_detail(request, pk):
    member = get_object_or_404(User.objects.select_related("profile"), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if member == request.user:
            messages.error(request, "O'z hisobingizni bu yerdan o'zgartira olmaysiz.")
        elif member.is_superuser and not request.user.is_superuser:
            messages.error(request, "Superadmin hisobini faqat superadmin o'zgartira oladi.")
        elif action == "toggle_active":
            member.is_active = not member.is_active
            member.save(update_fields=["is_active"])
            state = "faollashtirildi" if member.is_active else "bloklandi"
            log_activity(request, "admin_user_update", detail=f"{member.username} {state}")
            messages.success(request, f"{member.username} {state}.")
        elif action == "toggle_staff" and request.user.is_superuser:
            member.is_staff = not member.is_staff
            member.save(update_fields=["is_staff"])
            state = "admin qilindi" if member.is_staff else "adminlikdan olindi"
            log_activity(request, "admin_user_update", detail=f"{member.username} {state}")
            messages.success(request, f"{member.username} {state}.")
        return redirect("boshqaruv:user_detail", pk=member.pk)

    graph = FamilyGraph()
    sizes = _component_sizes(graph)
    trees = list(member.trees.all().order_by("-created_at"))
    memberships = member.tree_memberships.select_related("tree", "tree__owner")
    for t in trees:
        t.people_count = sizes.get(graph.component.get(t.root_person_id), 0)

    activity = ActivityLog.objects.filter(user=member).select_related("tree")
    profile = UserProfile.objects.filter(user=member).first()
    return render(request, "shajara/boshqaruv/user_detail.html", {
        "section": "users", "member": member, "profile": profile, "trees": trees, "memberships": memberships,
        "counts": {
            "persons": Person.objects.filter(added_by=member).count(),
            "stories": PersonStory.objects.filter(author=member).count(),
            "comments": TreeComment.objects.filter(author=member).count(),
            "requests_sent": ConnectionRequest.objects.filter(from_user=member).count(),
            "requests_received": ConnectionRequest.objects.filter(to_user=member).count(),
            "logins": activity.filter(action="login").count(),
        },
        "page": _page(request, activity, 30),
        "ips": (activity.exclude(ip_address=None).values("ip_address")
                .annotate(n=Count("id"), last=Max("created_at")).order_by("-last")[:6]),
    })


# ---------------------------------------------------------------- trees --

@staff_required
def tree_list(request):
    q = (request.GET.get("q") or "").strip()
    visibility = request.GET.get("visibility", "all")
    kind = request.GET.get("kind", "all")
    sort = request.GET.get("sort", "created")

    qs = Tree.objects.select_related("owner", "root_person").annotate(
        gratitude_n=Count("gratitudes", distinct=True), comment_n=Count("comments", distinct=True),
        member_n=Count("members", distinct=True),
    )
    if kind in ("oilaviy", "talimiy"):
        qs = qs.filter(kind=kind)
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(owner__username__icontains=q)
                       | Q(root_person__first_name__icontains=q) | Q(root_person__last_name__icontains=q))
    if visibility in ("public", "private"):
        qs = qs.filter(visibility=visibility)

    graph = FamilyGraph()
    sizes = _component_sizes(graph)
    trees = list(qs)
    for t in trees:
        comp = graph.component.get(t.root_person_id)
        t.people_count = sizes.get(comp, 0)
        t.linked_count = len(graph.trees_by_component.get(comp, [])) - 1
    key = {
        "created": lambda t: t.created_at, "people": lambda t: t.people_count,
        "name": lambda t: t.name.lower(), "owner": lambda t: t.owner.username,
    }.get(sort, lambda t: t.created_at)
    trees.sort(key=key, reverse=sort in ("created", "people"))

    return render(request, "shajara/boshqaruv/trees.html", {
        "section": "trees", "page": _page(request, trees, 25), "q": q, "visibility": visibility, "kind": kind,
        "sort": sort, "qs": _querystring(request), "total": len(trees),
    })


@staff_required
def tree_detail(request, pk):
    tree = get_object_or_404(Tree.objects.select_related("owner", "root_person"), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_visibility":
            tree.visibility = "private" if tree.is_public else "public"
            tree.save(update_fields=["visibility"])
            log_activity(request, "admin_tree_update", tree=tree,
                         detail=f"{tree.name}: {tree.get_visibility_display()}")
            messages.success(request, f"«{tree.name}» endi {tree.get_visibility_display().lower()}.")
            return redirect("boshqaruv:tree_detail", pk=tree.pk)
        if action == "delete" and request.POST.get("confirm_name") == tree.name:
            name = tree.name
            log_activity(request, "admin_tree_delete", detail=f"{name} (egasi: {tree.owner.username})")
            tree.delete()
            messages.success(request, f"«{name}» shajarasi o'chirildi. Shaxslar ma'lumotlar bazasida qoldi.")
            return redirect("boshqaruv:trees")
        messages.error(request, "Amal bajarilmadi — o'chirish uchun shajara nomini aynan yozing.")
        return redirect("boshqaruv:tree_detail", pk=tree.pk)

    graph = FamilyGraph()
    comp = graph.component.get(tree.root_person_id)
    member_ids = [pid for pid, c in graph.component.items() if c == comp]
    people = sorted((graph.people[pid] for pid in member_ids), key=lambda p: (p.last_name, p.first_name))
    linked = [t for t in graph.trees_by_component.get(comp, []) if t.pk != tree.pk]
    stats = Counter(p.gender for p in people)

    return render(request, "shajara/boshqaruv/tree_detail.html", {
        "section": "trees", "tree": tree, "people": people[:300], "people_total": len(people),
        "members": tree.members.select_related("user"),
        "quiz_total": tree.quiz_attempts.count(),
        "linked": linked, "men": stats.get("erkak", 0), "women": stats.get("ayol", 0),
        "with_years": sum(1 for p in people if p.display_year),
        "with_place": sum(1 for p in people if p.birth_region or p.birth_district or p.location),
        "activity": ActivityLog.objects.filter(tree=tree).select_related("user")[:20],
        "matches": MatchCandidate.objects.filter(status="pending")
                   .filter(Q(person_a_id__in=member_ids) | Q(person_b_id__in=member_ids))
                   .select_related("person_a", "person_b")[:10],
    })


# ------------------------------------------------------------- matching --

@staff_required
def match_list(request):
    status = request.GET.get("status", "pending")
    try:
        min_score = max(0, min(100, int(request.GET.get("min", 45))))
    except ValueError:
        min_score = 45
    qs = MatchCandidate.objects.select_related("person_a", "person_b", "reviewed_by").filter(score__gte=min_score)
    if status in ("pending", "merged", "rejected"):
        qs = qs.filter(status=status)
    counts = dict(MatchCandidate.objects.values_list("status").annotate(n=Count("id")))
    return render(request, "shajara/boshqaruv/matches.html", {
        "section": "matches", "page": _page(request, qs, 20), "status": status, "min_score": min_score,
        "counts": counts, "qs": _querystring(request), "last_run": MatchRun.objects.first(),
    })


@staff_required
@require_POST
def match_run(request):
    run = run_matching(triggered_by=request.user)
    log_activity(request, "admin_match_run",
                 detail=f"{run.persons_scanned} shaxs, {run.pairs_compared} juftlik, {run.candidates_new} yangi")
    messages.success(
        request,
        f"Qidiruv tugadi: {run.persons_scanned} ta shaxs, {run.pairs_compared} ta juftlik solishtirildi, "
        f"{run.candidates_found} ta moslik ({run.candidates_new} ta yangi).",
    )
    return redirect("boshqaruv:matches")


def _person_card(graph, pid):
    """Everything the side-by-side comparison shows about one record."""
    p = graph.people.get(pid)
    if p is None:
        return None

    def names(ids):
        return [graph.people[i] for i in ids if i in graph.people]

    return {
        "p": p,
        "father": graph.people.get(graph.father.get(pid)),
        "mother": graph.people.get(graph.mother.get(pid)),
        "spouses": names(graph.spouses.get(pid, ())),
        "children": names(graph.children.get(pid, ())),
        "trees": graph.trees_of(pid),
        "filled": sum(1 for f in ("last_name", "patronymic", "birth_year", "birth_date", "death_year",
                                  "birth_region", "birth_district", "birth_village", "occupation", "location")
                      if getattr(p, f)),
    }


COMPARE_FIELDS = [
    ("full_name", "Ism familiya"), ("patronymic", "Otasining ismi (maydon)"), ("get_gender_display", "Jinsi"),
    ("display_year", "Tug'ilgan yili"), ("death_year", "Vafot etgan yili"), ("birth_region", "Viloyat"),
    ("birth_district", "Tuman"), ("birth_village", "Qishloq / mahalla"), ("location", "Yashash joyi"),
    ("occupation", "Kasbi"),
]


def _value(p, attr):
    v = getattr(p, attr)
    return v() if callable(v) else (v or "")


def _plan_summary(log):
    counts = Counter(step["kind"] for step in log)
    return [
        (label, counts[kind]) for kind, label in (
            ("person", "shaxs yozuvi birlashadi"), ("family", "oila o'zgarishi"),
            ("fill", "yozuvga ma'lumot to'ldiriladi"), ("differ", "farq qiluvchi qiymat (qolganniki saqlanadi)"),
            ("story", "hikoya ko'chirish"), ("tree", "shajara bosh shaxsi yangilanadi"),
        ) if counts[kind]
    ]


@staff_required
def match_detail(request, pk):
    cand = get_object_or_404(MatchCandidate.objects.select_related("reviewed_by"), pk=pk)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reject":
            cand.status, cand.note = "rejected", request.POST.get("note", "")[:1000]
            cand.reviewed_by, cand.reviewed_at = request.user, timezone.now()
            cand.save()
            log_activity(request, "admin_match_reject", detail=f"{cand.pair_key} ({cand.score}%)")
            messages.success(request, "Moslik rad etildi. Keyingi qidiruvlarda qayta taklif qilinmaydi.")
            return redirect("boshqaruv:matches")
        if action == "reopen" and cand.status == "rejected":
            cand.status, cand.reviewed_by, cand.reviewed_at = "pending", None, None
            cand.save()
            messages.success(request, "Moslik qayta ko'rib chiqishga qaytarildi.")
            return redirect("boshqaruv:match_detail", pk=cand.pk)
        if action == "merge" and cand.status == "pending":
            if request.POST.get("understood") != "1":
                messages.error(request, "Birlashtirishdan oldin ogohlantirishni o'qib, belgini qo'ying.")
                return redirect(f"{reverse('boshqaruv:match_detail', args=[cand.pk])}?keep={request.POST.get('keep', 'a')}")
            keep_side = request.POST.get("keep", "a")
            keep_id, drop_id = ((cand.person_a_id, cand.person_b_id) if keep_side == "a"
                                else (cand.person_b_id, cand.person_a_id))
            if not keep_id or not drop_id:
                messages.error(request, "Yozuvlardan biri endi mavjud emas.")
                return redirect("boshqaruv:matches")
            try:
                record = execute_merge(keep_id, drop_id, actor=request.user, candidate=cand)
            except MergeConflict as exc:
                messages.error(request, f"Birlashtirilmadi: {exc}")
                return redirect("boshqaruv:match_detail", pk=cand.pk)
            log_activity(request, "admin_merge", person=record.kept_person,
                         detail=f"{record.dropped_name} → {record.kept_name} ({record.persons_merged} ta yozuv)")
            messages.success(request, f"Birlashtirildi: {record.persons_merged} ta yozuv bitta oilaga jamlandi.")
            return redirect("boshqaruv:merge_detail", pk=record.pk)
        return redirect("boshqaruv:match_detail", pk=cand.pk)

    graph = FamilyGraph()
    a = _person_card(graph, cand.person_a_id) if cand.person_a_id else None
    b = _person_card(graph, cand.person_b_id) if cand.person_b_id else None

    rows = []
    if a and b:
        for attr, label in COMPARE_FIELDS:
            va, vb = _value(a["p"], attr), _value(b["p"], attr)
            state = "empty" if not va and not vb else "one" if not va or not vb else \
                "same" if str(va).strip().lower() == str(vb).strip().lower() else "diff"
            rows.append({"label": label, "a": va, "b": vb, "state": state})

    preview = None
    keep_side = request.GET.get("keep")
    if keep_side not in ("a", "b") and a and b:
        keep_side = "a" if a["filled"] >= b["filled"] else "b"
    if cand.status == "pending" and a and b:
        keep_id, drop_id = ((a["p"].id, b["p"].id) if keep_side == "a" else (b["p"].id, a["p"].id))
        log, merged, trees, error = preview_merge(keep_id, drop_id)
        owners = {t["owner"] for t in trees}
        preview = {
            "log": log, "merged": merged, "trees": trees, "error": error,
            "summary": _plan_summary(log),
            "cross_owner": len(owners) > 1,
            "has_private": any(t["visibility"] == "private" for t in trees),
        }

    for part in cand.breakdown:
        part["pct"] = round(part["points"] / part["weight"] * 100) if part.get("weight") else 0

    return render(request, "shajara/boshqaruv/match_detail.html", {
        "section": "matches", "cand": cand, "a": a, "b": b, "rows": rows,
        "keep": keep_side, "preview": preview,
    })


# --------------------------------------------------------------- merges --

@staff_required
def merge_list(request):
    qs = MergeRecord.objects.select_related("actor", "kept_person")
    return render(request, "shajara/boshqaruv/merges.html", {
        "section": "merges", "page": _page(request, qs, 25),
    })


@staff_required
def merge_detail(request, pk):
    record = get_object_or_404(MergeRecord.objects.select_related("actor", "kept_person", "candidate"), pk=pk)
    snap = record.snapshot or {}
    return render(request, "shajara/boshqaruv/merge_detail.html", {
        "section": "merges", "record": record, "summary": _plan_summary(record.log),
        "snap_people": len(snap.get("people", [])), "snap_families": len(snap.get("families", [])),
    })


@staff_required
def merge_snapshot(request, pk):
    record = get_object_or_404(MergeRecord, pk=pk)
    response = HttpResponse(json.dumps(record.snapshot, ensure_ascii=False, indent=2),
                            content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="birlashtirish-{record.pk}-oldingi-holat.json"'
    return response


# ------------------------------------------------------------- activity --

@staff_required
def activity_list(request):
    q = (request.GET.get("q") or "").strip()
    action = request.GET.get("action", "")
    period = request.GET.get("period", "30")
    qs = ActivityLog.objects.select_related("user", "tree", "person")
    if q:
        qs = qs.filter(Q(user__username__icontains=q) | Q(detail__icontains=q) | Q(ip_address__icontains=q))
    if action:
        qs = qs.filter(action=action)
    if period in ("1", "7", "30", "90"):
        qs = qs.filter(created_at__gte=timezone.now() - timedelta(days=int(period)))
    groups = defaultdict(list)
    for key, label in ACTIVITY_CHOICES:
        groups["Admin" if key.startswith("admin_") else "Foydalanuvchi"].append((key, label))
    return render(request, "shajara/boshqaruv/activity.html", {
        "section": "activity", "page": _page(request, qs, 50), "q": q, "action": action,
        "period": period, "action_groups": dict(groups), "qs": _querystring(request),
        "total": qs.count(),
    })


# ------------------------------------------------------ map & unified tree --

from .regions import ABROAD, REGION_NAMES  # noqa: E402
from .unified import AUTO_MERGE_SCORE, get_unified  # noqa: E402
from . import region_insights  # noqa: E402

THRESHOLDS = (55, 70, 85)
MAP_METRICS = [
    ("users", "Ro'yxatdan o'tganlar", "profilida shu viloyatni tanlagan foydalanuvchilar"),
    ("online", "Hozir onlayn", "so'nggi 5 daqiqada saytda bo'lganlar"),
    ("trees", "Shajaralar", "bosh shaxsi (yoki egasi) shu viloyatdan bo'lgan shajaralar"),
    ("trees_connected", "Bog'langan shajaralar", "boshqa shajara bilan bitta oila tarmog'iga ulanganlari"),
    ("people", "Shaxslar", "haqiqiy shaxslar — dublikatlar bitta sanaladi"),
]


def _threshold(request):
    try:
        value = int(request.GET.get("chegara", AUTO_MERGE_SCORE))
    except ValueError:
        value = AUTO_MERGE_SCORE
    return value if value in THRESHOLDS else AUTO_MERGE_SCORE


@staff_required
def region_map(request):
    min_score = _threshold(request)
    metric = request.GET.get("olchov", "users")
    if metric not in {m[0] for m in MAP_METRICS}:
        metric = "users"
    u = get_unified(min_score)
    data = region_insights.build(u, min_score)
    table = [data["rows"][name] for name in REGION_NAMES]
    table.sort(key=lambda r: (-r[metric], r["name"]))
    return render(request, "shajara/boshqaruv/xarita.html", {
        "section": "map", "metric": metric, "metrics": MAP_METRICS,
        "metric_label": dict((m[0], m[1]) for m in MAP_METRICS)[metric],
        "min_score": min_score, "thresholds": THRESHOLDS,
        "table": table, "abroad": data["rows"][ABROAD], "totals": data["totals"],
        "map_data": {
            "rows": data["rows"], "links": data["links"], "marriages": data["marriages"], "metric": metric,
            "metrics": [{"key": k, "label": label} for k, label, _ in MAP_METRICS],
            "live_url": reverse("boshqaruv:map_live"),
        },
    })


@staff_required
def region_map_live(request):
    """Online counts for the map and dashboard, polled every few seconds."""
    u = get_unified(AUTO_MERGE_SCORE)
    if not hasattr(u, "user_regions"):
        u.region_stats()
    return JsonResponse(region_insights.live_counts(u.user_regions))


@staff_required
def unified_overview(request):
    min_score = _threshold(request)
    region = request.GET.get("viloyat", "")
    if region not in REGION_NAMES + [ABROAD]:
        region = ""
    u = get_unified(min_score)
    all_networks = u.family_networks()
    networks = u.family_networks(region=region) if region else all_networks
    in_trees = sum(r["records"] for r in all_networks)
    people = sum(r["people"] for r in all_networks)
    biggest = all_networks[0] if all_networks else None
    for r in networks[:40]:
        r["pct"] = round(r["people"] / biggest["people"] * 100) if biggest else 0

    return render(request, "shajara/boshqaruv/umumiy.html", {
        "section": "unified", "min_score": min_score, "thresholds": THRESHOLDS, "region": region,
        "regions": REGION_NAMES + [ABROAD],
        "networks": networks[:40], "network_total": len(networks), "biggest": biggest,
        "stats": {
            "records": in_trees, "people": people, "duplicates": in_trees - people,
            "dup_pct": round((in_trees - people) / in_trees * 100, 1) if in_trees else 0,
            "networks": len(all_networks), "multi": sum(1 for r in all_networks if len(r["trees"]) > 1),
            "links": u.links_used, "structural": u.links_structural, "conflicts": len(u.conflicts),
            "orphans": u.record_count() - in_trees,
        },
    })


@staff_required
def unified_board(request, key):
    min_score = _threshold(request)
    u = get_unified(min_score)
    data = u.board(key)
    if data is None or not u.trees_by_component.get(key):
        raise Http404
    people = data["people"]
    for ind in people:
        ind.detail_url = f"{reverse('boshqaruv:unified_person', args=[ind.id])}?chegara={min_score}"
    regions = Counter(p.region or "Noma'lum" for p in people).most_common()
    peak = regions[0][1] if regions else 1
    years = sorted(int(p.display_year) for p in people if str(p.display_year).isdigit())
    return render(request, "shajara/boshqaruv/umumiy_board.html", {
        "section": "unified", "min_score": min_score, "key": key,
        "rows": data["rows"], "root": data["root"], "families_json": data["families_json"],
        "board_key": f"umumiy-{key}", "board_title": f"Umumiy shajara: {data['root'].full_name}",
        "a": {
            "people": len(people), "records": sum(p.merged_count for p in people),
            "merged_people": sum(1 for p in people if p.merged_count > 1), "generations": data["generations"],
            "trees": data["trees"], "owners": sorted({t.owner.username for t in data["trees"]}),
            "men": sum(1 for p in people if p.gender == "erkak"),
            "women": sum(1 for p in people if p.gender == "ayol"),
            "year_from": years[0] if years else None, "year_to": years[-1] if years else None,
            "with_year": len(years), "with_place": sum(1 for p in people if p.region),
            "regions": [(name, n, round(n / peak * 100)) for name, n in regions[:6]],
            "conflicts": sum(1 for p in people if p.id in u.conflicts),
        },
    })


@staff_required
def unified_person(request, pid):
    min_score = _threshold(request)
    u = get_unified(min_score)
    iid = u.of.get(pid)
    if iid is None:
        raise Http404
    ind = u.individuals[iid]
    member_ids = [m.id for m in ind.members]
    links = (MatchCandidate.objects.filter(person_a_id__in=member_ids, person_b_id__in=member_ids)
             .exclude(status="rejected"))
    records = [{"p": m, "trees": u.source.trees_of(m.id)} for m in ind.members]
    return render(request, "shajara/boshqaruv/umumiy_shaxs.html", {
        "section": "unified", "ind": ind, "records": records, "links": links,
        "key": u.component[iid], "min_score": min_score,
    })


# --------------------------------------------------------- open (SEO) pages --

from django import forms  # noqa: E402
from django.db.models import Sum  # noqa: E402

from . import public_views  # noqa: E402


class OpenPageForm(forms.ModelForm):
    class Meta:
        model = Tree
        fields = ["is_featured", "slug", "seo_description"]

    def clean_slug(self):
        raw = (self.cleaned_data.get("slug") or "").strip()
        slug = public_views.uz_slug(raw) if raw else ""
        if self.cleaned_data.get("is_featured") or self.data.get("is_featured"):
            slug = slug or public_views.uz_slug(self.instance.name)
        if slug and Tree.objects.filter(slug=slug).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bu manzil boshqa shajarada band.")
        return slug or None

    def clean(self):
        cd = super().clean()
        if cd.get("is_featured") and not self.instance.can_be_featured:
            raise forms.ValidationError("Faqat ommaviy ta'limiy shajara ochiq sahifaga chiqariladi.")
        return cd


@staff_required
def seo_pages(request):
    if request.method == "POST":
        tree = get_object_or_404(Tree, pk=request.POST.get("tree"))
        form = OpenPageForm(request.POST, instance=tree)
        if form.is_valid():
            was = tree.is_featured
            obj = form.save(commit=False)
            if obj.is_featured and not was:
                obj.featured_at = timezone.now()
            obj.save(update_fields=["is_featured", "slug", "seo_description", "featured_at"])
            state = "ochiq sahifada" if obj.is_featured else "yopiq"
            log_activity(request, "admin_seo_update", tree=obj, detail=f"{obj.name}: {state}, /{obj.slug or ''}")
            messages.success(request, f"«{obj.name}» saqlandi — {state}.")
        else:
            errors = "; ".join(e for errs in form.errors.values() for e in errs)
            messages.error(request, f"«{tree.name}» saqlanmadi: {errors}")
        return redirect(f"{reverse('boshqaruv:seo')}#t{tree.pk}")

    candidates = list(Tree.objects.filter(visibility="public", kind="talimiy")
                      .select_related("owner", "root_person").order_by("-is_featured", "-public_views", "name"))
    for t in candidates:
        t.stats = public_views.tree_stats(t)
        t.form = OpenPageForm(instance=t, prefix=None)
        t.desc_len = len(t.seo_description or "")
    featured = [t for t in candidates if t.is_open_page]
    base = public_views.site_url(request)
    return render(request, "shajara/boshqaruv/seo.html", {
        "section": "seo", "candidates": candidates, "featured": featured, "base": base,
        "totals": {
            "featured": len(featured),
            "views": Tree.objects.aggregate(n=Sum("public_views"))["n"] or 0,
            "urls": public_views.sitemap_count(request),
            "people": sum(t.stats["people"] for t in featured),
            "family_public": Tree.objects.filter(visibility="public", kind="oilaviy").count(),
        },
        "site_url_set": bool(getattr(settings, "SITE_URL", "")),
        "debug": settings.DEBUG,
    })


# ------------------------------------------------------- site SEO settings --

import re as _re  # noqa: E402

from django.core.mail import EmailMultiAlternatives  # noqa: E402

from . import seo as seo_tools  # noqa: E402
from .models import PAGE_SEO_KEYS, SEO_FILE_RESERVED, PageSeo, SeoFile, SiteSetting  # noqa: E402


class SiteSettingForm(forms.ModelForm):
    class Meta:
        model = SiteSetting
        fields = [
            "site_name", "default_description", "default_og_image",
            "google_verification", "bing_verification", "yandex_verification",
            "ga_measurement_id", "yandex_metrica_id",
            "extra_head_html", "block_indexing", "robots_txt", "sitemap_extra",
        ]
        widgets = {
            "default_description": forms.Textarea(attrs={"rows": 2}),
            "extra_head_html": forms.Textarea(attrs={"rows": 4, "spellcheck": "false"}),
            "robots_txt": forms.Textarea(attrs={"rows": 8, "spellcheck": "false"}),
            "sitemap_extra": forms.Textarea(attrs={"rows": 3, "spellcheck": "false"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.can_edit_head = bool(user and user.is_superuser)
        if not self.can_edit_head:
            self.fields["extra_head_html"].disabled = True
        for name in ("google_verification", "bing_verification", "yandex_verification"):
            self.fields[name].widget.attrs.update({"placeholder": "Kodni yoki butun <meta> tegini qo'ying", "spellcheck": "false"})

    def _verification(self, name):
        code = seo_tools.parse_verification(self.cleaned_data.get(name))
        if code and not seo_tools.CODE_RE.match(code):
            raise forms.ValidationError("Kod noto'g'ri: faqat harf, raqam va - _ . belgilari (6–200 ta).")
        return code

    def clean_google_verification(self):
        return self._verification("google_verification")

    def clean_bing_verification(self):
        return self._verification("bing_verification")

    def clean_yandex_verification(self):
        return self._verification("yandex_verification")

    def clean_ga_measurement_id(self):
        value = (self.cleaned_data.get("ga_measurement_id") or "").strip().upper()
        if value and not seo_tools.GA_RE.match(value):
            raise forms.ValidationError("Masalan: G-ABC123XYZ4")
        return value

    def clean_yandex_metrica_id(self):
        value = (self.cleaned_data.get("yandex_metrica_id") or "").strip()
        if value and not seo_tools.METRICA_RE.match(value):
            raise forms.ValidationError("Faqat raqamlar (4–12 ta).")
        return value

    def clean_extra_head_html(self):
        value = self.cleaned_data.get("extra_head_html") or ""
        if not self.can_edit_head:
            return self.instance.extra_head_html
        error = seo_tools.check_head_html(value)
        if error:
            raise forms.ValidationError(error)
        return value.strip()

    def clean_default_og_image(self):
        value = (self.cleaned_data.get("default_og_image") or "").strip()
        if value and not value.startswith(("http://", "https://", "/")):
            raise forms.ValidationError("https://... yoki /static/... ko'rinishida yozing.")
        return value

    def clean_sitemap_extra(self):
        lines = [x.strip() for x in (self.cleaned_data.get("sitemap_extra") or "").splitlines() if x.strip()]
        for line in lines:
            if not line.startswith(("http://", "https://", "/")) or " " in line:
                raise forms.ValidationError(f"«{line[:50]}» manzili noto'g'ri: / yoki https:// bilan boshlang.")
        return "\n".join(lines)


class PageSeoForm(forms.ModelForm):
    class Meta:
        model = PageSeo
        fields = ["title", "description", "og_image", "noindex"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}

    def clean_og_image(self):
        value = (self.cleaned_data.get("og_image") or "").strip()
        if value and not value.startswith(("http://", "https://", "/")):
            raise forms.ValidationError("https://... yoki /static/... ko'rinishida yozing.")
        return value


@staff_required
def seo_settings(request):
    cfg, _ = SiteSetting.objects.get_or_create(pk=1)
    page_rows = {key: PageSeo.objects.filter(key=key).first() or PageSeo(key=key) for key, _ in PAGE_SEO_KEYS}

    if request.method == "POST":
        form = SiteSettingForm(request.POST, instance=cfg, user=request.user)
        page_forms = {key: PageSeoForm(request.POST, instance=page_rows[key], prefix=key) for key, _ in PAGE_SEO_KEYS}
        if form.is_valid() and all(f.is_valid() for f in page_forms.values()):
            obj = form.save(commit=False)
            obj.updated_by = request.user
            obj.save()
            for key, pf in page_forms.items():
                row = pf.save(commit=False)
                row.key = key
                row.save()
            log_activity(request, "admin_seo_settings", detail="Sayt SEO sozlamalari saqlandi")
            messages.success(request, "SEO sozlamalari saqlandi.")
            return redirect("boshqaruv:seo_settings")
        messages.error(request, "Saqlanmadi — qizil belgilangan maydonlarni tuzating.")
    else:
        form = SiteSettingForm(instance=cfg, user=request.user)
        page_forms = {key: PageSeoForm(instance=page_rows[key], prefix=key) for key, _ in PAGE_SEO_KEYS}

    base = public_views.site_url(request)
    return render(request, "shajara/boshqaruv/seo_settings.html", {
        "section": "seo", "seo_tab": "settings", "form": form, "cfg": cfg,
        "page_forms": [(key, label, page_forms[key]) for key, label in PAGE_SEO_KEYS],
        "base": base,
        "head_preview": seo_tools.head_snippets(cfg),
        "robots_preview": seo_tools.robots_body(base, cfg),
        "sitemap_total": public_views.sitemap_count(request),
        "og_default": seo_tools.absolute(base, cfg.default_og_image),
        "files_active": SeoFile.objects.filter(is_active=True).count(),
    })


class SeoFileForm(forms.ModelForm):
    class Meta:
        model = SeoFile
        fields = ["path", "content_type", "content", "note", "is_active"]
        widgets = {"content": forms.Textarea(attrs={"rows": 3, "spellcheck": "false"})}

    def clean_path(self):
        value = (self.cleaned_data.get("path") or "").strip().lstrip("/")
        if not seo_tools.FILE_PATH_RE.match(value):
            raise forms.ValidationError("Masalan: google1a2b3c.html, BingSiteAuth.xml, ads.txt yoki .well-known/security.txt")
        if value.lower() in SEO_FILE_RESERVED:
            raise forms.ValidationError("Bu manzil tizimniki (robots.txt va sitemap.xml «Sozlamalar»da boshqariladi).")
        if SeoFile.objects.filter(path=value).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Bunday fayl allaqachon bor.")
        return value

    def clean_content(self):
        value = self.cleaned_data.get("content") or ""
        if len(value) > 20000:
            raise forms.ValidationError("Fayl juda katta (20 000 belgigacha).")
        return value


def _guess_content_type(path):
    ext = path.rsplit(".", 1)[-1].lower()
    return {"html": "text/html", "htm": "text/html", "xml": "application/xml", "json": "application/json"}.get(ext, "text/plain")


@staff_required
def seo_files(request):
    base = public_views.site_url(request)
    if request.method == "POST":
        action = request.POST.get("action", "save")
        if action == "delete":
            row = get_object_or_404(SeoFile, pk=request.POST.get("id"))
            path = row.path
            row.delete()
            log_activity(request, "admin_seo_file", detail=f"/{path} o'chirildi")
            messages.success(request, f"/{path} o'chirildi.")
            return redirect("boshqaruv:seo_files")
        instance = SeoFile.objects.filter(pk=request.POST.get("id")).first() if request.POST.get("id") else None
        data = request.POST.copy()
        if not data.get("content_type"):
            data["content_type"] = _guess_content_type(data.get("path", ""))
        form = SeoFileForm(data, instance=instance)
        if form.is_valid():
            row = form.save()
            log_activity(request, "admin_seo_file", detail=f"/{row.path} saqlandi")
            messages.success(request, f"/{row.path} saqlandi — {base}/{row.path}")
            return redirect("boshqaruv:seo_files")
        errors = "; ".join(e for errs in form.errors.values() for e in errs)
        messages.error(request, f"Saqlanmadi: {errors}")
        return redirect("boshqaruv:seo_files")

    return render(request, "shajara/boshqaruv/seo_files.html", {
        "section": "seo", "seo_tab": "files", "files": SeoFile.objects.all(), "base": base,
        "new_form": SeoFileForm(), "types": SeoFile._meta.get_field("content_type").choices,
    })


# ------------------------------------------------------------ system health --

def _redact(text):
    secret = settings.EMAIL_HOST_PASSWORD
    return text.replace(secret, "********") if secret else text


def _dir_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


@staff_required
def system_health(request):
    now = timezone.now()
    week = now - timedelta(days=7)
    db_name = settings.DATABASES["default"]["NAME"]
    db_size = os.path.getsize(db_name) if os.path.exists(db_name) else 0
    failures = ActivityLog.objects.filter(action="email_failed").select_related("user")
    total_users = User.objects.count()
    unverified = User.objects.exclude(profile__email_verified=True).count()
    checks = [
        {"ok": not settings.DEBUG, "label": "DEBUG rejimi", "text": "o'chirilgan" if not settings.DEBUG else "yoqilgan — serverda DJANGO_DEBUG=0 bo'lishi kerak"},
        {"ok": bool(getattr(settings, "SITE_URL", "")), "label": "SITE_URL", "text": settings.SITE_URL or "bo'sh — .env ga SITE_URL=https://e-shajara.uz yozing"},
        {"ok": settings.EMAIL_BACKEND.endswith("smtp.EmailBackend"), "label": "Email yuborish",
         "text": "SMTP ulangan" if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") else "konsol rejimi — xatlar haqiqatda yuborilmaydi (.env da EMAIL_HOST_USER yo'q)"},
        {"ok": "@" in settings.DEFAULT_FROM_EMAIL.split("<")[-1], "label": "Jo'natuvchi manzil", "text": settings.DEFAULT_FROM_EMAIL},
    ]
    return render(request, "shajara/boshqaruv/system.html", {
        "section": "system", "env": seo_tools.env_report(), "checks": checks,
        "db_size": _human(db_size), "media_size": _human(_dir_size(settings.MEDIA_ROOT)),
        "failures_7": failures.filter(created_at__gte=week).count(),
        "failures": failures[:8],
        "unverified": unverified, "total_users": total_users,
        "test_to": request.user.email,
    })


@staff_required
@require_POST
def system_test_email(request):
    to = (request.POST.get("to") or request.user.email or "").strip()
    if "@" not in to:
        messages.error(request, "Test xat uchun to'g'ri email manzil kiriting.")
        return redirect("boshqaruv:system")
    try:
        msg = EmailMultiAlternatives(
            "e-Shajara — test xat", "Bu boshqaruv panelidan yuborilgan test xat. Agar buni o'qiyotgan bo'lsangiz, email to'g'ri ishlayapti.",
            settings.DEFAULT_FROM_EMAIL, [to])
        msg.attach_alternative(
            "<div style=\"font-family:Georgia,serif;max-width:420px;margin:auto;padding:24px;border:1px solid #dbeddf;border-radius:14px\">"
            "<h2 style=\"color:#12633a;margin:0 0 8px\">e-Shajara</h2>"
            "<p>Bu boshqaruv panelidan yuborilgan <b>test xat</b>. Agar buni o'qiyotgan bo'lsangiz, email to'g'ri ishlayapti.</p></div>",
            "text/html")
        msg.send(fail_silently=False)
    except Exception as exc:
        detail = _redact(f"{type(exc).__name__}: {exc}")[:280]
        log_activity(request, "admin_email_test", detail=f"{to}: XATO — {detail}")
        messages.error(request, f"Xat yuborilmadi. {detail}")
    else:
        log_activity(request, "admin_email_test", detail=f"{to}: yuborildi")
        note = "" if settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") else " (konsol rejimi: xat faqat server logida ko'rinadi)"
        messages.success(request, f"Test xat {to} manziliga yuborildi{note}. Spam papkasini ham tekshiring.")
    return redirect("boshqaruv:system")