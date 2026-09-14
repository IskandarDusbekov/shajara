"""Cross-tree matching ("identity resolution").

Different people build their own trees and often enter the same ancestor
twice, in slightly different spellings, in graphs that are not connected.
This module finds such pairs and gives each one an explainable confidence
score. It never changes the family data itself: it only writes
MatchCandidate rows for staff to review (see merge.py for the merge).

How a score is built (weights add up to 100):

    Ism ................. 25   first name similarity (hard gate)
    Familiya ............ 15   surname root (Karimov/Karimova -> karim)
    Yillar .............. 20   birth year (14) and death year (6), within ±5
    Joy ................. 10   birth region / district / village, residence
    Otasining ismi ...... 15   father's first name, or the patronymic field
    Onasining ismi ......  5
    Turmush o'rtog'i ....  5
    Farzandlari .........  5   share of children whose names match

    + Qarindoshlari ham mos  up to +15: 5 for every parent, spouse or child
                             pair that is itself a likely match

Unknown evidence earns nothing, so a bare name match stays well below the
review threshold: a pair has to agree on several independent things to
surface. Clear contradictions (other gender, birth years > 10 apart, a
different father) either rule a pair out or cost points.

Two structural rules run over the whole result set: relatives that match
each other corroborate the pair (a family matching as a family is far
stronger evidence than two lone names), and one person cannot be the same
as two siblings, so only the better of such rival pairs is kept.

Scaling: persons are only compared inside a "block" (gender + consonant
skeleton of the first name), and never with someone already in the same
connected family graph, so the work grows with block sizes, not N².
"""

import re
import unicodedata
from collections import defaultdict

from django.db import transaction
from django.utils import timezone

MIN_SCORE = 45          # below this a pair is noise and is not stored
CORROBORATION_FLOOR = 35   # relatives scoring at least this back each other up
CORROBORATION_POINTS = 5   # per matching relative pair ...
CORROBORATION_CAP = 15     # ... up to this many points
FIRST_NAME_GATE = 0.84  # Jaro-Winkler below this: different first names
YEAR_WINDOW = 5
YEAR_REJECT = 10

# ------------------------------------------------------------ normalising --

_APOSTROPHES = "ʻʼ‘’`´ʹ′"
_CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ғ": "g'", "д": "d", "е": "e", "ё": "yo",
    "ж": "j", "з": "z", "и": "i", "й": "y", "к": "k", "қ": "q", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ў": "o'",
    "ф": "f", "х": "x", "ҳ": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "'",
    "ь": "", "ы": "i", "э": "e", "ю": "yu", "я": "ya",
}
# Spelling variants that should compare as equal: Uzbek Latin vs Russian-style
# transliteration ("Xo'jayev" / "Khodjaev"), and letters people swap freely.
_FOLDS = [
    ("o'", "o"), ("g'", "g"), ("'", ""), ("kh", "h"), ("x", "h"), ("q", "k"),
    ("dj", "j"), ("dzh", "j"), ("zh", "j"), ("ye", "e"), ("yu", "u"), ("w", "v"),
]
_SURNAME_SUFFIXES = ("ovna", "evna", "ovich", "evich", "yeva", "yev", "ova", "eva", "ov", "ev", "iy", "i")
_PATRONYMIC_SUFFIXES = ("ovich", "evich", "ovna", "evna")
_PATRONYMIC_WORDS = ("o'g'li", "og'li", "ogli", "ugli", "o'g'i", "qizi", "kizi")


def transliterate(text):
    """Lower-case Uzbek/Russian text in Latin script with one apostrophe."""
    text = (text or "").strip().lower()
    for ch in _APOSTROPHES:
        text = text.replace(ch, "'")
    return "".join(_CYRILLIC.get(ch, ch) for ch in text)


def fold(text):
    """A spelling-insensitive form of a name, used for comparison only."""
    text = transliterate(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    for a, b in _FOLDS:
        text = text.replace(a, b)
    text = re.sub(r"[^a-z]", "", text)
    return re.sub(r"(.)\1+", r"\1", text)   # "Abdullaa" and "Abdula" agree


def surname_root(text):
    word = fold(text)
    for suffix in _SURNAME_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def patronymic_root(text):
    """'Ahmadovich', 'Ahmad o'g'li', 'Ахмадовна' -> 'ahmad'."""
    raw = transliterate(text)
    for word in _PATRONYMIC_WORDS:
        raw = raw.replace(word, " ")
    word = fold(raw)
    for suffix in _PATRONYMIC_SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 2:
            return word[: -len(suffix)]
    return word


def block_key(gender, first_name):
    """Gender + the first three consonants: 'Muhammad' and 'Mohammed' share
    'mhm', 'Ahmad' and 'Axmad' share 'hmd'."""
    consonants = re.sub(r"[aeiouy]", "", fold(first_name))
    skeleton = consonants[:3] or fold(first_name)[:3]
    return f"{gender}:{skeleton}" if skeleton else None


def jaro_winkler(a, b):
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    window = max(la, lb) // 2 - 1
    a_hits, b_hits = [False] * la, [False] * lb
    matches = 0
    for i, ch in enumerate(a):
        lo, hi = max(0, i - window), min(i + window + 1, lb)
        for j in range(lo, hi):
            if not b_hits[j] and b[j] == ch:
                a_hits[i] = b_hits[j] = True
                matches += 1
                break
    if not matches:
        return 0.0
    transpositions, k = 0, 0
    for i in range(la):
        if a_hits[i]:
            while not b_hits[k]:
                k += 1
            if a[i] != b[k]:
                transpositions += 1
            k += 1
    m = float(matches)
    jaro = (m / la + m / lb + (m - transpositions / 2) / m) / 3
    prefix = 0
    for x, y in zip(a[:4], b[:4]):
        if x != y:
            break
        prefix += 1
    return jaro + prefix * 0.1 * (1 - jaro)


def year_of(value):
    match = re.search(r"\d{3,4}", str(value or ""))
    return int(match.group()) if match else None


def names_match(p, q, threshold=0.9):
    """Two records name the same person closely enough to be merged when
    their families are already known to be the same (children, spouses)."""
    if p.gender != q.gender:
        return False
    if jaro_winkler(fold(p.first_name), fold(q.first_name)) < threshold:
        return False
    if p.last_name and q.last_name:
        return jaro_winkler(surname_root(p.last_name), surname_root(q.last_name)) >= 0.8
    return True


# ------------------------------------------------------------------ graph --

class FamilyGraph:
    """Everyone and every family, loaded once, with the lookups scoring needs."""

    def __init__(self):
        from .models import Family, Person, Tree

        self.people = {p.id: p for p in Person.objects.all()}
        self.father, self.mother = {}, {}
        self.spouses = defaultdict(set)
        self.children = defaultdict(set)
        parent = {pid: pid for pid in self.people}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry

        kids_by_family = defaultdict(list)
        for pid, p in self.people.items():
            if p.child_family_id:
                kids_by_family[p.child_family_id].append(pid)

        for fam in Family.objects.all():
            members = [m for m in (fam.father_id, fam.mother_id) if m in self.people]
            kids = kids_by_family.get(fam.id, [])
            for kid in kids:
                if fam.father_id in self.people:
                    self.father[kid] = fam.father_id
                if fam.mother_id in self.people:
                    self.mother[kid] = fam.mother_id
            if fam.father_id in self.people and fam.mother_id in self.people:
                self.spouses[fam.father_id].add(fam.mother_id)
                self.spouses[fam.mother_id].add(fam.father_id)
            for par in members:
                self.children[par].update(kids)
            linked = members + kids
            for other in linked[1:]:
                union(linked[0], other)

        self.component = {pid: find(pid) for pid in self.people}
        self.trees_by_component = defaultdict(list)
        for tree in Tree.objects.select_related("owner"):
            if tree.root_person_id in self.component:
                self.trees_by_component[self.component[tree.root_person_id]].append(tree)

    def trees_of(self, pid):
        return self.trees_by_component.get(self.component.get(pid), [])

    def father_name(self, pid):
        """Father's first name from the graph, else the patronymic field."""
        fid = self.father.get(pid)
        if fid:
            return fold(self.people[fid].first_name)
        patronymic = self.people[pid].patronymic
        return patronymic_root(patronymic) if patronymic else ""

    def mother_name(self, pid):
        mid = self.mother.get(pid)
        return fold(self.people[mid].first_name) if mid else ""


# ---------------------------------------------------------------- scoring --

def _criterion(key, label, weight, share, detail):
    share = max(0.0, min(1.0, share))
    return {"key": key, "label": label, "weight": weight,
            "points": round(weight * share, 1), "detail": detail}


def _best_overlap(names_a, names_b, threshold=0.88):
    if not names_a or not names_b:
        return None
    hits = sum(1 for a in names_a if max(jaro_winkler(a, b) for b in names_b) >= threshold)
    return hits / max(len(names_a), len(names_b)), hits


_PLACE_WORDS = re.compile(
    r"(viloyati|viloyat|tumani|tuman|shahri|shahar|qishlog'i|qishloq|mahallasi|mahalla|"
    r"respublikasi|ovuli|ovul|mfy|область|район|город|село)"
)


def place_name(text):
    """'Urgut tumani' and 'Urgut' are the same place for matching."""
    return fold(_PLACE_WORDS.sub(" ", transliterate(text)))


def _place_parts(p):
    return {
        "region": place_name(p.birth_region), "district": place_name(p.birth_district),
        "village": place_name(p.birth_village), "location": place_name(p.location),
    }


def score_pair(graph, a_id, b_id):
    """Return (score 0-100, breakdown list) or None when the pair is ruled out."""
    a, b = graph.people[a_id], graph.people[b_id]
    if a.gender != b.gender:
        return None

    parts, penalty = [], 0

    # 1. First name — a gate as well as evidence.
    first = jaro_winkler(fold(a.first_name), fold(b.first_name))
    if first < FIRST_NAME_GATE:
        return None
    parts.append(_criterion("first_name", "Ism", 25, (first - FIRST_NAME_GATE) / (1 - FIRST_NAME_GATE) * 0.4 + 0.6
                            if first < 1 else 1.0, f"{a.first_name} ↔ {b.first_name} ({round(first * 100)}%)"))

    # 2. Surname root.
    if a.last_name and b.last_name:
        sim = jaro_winkler(surname_root(a.last_name), surname_root(b.last_name))
        share = 1.0 if sim >= 0.95 else (sim - 0.75) / 0.2 if sim >= 0.75 else 0.0
        parts.append(_criterion("last_name", "Familiya", 15, share, f"{a.last_name} ↔ {b.last_name}"))
        if sim < 0.6:
            penalty += 5
    else:
        parts.append(_criterion("last_name", "Familiya", 15, 0, "bir tomonda kiritilmagan"))

    # 3. Years.
    ya, yb = year_of(a.birth_date.year if a.birth_date else a.birth_year), \
        year_of(b.birth_date.year if b.birth_date else b.birth_year)
    if ya and yb:
        diff = abs(ya - yb)
        if diff > YEAR_REJECT:
            return None
        share = 1 - diff / (YEAR_WINDOW + 1) if diff <= YEAR_WINDOW else 0.0
        parts.append(_criterion("birth", "Tug'ilgan yili", 14, share, f"{ya} ↔ {yb} (farq {diff} yil)"))
    else:
        parts.append(_criterion("birth", "Tug'ilgan yili", 14, 0, "bir tomonda noma'lum"))
    da, db = year_of(a.death_year), year_of(b.death_year)
    if da and db:
        diff = abs(da - db)
        share = 1 - diff / (YEAR_WINDOW + 1) if diff <= YEAR_WINDOW else 0.0
        if diff > YEAR_REJECT:
            penalty += 8
        parts.append(_criterion("death", "Vafot etgan yili", 6, share, f"{da} ↔ {db} (farq {diff} yil)"))
    else:
        parts.append(_criterion("death", "Vafot etgan yili", 6, 0, "bir tomonda noma'lum"))

    # 4. Place.
    pa, pb = _place_parts(a), _place_parts(b)
    share, notes = 0.0, []
    if pa["region"] and pb["region"]:
        if jaro_winkler(pa["region"], pb["region"]) >= 0.92:
            share += 0.4
            notes.append("viloyat mos")
        else:
            penalty += 4
            notes.append("viloyat farq qiladi")
    if pa["district"] and pb["district"] and jaro_winkler(pa["district"], pb["district"]) >= 0.9:
        share += 0.35
        notes.append("tuman mos")
    if pa["village"] and pb["village"] and jaro_winkler(pa["village"], pb["village"]) >= 0.9:
        share += 0.25
        notes.append("qishloq/mahalla mos")
    if not notes and pa["location"] and pb["location"] and jaro_winkler(pa["location"], pb["location"]) >= 0.9:
        share += 0.4
        notes.append("yashash joyi mos")
    parts.append(_criterion("place", "Joy", 10, share, ", ".join(notes) or "ma'lumot yetarli emas"))

    # 5. Graph: father, mother, spouse, children.
    fa, fb = graph.father_name(a_id), graph.father_name(b_id)
    if fa and fb:
        sim = jaro_winkler(fa, fb)
        if sim >= 0.9:
            parts.append(_criterion("father", "Otasining ismi", 15, 1.0 if sim >= 0.97 else 0.8, "mos keladi"))
        else:
            penalty += 10
            parts.append(_criterion("father", "Otasining ismi", 15, 0, "farq qiladi"))
    else:
        parts.append(_criterion("father", "Otasining ismi", 15, 0, "bir tomonda noma'lum"))

    ma, mb = graph.mother_name(a_id), graph.mother_name(b_id)
    if ma and mb:
        sim = jaro_winkler(ma, mb)
        if sim < 0.85:
            penalty += 3
        parts.append(_criterion("mother", "Onasining ismi", 5, 1.0 if sim >= 0.9 else 0, "mos" if sim >= 0.9 else "farq qiladi"))
    else:
        parts.append(_criterion("mother", "Onasining ismi", 5, 0, "bir tomonda noma'lum"))

    sa = [fold(graph.people[x].first_name) for x in graph.spouses.get(a_id, ())]
    sb = [fold(graph.people[x].first_name) for x in graph.spouses.get(b_id, ())]
    overlap = _best_overlap(sa, sb)
    parts.append(_criterion("spouse", "Turmush o'rtog'i", 5, 1.0 if overlap and overlap[1] else 0,
                            "mos" if overlap and overlap[1] else ("bir tomonda noma'lum" if overlap is None else "mos emas")))

    ca = [fold(graph.people[x].first_name) for x in graph.children.get(a_id, ())]
    cb = [fold(graph.people[x].first_name) for x in graph.children.get(b_id, ())]
    overlap = _best_overlap(ca, cb)
    parts.append(_criterion("children", "Farzandlari", 5, overlap[0] if overlap else 0,
                            f"{overlap[1]} ta ism mos" if overlap else "bir tomonda noma'lum"))

    raw = sum(p["points"] for p in parts) - penalty
    if penalty:
        parts.append({"key": "penalty", "label": "Qarama-qarshiliklar", "weight": 0,
                      "points": -penalty, "detail": "bir-biriga zid ma'lumotlar uchun ayirildi"})
    return max(0, min(100, round(raw))), parts


def _relatives(graph, pid):
    rel = set()
    for key in (graph.father.get(pid), graph.mother.get(pid)):
        if key:
            rel.add(key)
    return rel | set(graph.spouses.get(pid, ())) | set(graph.children.get(pid, ()))


def apply_structure(graph, scored):
    """Corroborate pairs through matching relatives, then drop rival pairs
    that would make one person the same as two siblings."""
    strong = {pair for pair, (score, _) in scored.items() if score >= CORROBORATION_FLOOR}
    lookup = strong | {(b, a) for a, b in strong}

    result = {}
    for (a_id, b_id), (score, parts) in scored.items():
        rel_a, rel_b = _relatives(graph, a_id), _relatives(graph, b_id)
        backers = sum(1 for x in rel_a for y in rel_b if (x, y) in lookup)
        bonus = min(CORROBORATION_CAP, backers * CORROBORATION_POINTS)
        parts = list(parts)
        if bonus:
            parts.append({"key": "relatives", "label": "Qarindoshlari ham mos", "weight": CORROBORATION_CAP,
                          "points": bonus, "detail": f"{backers} ta qarindosh juftligi mos keladi"})
        result[(a_id, b_id)] = (min(100, score + bonus), parts)

    def sibling_group(pid):
        fam = graph.people[pid].child_family_id
        return fam or f"solo-{pid}"

    # For every person keep only the best partner among siblings on the other side.
    best = {}
    for (a_id, b_id), (score, _) in result.items():
        for me, other in ((a_id, b_id), (b_id, a_id)):
            slot = (me, sibling_group(other))
            if slot not in best or score > best[slot][0]:
                best[slot] = (score, (a_id, b_id))
    keep = {pair for _, pair in best.values()}
    return {pair: value for pair, value in result.items()
            if pair in keep and all(best[(me, sibling_group(o))][1] == pair
                                    for me, o in ((pair[0], pair[1]), (pair[1], pair[0])))}


def _snapshot(graph, pid):
    p = graph.people[pid]
    return {
        "id": pid, "name": p.full_name, "gender": p.gender, "year": p.display_year or "",
        "trees": [{"id": t.id, "name": t.name, "owner": t.owner.username} for t in graph.trees_of(pid)],
    }


# ----------------------------------------------------------------- runner --

def run_matching(triggered_by=None):
    """Scan everyone, refresh the candidate list, return the MatchRun."""
    from .models import MatchCandidate, MatchRun

    run = MatchRun.objects.create(triggered_by=triggered_by)
    graph = FamilyGraph()

    # Only people who belong to some tree are worth matching; loose records
    # left behind by deleted trees are nobody's family any more.
    eligible = [pid for pid in graph.people if graph.trees_of(pid)]
    blocks = defaultdict(list)
    for pid in eligible:
        p = graph.people[pid]
        key = block_key(p.gender, p.first_name)
        if key:
            blocks[key].append(pid)

    scored = {}
    compared = 0
    for members in blocks.values():
        members.sort()
        for i, a_id in enumerate(members):
            for b_id in members[i + 1:]:
                if graph.component[a_id] == graph.component[b_id]:
                    continue    # already one family graph
                compared += 1
                result = score_pair(graph, a_id, b_id)
                if result:
                    scored[(a_id, b_id)] = result

    found = {}
    for (a_id, b_id), (score, parts) in apply_structure(graph, scored).items():
        if score >= MIN_SCORE:
            found[MatchCandidate.key_for(a_id, b_id)] = (a_id, b_id, (score, parts))

    new = 0
    with transaction.atomic():
        existing = {c.pair_key: c for c in MatchCandidate.objects.filter(pair_key__in=list(found))}
        for key, (a_id, b_id, (score, parts)) in found.items():
            snapshot = {"a": _snapshot(graph, a_id), "b": _snapshot(graph, b_id)}
            cand = existing.get(key)
            if cand is None:
                MatchCandidate.objects.create(
                    person_a_id=a_id, person_b_id=b_id, pair_key=key,
                    score=score, breakdown=parts, snapshot=snapshot,
                )
                new += 1
            elif cand.status == "pending":
                cand.score, cand.breakdown, cand.snapshot = score, parts, snapshot
                cand.save(update_fields=["score", "breakdown", "snapshot", "updated_at"])
            # rejected / merged decisions are the admin's and are left alone

        # Pending hypotheses that no longer hold (edited data, already joined).
        MatchCandidate.objects.filter(status="pending").exclude(pair_key__in=list(found)).delete()

    run.persons_scanned = len(eligible)
    run.pairs_compared = compared
    run.candidates_found = len(found)
    run.candidates_new = new
    run.finished_at = timezone.now()
    run.save()
    return run
