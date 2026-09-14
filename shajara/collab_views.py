"""Building one tree together.

The owner opens the tree's "A'zolar" page and makes an invite link, choosing
what the people who open it may do: an editor (muharrir) adds and edits
people, a viewer (kuzatuvchi) looks, writes stories and takes the self-test.
The link goes out by Telegram or any messenger; whoever opens it signs in (or
signs up) and joins. A family grows its tree this way — one relative starts,
the others fill in their branches — and a teacher gathers a class around a
learning tree.
"""

from datetime import timedelta
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import F
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .activity import log_activity
from .forms import InviteForm, MemberRoleForm
from .models import MEMBER_ROLE_HELP, QuizAttempt, Tree, TreeInvite, TreeMember
from .tree import tree_role

MAX_ACTIVE_INVITES = 20


def _tree_or_404(tree_key):
    return get_object_or_404(Tree.objects.select_related("owner", "root_person"), public_id=tree_key)


@login_required
def members_view(request, tree_key):
    """Who builds this tree. Everyone in it sees the list; the owner also
    manages invites and roles here."""
    tree = _tree_or_404(tree_key)
    role = tree_role(request.user, tree)
    if role is None:
        return HttpResponseForbidden("Bu sahifa faqat shajara a'zolariga ko'rinadi.")
    is_owner = role == "owner"

    members = list(tree.members.select_related("user", "invited_by"))
    contributions = {}
    from .models import ActivityLog
    counted = ("person_add", "person_edit", "story_add")
    for user_id, action in ActivityLog.objects.filter(tree=tree, action__in=counted).values_list("user_id", "action"):
        contributions[user_id] = contributions.get(user_id, 0) + 1

    results = {}
    if tree.is_learning:
        for attempt in QuizAttempt.objects.filter(tree=tree).order_by("created_at"):
            row = results.setdefault(attempt.user_id, {"best": 0, "count": 0, "last": None})
            row["best"] = max(row["best"], attempt.percent)
            row["count"] += 1
            row["last"] = attempt.created_at
    for m in members:
        m.contributions = contributions.get(m.user_id, 0)
        m.quiz = results.get(m.user_id)

    invites = []
    if is_owner:
        for inv in tree.invites.filter(revoked=False):
            if inv.is_expired:
                continue
            inv.url = request.build_absolute_uri(reverse("invite_accept", args=[inv.token]))
            text = (f"«{tree.name}» ta'limiy shajarasiga qo'shiling" if tree.is_learning
                    else f"Oilamiz shajarasini birga to'ldiraylik: «{tree.name}»")
            inv.telegram = f"https://t.me/share/url?url={quote(inv.url, safe='')}&text={quote(text, safe='')}"
            invites.append(inv)

    return render(request, "shajara/members.html", {
        "tree": tree, "role": role, "is_owner": is_owner,
        "owner_contributions": contributions.get(tree.owner_id, 0),
        "owner_quiz": results.get(tree.owner_id),
        "members": members, "invites": invites,
        "invite_form": InviteForm(), "role_help": MEMBER_ROLE_HELP,
        "just_created": request.GET.get("yangi", ""),
    })


@require_POST
@login_required
def invite_create_view(request, tree_key):
    tree = _tree_or_404(tree_key)
    if tree.owner_id != request.user.id:
        return HttpResponseForbidden("Faqat shajara egasi taklif havolasi yarata oladi.")
    form = InviteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Huquq va muddatni tanlang.")
        return redirect("tree_members", tree_key=tree.url_key)
    active = [i for i in tree.invites.filter(revoked=False) if not i.is_expired]
    if len(active) >= MAX_ACTIVE_INVITES:
        messages.error(request, "Faol havolalar juda ko'p. Keraksizlarini bekor qiling.")
        return redirect("tree_members", tree_key=tree.url_key)
    days = int(form.cleaned_data["ttl"])
    invite = TreeInvite.objects.create(
        tree=tree, role=form.cleaned_data["role"], created_by=request.user,
        expires_at=timezone.now() + timedelta(days=days) if days else None,
    )
    log_activity(request, "invite_create", tree=tree,
                 detail=f"{invite.get_role_display()}, {days or 'muddatsiz'} kun")
    return redirect(reverse("tree_members", args=[tree.url_key]) + f"?yangi={invite.pk}#taklif")


@require_POST
@login_required
def invite_revoke_view(request, tree_key, pk):
    tree = _tree_or_404(tree_key)
    if tree.owner_id != request.user.id:
        return HttpResponseForbidden("Faqat shajara egasi havolani bekor qila oladi.")
    invite = get_object_or_404(TreeInvite, pk=pk, tree=tree)
    invite.revoked = True
    invite.save(update_fields=["revoked"])
    log_activity(request, "invite_revoke", tree=tree, detail=invite.get_role_display())
    messages.success(request, "Havola bekor qilindi — endi u orqali hech kim qo'shila olmaydi.")
    return redirect("tree_members", tree_key=tree.url_key)


def invite_accept_view(request, token):
    """Opening an invite. Signed-out visitors see what they are invited to
    and sign in or up first; the address brings them back here."""
    invite = get_object_or_404(TreeInvite.objects.select_related("tree", "tree__owner", "created_by"), token=token)
    tree = invite.tree
    context = {"invite": invite, "tree": tree, "role_help": MEMBER_ROLE_HELP}
    if invite.is_active:
        # What the invited person (and a messenger's link preview) gets to see
        # before joining: the size of the tree and its picture.
        from .tree import compute_levels
        levels, _, _ = compute_levels(tree.root_person)
        context.update({
            "people_count": len(levels),
            "generations": len(set(levels.values())),
            "member_count": tree.members.count() + 1,
            "preview_url": request.build_absolute_uri(reverse("invite_preview", args=[invite.token])),
        })

    if not invite.is_active:
        context["dead"] = True
        return render(request, "shajara/invite.html", context, status=410)

    if not request.user.is_authenticated:
        return render(request, "shajara/invite.html", context)

    current = tree_role(request.user, tree)
    if current is not None:
        context["already"] = current
        return render(request, "shajara/invite.html", context)

    if request.method == "POST":
        try:
            TreeMember.objects.create(tree=tree, user=request.user, role=invite.role, invited_by=invite.created_by)
        except IntegrityError:
            pass
        else:
            TreeInvite.objects.filter(pk=invite.pk).update(uses=F("uses") + 1)
            log_activity(request, "member_join", tree=tree,
                         detail=f"{tree.name} — {invite.get_role_display()}")
            messages.success(request, f"Siz «{tree.name}» shajarasiga qo'shildingiz.")
        return redirect("index", tree_key=tree.url_key)

    return render(request, "shajara/invite.html", context)


@require_POST
@login_required
def member_update_view(request, tree_key, pk):
    tree = _tree_or_404(tree_key)
    member = get_object_or_404(TreeMember.objects.select_related("user"), pk=pk, tree=tree)
    is_owner = tree.owner_id == request.user.id
    action = request.POST.get("action")

    if action == "leave" and member.user_id == request.user.id:
        member.delete()
        log_activity(request, "member_leave", tree=tree, detail=tree.name)
        messages.success(request, f"Siz «{tree.name}» shajarasidan chiqdingiz.")
        return redirect("my_trees")

    if not is_owner:
        return HttpResponseForbidden("Faqat shajara egasi a'zolarni boshqara oladi.")

    if action == "remove":
        name = member.user.username
        member.delete()
        log_activity(request, "member_remove", tree=tree, detail=name)
        messages.success(request, f"@{name} shajaradan chiqarildi.")
    elif action == "role":
        form = MemberRoleForm(request.POST)
        if form.is_valid() and form.cleaned_data["role"] != member.role:
            member.role = form.cleaned_data["role"]
            member.save(update_fields=["role"])
            log_activity(request, "member_role", tree=tree,
                         detail=f"@{member.user.username}: {member.get_role_display()}")
            messages.success(request, f"@{member.user.username} endi — {member.get_role_display().lower()}.")
    return redirect("tree_members", tree_key=tree.url_key)
