"""Merging two person records that describe the same human being.

A merge is graph surgery, not a field copy. When A and B are the same
person, their parents are the same people too, and so are a spouse listed
under both and any child listed under both. `Merger` follows those links
and folds each duplicate into the record that is kept:

    merge(keep, drop)
      ├─ fill keep's empty fields from drop, move stories, re-root trees
      ├─ parents:   drop's parent family → keep's (duplicate parents merge)
      ├─ marriages: drop's marriages move to keep; two marriages to the
      │             same spouse become one (and the spouse records merge)
      └─ children:  a child present in both families is merged, others move

Everything happens in one transaction. `preview_merge` runs the identical
code and rolls back, so what the admin is shown is exactly what will
happen. A snapshot of both graphs is stored with the MergeRecord.
"""

from django.db import transaction
from django.db.models import Q

from .matching import names_match

FILLABLE_FIELDS = [
    ("last_name", "familiya"), ("patronymic", "otasining ismi"), ("birth_date", "tug'ilgan sana"),
    ("birth_year", "tug'ilgan yil"), ("death_year", "vafot yili"), ("birth_region", "viloyat"),
    ("birth_district", "tuman"), ("birth_village", "qishloq/mahalla"), ("occupation", "kasb"),
    ("location", "yashash joyi"), ("bio", "qisqacha ma'lumot"), ("photo", "surat"),
]
MAX_MERGES = 250


class MergeConflict(Exception):
    """The data contradicts itself; nothing was changed."""


class _Rollback(Exception):
    pass


class Merger:
    def __init__(self):
        self.log = []
        self.alias = {}         # dropped person id -> id it was merged into
        self.family_alias = {}  # dropped family id -> family it was folded into
        self.merged = 0

    # ---------------------------------------------------------------- utils
    def note(self, kind, text):
        self.log.append({"kind": kind, "text": text})

    def resolve(self, pid):
        while pid in self.alias:
            pid = self.alias[pid]
        return pid

    def resolve_family(self, fid):
        while fid in self.family_alias:
            fid = self.family_alias[fid]
        return fid

    @staticmethod
    def _person(pid):
        from .models import Person
        return Person.objects.filter(pk=pid).first()

    # --------------------------------------------------------------- people
    def merge(self, keep_id, drop_id, depth=0):
        from .models import Family, Person, PersonStory, Tree

        keep_id, drop_id = self.resolve(keep_id), self.resolve(drop_id)
        if not keep_id or not drop_id or keep_id == drop_id:
            return
        if depth > 30 or self.merged >= MAX_MERGES:
            raise MergeConflict("Birlashtirish zanjiri juda uzun — ma'lumotlarda xato bo'lishi mumkin.")

        keep, drop = self._person(keep_id), self._person(drop_id)
        if keep is None or drop is None:
            return
        if keep.gender != drop.gender:
            raise MergeConflict(
                f"«{keep.full_name}» va «{drop.full_name}» jinsi har xil — ular bir odam bo'la olmaydi."
            )

        self.merged += 1
        prefix = "Asosiy juftlik" if depth == 0 else "Bog'liq shaxs"
        self.note("person", f"{prefix}: «{drop.full_name}» (#{drop.id}) → «{keep.full_name}» (#{keep.id})")

        filled, differ = [], []
        for field, label in FILLABLE_FIELDS:
            kv, dv = getattr(keep, field), getattr(drop, field)
            if not kv and dv:
                setattr(keep, field, dv)
                filled.append(label)
            elif kv and dv and str(kv).strip().lower() != str(dv).strip().lower():
                differ.append(f"{label}: «{kv}» qoldi, «{dv}» tashlandi")
        keep.save()
        if filled:
            self.note("fill", f"«{keep.full_name}»ga to'ldirildi: " + ", ".join(filled))
        for d in differ:
            self.note("differ", d)

        moved = PersonStory.objects.filter(person_id=drop_id).update(person_id=keep_id)
        if moved:
            self.note("story", f"{moved} ta hikoya ko'chirildi")
        for tree in Tree.objects.filter(root_person_id=drop_id):
            tree.root_person_id = keep_id
            tree.save(update_fields=["root_person"])
            self.note("tree", f"«{tree.name}» shajarasining bosh shaxsi endi «{keep.full_name}»")

        self.alias[drop_id] = keep_id

        # Parents.
        kf, df = keep.child_family_id, drop.child_family_id
        if df:
            Person.objects.filter(pk=drop_id).update(child_family=None)
            if not kf:
                Person.objects.filter(pk=keep_id).update(child_family_id=df)
                self.note("family", f"«{keep.full_name}» ota-onasi bilan ulandi")
            elif kf != df:
                self.merge_families(kf, df, depth)

        # Marriages.
        for fam in Family.objects.filter(Q(father_id=drop_id) | Q(mother_id=drop_id)):
            if fam.father_id == drop_id:
                fam.father_id = keep_id
            else:
                fam.mother_id = keep_id
            fam.save()
        self.dedupe_marriages(keep_id, depth)

        Person.objects.filter(pk=drop_id).delete()

    # ------------------------------------------------------------- families
    def merge_families(self, keep_fid, drop_fid, depth):
        from .models import Family, Person

        keep_fid, drop_fid = self.resolve_family(keep_fid), self.resolve_family(drop_fid)
        if keep_fid == drop_fid:
            return
        kf = Family.objects.filter(pk=keep_fid).first()
        df = Family.objects.filter(pk=drop_fid).first()
        if kf is None or df is None:
            return
        self.family_alias[drop_fid] = keep_fid

        for slot in ("father", "mother"):
            kp = self.resolve(getattr(kf, f"{slot}_id")) if getattr(kf, f"{slot}_id") else None
            dp = self.resolve(getattr(df, f"{slot}_id")) if getattr(df, f"{slot}_id") else None
            if dp and not kp:
                setattr(df, f"{slot}_id", None)
                df.save()
                setattr(kf, f"{slot}_id", dp)
                kf.save()
            elif kp and dp and kp != dp:
                # Detach first so the recursive merge does not see this family
                # as a second marriage of the kept parent.
                setattr(df, f"{slot}_id", None)
                df.save()
                self.merge(kp, dp, depth + 1)
                # The recursion may have folded the kept family into another
                # marriage of the same couple; carry on with wherever it went.
                keep_fid = self.resolve_family(keep_fid)
                kf = Family.objects.get(pk=keep_fid)

        keep_kids = list(Person.objects.filter(child_family_id=keep_fid))
        for child in list(Person.objects.filter(child_family_id=drop_fid)):
            twin = next((k for k in keep_kids if names_match(k, child)), None)
            if twin:
                Person.objects.filter(pk=child.id).update(child_family=None)
                self.merge(twin.id, child.id, depth + 1)
            else:
                Person.objects.filter(pk=child.id).update(child_family_id=keep_fid)
                self.note("family", f"«{child.full_name}» umumiy oilaga qo'shildi")

        Family.objects.filter(pk=drop_fid).delete()

    def dedupe_marriages(self, pid, depth):
        """Two marriages of one person to the same spouse become one."""
        from .models import Family

        def other(fam):
            return fam.mother_id if fam.father_id == pid else fam.father_id

        changed = True
        while changed:
            changed = False
            fams = list(Family.objects.filter(Q(father_id=pid) | Q(mother_id=pid)).order_by("id"))
            with_spouse = [f for f in fams if other(f)]
            for i, a in enumerate(fams):
                for b in fams[i + 1:]:
                    sa, sb = other(a), other(b)
                    same = False
                    if sa and sb:
                        pa, pb = self._person(sa), self._person(sb)
                        same = sa == sb or (pa and pb and names_match(pa, pb))
                    elif not sa and not sb:
                        same = True
                    elif len(with_spouse) == 1:
                        # A family recorded without the spouse is joined to the
                        # only marriage there is; with several it stays apart.
                        same = True
                    if same:
                        keep_f, drop_f = (a, b) if (sa or not sb) else (b, a)
                        self.note("family", "Bir xil nikoh ikki marta yozilgan edi — bittaga birlashtirildi")
                        self.merge_families(keep_f.id, drop_f.id, depth + 1)
                        changed = True
                        break
                if changed:
                    break


# --------------------------------------------------------------- snapshots --

def component_ids(person_id):
    from .models import Person
    from .tree import person_ids_in_tree
    person = Person.objects.filter(pk=person_id).first()
    return person_ids_in_tree(person) if person else set()


def graph_snapshot(person_ids):
    from .models import Family, Person
    people = Person.objects.filter(pk__in=person_ids)
    fam_ids = set(people.exclude(child_family=None).values_list("child_family_id", flat=True))
    fam_ids |= set(Family.objects.filter(Q(father_id__in=person_ids) | Q(mother_id__in=person_ids))
                   .values_list("id", flat=True))
    return {
        "people": [
            {"id": p.id, "first_name": p.first_name, "last_name": p.last_name, "patronymic": p.patronymic,
             "gender": p.gender, "birth_year": p.birth_year,
             "birth_date": p.birth_date.isoformat() if p.birth_date else None,
             "death_year": p.death_year, "birth_region": p.birth_region, "birth_district": p.birth_district,
             "birth_village": p.birth_village, "location": p.location, "occupation": p.occupation,
             "bio": p.bio, "child_family_id": p.child_family_id}
            for p in people
        ],
        "families": list(Family.objects.filter(pk__in=fam_ids).values("id", "father_id", "mother_id")),
    }


def trees_touched(person_ids):
    from .models import Tree
    return [
        {"id": t.id, "name": t.name, "owner": t.owner.username, "visibility": t.visibility}
        for t in Tree.objects.filter(root_person_id__in=person_ids).select_related("owner")
    ]


# ------------------------------------------------------------------ public --

def _run(keep_id, drop_id):
    before = component_ids(keep_id) | component_ids(drop_id)
    merger = Merger()
    merger.merge(keep_id, drop_id)
    return merger, before


def preview_merge(keep_id, drop_id):
    """Dry run: returns (log, trees, error). Nothing is saved."""
    trees = trees_touched(component_ids(keep_id) | component_ids(drop_id))
    try:
        with transaction.atomic():
            merger, _ = _run(keep_id, drop_id)
            result = (merger.log, merger.merged, trees, None)
            raise _Rollback
    except _Rollback:
        return result
    except MergeConflict as exc:
        return [], 0, trees, str(exc)


def execute_merge(keep_id, drop_id, actor=None, candidate=None):
    """Merge for real and write a MergeRecord. Raises MergeConflict."""
    from .models import MatchCandidate, MergeRecord, Person

    keep = Person.objects.get(pk=keep_id)
    drop = Person.objects.get(pk=drop_id)
    with transaction.atomic():
        ids = component_ids(keep_id) | component_ids(drop_id)
        snapshot = graph_snapshot(ids)
        trees = trees_touched(ids)
        kept_name, dropped_name = keep.full_name, drop.full_name
        merger, _ = _run(keep_id, drop_id)
        record = MergeRecord.objects.create(
            actor=actor, candidate=candidate, kept_person_id=keep_id,
            kept_name=kept_name, dropped_name=dropped_name,
            persons_merged=merger.merged, log=merger.log, trees=trees, snapshot=snapshot,
        )
        if candidate is not None:
            candidate.status = "merged"
            candidate.reviewed_by = actor
            from django.utils import timezone
            candidate.reviewed_at = timezone.now()
            candidate.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
        # Hypotheses about records that no longer exist are meaningless now.
        MatchCandidate.objects.filter(status="pending").filter(
            Q(person_a__isnull=True) | Q(person_b__isnull=True)
        ).delete()
    return record
