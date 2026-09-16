""""O'zingizni sinang" — a self-test built from a tree.

Questions come straight from the family links and the facts entered for each
person (who is whose father, who married whom, when someone was born, what
they did), so any tree becomes a revision exercise: an applicant going over a
dynasty before an exam, or a teacher checking a class.

The right answers stay on the server. The page sends one answer at a time and
learns whether it was right only after it is locked in, and the finished
score is recorded for the teacher.
"""

import json
import random
import re

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import share_cards
from .activity import log_activity
from .models import QuizAttempt, Tree
from .public_views import site_url
from .tree import can_view_tree, compute_levels

QUIZ_LENGTH = 10
MIN_PEOPLE = 3
OPTIONS = 4


def _year(p):
    m = re.search(r"\d{3,4}", p.display_year or "")
    return int(m.group()) if m else None


class _Deck:
    """The tree's people and links, arranged for asking questions."""

    def __init__(self, root):
        _, people, families = compute_levels(root)
        self.people = people
        self.father, self.mother, self.children, self.spouses = {}, {}, {}, {}
        for fam in families.values():
            kids = [c.id for c in fam.children.all() if c.id in people]
            for kid in kids:
                if fam.father_id in people:
                    self.father[kid] = fam.father_id
                if fam.mother_id in people:
                    self.mother[kid] = fam.mother_id
            for parent in (fam.father_id, fam.mother_id):
                if parent in people:
                    self.children.setdefault(parent, []).extend(kids)
            if fam.father_id in people and fam.mother_id in people:
                self.spouses.setdefault(fam.father_id, []).append(fam.mother_id)
                self.spouses.setdefault(fam.mother_id, []).append(fam.father_id)

        # Two people with the same name need telling apart in the options.
        counts = {}
        for p in people.values():
            counts[p.full_name] = counts.get(p.full_name, 0) + 1
        self.label = {}
        for p in people.values():
            name = p.full_name
            if counts[name] > 1:
                extra = p.display_year or (self.people[self.father[p.id]].first_name + " farzandi"
                                           if p.id in self.father else f"#{p.id}")
                name = f"{name} ({extra})"
            self.label[p.id] = name

    def pick_people(self, rng, pool, exclude, k):
        choices = [pid for pid in pool if pid not in exclude]
        rng.shuffle(choices)
        return choices[:k]


def _options(rng, correct_label, wrong_labels):
    wrong = []
    for w in wrong_labels:
        if w != correct_label and w not in wrong:
            wrong.append(w)
    options = [correct_label] + wrong[:OPTIONS - 1]
    if len(options) < 2:
        return None, None
    rng.shuffle(options)
    return options, options.index(correct_label)


def build_quiz(root, rng=None):
    """Up to QUIZ_LENGTH questions: [{"text", "options", "answer", "explain"}]."""
    rng = rng or random.Random()
    deck = _Deck(root)
    if len(deck.people) < MIN_PEOPLE:
        return []
    ids = list(deck.people)
    men = [i for i in ids if deck.people[i].gender == "erkak"]
    women = [i for i in ids if deck.people[i].gender == "ayol"]
    L, P = deck.label, deck.people
    makers = []

    def parent_question(kid, parent_id, word, pool):
        wrong = deck.pick_people(rng, pool, {parent_id, kid}, OPTIONS - 1)
        options, answer = _options(rng, L[parent_id], [L[w] for w in wrong])
        if options:
            return {"text": f"{L[kid]}ning {word} kim?", "options": options, "answer": answer,
                    "explain": f"{L[parent_id]} — {P[kid].first_name}ning {word}."}

    for kid, dad in deck.father.items():
        makers.append(("ota", lambda kid=kid, dad=dad: parent_question(kid, dad, "otasi", men)))
    for kid, mom in deck.mother.items():
        makers.append(("ona", lambda kid=kid, mom=mom: parent_question(kid, mom, "onasi", women)))

    for parent, kids in deck.children.items():
        if not kids:
            continue

        def child_question(parent=parent, kids=kids):
            kid = rng.choice(kids)
            wrong = deck.pick_people(rng, ids, set(kids) | {parent} | set(deck.spouses.get(parent, [])), OPTIONS - 1)
            options, answer = _options(rng, L[kid], [L[w] for w in wrong])
            if options:
                return {"text": f"Quyidagilardan kim {L[parent]}ning farzandi?", "options": options,
                        "answer": answer, "explain": f"{L[kid]} — {P[parent].first_name}ning farzandi."}
        makers.append(("farzand", child_question))

    for person, partners in deck.spouses.items():
        def spouse_question(person=person, partners=partners):
            partner = rng.choice(partners)
            pool = women if P[person].gender == "erkak" else men
            wrong = deck.pick_people(rng, pool, set(partners) | {person}, OPTIONS - 1)
            options, answer = _options(rng, L[partner], [L[w] for w in wrong])
            if options:
                return {"text": f"{L[person]}ning turmush o'rtog'i kim?", "options": options, "answer": answer,
                        "explain": f"{L[person]} va {L[partner]} — er-xotin."}
        makers.append(("turmush", spouse_question))

    dated = [i for i in ids if _year(P[i])]
    for pid in dated:
        def year_question(pid=pid):
            year = _year(P[pid])
            others = sorted({_year(P[i]) for i in dated if _year(P[i]) != year})
            rng.shuffle(others)
            wrong = others[:OPTIONS - 1]
            step = 7
            while len(wrong) < OPTIONS - 1:
                candidate = year + step * rng.choice((-1, 1)) * (len(wrong) + 1)
                if candidate != year and candidate not in wrong:
                    wrong.append(candidate)
                step += 3
            options, answer = _options(rng, str(year), [str(w) for w in wrong])
            if options:
                return {"text": f"{L[pid]} qaysi yili tug'ilgan?", "options": options, "answer": answer,
                        "explain": f"{L[pid]} {P[pid].display_year} yilda tug'ilgan."}
        makers.append(("yil", year_question))

    with_job = [i for i in ids if P[i].occupation.strip()]
    jobs = sorted({P[i].occupation.strip() for i in with_job})
    if len(jobs) >= 2:
        for pid in with_job:
            def job_question(pid=pid):
                job = P[pid].occupation.strip()
                wrong = [j for j in jobs if j.lower() != job.lower()]
                rng.shuffle(wrong)
                options, answer = _options(rng, job, wrong)
                if options:
                    return {"text": f"{L[pid]} kim bo'lgan?", "options": options, "answer": answer,
                            "explain": f"{L[pid]} — {job}."}
            makers.append(("kasb", job_question))

    for pid, kids in deck.children.items():
        grandkids = [g for k in kids for g in deck.children.get(k, [])]
        if not grandkids:
            continue

        def grand_question(pid=pid, grandkids=grandkids, kids=kids):
            g = rng.choice(grandkids)
            word = "bobosi" if P[pid].gender == "erkak" else "buvisi"
            close = set(kids) | {g} | set(deck.spouses.get(pid, []))
            pool = men if P[pid].gender == "erkak" else women
            wrong = deck.pick_people(rng, pool, close | {pid}, OPTIONS - 1)
            options, answer = _options(rng, L[pid], [L[w] for w in wrong])
            if options:
                return {"text": f"{L[g]}ning {word} kim?", "options": options, "answer": answer,
                        "explain": f"{L[pid]} — {P[g].first_name}ning {word}."}
        makers.append(("avlod", grand_question))

    # Mix kinds evenly: take one of each kind in turn, in random order.
    by_kind = {}
    for kind, make in makers:
        by_kind.setdefault(kind, []).append(make)
    for items in by_kind.values():
        rng.shuffle(items)
    kinds = list(by_kind)
    rng.shuffle(kinds)
    questions, seen = [], set()
    while len(questions) < QUIZ_LENGTH and any(by_kind.values()):
        for kind in kinds:
            if not by_kind[kind] or len(questions) >= QUIZ_LENGTH:
                continue
            q = by_kind[kind].pop()()
            if q and q["text"] not in seen:
                seen.add(q["text"])
                questions.append(q)
    return questions


def _session_key(tree):
    return f"quiz:{tree.pk}"


@login_required
def quiz_view(request, tree_key):
    tree = get_object_or_404(Tree.objects.select_related("root_person", "owner"), public_id=tree_key)
    if not can_view_tree(request.user, tree):
        return HttpResponseForbidden("Bu shajara sizga ko'rinmaydi.")
    questions = build_quiz(tree.root_person)
    request.session[_session_key(tree)] = {
        "answers": [q["answer"] for q in questions],
        "explain": [q["explain"] for q in questions],
        "given": {},
        "saved": False,
    }
    public = [{"text": q["text"], "options": q["options"]} for q in questions]
    history = QuizAttempt.objects.filter(tree=tree, user=request.user)[:5]
    response = render(request, "shajara/quiz.html", {
        "tree": tree, "questions_json": public, "count": len(public), "history": history,
        "min_people": MIN_PEOPLE,
    })
    response["Cache-Control"] = "no-store, private"
    return response


@require_POST
@login_required
def quiz_answer_view(request, tree_key):
    tree = get_object_or_404(Tree, public_id=tree_key)
    if not can_view_tree(request.user, tree):
        return JsonResponse({"error": "forbidden"}, status=403)
    state = request.session.get(_session_key(tree))
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
        index, choice = int(data.get("q")), int(data.get("choice"))
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return JsonResponse({"error": "bad request"}, status=400)
    if not state or not 0 <= index < len(state["answers"]):
        return JsonResponse({"error": "Test eskirgan. Sahifani yangilang."}, status=409)

    given = state["given"]
    key = str(index)
    if key not in given:           # the first answer is the one that counts
        given[key] = choice
    correct = state["answers"][index]
    total = len(state["answers"])
    score = sum(1 for k, v in given.items() if state["answers"][int(k)] == v)
    done = len(given) == total

    share = None
    if done and not state["saved"]:
        attempt = QuizAttempt.objects.create(tree=tree, user=request.user, score=score, total=total)
        log_activity(request, "quiz_finish", tree=tree, detail=f"{score}/{total}")
        state["saved"] = True
        token = share_cards.make_token("test", attempt.pk)
        name = f"«{tree.name}»" if tree.is_public else "oilam shajarasi"
        share = {
            "url": site_url(request) + reverse("share_test", args=[token]),
            "card": reverse("share_test_png", args=[token]),
            "text": f"{name} bo'yicha testda {score}/{total} topdim. Siz nechta topasiz?",
        }
    request.session[_session_key(tree)] = state

    return JsonResponse({
        "ok": given[key] == correct, "correct": correct, "explain": state["explain"][index],
        "done": done, "score": score, "total": total, "share": share,
    })
