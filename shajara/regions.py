"""Uzbekistan's regions: names, short labels, and a way to recognise a
region in free text ("Samarqand, Urgut tumani", "Nukus").

The admin map draws the real borders from static/data/uz-regions.geojson,
whose features carry these same names.
"""

import re

from .matching import fold

# (name, short label, column, row) — rough west→east, north→south order.
REGIONS = [
    ("Qoraqalpog'iston Respublikasi", "Qoraqalpog'iston", 0, 0),
    ("Xorazm viloyati", "Xorazm", 1, 1),
    ("Buxoro viloyati", "Buxoro", 2, 2),
    ("Navoiy viloyati", "Navoiy", 3, 2),
    ("Samarqand viloyati", "Samarqand", 3, 3),
    ("Qashqadaryo viloyati", "Qashqadaryo", 3, 4),
    ("Surxondaryo viloyati", "Surxondaryo", 4, 5),
    ("Jizzax viloyati", "Jizzax", 4, 2),
    ("Sirdaryo viloyati", "Sirdaryo", 5, 2),
    ("Toshkent shahri", "Toshkent sh.", 5, 1),
    ("Toshkent viloyati", "Toshkent vil.", 6, 1),
    ("Namangan viloyati", "Namangan", 7, 1),
    ("Farg'ona viloyati", "Farg'ona", 7, 2),
    ("Andijon viloyati", "Andijon", 8, 2),
]
ABROAD = "Boshqa"
REGION_NAMES = [r[0] for r in REGIONS]
SHORT = {r[0]: r[1] for r in REGIONS}

# Words that point at a region: the region itself plus its main towns.
_KEYWORDS = {
    "Qoraqalpog'iston Respublikasi": ["korakalpogiston", "karakalpakstan", "nukus", "hojayli", "tahiatosh",
                                     "beruniy", "tortkol", "chimboy", "kungirot", "muynok"],
    "Xorazm viloyati": ["horazm", "horezm", "urganch", "hiva", "hazorasp", "gurlan", "shovot", "hanka", "yangiarik"],
    "Buxoro viloyati": ["buhoro", "buhara", "gijduvon", "kogon", "romitan", "vobkent", "shofirkon", "karakol"],
    "Navoiy viloyati": ["navoiy", "navoi", "zarafshon", "uchkuduk", "karmana", "nurota", "konimeh"],
    "Samarqand viloyati": ["samarkand", "urgut", "katakorgon", "kattakorgon", "ishtihon", "payarik", "jomboy",
                           "bulungur", "narpay", "pastdargom", "nurobod", "tayloq"],
    "Qashqadaryo viloyati": ["kashkadaryo", "kashkadarya", "karshi", "shahrisabz", "kitob", "guzor", "koson",
                             "muborak", "dehkonobod", "chirakchi", "kamashi", "yakkabog"],
    "Surxondaryo viloyati": ["surhondaryo", "surhandarya", "termiz", "denov", "sherobod", "boysun", "sariosiyo",
                             "kumkorgon", "jarkorgon", "shorchi", "angor"],
    "Jizzax viloyati": ["jizah", "jizzah", "gallaorol", "zomin", "dostlik", "pahtakor", "forish", "baht"],
    "Sirdaryo viloyati": ["sirdaryo", "sirdarya", "guliston", "yangier", "shirin", "boyovut", "sayhunobod"],
    "Toshkent viloyati": ["chirchik", "angren", "olmalik", "bekobod", "ohangaron", "yangiyol", "bostonlik",
                          "parkent", "piskent", "kibray", "zangiota", "ortachirchik", "yukorichirchik", "toshkentviloyati"],
    "Namangan viloyati": ["namangan", "chust", "pop", "kosonsoy", "uchkorgon", "chortok", "yangikorgon", "mingbulok"],
    "Farg'ona viloyati": ["fargona", "fergana", "kokon", "kokand", "margilon", "margilan", "kuvasoy", "rishton",
                          "oltiarik", "beshariq", "kuva"],
    "Andijon viloyati": ["andijon", "andijan", "asaka", "shahrihon", "hojaobod", "marhamat", "paytug",
                         "boz", "izboskan", "jalakuduk", "oltinkol", "kurgontepa"],
}
_ABROAD_WORDS = ["rossiya", "moskva", "kazakiston", "tojikiston", "kirgiziston", "turkiya", "amerika", "usa",
                 "germaniya", "koreya", "afgoniston", "turkmaniston", "saudiya"]


def _tokens(text):
    return [fold(t) for t in re.split(r"[\s,;./()\-]+", text or "") if t]


def region_from_text(text):
    """Best guess of a region named in free text, or ''."""
    if not text:
        return ""
    folded_all = fold(text)
    tokens = set(_tokens(text))
    for name in REGION_NAMES:
        if fold(name) and fold(name) in folded_all:
            return name
    for name, words in _KEYWORDS.items():
        if tokens & set(words) or any(w in folded_all for w in words if len(w) >= 8):
            return name
    if "toshkent" in folded_all or "tashkent" in folded_all:
        return "Toshkent viloyati" if "viloyat" in folded_all else "Toshkent shahri"
    if tokens & set(_ABROAD_WORDS):
        return ABROAD
    return ""


def person_region(person):
    """(region, how) — how is 'kiritilgan' when the birth region field was
    filled in, 'matndan' when it was recognised in other place text."""
    if person.birth_region:
        return person.birth_region, "kiritilgan"
    guess = region_from_text(" ".join(x for x in (person.birth_district, person.birth_village, person.location) if x))
    return (guess, "matndan") if guess else ("", "")
