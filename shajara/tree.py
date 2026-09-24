"""Tree traversal helpers: BFS leveling and linking two people together."""

from collections import deque

from django.db.models import Q

from .models import Family

UP_LABELS = ["Ota-ona", "Bobo-buvi"]
DOWN_LABELS = ["Farzandlar", "Nevaralar", "Chevaralar", "Evara-chevaralar"]


def level_label(level, root_name=None):
    if level == 0:
        return root_name or "Siz"
    if level < 0:
        idx = -level - 1
        return UP_LABELS[idx] if idx < len(UP_LABELS) else f"{-level}-avlod yuqori"
    idx = level - 1
    return DOWN_LABELS[idx] if idx < len(DOWN_LABELS) else f"{level}-avlod pastki"


def compute_levels(root_person):
    """BFS outward from root_person across every marriage/parent-child link.
    Returns (levels, people, families)."""
    levels = {root_person.id: 0}
    queue = deque([root_person.id])
    people = {root_person.id: root_person}
    families = {}

    while queue:
        pid = queue.popleft()
        lvl = levels[pid]
        person = people[pid]

        if person.child_family_id:
            fam = families.get(person.child_family_id)
            if fam is None:
                fam = Family.objects.select_related("father", "mother").get(pk=person.child_family_id)
                families[fam.id] = fam
            for parent in (fam.father, fam.mother):
                if parent and parent.id not in levels:
                    levels[parent.id] = lvl - 1
                    people[parent.id] = parent
                    queue.append(parent.id)
            for child in fam.children.all():
                if child.id not in levels:
                    levels[child.id] = lvl
                    people[child.id] = child
                    queue.append(child.id)

        parent_families = Family.objects.filter(
            Q(father_id=pid) | Q(mother_id=pid)
        ).select_related("father", "mother")
        for fam in parent_families:
            families[fam.id] = fam
            for parent in (fam.father, fam.mother):
                if parent and parent.id not in levels:
                    levels[parent.id] = lvl
                    people[parent.id] = parent
                    queue.append(parent.id)
            for child in fam.children.all():
                if child.id not in levels:
                    levels[child.id] = lvl + 1
                    people[child.id] = child
                    queue.append(child.id)

    return levels, people, families


def group_people_by_level(people, levels):
    rows = {}
    for p in people.values():
        rows.setdefault(levels[p.id], []).append(p)
    for lvl in rows:
        rows[lvl].sort(key=lambda p: (p.child_family_id or 0, p.id))
    return rows


def sibling_groups(persons, families=None):
    """Cluster same-level persons who share a child_family, preserving order,
    and splice each person's spouse(s) in right next to them so married
    couples always render side by side instead of drifting to wherever
    their own birth family happens to sort."""
    families = families or {}
    by_id = {p.id: p for p in persons}

    groups, order = {}, []
    for p in persons:
        key = p.child_family_id or f"solo-{p.id}"
        if key not in groups:
            groups[key] = {"is_sibling_group": bool(p.child_family_id), "persons": []}
            order.append(key)
        groups[key]["persons"].append(p)

    placed_ids = set()
    result = []
    for key in order:
        group = groups[key]
        if all(p.id in placed_ids for p in group["persons"]):
            continue
        merged = []
        for p in group["persons"]:
            if p.id in placed_ids:
                continue
            merged.append(p)
            placed_ids.add(p.id)
            for fam in families.values():
                if fam.father_id != p.id and fam.mother_id != p.id:
                    continue
                spouse_id = fam.mother_id if fam.father_id == p.id else fam.father_id
                if spouse_id and spouse_id in by_id and spouse_id not in placed_ids:
                    merged.append(by_id[spouse_id])
                    placed_ids.add(spouse_id)
        if merged:
            result.append({"is_sibling_group": group["is_sibling_group"], "persons": merged})
    return result


def get_or_create_child_family(person):
    """The family this person is a child in, creating a blank one if needed."""
    if person.child_family_id:
        return person.child_family
    fam = Family.objects.create()
    person.child_family = fam
    person.save(update_fields=["child_family"])
    return fam


def get_or_create_spouse_family(anchor):
    """Reuse a marriage with an empty spouse slot if one exists, else start a new marriage."""
    other_field = "mother" if anchor.gender == "erkak" else "father"
    existing = anchor.parent_families().filter(**{f"{other_field}__isnull": True}).first()
    if existing:
        return existing
    fam = Family.objects.create()
    if anchor.gender == "erkak":
        fam.father = anchor
    else:
        fam.mother = anchor
    fam.save()
    return fam


def attach_existing(existing_person, anchor_person, relation):
    """Link an already-existing Person to anchor_person by `relation`.
    Returns (ok, error_message)."""

    if relation in ("ota", "ona"):
        fam = get_or_create_child_family(anchor_person)
        if relation == "ota":
            if fam.father_id:
                return False, "Bu odamning otasi allaqachon kiritilgan."
            fam.father = existing_person
        else:
            if fam.mother_id:
                return False, "Bu odamning onasi allaqachon kiritilgan."
            fam.mother = existing_person
        fam.save()

    elif relation == "farzand":
        fam = anchor_person.parent_families().first()
        if not fam:
            fam = Family.objects.create()
            if anchor_person.gender == "erkak":
                fam.father = anchor_person
            else:
                fam.mother = anchor_person
            fam.save()
        existing_person.child_family = fam
        existing_person.save(update_fields=["child_family"])

    elif relation == "akauka":
        fam = get_or_create_child_family(anchor_person)
        existing_person.child_family = fam
        existing_person.save(update_fields=["child_family"])

    elif relation == "turmush":
        fam = get_or_create_spouse_family(anchor_person)
        if anchor_person.gender == "erkak":
            if fam.mother_id:
                return False, "Bu joy band."
            fam.mother = existing_person
        else:
            if fam.father_id:
                return False, "Bu joy band."
            fam.father = existing_person
        fam.save()

    else:
        return False, "Noma'lum bog'lanish turi."

    return True, None


def person_ids_in_tree(root_person):
    """All person ids reachable from root_person (their connected tree)."""
    levels, _, _ = compute_levels(root_person)
    return set(levels.keys())


def tree_role(user, tree):
    """How `user` relates to `tree`: "owner", "muharrir" (may add and edit),
    "kuzatuvchi" (may look), or None. Cached on the tree object for the
    request, since one page asks several times."""
    if not getattr(user, "is_authenticated", False):
        return None
    cache = tree.__dict__.setdefault("_role_cache", {})
    if user.id not in cache:
        if tree.owner_id == user.id:
            cache[user.id] = "owner"
        else:
            from .models import TreeMember
            cache[user.id] = (
                TreeMember.objects.filter(tree=tree, user=user).values_list("role", flat=True).first()
            )
    return cache[user.id]


def can_view_tree(user, tree):
    # Staff review data across trees (matching, merging); their looks into
    # private trees are written to the activity log by the views.
    return (
        tree.is_public or tree_role(user, tree) is not None
        or bool(getattr(user, "is_staff", False))
    )


def can_edit_tree(user, tree):
    """The owner and the members they made editors build the tree together."""
    return tree_role(user, tree) in ("owner", "muharrir")


def can_edit_in_tree(user, tree, person):
    if not can_edit_tree(user, tree):
        return False
    if person.id == tree.root_person_id:
        return True
    return person.id in person_ids_in_tree(tree.root_person)


def can_delete_in_tree(user, tree, person):
    """Removing someone is the owner's call; an editor may only take back
    a person they added themselves."""
    if not can_edit_in_tree(user, tree, person):
        return False
    return tree_role(user, tree) == "owner" or person.added_by_id == user.id


def trees_for_user(user):
    """Every tree the user owns or was let into."""
    from .models import Tree
    return Tree.objects.filter(Q(owner=user) | Q(members__user=user)).distinct()


# ------------------------------------------------------ JSON export/import --

def export_tree_json(root):
    """A self-contained snapshot of everything reachable from root, using
    local keys instead of database ids so it can be restored anywhere."""
    levels, people, families = compute_levels(root)

    people_out = []
    for p in people.values():
        people_out.append({
            "key": f"p{p.id}",
            "first_name": p.first_name, "last_name": p.last_name, "gender": p.gender,
            "birth_date": p.birth_date.isoformat() if p.birth_date else None,
            "birth_year": p.birth_year, "death_year": p.death_year,
            "occupation": p.occupation, "location": p.location, "bio": p.bio,
            "patronymic": p.patronymic, "birth_region": p.birth_region,
            "birth_district": p.birth_district, "birth_village": p.birth_village,
            "child_family_key": f"f{p.child_family_id}" if p.child_family_id else None,
            "stories": [
                {
                    "author": story.author.username if story.author else None,
                    "text": story.text, "created_at": story.created_at.isoformat(),
                }
                for story in p.stories.select_related("author").order_by("created_at")
            ],
        })

    families_out = [
        {
            "key": f"f{f.id}",
            "father_key": f"p{f.father_id}" if f.father_id else None,
            "mother_key": f"p{f.mother_id}" if f.mother_id else None,
        }
        for f in families.values()
    ]

    return {
        "version": 1,
        "root_key": f"p{root.id}",
        "people": people_out,
        "families": families_out,
    }


def import_tree_json(user, data):
    """Recreate a tree from an export_tree_json() snapshot and make `user`
    the owner of its root person. Caller must ensure `user` has no tree yet."""
    from .models import Person, PersonStory
    from django.contrib.auth import get_user_model

    User = get_user_model()
    key_to_person = {}
    for pdata in data.get("people", []):
        person = Person.objects.create(
            first_name=pdata.get("first_name", ""), last_name=pdata.get("last_name", ""),
            gender=pdata.get("gender") or "erkak",
            birth_date=pdata.get("birth_date") or None,
            birth_year=pdata.get("birth_year", ""), death_year=pdata.get("death_year", ""),
            occupation=pdata.get("occupation", ""), location=pdata.get("location", ""),
            bio=pdata.get("bio", ""), added_by=user,
            patronymic=pdata.get("patronymic", ""), birth_region=pdata.get("birth_region", ""),
            birth_district=pdata.get("birth_district", ""), birth_village=pdata.get("birth_village", ""),
        )
        key_to_person[pdata["key"]] = person

    key_to_family = {fdata["key"]: Family.objects.create() for fdata in data.get("families", [])}
    for fdata in data.get("families", []):
        fam = key_to_family[fdata["key"]]
        fam.father = key_to_person.get(fdata.get("father_key"))
        fam.mother = key_to_person.get(fdata.get("mother_key"))
        fam.save()

    for pdata in data.get("people", []):
        person = key_to_person[pdata["key"]]
        cf_key = pdata.get("child_family_key")
        if cf_key:
            person.child_family = key_to_family.get(cf_key)
            person.save(update_fields=["child_family"])
        for sdata in pdata.get("stories", []):
            author = None
            if sdata.get("author"):
                author = User.objects.filter(username=sdata["author"]).first()
            PersonStory.objects.create(person=person, author=author, text=sdata.get("text", ""))

    return key_to_person.get(data.get("root_key"))


# ------------------------------------------------------------ what to add next --

def _own(name):
    """«Karim» -> «Karimning» (genitive, for «Karimning otasi»)."""
    return f"{name}ning"


def next_steps(tree, people, families, levels, limit=3):
    """A short, ordered list of the relatives worth adding next, so nobody has
    to guess: the person's parents first, then siblings, spouse and children,
    then the grandparents. Each item is ready to link to the add-relative form.
    Returns (steps, progress)."""
    from django.urls import reverse

    add_url = reverse("add_relative", args=[tree.url_key])
    root = people[tree.root_person_id]

    def parents(p):
        fam = families.get(p.child_family_id) if p.child_family_id else None
        return (fam.father_id, fam.mother_id) if fam else (None, None)

    def siblings_of(p):
        return [q for q in people.values() if q.id != p.id and p.child_family_id and q.child_family_id == p.child_family_id]

    def spouse_families(p):
        return [f for f in families.values() if p.id in (f.father_id, f.mother_id)]

    def step(anchor, relation, title, hint):
        return {"anchor": anchor.id, "relation": relation, "title": title, "hint": hint,
                "url": f"{add_url}?anchor={anchor.id}&relation={relation}"}

    steps = []
    father_id, mother_id = parents(root)
    if not father_id:
        steps.append(step(root, "ota", "Otangizni qo'shing", "Faqat ismi yetarli — yilni bilmasangiz, bo'sh qoldiring."))
    if not mother_id:
        steps.append(step(root, "ona", "Onangizni qo'shing", "Shajara ota-onadan o'sadi. Bir daqiqa yetadi."))
    if (father_id or mother_id) and not siblings_of(root):
        steps.append(step(root, "akauka", "Aka-uka, opa-singillaringizni qo'shing", "Yonma-yon turgan avlod shajarani jonlantiradi."))
    fams = spouse_families(root)
    spouse_present = any((f.mother_id if f.father_id == root.id else f.father_id) for f in fams)
    if not spouse_present:
        steps.append(step(root, "turmush", "Turmush o'rtog'ingizni qo'shing", "Er-xotin xaritada doim yonma-yon turadi."))
    has_children = any(p.child_family_id in {f.id for f in fams} for p in people.values())
    if not has_children:
        steps.append(step(root, "farzand", "Farzandlaringizni qo'shing", "Kelajak avlod ham shajaraning bir qismi."))

    for pid, label in ((father_id, "ota"), (mother_id, "ona")):
        person = people.get(pid) if pid else None
        if not person:
            continue
        gf, gm = parents(person)
        who = _own(person.first_name)
        if not gf:
            steps.append(step(person, "ota", f"{who} otasini qo'shing", "Bobo-buvilar hayotligida yozib qo'yish — eng qimmat ish."))
        if not gm:
            steps.append(step(person, "ona", f"{who} onasini qo'shing", "Bilganingizcha yozing, qolganini qarindoshlar to'ldiradi."))

    # Farther up: any top-most ancestor still missing a parent.
    for p in sorted(people.values(), key=lambda p: levels[p.id]):
        if len(steps) >= limit + 4:
            break
        if p.id in (root.id, father_id, mother_id):
            continue
        f, m = parents(p)
        if levels[p.id] < 0 and not f:
            steps.append(step(p, "ota", f"{_own(p.first_name)} otasini qo'shing", "Yana bir avlod ildizga yaqinlashtiradi."))

    generations = (max(levels.values()) - min(levels.values()) + 1) if levels else 1
    progress = {"people": len(people), "generations": generations, "goal": 7,
                "dots": [i < generations for i in range(7)]}
    return steps[:limit], progress


def next_intro(people_count):
    """Warm, specific wording for the guide card, by how far along the tree is."""
    if people_count <= 1:
        return {"kicker": "1-qadam", "title": "Ajoyib boshlanish! Endi ota-onangizni qo'shamiz",
                "lead": "Shajara ildizdan o'sadi. Bir tugmani bosing, ismini yozing — o'zi saqlanadi."}
    if people_count <= 3:
        return {"kicker": "Yaxshi ketyapti", "title": "Shajarangiz o'sib bormoqda",
                "lead": "Har bir yangi inson oilangiz xotirasini boyitadi. Keyingi qadamni tanlang:"}
    return {"kicker": "Zo'r natija", "title": "Yana kimni qo'shamiz?",
            "lead": "Bilgan odamingizdan boshlang — qolganini qarindoshlaringiz to'ldiradi."}