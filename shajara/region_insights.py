"""Per-region figures for the admin map: who signed up where, who is online
right now, which trees belong to a region and how those trees are joined to
trees elsewhere.

A tree belongs to the region its root person was born in; failing that, to
its owner's region; failing that, to where most people of its family network
come from. Two trees are "joined" when the unified graph (unified.py) puts
them in one family network — through a confirmed match or a real merge.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from itertools import combinations

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from .models import UserProfile
from .presence import online_since
from .regions import ABROAD, REGION_NAMES, SHORT

UNKNOWN = ""
BUCKETS = REGION_NAMES + [ABROAD]


def _ago(moment, now):
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 60:
        return "hozirgina"
    return f"{seconds // 60} daq. oldin"


def online_users(user_regions, limit=None):
    """Online accounts, newest first, each with the region they count under."""
    now = timezone.now()
    rows = []
    qs = (UserProfile.objects.filter(last_seen__gte=online_since(), user__is_active=True)
          .select_related("user").order_by("-last_seen"))
    for profile in qs[:limit] if limit else qs:
        user = profile.user
        if profile.region:
            region, how = profile.region, "o'zi tanlagan"
        else:
            region, how = user_regions.get(user.id, (UNKNOWN, ""))
        rows.append({
            "id": user.id, "username": user.username, "name": user.get_full_name() or user.username,
            "region": region, "how": how, "ago": _ago(profile.last_seen, now),
            "staff": user.is_staff, "url": reverse("boshqaruv:user_detail", args=[user.id]),
        })
    return rows


def live_counts(user_regions):
    users = online_users(user_regions)
    per_region = Counter(u["region"] for u in users)
    return {
        "total": len(users),
        "unknown": per_region.get(UNKNOWN, 0),
        "regions": {name: per_region.get(name, 0) for name in BUCKETS},
        "users": users[:60],
        "at": timezone.localtime().strftime("%H:%M:%S"),
    }


def build(u, min_score):
    """Everything the map page shows, keyed by region name."""
    stats, unknown_people, users_unknown = u.region_stats()   # also fills u.user_regions
    User = get_user_model()
    now = timezone.now()
    month_ago = now - timedelta(days=30)

    rows = {name: {
        "name": name, "short": SHORT.get(name, "Chet el"),
        "users": 0, "users_guess": stats[name]["users_guess"], "new_30": 0, "online": 0,
        "trees": 0, "trees_family": 0, "trees_learning": 0, "trees_connected": 0,
        "people": stats[name]["people"], "records": stats[name]["records"],
        "duplicates": stats[name]["duplicates"],
        "partners": Counter(), "inner_links": 0, "kin": Counter(), "marriage_ties": 0, "top_trees": [], "online_users": [],
    } for name in BUCKETS}

    # ---- accounts
    for region, joined in UserProfile.objects.exclude(region="").values_list("region", "user__date_joined"):
        if region in rows:
            rows[region]["users"] += 1
            if joined >= month_ago:
                rows[region]["new_30"] += 1

    live = live_counts(u.user_regions)
    for entry in live["users"]:
        if entry["region"] in rows:
            rows[entry["region"]]["online"] += 1
            if len(rows[entry["region"]]["online_users"]) < 12:
                rows[entry["region"]]["online_users"].append(entry)

    # ---- trees and the networks joining them
    network_region = {}
    network_size = {}
    for net in u.family_networks():
        network_region[net["key"]] = net["region"]
        network_size[net["key"]] = net["people"]

    tree_region = {}
    tree_rows = []
    for comp, trees in u.trees_by_component.items():
        for tree in trees:
            iid = u.of.get(tree.root_person_id)
            region = u.individuals[iid].region if iid else ""
            if not region:
                region = u.user_regions.get(tree.owner_id, ("", ""))[0]
            if not region:
                region = network_region.get(comp, "")
            tree_region[tree.pk] = region
            tree_rows.append((tree, comp, region))

    for tree, comp, region in tree_rows:
        if region not in rows:
            continue
        r = rows[region]
        joined = len(u.trees_by_component[comp]) > 1
        r["trees"] += 1
        r["trees_learning" if tree.kind == "talimiy" else "trees_family"] += 1
        r["trees_connected"] += joined
        r["top_trees"].append({
            "name": tree.name, "owner": tree.owner.username, "people": network_size.get(comp, 0),
            "joined": len(u.trees_by_component[comp]) - 1, "kind": tree.kind,
            "url": reverse("boshqaruv:tree_detail", args=[tree.pk]),
        })

    links = Counter()
    multi_networks = 0
    for comp, trees in u.trees_by_component.items():
        if len(trees) < 2:
            continue
        multi_networks += 1
        regions = sorted({tree_region[t.pk] for t in trees if tree_region.get(t.pk) in rows})
        if len(regions) == 1:
            rows[regions[0]]["inner_links"] += 1
        for a, b in combinations(regions, 2):
            links[(a, b)] += 1
            rows[a]["partners"][b] += 1
            rows[b]["partners"][a] += 1

    # Marriages between people born in different regions tie those regions
    # together even when the two families have no shared tree yet.
    marriages = Counter()
    for fam in u.families.values():
        if fam.father_id is None or fam.mother_id is None:
            continue
        if not u.trees_by_component.get(u.component.get(fam.father_id)):
            continue
        ra, rb = u.individuals[fam.father_id].region, u.individuals[fam.mother_id].region
        if ra in rows and rb in rows and ra != rb:
            a, b = sorted((ra, rb))
            marriages[(a, b)] += 1
            rows[a]["marriage_ties"] += 1
            rows[b]["marriage_ties"] += 1
            rows[a]["kin"][b] += 1
            rows[b]["kin"][a] += 1

    for r in rows.values():
        r["kin"] = [{"name": n, "short": SHORT.get(n, "Chet el"), "n": c} for n, c in r["kin"].most_common()]
        r["top_trees"].sort(key=lambda t: (-t["joined"], -t["people"]))
        r["top_trees"] = r["top_trees"][:6]
        r["partners"] = [{"name": n, "short": SHORT.get(n, "Chet el"), "n": c} for n, c in r["partners"].most_common()]
        r["users_total"] = r["users"] + r["users_guess"]
        biggest = stats[r["name"]]["biggest"]
        r["biggest"] = ({"people": biggest["people"], "trees": len(biggest["trees"]),
                         "url": f"{reverse('boshqaruv:unified_board', args=[biggest['key']])}?chegara={min_score}"}
                        if biggest else None)
        r["networks_url"] = f"{reverse('boshqaruv:unified')}?chegara={min_score}&viloyat={r['name']}"

    all_users = User.objects.count()
    known_users = sum(r["users"] for r in rows.values())
    trees_total = len(tree_rows)
    return {
        "rows": rows,
        "links": [{"a": a, "b": b, "n": n} for (a, b), n in links.most_common()],
        "marriages": [{"a": a, "b": b, "n": n} for (a, b), n in marriages.most_common()],
        "live": {k: live[k] for k in ("total", "unknown", "regions", "at")},
        "totals": {
            "users": all_users, "users_known": known_users,
            "users_known_pct": round(known_users / all_users * 100) if all_users else 0,
            "users_guess": sum(r["users_guess"] for r in rows.values()), "users_unknown": users_unknown,
            "new_30": User.objects.filter(date_joined__gte=month_ago).count(),
            "online": live["total"], "online_unknown": live["unknown"],
            "trees": trees_total, "trees_connected": sum(r["trees_connected"] for r in rows.values()),
            "trees_unplaced": sum(1 for _, _, region in tree_rows if region not in rows),
            "networks_multi": multi_networks, "cross_links": sum(links.values()),
            "marriage_ties": sum(marriages.values()),
            "people_unknown": unknown_people,
        },
    }
