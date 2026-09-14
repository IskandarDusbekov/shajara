"""Demo family trees for every region, for trying the platform out.

    python manage.py seed_regions              # 3 trees per region
    python manage.py seed_regions --per-region 5
    python manage.py seed_regions --clear      # remove everything it made

Everything it creates belongs to users named demo_*, so --clear can take it
all away again without touching real data. What the trees look like:

  * 3–5 generations each, birth years that make sense (a child is born to
    parents in their twenties or thirties, the old generations have died),
    districts of the tree's own region, occupations, short biographies and
    family stories;
  * the first two trees of a region start from the same great-grandparents,
    entered twice by different people — the admin panel's cross-tree matching
    should find them ("bog'lanadigan");
  * the third tree is really joined: its founder's mother is a daughter from
    the first tree, so both families form one graph;
  * a few brides come from a neighbouring region, which joins regions;
  * the rest stand alone ("bog'lanmaydigan");
  * some trees are public, some private, some have editors and viewers.
"""

import json
import random
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from shajara.models import (
    REGION_CHOICES, ConnectionRequest, Family, Person, PersonStory, Tree, TreeMember, UserProfile,
)

User = get_user_model()
PREFIX = "demo_"

MEN = ["Abdulla", "Akmal", "Alisher", "Anvar", "Aziz", "Bahodir", "Bekzod", "Botir", "Dilshod", "Doniyor", "Eldor",
       "Farhod", "G'ayrat", "Hamid", "Ibrohim", "Ilhom", "Jahongir", "Jamshid", "Karim", "Komil", "Laziz", "Mansur",
       "Muhammad", "Nodir", "Nurali", "Odil", "Otabek", "Po'lat", "Qodir", "Rustam", "Rashid", "Sanjar", "Sardor",
       "Sherzod", "Shuhrat", "Temur", "Tohir", "Ulug'bek", "Umid", "Vali", "Xurshid", "Yusuf", "Zafar", "Zokir",
       "Ergash", "To'lqin", "Hasan", "Husan", "Sobir", "Rahim", "Salim", "Olim", "Qo'chqor", "Erkin", "Baxtiyor"]
WOMEN = ["Aziza", "Barno", "Dilnoza", "Dildora", "Feruza", "Gulnora", "Gulchehra", "Hilola", "Iroda", "Kamola",
         "Laylo", "Malika", "Madina", "Mohira", "Muazzam", "Nargiza", "Nigora", "Nodira", "Oydin", "Ozoda", "Robiya",
         "Sabohat", "Saida", "Sevara", "Shahnoza", "Shoira", "Umida", "Xadicha", "Yulduz", "Zarina", "Zuhra",
         "Munisa", "Oygul", "Mehribon", "To'xtaxon", "Salomat", "Bahor", "Qunduz", "Rayhon", "Mavluda"]
OCCUPATIONS = {
    "old": ["dehqon", "bog'bon", "chorvador", "temirchi", "kulol", "duradgor", "to'quvchi", "choyxonachi", "mirob",
            "savdogar", "tegirmonchi", "novvoy"],
    "mid": ["o'qituvchi", "shifokor", "muhandis", "hisobchi", "haydovchi", "agronom", "kolxoz raisi", "tikuvchi",
            "hamshira", "quruvchi", "kutubxonachi", "zootexnik"],
    "new": ["dasturchi", "talaba", "iqtisodchi", "tadbirkor", "huquqshunos", "dizayner", "o'quvchi", "shifokor",
            "o'qituvchi", "jurnalist", "muhandis", "bank xodimi"],
}
STORY_TEMPLATES = [
    "{name} har bahorda hovliga o'rik va tut ko'chatlarini o'zi o'tqazardi. O'sha daraxtlarning ba'zilari hozir ham {district}dagi uyimizda meva beradi.",
    "Oilamizda {name} damlagan palovni hamon eslaymiz: bayramlarda qozon atrofida butun mahalla yig'ilardi.",
    "{name} {district}da {occupation} bo'lib ishlagan. Qo'shnilari uni halolligi va saxiyligi uchun hurmat qilishardi.",
    "{name} bolalarga ertak aytib berishni yaxshi ko'rardi. Uning «Zumrad va Qimmat» ertagini aytishi hali ham qulog'imizda.",
    "Qattiq qish kelgan yili {name} o'z g'aramidagi somonni butun qishloq bilan bo'lishgan — bu voqeani qariyalar hamon gapirib yuradi.",
    "{name} nevaralariga har yozda {district} tog'lariga olib chiqib, o'tlar va buloqlarning nomini o'rgatardi.",
]
WAR_STORY = ("{name} 1942-yilda frontga ketgan, {year}-yilda yarador bo'lib qaytgan. Uydagilarga yozgan uchburchak "
             "xatlari oilada qimmatli yodgorlik sifatida saqlanadi.")
BIO_TEMPLATES = [
    "{district}da tug'ilgan. Umrining ko'p qismini {occupation} sifatida o'tkazgan.",
    "{district}da voyaga yetgan, {occupation} bo'lib ishlagan. {kids} nafar farzandni tarbiyalagan.",
    "Yoshligidan mehnatkash bo'lgan, {occupation} kasbini otasidan o'rgangan.",
]

# neighbouring regions, for brides who move
NEIGHBOURS = {
    "Samarqand viloyati": "Qashqadaryo viloyati", "Qashqadaryo viloyati": "Surxondaryo viloyati",
    "Buxoro viloyati": "Navoiy viloyati", "Navoiy viloyati": "Samarqand viloyati",
    "Toshkent viloyati": "Toshkent shahri", "Toshkent shahri": "Sirdaryo viloyati",
    "Sirdaryo viloyati": "Jizzax viloyati", "Jizzax viloyati": "Samarqand viloyati",
    "Farg'ona viloyati": "Andijon viloyati", "Andijon viloyati": "Namangan viloyati",
    "Namangan viloyati": "Farg'ona viloyati", "Xorazm viloyati": "Qoraqalpog'iston Respublikasi",
    "Qoraqalpog'iston Respublikasi": "Xorazm viloyati", "Surxondaryo viloyati": "Qashqadaryo viloyati",
}


def load_districts():
    path = Path(settings.BASE_DIR) / "static" / "js" / "uz-regions.js"
    text = path.read_text(encoding="utf-8")
    body = text[text.index("{"): text.rindex("}") + 1]
    return json.loads(body)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "", text.lower().replace("'", ""))[:10]


def surname_for(name, female):
    base = name.replace("'", "")
    if base.endswith(("a", "o", "u", "i", "e")):
        base += "y"
    return base + ("ova" if female else "ov")


class Builder:
    def __init__(self, rng, owner, region, districts):
        self.rng, self.owner, self.region = rng, owner, region
        self.districts = districts.get(region) or [""]
        self.people = []

    def person(self, first, gender, year, last="", father_name="", child_family=None, region=None,
               district=None, era="mid", **extra):
        rng = self.rng
        death = ""
        if year < 1935:
            death = str(min(2023, year + rng.randint(58, 88)))
        elif year < 1955 and rng.random() < 0.3:
            death = str(min(2024, year + rng.randint(55, 70)))
        approx = year < 1915 and rng.random() < 0.6
        patronymic = ""
        if father_name:
            patronymic = f"{father_name} {'qizi' if gender == 'ayol' else 'o‘g‘li'}".replace("‘", "'")
        p = Person.objects.create(
            first_name=first, last_name=last, gender=gender, patronymic=patronymic,
            birth_year=f"~{year}" if approx else str(year), death_year=death,
            birth_region=region or self.region,
            birth_district=district if district is not None else rng.choice(self.districts),
            occupation=rng.choice(OCCUPATIONS[era]) if era != "child" else "",
            child_family=child_family, added_by=self.owner, **extra,
        )
        self.people.append(p)
        return p

    def bio_and_story(self, p, kids=0):
        rng = self.rng
        if p.occupation and rng.random() < 0.55:
            p.bio = rng.choice(BIO_TEMPLATES).format(district=p.birth_district or "qishloq", occupation=p.occupation,
                                                     kids=kids or rng.randint(2, 6))
            p.save(update_fields=["bio"])
        year = int(re.sub(r"\D", "", p.birth_year) or 1950)
        if p.gender == "erkak" and 1900 <= year <= 1924 and rng.random() < 0.6:
            PersonStory.objects.create(person=p, author=self.owner,
                                       text=WAR_STORY.format(name=p.first_name, year=rng.choice([1943, 1944, 1945])))
        elif year < 1960 and rng.random() < 0.35:
            PersonStory.objects.create(person=p, author=self.owner, text=rng.choice(STORY_TEMPLATES).format(
                name=p.first_name, district=p.birth_district or "qishloq", occupation=p.occupation or "mehnatkash"))


class Command(BaseCommand):
    help = "Har bir viloyat uchun sinov shajaralarini yaratadi (demo_* foydalanuvchilar)."

    def add_arguments(self, parser):
        parser.add_argument("--per-region", type=int, default=3)
        parser.add_argument("--seed", type=int, default=2026)
        parser.add_argument("--clear", action="store_true", help="demo_* ma'lumotlarini o'chirish")

    def handle(self, *args, **opts):
        if opts["clear"]:
            self.clear()
            return
        if User.objects.filter(username__startswith=PREFIX + "r").exists():
            self.stdout.write(self.style.WARNING("Sinov ma'lumotlari allaqachon bor. Avval --clear bilan o'chiring."))
            return
        rng = random.Random(opts["seed"])
        districts = load_districts()
        regions = [value for value, _ in REGION_CHOICES if value and value != "Boshqa"]
        with transaction.atomic():
            made = self.build(rng, regions, districts, max(1, opts["per_region"]))
        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {made['users']} foydalanuvchi, {made['trees']} shajara, {made['people']} shaxs, "
            f"{made['stories']} hikoya. Kirish paroli: demo-parol-2026"))

    # ----------------------------------------------------------------- clear --
    def clear(self):
        users = User.objects.filter(username__startswith=PREFIX)
        people = Person.objects.filter(added_by__in=users)
        fam_ids = set(people.exclude(child_family=None).values_list("child_family_id", flat=True))
        fam_ids |= set(Family.objects.filter(Q(father__in=people) | Q(mother__in=people)).values_list("id", flat=True))
        trees = Tree.objects.filter(owner__in=users).count()
        with transaction.atomic():
            Tree.objects.filter(owner__in=users).delete()
            n_people = people.count()
            people.delete()
            Family.objects.filter(id__in=fam_ids, father=None, mother=None).delete()
            n_users = users.count()
            users.delete()
        self.stdout.write(self.style.SUCCESS(f"O'chirildi: {n_users} foydalanuvchi, {trees} shajara, {n_people} shaxs."))

    # ----------------------------------------------------------------- build --
    def build(self, rng, regions, districts, per_region):
        counts = {"users": 0, "trees": 0, "people": 0, "stories": 0}
        first_trees = {}         # region -> (builder, a daughter who can marry out)
        all_users = []
        for r_index, region in enumerate(regions):
            shared_top = None
            for t_index in range(per_region):
                username = f"{PREFIX}r{r_index + 1:02d}_{slug(region)}_{t_index + 1}"
                first = rng.choice(MEN + WOMEN)
                user = User.objects.create_user(username, password="demo-parol-2026", first_name=first,
                                                last_name=surname_for(rng.choice(MEN), first in WOMEN))
                role = rng.choice(["oila", "oila", "oila", "talaba", "oqituvchi", "abituriyent"])
                UserProfile.objects.create(user=user, region=region, role=role, email_verified=False)
                all_users.append(user)
                counts["users"] += 1

                b = Builder(rng, user, region, districts)
                clan = rng.choice(MEN)
                gens = rng.randint(3, 5)
                top_year = rng.randint(1880, 1915) if gens >= 4 else rng.randint(1915, 1940)

                # generation 0: the founding couple — shared by trees 1 and 2 of a region
                if t_index == 1 and shared_top:
                    src_h, src_w = shared_top
                    husband = b.person(src_h.first_name, "erkak", int(re.sub(r"\D", "", src_h.birth_year)),
                                       district=src_h.birth_district, era="old")
                    wife = b.person(src_w.first_name, "ayol", int(re.sub(r"\D", "", src_w.birth_year)),
                                    district=src_w.birth_district, era="old")
                else:
                    husband = b.person(rng.choice(MEN), "erkak", top_year, era="old")
                    wife = b.person(rng.choice(WOMEN), "ayol", top_year + rng.randint(1, 6), era="old")
                    if t_index == 0:
                        shared_top = (husband, wife)
                fam = Family.objects.create(father=husband, mother=wife)
                b.bio_and_story(husband)
                b.bio_and_story(wife)

                generation = [(husband, wife, fam, top_year)]
                surname_root = clan
                root_candidate = husband
                daughter_to_share = None
                for g in range(1, gens):
                    next_generation = []
                    era = "old" if g == 1 and top_year < 1915 else "mid" if g <= 2 else "new"
                    for dad, mom, family, parent_year in generation:
                        n_kids = rng.randint(1, 3) if g == gens - 1 else rng.randint(2, 4)
                        continuing = rng.randrange(n_kids)
                        for k in range(n_kids):
                            gender = rng.choice(["erkak", "ayol"])
                            year = parent_year + rng.randint(21, 32) + k * rng.randint(2, 4)
                            if year > 2020:
                                break
                            last = surname_for(surname_root, gender == "ayol") if year > 1925 else ""
                            names = MEN if gender == "erkak" else WOMEN
                            child = b.person(rng.choice(names), gender, year, last=last, father_name=dad.first_name,
                                             child_family=family, era=era if year < 2005 else "child")
                            b.bio_and_story(child)
                            root_candidate = child
                            if gender == "ayol" and daughter_to_share is None and g >= 1:
                                daughter_to_share = child
                            if k == continuing and g < gens - 1:
                                spouse_gender = "ayol" if gender == "erkak" else "erkak"
                                spouse_region = region
                                if rng.random() < 0.15:
                                    spouse_region = NEIGHBOURS.get(region, region)
                                spouse = b.person(
                                    rng.choice(WOMEN if spouse_gender == "ayol" else MEN), spouse_gender,
                                    year + rng.randint(-4, 3),
                                    last=surname_for(rng.choice(MEN), spouse_gender == "ayol") if year > 1925 else "",
                                    region=spouse_region,
                                    district=rng.choice(districts.get(spouse_region) or [""]), era=era,
                                )
                                new_family = Family.objects.create(
                                    father=child if gender == "erkak" else spouse,
                                    mother=spouse if gender == "erkak" else child,
                                )
                                father = child if gender == "erkak" else spouse
                                next_generation.append((father, new_family.mother, new_family, year))
                    if not next_generation:
                        break
                    generation = next_generation

                # tree 3 of a region is really joined to tree 1: its founder's
                # mother is a daughter from that family
                if t_index == 2 and region in first_trees and first_trees[region]:
                    bride = first_trees[region]
                    bride_year = int(re.sub(r"\D", "", bride.birth_year) or 1960)
                    # the groom is an unmarried son of this tree's own family
                    married = set(Family.objects.filter(father__in=b.people).values_list("father_id", flat=True))
                    sons = [x for x in b.people if x.gender == "erkak" and x.child_family_id and x.id not in married]
                    if sons:
                        groom = min(sons, key=lambda x: abs(int(re.sub(r"\D", "", x.birth_year) or 0) - bride_year))
                    else:
                        groom = b.person(rng.choice(MEN), "erkak", bride_year + rng.randint(0, 4),
                                         last=surname_for(clan, False) if bride_year > 1925 else "", era="mid",
                                         father_name=husband.first_name, child_family=fam)
                    joined = Family.objects.create(father=groom, mother=bride)
                    son = b.person(rng.choice(MEN), "erkak", bride_year + rng.randint(22, 30),
                                   last=surname_for(clan, False), father_name=groom.first_name,
                                   child_family=joined, era="new")
                    b.bio_and_story(son)
                    PersonStory.objects.create(
                        person=bride, author=user,
                        text=f"{bride.first_name} opamiz {groom.first_name} akaga turmushga chiqqach, ikki oila "
                             f"bir-biriga yaqin bo'lib qoldi — to'ylar va hayitlarda hammamiz birga bo'lamiz.")
                    root_candidate = son

                if t_index == 0:
                    first_trees[region] = daughter_to_share

                name = rng.choice([f"{surname_for(clan, False)}lar oilasi", f"{clan} bobo avlodlari",
                                   f"{region.split()[0]}lik {surname_for(clan, False)}lar"])
                tree = Tree.objects.create(
                    owner=user, root_person=root_candidate, name=name, kind="oilaviy",
                    visibility="public" if rng.random() < 0.45 else "private",
                    description=(f"{region}dagi {surname_for(clan, False)}lar sulolasi: {gens} avlod. "
                                 "Sinov uchun yaratilgan namunaviy shajara."),
                )
                counts["trees"] += 1
                counts["people"] += len(b.people)

        # a little life: editors, viewers and a few pending requests
        demo_trees = list(Tree.objects.filter(owner__username__startswith=PREFIX))
        for tree in demo_trees:
            if rng.random() < 0.4:
                helper = rng.choice(all_users)
                if helper != tree.owner:
                    TreeMember.objects.get_or_create(tree=tree, user=helper,
                                                     defaults={"role": rng.choice(["muharrir", "kuzatuvchi"]),
                                                               "invited_by": tree.owner})
        for _ in range(min(8, len(demo_trees))):
            t = rng.choice(demo_trees)
            to = rng.choice(all_users)
            if to != t.owner:
                ConnectionRequest.objects.create(from_user=t.owner, from_tree=t, to_user=to,
                                                 message="Salom! Bobolarimiz bir qishloqdan chiqqan bo'lishi mumkin.")
        counts["stories"] = PersonStory.objects.filter(author__username__startswith=PREFIX).count()
        return counts
