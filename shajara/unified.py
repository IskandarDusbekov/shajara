"""The admin's "umumiy shajara": every tree on the platform folded into one
resolved family graph.

Nothing here writes to the database. Person records that cross-tree matching
(matching.py) judged to be the same human being at or above a confidence
threshold are treated as one *individual*; families are rebuilt between
individuals; connected groups of individuals become unified family networks.
Users' own trees stay exactly as they entered them — only staff see this
resolved picture, and a wrong guess costs nothing but a misleading chart
(rejected matches are never used).

The result is built in memory and memoised for a minute per data version, so
the map, the overview and the board views of one visit share one build.
"""

import time
from collections import Counter, defaultdict, deque

from django.db.models import Count, Max

from .matching import FamilyGraph, names_match
from .regions import ABROAD, REGION_NAMES, person_region
from .tree import level_label, sibling_groups

AUTO_MERGE_SCORE = 70
_MEMO = {}
_MEMO_TTL = 60
_FILL_FIELDS = ("last_name", "patronymic", "birth_year", "death_year", "birth_region", "birth_district",
                "birth_village", "occupation", "location", "bio")


class Individual:
    """One resolved human being, backed by one or more person records."""

    def __init__(self, members):
        def richness(p):
            return (sum(1 for f in _FILL_FIELDS if getattr(p, f)) + (1 if p.birth_date else 0), -p.id)

        members = sorted(members, key=richness, reverse=True)
        best = members[0]
        self.id = best.id
        self.members = members
        self.gender = best.gender
        self.first_name = best.first_name
        for field in _FILL_FIELDS:
            value = next((getattr(m, field) for m in members if getattr(m, field)), "")
            setattr(self, field, value)
        self.birth_date = next((m.birth_date for m in members if m.birth_date), None)
        self.photo = next((m.photo for m in members if m.photo), None)
        self.child_family_id = None
        self.trees = []
        self.region, self.region_how = "", ""
        for m in members:
            region, how = person_region(m)
            if region:
                self.region, self.region_how = region, how
                if how == "kiritilgan":
                    break

    # the attributes the board template reads on a Person
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def display_year(self):
        return str(self.birth_date.year) if self.birth_date else self.birth_year

    @property
    def birth_place(self):
        return ", ".join(x for x in (self.birth_village, self.birth_district, self.birth_region) if x)

    def get_gender_display(self):
        return "Ayol" if self.gender == "ayol" else "Erkak"

    @property
    def merged_count(self):
        return len(self.members)


class VFamily:
    def __init__(self, fid, father_id, mother_id):
        self.id, self.father_id, self.mother_id = fid, father_id, mother_id
        self.child_ids = []


class UnifiedGraph:
    def __init__(self, min_score=AUTO_MERGE_SCORE):
        from .models import MatchCandidate

        self.min_score = min_score
        g = FamilyGraph()
        self.source = g

        # 1. Identity clusters from confident, non-rejected matches.
        parent = {pid: pid for pid in g.people}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        self.links_used = 0
        rejected = set()
        for a, b, status, score in MatchCandidate.objects.values_list("person_a_id", "person_b_id", "status", "score"):
            if status == "rejected":
                rejected.add(frozenset((a, b)))
            elif score >= min_score and a in parent and b in parent and find(a) != find(b):
                parent[find(a)] = find(b)
                self.links_used += 1

        # Same person ⇒ same parents, and a spouse or child named alike in both
        # records is the same person too — the rule the real merge follows.
        # Propagate to a fixed point; an admin's rejection always wins.
        self.links_structural = 0
        changed = True
        while changed:
            changed = False
            groups = defaultdict(list)
            for pid in g.people:
                groups[find(pid)].append(pid)
            for members in groups.values():
                if len(members) < 2:
                    continue
                for relatives in (
                    [g.father[m] for m in members if m in g.father],
                    [g.mother[m] for m in members if m in g.mother],
                    [s for m in members for s in g.spouses.get(m, ())],
                    [c for m in members for c in g.children.get(m, ())],
                ):
                    for i, x in enumerate(relatives):
                        for y in relatives[i + 1:]:
                            if find(x) == find(y) or frozenset((x, y)) in rejected:
                                continue
                            if names_match(g.people[x], g.people[y]):
                                parent[find(x)] = find(y)
                                self.links_structural += 1
                                changed = True

        clusters = defaultdict(list)
        for pid in g.people:
            clusters[find(pid)].append(g.people[pid])
        self.individuals = {}
        self.of = {}
        for members in clusters.values():
            ind = Individual(members)
            self.individuals[ind.id] = ind
            for m in members:
                self.of[m.id] = ind.id

        # 2. Families between individuals. Two records of one marriage become one.
        from .models import Family

        self.families = {}
        by_couple = {}
        family_of_record = {}
        for fam in Family.objects.all():
            f = self.of.get(fam.father_id) if fam.father_id in self.of else None
            m = self.of.get(fam.mother_id) if fam.mother_id in self.of else None
            if f is None and m is None:
                key = ("solo", fam.id)
            else:
                key = (f, m)
            if key not in by_couple:
                vf = VFamily(fam.id, f, m)
                by_couple[key] = vf
                self.families[vf.id] = vf
            family_of_record[fam.id] = by_couple[key]

        # A marriage recorded without the spouse joins the person's only full marriage.
        full_marriages = defaultdict(list)
        for (f, m), vf in [(k, v) for k, v in by_couple.items() if k[0] != "solo"]:
            if f is not None and m is not None:
                full_marriages[f].append(vf)
                full_marriages[m].append(vf)
        for key, vf in list(by_couple.items()):
            if key[0] == "solo":
                continue
            f, m = key
            if (f is None) != (m is None):
                known = f if f is not None else m
                if len(full_marriages.get(known, [])) == 1:
                    target = full_marriages[known][0]
                    for fid, mapped in family_of_record.items():
                        if mapped is vf:
                            family_of_record[fid] = target
                    self.families.pop(vf.id, None)

        # 3. Each individual is a child of one family; disagreement is a conflict.
        self.conflicts = []
        votes = defaultdict(Counter)
        for pid, person in g.people.items():
            if person.child_family_id and person.child_family_id in family_of_record:
                votes[self.of[pid]][family_of_record[person.child_family_id].id] += 1
        for iid, counter in votes.items():
            fid = counter.most_common(1)[0][0]
            self.individuals[iid].child_family_id = fid
            self.families[fid].child_ids.append(iid)
            if len(counter) > 1:
                self.conflicts.append(iid)

        # 4. Connected family networks.
        comp = {iid: iid for iid in self.individuals}

        def cfind(x):
            while comp[x] != x:
                comp[x] = comp[comp[x]]
                x = comp[x]
            return x

        for vf in self.families.values():
            linked = [x for x in (vf.father_id, vf.mother_id) if x is not None] + vf.child_ids
            for other in linked[1:]:
                ra, rb = cfind(linked[0]), cfind(other)
                if ra != rb:
                    comp[ra] = rb
        self.component = {iid: cfind(iid) for iid in self.individuals}
        self.members_of = defaultdict(list)
        for iid, c in self.component.items():
            self.members_of[c].append(iid)

        all_trees = [t for ts in g.trees_by_component.values() for t in ts]
        for tree in all_trees:
            iid = self.of.get(tree.root_person_id)
            if iid:
                self.individuals[iid].trees.append(tree)
        self.trees_by_component = defaultdict(list)
        for iid, ind in self.individuals.items():
            for tree in ind.trees:
                self.trees_by_component[self.component[iid]].append(tree)

    # ------------------------------------------------------------ analytics
    def record_count(self):
        return len(self.source.people)

    def family_networks(self, region=None, limit=None):
        """Networks that belong to some tree, biggest first."""
        rows = []
        for c, iids in self.members_of.items():
            trees = self.trees_by_component.get(c)
            if not trees:
                continue
            inds = [self.individuals[i] for i in iids]
            regions = Counter(ind.region for ind in inds if ind.region)
            main_region = regions.most_common(1)[0][0] if regions else ""
            if region and main_region != region:
                continue
            records = sum(ind.merged_count for ind in inds)
            years = sorted(int(y) for y in (ind.display_year for ind in inds) if str(y).isdigit())
            rows.append({
                "key": c, "people": len(inds), "records": records, "duplicates": records - len(inds),
                "trees": trees, "owners": sorted({t.owner.username for t in trees}),
                "region": main_region, "regions": regions.most_common(4),
                "year_from": years[0] if years else None, "year_to": years[-1] if years else None,
                "men": sum(1 for i in inds if i.gender == "erkak"),
                "conflicts": sum(1 for i in iids if i in self.conflicts),
            })
        rows.sort(key=lambda r: (-r["people"], -len(r["trees"])))
        return rows[:limit] if limit else rows

    def region_stats(self):
        from django.contrib.auth import get_user_model
        from .models import UserProfile

        stats = {name: {"people": 0, "records": 0, "duplicates": 0, "users": 0, "users_guess": 0, "trees": 0}
                 for name in REGION_NAMES + [ABROAD]}
        unknown_people = 0
        for ind in self.individuals.values():
            if not self.trees_by_component.get(self.component[ind.id]):
                continue
            if ind.region in stats:
                s = stats[ind.region]
                s["people"] += 1
                s["records"] += ind.merged_count
                s["duplicates"] += ind.merged_count - 1
            else:
                unknown_people += 1
            for tree in ind.trees:
                if ind.region in stats:
                    stats[ind.region]["trees"] += 1

        # Users: the region they chose; otherwise a guess from the people they entered.
        User = get_user_model()
        chosen = dict(UserProfile.objects.exclude(region="").values_list("user_id", "region"))
        added = defaultdict(Counter)
        for person in self.source.people.values():
            if person.added_by_id and person.added_by_id not in chosen:
                ind = self.individuals[self.of[person.id]]
                if ind.region:
                    added[person.added_by_id][ind.region] += 1
        users_unknown = 0
        self.user_regions = {}
        for uid in User.objects.values_list("id", flat=True):
            if uid in chosen and chosen[uid] in stats:
                stats[chosen[uid]]["users"] += 1
                self.user_regions[uid] = (chosen[uid], "o'zi tanlagan")
            elif added.get(uid):
                region = added[uid].most_common(1)[0][0]
                stats[region]["users_guess"] += 1
                self.user_regions[uid] = (region, "taxminiy")
            else:
                users_unknown += 1

        biggest = {}
        for row in self.family_networks():
            if row["region"] and row["region"] not in biggest:
                biggest[row["region"]] = row
        for name, s in stats.items():
            s["users_total"] = s["users"] + s["users_guess"]
            s["biggest"] = biggest.get(name)
        return stats, unknown_people, users_unknown

    # ----------------------------------------------------------- the board
    def board(self, component_key):
        """Rows, families and root for rendering one network on the map board."""
        iids = self.members_of.get(component_key)
        if not iids:
            return None
        trees = self.trees_by_component.get(component_key, [])
        # Anchor on the root of the largest source tree the network contains.
        sizes = Counter(self.source.component[t.root_person_id] for t in trees)
        anchor_tree = max(trees, key=lambda t: sizes[self.source.component[t.root_person_id]]) if trees else None
        root_id = self.of.get(anchor_tree.root_person_id) if anchor_tree else iids[0]
        root = self.individuals[root_id]

        spouse_fams = defaultdict(list)
        for vf in self.families.values():
            for p in (vf.father_id, vf.mother_id):
                if p is not None:
                    spouse_fams[p].append(vf)

        levels = {root_id: 0}
        queue = deque([root_id])
        used_families = {}
        while queue:
            iid = queue.popleft()
            lvl = levels[iid]
            ind = self.individuals[iid]
            if ind.child_family_id:
                vf = self.families[ind.child_family_id]
                used_families[vf.id] = vf
                for par in (vf.father_id, vf.mother_id):
                    if par is not None and par not in levels:
                        levels[par] = lvl - 1
                        queue.append(par)
                for sib in vf.child_ids:
                    if sib not in levels:
                        levels[sib] = lvl
                        queue.append(sib)
            for vf in spouse_fams.get(iid, []):
                used_families[vf.id] = vf
                other = vf.mother_id if vf.father_id == iid else vf.father_id
                if other is not None and other not in levels:
                    levels[other] = lvl
                    queue.append(other)
                for kid in vf.child_ids:
                    if kid not in levels:
                        levels[kid] = lvl + 1
                        queue.append(kid)

        rows = defaultdict(list)
        for iid, lvl in levels.items():
            rows[lvl].append(self.individuals[iid])
        for lvl in rows:
            rows[lvl].sort(key=lambda p: (p.child_family_id or 0, p.id))
        row_list = [
            {"level": lvl, "label": level_label(lvl, root.full_name),
             "groups": sibling_groups(rows[lvl], used_families)}
            for lvl in sorted(rows)
        ]
        families_json = [
            {"id": vf.id, "father_id": vf.father_id, "mother_id": vf.mother_id,
             "child_ids": [c for c in vf.child_ids if c in levels]}
            for vf in used_families.values()
        ]
        inds = [self.individuals[i] for i in levels]
        return {
            "root": root, "rows": row_list, "families_json": families_json,
            "generations": (max(levels.values()) - min(levels.values()) + 1) if levels else 0,
            "people": inds, "trees": trees,
        }


def _version():
    from .models import Family, MatchCandidate, Person, Tree
    return (
        Person.objects.aggregate(n=Count("id"), t=Max("updated_at")).values(),
        Family.objects.aggregate(n=Count("id"), m=Max("id")).values(),
        MatchCandidate.objects.aggregate(n=Count("id"), t=Max("updated_at")).values(),
        Tree.objects.aggregate(n=Count("id"), t=Max("updated_at")).values(),
    )


def get_unified(min_score=AUTO_MERGE_SCORE):
    key = (min_score, str([tuple(v) for v in _version()]))
    hit = _MEMO.get(key)
    if hit and time.monotonic() - hit[0] < _MEMO_TTL:
        return hit[1]
    graph = UnifiedGraph(min_score)
    _MEMO.clear()
    _MEMO[key] = (time.monotonic(), graph)
    return graph
