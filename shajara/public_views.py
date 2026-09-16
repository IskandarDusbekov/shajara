"""Pages anyone can open without an account: the landing page, open (SEO)
tree and person pages, share pages behind the share cards, sitemap and
robots.txt.

Only trees an admin marked as featured, public and of the learning kind are
ever rendered here — family trees hold living people and never are.
"""

import json
import re

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.cache import cache_control

from . import share_cards
from .book import Lineage, life_span, long_date, ordinal_generation
from .models import REGION_CHOICES, Person, PersonStory, QuizAttempt, Tree
from .tree import compute_levels

OPEN_CACHE_SECONDS = 600
REGION_LABELS = dict(REGION_CHOICES)


# ---------------------------------------------------------------- helpers --

def site_url(request):
    return (getattr(settings, "SITE_URL", "") or request.build_absolute_uri("/")).rstrip("/")


def site_host(request):
    return re.sub(r"^https?://", "", site_url(request))


def uz_slug(text):
    """«Mirzo Ulug'bek» -> "mirzo-ulugbek" (apostrophes of o' and g' dropped)."""
    text = re.sub(r"[ʻʼ‘’'`]", "", text or "")
    return slugify(text)[:80] or "shaxs"


def ld_json(data):
    """Schema.org data for a <script type="application/ld+json"> block."""
    if isinstance(data, list):
        graph = [{k: v for k, v in item.items() if k != "@context"} for item in data]
        data = {"@context": "https://schema.org", "@graph": graph}
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")


def open_trees():
    return (Tree.objects.filter(is_featured=True, visibility="public", kind="talimiy")
            .exclude(slug__isnull=True).exclude(slug="").select_related("root_person", "owner")
            .order_by("-featured_at", "name"))


def _excerpt(text, limit=170):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:—-") + "…"


def generation_count(levels):
    return (max(levels.values()) - min(levels.values()) + 1) if levels else 0


def tree_stats(tree):
    """People and generations of any tree (cached briefly)."""
    key = f"tree-stats:{tree.pk}:{tree.updated_at.timestamp()}"
    stats = cache.get(key)
    if stats is None:
        levels, _, _ = compute_levels(tree.root_person)
        stats = {"people": len(levels), "generations": generation_count(levels)}
        cache.set(key, stats, 120)
    return stats


def open_tree_data(tree):
    """Everything the open tree and person pages show, as plain data."""
    key = f"open-tree:{tree.pk}:{tree.updated_at.timestamp()}"
    data = cache.get(key)
    if data is not None:
        return data

    lin = Lineage(tree.root_person)
    top = min(lin.levels.values()) if lin.levels else 0
    stories = {}
    for s in PersonStory.objects.filter(person_id__in=lin.people.keys()).order_by("created_at"):
        stories.setdefault(s.person_id, []).append(s.text)

    people = {}
    for pid, p in lin.people.items():
        place = ", ".join(x for x in (p.birth_village, p.birth_district,
                                       REGION_LABELS.get(p.birth_region, "") if p.birth_region not in ("", "Boshqa") else "")
                          if x)
        slug = f"{pid}-{uz_slug(p.full_name)}"
        siblings = []
        if p.child_family_id:
            siblings = [c for c in lin.people if c != pid and lin.people[c].child_family_id == p.child_family_id]
        people[pid] = {
            "id": pid, "name": p.full_name, "first_name": p.first_name, "gender": p.gender,
            "patronymic": p.patronymic, "years": life_span(p), "birth_year": p.display_year or "",
            "death_year": p.death_year or "", "birth_date": long_date(p.birth_date) if p.birth_date else "",
            "birth_iso": p.birth_date.isoformat() if p.birth_date else "",
            "occupation": p.occupation, "place": place, "location": p.location, "bio": p.bio,
            "excerpt": _excerpt(p.bio), "number": lin.number.get(pid) or "", "slug": slug,
            "url": reverse("open_person", args=[tree.slug, slug]),
            "generation": lin.levels[pid] - top + 1, "is_root": pid == tree.root_person_id,
            "father": lin.father.get(pid), "mother": lin.mother.get(pid),
            "spouses": list(lin.spouses.get(pid, [])), "children": list(lin.children.get(pid, [])),
            "siblings": siblings, "stories": stories.get(pid, []),
        }

    order = {pid: i for i, (pid, _num, _depth) in enumerate(lin.register)}
    generations = {}
    for pid, info in people.items():
        generations.setdefault(info["generation"], []).append(pid)
    gen_list = []
    for n in sorted(generations):
        ids = sorted(generations[n], key=lambda pid: (order.get(pid, order.get(lin.married_to.get(pid), 10 ** 6) + 0.5), pid))
        gen_list.append({"n": n, "title": ordinal_generation(n), "ids": ids})

    data = {
        "people": people, "generations": gen_list,
        "count": len(people), "generation_count": len(gen_list),
        "story_count": sum(len(v) for v in stories.values()),
        "with_bio": sum(1 for v in people.values() if v["bio"]),
    }
    cache.set(key, data, OPEN_CACHE_SECONDS)
    return data


def _person_ld(info, base, tree):
    item = {"@type": "Person", "name": info["name"], "url": base + info["url"]}
    if info["birth_iso"]:
        item["birthDate"] = info["birth_iso"]
    elif info["birth_year"].strip("~").isdigit():
        item["birthDate"] = info["birth_year"].strip("~")
    if info["death_year"].strip("~").isdigit():
        item["deathDate"] = info["death_year"].strip("~")
    if info["occupation"]:
        item["jobTitle"] = info["occupation"]
    if info["excerpt"]:
        item["description"] = info["excerpt"]
    return item


def _breadcrumbs(base, items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": name, "item": base + url} for i, (name, url) in enumerate(items)
    ]}


# ------------------------------------------------------------ landing page --

def landing_view(request):
    if request.user.is_authenticated:
        return redirect("my_trees")
    trees = []
    for tree in open_trees()[:6]:
        data = open_tree_data(tree)
        trees.append({"tree": tree, "people": data["count"], "generations": data["generation_count"],
                      "stories": data["story_count"]})
    base = site_url(request)
    faq = LANDING_FAQ
    ld = [
        {"@context": "https://schema.org", "@type": "WebSite", "name": "e-Shajara", "url": base + "/",
         "inLanguage": "uz", "description": LANDING_DESCRIPTION},
        {"@context": "https://schema.org", "@type": "Organization", "name": "e-Shajara", "url": base + "/",
         "logo": base + reverse("open_tree_card_default")},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]},
    ]
    return render(request, "shajara/landing.html", {
        "open_trees": trees,
        "stats": {
            "people": Person.objects.count(),
            "trees": Tree.objects.count(),
            "learning": Tree.objects.filter(visibility="public", kind="talimiy").count(),
        },
        "faq": faq, "ld_json": ld_json(ld), "base": base,
        "canonical": base + "/", "meta_description": LANDING_DESCRIPTION,
        "og_image": base + reverse("open_tree_card_default"),
    })


LANDING_DESCRIPTION = (
    "e-Shajara — oila shajarasini qarindoshlar bilan birga tuzish, yetti avlodni bir sahifada saqlash va "
    "Temuriylar, Boburiylar kabi sulolalar shajarasi orqali tarixni o'rganish uchun bepul platforma."
)

LANDING_FAQ = [
    ("e-Shajara bepulmi?",
     "Ha. Ro'yxatdan o'tish, shajara tuzish, qarindoshlarni taklif qilish, PDF kitob va rasm yuklab olish bepul."),
    ("Oilam haqidagi ma'lumotlarni kim ko'radi?",
     "Oila shajarasi standart holatda shaxsiy: uni faqat siz va o'zingiz taklif qilgan qarindoshlar ko'radi. "
     "Oila shajaralari qidiruv tizimlariga chiqarilmaydi."),
    ("Qarindoshlarim qanday qo'shiladi?",
     "Shajaradagi «A'zolar» bo'limida taklif havolasini yaratib, Telegram orqali yuborasiz. Har bir kishiga "
     "muharrir (qo'sha oladi) yoki kuzatuvchi (faqat ko'radi) huquqini berasiz."),
    ("Bobomning yilini aniq bilmasam-chi?",
     "Faqat ism majburiy. Yilni «taxminan» deb belgilashingiz yoki bo'sh qoldirishingiz mumkin — keyinroq "
     "qarindoshlar aniqlashtiradi."),
    ("PDF kitobda nimalar bo'ladi?",
     "Muqova, mundarija, har bir avlod va oila bo'yicha boblar, har bir inson haqida maqola va hikoyalar. "
     "Har bir nusxada haqiqiyligini tekshirish mumkin bo'lgan kod va QR bor."),
    ("O'qituvchi yoki abituriyent sifatida qanday foydalanaman?",
     "Kutubxonadagi tayyor sulola shajaralarini o'rganasiz, avtomatik tuziladigan testlar bilan o'zingizni "
     "sinaysiz yoki darsingiz uchun o'z ta'limiy shajarangizni tuzib, o'quvchilarni taklif qilasiz."),
]


# --------------------------------------------------------------- open pages --

def open_index_view(request):
    trees = []
    for tree in open_trees():
        data = open_tree_data(tree)
        trees.append({"tree": tree, "people": data["count"], "generations": data["generation_count"],
                      "stories": data["story_count"]})
    base = site_url(request)
    description = ("Temuriylar, Boburiylar, Chingiziylar va boshqa sulolalarning to'liq shajaralari: avlodlar, "
                   "tarjimai hollar, tarixiy hikoyalar va manbalar. Ro'yxatdan o'tmasdan o'qing.")
    ld = [
        _breadcrumbs(base, [("Bosh sahifa", "/"), ("Tarixiy shajaralar", reverse("open_index"))]),
        {"@context": "https://schema.org", "@type": "CollectionPage", "name": "Tarixiy shajaralar",
         "url": base + reverse("open_index"), "description": description, "inLanguage": "uz",
         "hasPart": [{"@type": "CreativeWork", "name": t["tree"].name,
                      "url": base + reverse("open_tree", args=[t["tree"].slug])} for t in trees]},
    ]
    return render(request, "shajara/site/open_index.html", {
        "trees": trees, "base": base, "canonical": base + reverse("open_index"),
        "meta_description": description, "ld_json": ld_json(ld),
        "og_image": base + reverse("open_tree_card_default"),
    })


def _open_tree_or_404(slug):
    tree = open_trees().filter(slug=slug).first()
    if not tree:
        raise Http404
    return tree


def open_tree_view(request, slug):
    tree = _open_tree_or_404(slug)
    data = open_tree_data(tree)
    if request.method == "GET":
        Tree.objects.filter(pk=tree.pk).update(public_views=F("public_views") + 1)

    base = site_url(request)
    url = reverse("open_tree", args=[tree.slug])
    people = data["people"]
    generations = [{"n": g["n"], "title": g["title"], "people": [people[pid] for pid in g["ids"]]}
                   for g in data["generations"]]
    root = people.get(tree.root_person_id)
    highlights = [p for p in people.values() if p["stories"]]
    highlights.sort(key=lambda p: (-len(p["stories"]), p["generation"]))
    description = tree.seo_description or _excerpt(tree.description, 158) or (
        f"{tree.name}: {data['count']} shaxs, {data['generation_count']} avlod — tarjimai hollar va hikoyalar.")
    ld = [
        _breadcrumbs(base, [("Bosh sahifa", "/"), ("Tarixiy shajaralar", reverse("open_index")), (tree.name, url)]),
        {"@context": "https://schema.org", "@type": "Article", "headline": tree.name, "description": description,
         "inLanguage": "uz", "url": base + url, "image": base + reverse("open_tree_card", args=[tree.slug]),
         "dateModified": tree.updated_at.isoformat(), "datePublished": tree.created_at.isoformat(),
         "author": {"@type": "Organization", "name": "e-Shajara"},
         "about": [_person_ld(p, base, tree) for p in list(people.values())[:60]]},
    ]
    others = [t for t in open_trees() if t.pk != tree.pk][:3]
    return render(request, "shajara/site/open_tree.html", {
        "tree": tree, "data": data, "generations": generations, "root": root,
        "highlights": highlights[:4], "sources": tree.source_list, "others": others,
        "base": base, "canonical": base + url, "meta_description": description,
        "og_image": base + reverse("open_tree_card", args=[tree.slug]), "ld_json": ld_json(ld),
        "share_text": f"{tree.name} — {data['count']} shaxs, {data['generation_count']} avlod",
    })


def open_person_view(request, slug, person_slug):
    tree = _open_tree_or_404(slug)
    match = re.match(r"^(\d+)(?:-|$)", person_slug)
    if not match:
        raise Http404
    data = open_tree_data(tree)
    info = data["people"].get(int(match.group(1)))
    if not info:
        raise Http404
    if info["slug"] != person_slug:
        return redirect(info["url"], permanent=True)

    people = data["people"]
    rel = lambda ids: [people[i] for i in ids if i in people]   # noqa: E731
    parents = rel([info["father"], info["mother"]])
    generation = next(g for g in data["generations"] if g["n"] == info["generation"])
    peers = [people[i] for i in generation["ids"] if i != info["id"]][:6]

    base = site_url(request)
    tree_url = reverse("open_tree", args=[tree.slug])
    title_years = f" ({info['years']})" if info["years"] else ""
    description = info["excerpt"] or (
        f"{info['name']}{title_years} — {tree.name} shajarasida: ota-onasi, farzandlari va hikoyalar.")
    person = _person_ld(info, base, tree)
    person["@context"] = "https://schema.org"
    for key, ids in (("parent", [info["father"], info["mother"]]), ("children", info["children"]),
                     ("spouse", info["spouses"]), ("sibling", info["siblings"])):
        linked = [{"@type": "Person", "name": people[i]["name"], "url": base + people[i]["url"]}
                  for i in ids if i in people]
        if linked:
            person[key] = linked
    ld = [
        _breadcrumbs(base, [("Bosh sahifa", "/"), ("Tarixiy shajaralar", reverse("open_index")),
                            (tree.name, tree_url), (info["name"], info["url"])]),
        person,
    ]
    return render(request, "shajara/site/open_person.html", {
        "tree": tree, "p": info, "parents": parents, "spouses": rel(info["spouses"]),
        "children": rel(info["children"]), "siblings": rel(info["siblings"]), "peers": peers,
        "generation": generation, "data": data,
        "base": base, "canonical": base + info["url"], "meta_description": description,
        "page_title": f"{info['name']}{title_years} — {tree.name}",
        "og_image": base + reverse("open_tree_card", args=[tree.slug]), "ld_json": ld_json(ld),
    })


@cache_control(public=True, max_age=3600)
def open_tree_card_view(request, slug=None):
    if slug is None:
        png = share_cards.avlod_card(7, 0, "e-Shajara — oila va tarix shajarasi", host=site_host(request))
        return HttpResponse(png, content_type="image/png")
    tree = _open_tree_or_404(slug)
    data = open_tree_data(tree)
    png = share_cards.tree_card(tree, data["count"], data["generation_count"], data["story_count"],
                                host=site_host(request))
    return HttpResponse(png, content_type="image/png")


# ------------------------------------------------------------- share pages --

def _share_page(request, *, title, description, card_url, headline, sub, tree=None):
    base = site_url(request)
    return render(request, "shajara/site/share.html", {
        "title": title, "meta_description": description, "og_image": base + card_url, "card_url": card_url,
        "headline": headline, "sub": sub, "base": base, "canonical": request.build_absolute_uri(request.path),
        "open_tree": tree if tree and tree.is_open_page else None,
    })


def _attempt(token):
    pk = share_cards.read_token("test", token)
    attempt = QuizAttempt.objects.select_related("tree").filter(pk=pk).first() if pk else None
    if not attempt:
        raise Http404
    return attempt


def share_test_view(request, token):
    a = _attempt(token)
    name = a.tree.name if a.tree.is_public else None
    what = f"«{name}»" if name else "oilasi shajarasi"
    return _share_page(
        request, tree=a.tree,
        title=f"{a.score}/{a.total} — {what} bo'yicha test natijasi",
        description="Siz nechta savolga to'g'ri javob bera olasiz? e-Shajara'da shajara bo'yicha testni ishlab ko'ring.",
        card_url=reverse("share_test_png", args=[token]),
        headline=f"{what.capitalize() if not name else what} bo'yicha {a.score}/{a.total}",
        sub="Siz nechta topasiz? Shajarangizni tuzing yoki tayyor sulola shajaralari bo'yicha o'zingizni sinang.",
    )


@cache_control(public=True, max_age=3600)
def share_test_png_view(request, token):
    a = _attempt(token)
    png = share_cards.test_card(a.score, a.total, a.tree.name if a.tree.is_public else None,
                                learning=a.tree.is_learning, host=site_host(request))
    return HttpResponse(png, content_type="image/png")


def _avlod_tree(token):
    pk = share_cards.read_token("avlod", token)
    tree = Tree.objects.select_related("root_person").filter(pk=pk).first() if pk else None
    if not tree:
        raise Http404
    return tree


def share_avlod_view(request, token):
    tree = _avlod_tree(token)
    stats = tree_stats(tree)
    g = stats["generations"]
    headline = f"Men {g} avlodimni bilaman" if g >= 7 else f"Men 7 avloddan {min(g, 7)} tasini bilaman"
    return _share_page(
        request, tree=tree, title=f"#YettiOtam — {headline}",
        description="Yetti otangni bilasanmi? Oila shajarangizni qarindoshlar bilan birga tuzing — e-Shajara.",
        card_url=reverse("share_avlod_png", args=[token]), headline=headline,
        sub="Yetti otangni bilasanmi? Bobo-buvilaringizdan so'rang, qarindoshlarni taklif qiling va yetti avlodni bir joyga jamlang.",
    )


@cache_control(public=True, max_age=600)
def share_avlod_png_view(request, token):
    tree = _avlod_tree(token)
    stats = tree_stats(tree)
    png = share_cards.avlod_card(stats["generations"], stats["people"],
                                 tree.name if tree.is_public else None, host=site_host(request))
    return HttpResponse(png, content_type="image/png")


# -------------------------------------------------------- sitemap & robots --

def sitemap_view(request):
    base = site_url(request)
    urls = [(base + "/", None, "1.0"), (base + reverse("open_index"), None, "0.9")]
    for tree in open_trees():
        data = open_tree_data(tree)
        lastmod = tree.updated_at.date().isoformat()
        urls.append((base + reverse("open_tree", args=[tree.slug]), lastmod, "0.8"))
        for info in data["people"].values():
            urls.append((base + info["url"], lastmod, "0.6"))
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod, priority in urls:
        lines.append("  <url><loc>%s</loc>%s<priority>%s</priority></url>" % (
            loc.replace("&", "&amp;"), f"<lastmod>{lastmod}</lastmod>" if lastmod else "", priority))
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml; charset=utf-8")


def robots_view(request):
    base = site_url(request)
    body = "\n".join([
        "User-agent: *",
        "Allow: /$",
        "Allow: /shajaralar/",
        "Allow: /static/",
        "Disallow: /shajara/",
        "Disallow: /boshqaruv/",
        "Disallow: /admin/",
        "Disallow: /taklif/",
        "Disallow: /media/",
        "",
        f"Sitemap: {base}/sitemap.xml",
        "",
    ])
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


def sitemap_count():
    """How many URLs the sitemap lists — for the admin's SEO page."""
    total = 2
    for tree in open_trees():
        total += 1 + open_tree_data(tree)["count"]
    return total

