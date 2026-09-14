"""Sample historical maps with real places, years and routes.

    python manage.py seed_maps           # create (or recreate) the samples
    python manage.py seed_maps --clear   # remove them

The base picture is drawn by basemap.py; each sample is that picture with its
own places and routes. Years follow the standard histories (see `sources`);
where a date is disputed the commonly taught one is used.
"""

import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction

from shajara.basemap import draw_basemap, fraction
from shajara.models import HistoricalMap, MapPlace, MapRoute, Person, Tree, UserProfile

User = get_user_model()
OWNER = "shajara_namuna"

# key: (name, kind, lat, lon, year, year_end, description)
TEMUR_PLACES = {
    "kesh": ("Kesh (Shahrisabz)", "tugilgan", 39.05, 66.83, 1336, None,
             "Amir Temur 1336-yil 9-aprelda Kesh yaqinidagi Xo‘ja Ilg‘or qishlog‘ida tug‘ilgan. Keyinchalik shaharda Oqsaroy qurdirgan."),
    "balx": ("Balx", "voqea", 36.76, 66.90, 1370, None,
             "1370-yilgi qurultoyda Temur Movarounnahrning amiri deb e’lon qilindi."),
    "samarqand": ("Samarqand", "poytaxt", 39.65, 66.96, 1370, 1405,
                  "Davlat poytaxti. Yurishlardan keltirilgan hunarmandlar Bibixonim masjidi, Shohizinda va Go‘ri Amirni bunyod etdi."),
    "urganch": ("Urganch (Xorazm)", "jang", 42.31, 59.15, 1372, 1388,
                "Xorazmga 1372–1388-yillarda besh marta yurish qilingan; 1379-yilda bo‘ysundirilgan, 1388-yilda shahar vayron etilgan."),
    "hirot": ("Hirot", "shahar", 34.35, 62.20, 1381, None,
              "1381-yilda Kurtlar sulolasi hukmdori Temurga taslim bo‘ldi. Keyinchalik Shohruhning poytaxti bo‘ldi."),
    "tabriz": ("Tabriz", "shahar", 38.08, 46.29, 1386, None, "Uch yillik yurish boshida (1386) egallandi."),
    "isfahon": ("Isfahon", "jang", 32.65, 51.67, 1387, None,
                "1387-yilda soliq yig‘uvchilarga qarshi qo‘zg‘olondan so‘ng shahar qattiq jazolandi."),
    "sheroz": ("Sheroz", "shahar", 29.60, 52.53, 1387, 1393,
               "1387-yilda bo‘ysundirilgan; 1393-yilda Muzaffariylar sulolasi tugatilgan. Hofiz Sheroziy bilan uchrashuv rivoyati mashhur."),
    "bagdod": ("Bag‘dod", "jang", 33.31, 44.36, 1393, 1401,
               "1393-yilda jangsiz egallangan, isyondan so‘ng 1401-yilda qayta olingan."),
    "terek": ("Terek bo‘yidagi jang", "jang", 43.55, 45.30, 1395, None,
              "1395-yil 15-aprel: Oltin O‘rda xoni To‘xtamish ustidan hal qiluvchi g‘alaba."),
    "saroy": ("Saroy Berka", "jang", 48.60, 45.40, 1395, None,
              "Oltin O‘rda poytaxti 1395-yilda vayron etildi — bu Buyuk ipak yo‘lining shimoliy tarmog‘iga katta zarba bo‘ldi."),
    "kobul": ("Kobul", "qarorgoh", 34.53, 69.17, 1398, None, "Hindiston yurishi oldidan qo‘shin yig‘ilgan joy (1398)."),
    "multon": ("Multon", "jang", 30.20, 71.47, 1398, None, "Nabirasi Pir Muhammad qamal qilgan shahar (1398)."),
    "dehli": ("Dehli", "jang", 28.61, 77.21, 1398, None,
              "1398-yil dekabrida Dehli sultoni Mahmud Tug‘luq qo‘shini tor-mor etildi."),
    "halab": ("Halab", "jang", 36.20, 37.16, 1400, None, "Mamluklar qal’asi 1400-yil oktabrida egallandi."),
    "damashq": ("Damashq", "jang", 33.51, 36.29, 1401, None,
                "1401-yil boshida egallandi; Ibn Xaldun Temur bilan shu yerda uchrashgan."),
    "anqara": ("Anqara jangi", "jang", 39.93, 32.86, 1402, None,
               "1402-yil 20-iyul: Usmonli sultoni Boyazid I qo‘shini yengildi, sultonning o‘zi asir olindi."),
    "qorabog": ("Qorabog‘ qishlovi", "qarorgoh", 39.80, 47.00, 1403, 1404, "Qo‘shin 1403–1404-yillar qishini shu yerda o‘tkazgan."),
    "otror": ("O‘tror", "vafot", 42.85, 68.30, 1405, None,
              "Xitoyga yurish yo‘lida, 1405-yil 12-fevralda shu yerda vafot etgan. Jasadi Samarqanddagi Go‘ri Amirga dafn qilingan."),
}
TEMUR_ROUTES = [
    ("Xorazm yurishlari (1372–1379)", "harbiy", "#7a5230", 1372, 1379,
     "Xorazmning so‘fiylar sulolasi bilan kurash.", [("samarqand", 1372), ("urganch", 1379), ("samarqand", 1380)]),
    ("Uch yillik yurish (1386–1388)", "harbiy", "#8e3b2f", 1386, 1388,
     "Eron va Ozarbayjonga yurish.", [("samarqand", 1386), ("tabriz", 1386), ("isfahon", 1387), ("sheroz", 1387), ("samarqand", 1388)]),
    ("Besh yillik yurish (1392–1396)", "harbiy", "#b3261e", 1392, 1396,
     "G‘arbiy Eron, Iroq va Oltin O‘rdaga yurish.",
     [("samarqand", 1392), ("sheroz", 1393), ("bagdod", 1393), ("tabriz", 1394), ("terek", 1395), ("saroy", 1395), ("samarqand", 1396)]),
    ("Hindiston yurishi (1398–1399)", "harbiy", "#c26a1b", 1398, 1399,
     "Hindukush orqali Dehlisultonligiga yurish.",
     [("samarqand", 1398), ("kobul", 1398), ("multon", 1398), ("dehli", 1398), ("samarqand", 1399)]),
    ("Yetti yillik yurish (1399–1404)", "harbiy", "#6b2a22", 1399, 1404,
     "Mamluklar va Usmonlilarga qarshi eng uzoq yurish.",
     [("samarqand", 1399), ("tabriz", 1400), ("halab", 1400), ("damashq", 1401), ("bagdod", 1401), ("anqara", 1402),
      ("qorabog", 1403), ("samarqand", 1404)]),
    ("Xitoy yurishi (1404–1405)", "harbiy", "#3b5b8c", 1404, 1405,
     "Min imperiyasiga yurish Temurning vafoti bilan to‘xtadi.", [("samarqand", 1404), ("otror", 1405)]),
]

SILK_PLACES = {
    "qashqar": ("Qashqar", "shahar", 39.47, 75.99, -126, None,
                "Xan elchisi Chjan Szyan g‘arbga yo‘l olganda o‘tgan vohalardan biri; Tarim havzasining savdo darvozasi."),
    "dovon": ("Dovon (Farg‘ona)", "shahar", 40.53, 70.94, -128, None,
              "Xitoy manbalarida «Dayuan» — «samoviy otlar» yurti. Chjan Szyan mil. av. 128-yil atrofida kelgan."),
    "osh": ("O‘sh", "shahar", 40.51, 72.80, None, None, "Farg‘ona vodiysidan Qashqarga o‘tuvchi dovonlar oldidagi bozor shahri."),
    "taroz": ("Talas jangi", "jang", 42.90, 71.37, 751, None,
              "751-yilda Abbosiylar va Tan imperiyasi qo‘shinlari to‘qnashdi. Rivoyatga ko‘ra, qog‘oz tayyorlash sirlari shundan so‘ng G‘arbga o‘tgan."),
    "choch": ("Choch (Toshkent)", "shahar", 41.31, 69.24, None, None, "Ipak yo‘lining Sirdaryo bo‘yidagi muhim bekati."),
    "samarqand": ("Samarqand (Marakanda)", "poytaxt", 39.65, 66.96, -329, None,
                  "Mil. av. 329-yilda Makedoniyalik Iskandar egallagan So‘g‘diyona poytaxti; Ipak yo‘lining markazi."),
    "buxoro": ("Buxoro", "shahar", 39.77, 64.42, 709, None, "709-yilda arab sarkardasi Qutayba ibn Muslim tomonidan egallangan; Somoniylar poytaxti (IX–X asrlar)."),
    "urganch": ("Urganch", "shahar", 42.31, 59.15, None, None, "Xorazm poytaxti; shimoliy savdo tarmog‘ining boshlanishi."),
    "termiz": ("Termiz", "shahar", 37.22, 67.28, None, None, "Amudaryo kechuvi; buddaviy ibodatxonalar markazi."),
    "balx": ("Balx", "shahar", 36.76, 66.90, None, None, "«Shaharlar onasi» — Baqtriya poytaxti."),
    "marv": ("Marv", "shahar", 37.66, 62.19, None, None, "Xurosonning yirik vohasi; Saljuqiylar davrida gullab-yashnagan."),
    "nishopur": ("Nishopur", "shahar", 36.21, 58.80, None, None, "Umar Xayyom yashagan shahar; firuza savdosi markazi."),
    "ray": ("Ray", "shahar", 35.59, 51.43, None, None, "Hozirgi Tehron yaqinidagi qadimiy shahar."),
    "hamadon": ("Hamadon", "shahar", 34.80, 48.51, None, None, "Qadimgi Ekbatana; Ibn Sino maqbarasi shu yerda."),
    "bagdod": ("Bag‘dod", "poytaxt", 33.31, 44.36, 762, None, "762-yilda Abbosiylar poytaxti sifatida barpo etilgan; «Bayt ul-hikma» markazi."),
    "halab": ("Halab", "shahar", 36.20, 37.16, None, None, "O‘rta yer dengizi sohiliga olib boruvchi karvon yo‘llari tuguni."),
    "antioxiya": ("Antioxiya", "shahar", 36.20, 36.16, None, None, "Ipak yo‘lining g‘arbiy uchi — Rim dunyosiga chiqish."),
    "kobul": ("Kobul", "shahar", 34.53, 69.17, None, None, "Hindistonga olib boruvchi janubiy tarmoq bekati."),
    "dehli": ("Dehli", "shahar", 28.61, 77.21, None, None, "Shimoliy Hindistonning savdo va siyosiy markazi."),
    "saroy": ("Saroy", "shahar", 48.60, 45.40, None, None, "Oltin O‘rda poytaxti; shimoliy tarmoq bekati."),
    "kafa": ("Kafa (Qrim)", "shahar", 45.03, 35.38, None, None, "Qora dengizdagi genuyaliklar porti — shimoliy tarmoqning dengiz darvozasi."),
}
SILK_ROUTES = [
    ("Chjan Szyan elchiligi (mil. av. 138–126)", "elchilik", "#7a4fa0", -138, -126,
     "Xan imperatori Udi yuborgan elchi G‘arbiy o‘lkalarni «kashf etgan» safar.",
     [("qashqar", -130), ("dovon", -129), ("samarqand", -129), ("balx", -128), ("qashqar", -126)]),
    ("Asosiy sharq–g‘arb yo‘li", "savdo", "#a47b32", None, None,
     "Qashqardan O‘rta yer dengizigacha bo‘lgan asosiy karvon yo‘li.",
     [("qashqar", None), ("osh", None), ("dovon", None), ("choch", None), ("samarqand", None), ("buxoro", None),
      ("marv", None), ("nishopur", None), ("ray", None), ("hamadon", None), ("bagdod", None), ("halab", None), ("antioxiya", None)]),
    ("Shimoliy tarmoq (Xorazm – Qrim)", "savdo", "#6b8e23", None, None,
     "Dashti Qipchoq orqali Qora dengizga chiquvchi yo‘l.",
     [("buxoro", None), ("urganch", None), ("saroy", None), ("kafa", None)]),
    ("Janubiy tarmoq (Termiz – Dehli)", "savdo", "#2f5ea8", None, None,
     "Hindukush dovonlari orqali Hindistonga boruvchi yo‘l.",
     [("samarqand", None), ("termiz", None), ("balx", None), ("kobul", None), ("dehli", None)]),
]

BABUR_PLACES = {
    "andijon": ("Andijon", "tugilgan", 40.78, 72.34, 1483, 1494,
                "Zahiriddin Muhammad Bobur 1483-yil 14-fevralda tug‘ilgan; 1494-yilda 12 yoshida Farg‘ona taxtiga o‘tirgan."),
    "samarqand": ("Samarqand", "shahar", 39.65, 66.96, 1497, 1511,
                  "Bobur Samarqandni uch marta egallagan: 1497, 1500 va 1511-yillarda — lekin uzoq ushlab turolmagan."),
    "sarpul": ("Sarpul jangi", "jang", 39.75, 66.55, 1501, None, "1501-yilda Muhammad Shayboniyxonga yutqazdi."),
    "kobul": ("Kobul", "poytaxt", 34.53, 69.17, 1504, 1530,
              "1504-yilda Kobulni egallab, yangi davlatiga poytaxt qildi. Vasiyatiga ko‘ra shu yerdagi Bog‘i Boburda dafn etilgan."),
    "qandahor": ("Qandahor", "shahar", 31.61, 65.70, 1522, None, "Uzoq kurashlardan so‘ng 1522-yilda egallandi."),
    "panipat": ("Panipat jangi", "jang", 29.39, 76.97, 1526, None,
                "1526-yil 21-aprel: Ibrohim Lodiy qo‘shini tor-mor etildi — Boburiylar saltanatiga asos solindi. To‘plar va «tulg‘ama» usuli qo‘llangan."),
    "dehli": ("Dehli", "shahar", 28.61, 77.21, 1526, None, "Panipatdan so‘ng Bobur nomiga xutba o‘qildi."),
    "agra": ("Agra", "vafot", 27.18, 78.01, 1526, 1530,
             "Saltanat poytaxti; Bobur 1530-yil 26-dekabrda shu yerda vafot etgan. «Boburnoma»ning katta qismi Hindistonda yozilgan."),
    "xonva": ("Xonva jangi", "jang", 27.03, 77.53, 1527, None, "1527-yil mart: Rajput hukmdori Rana Sanga ustidan g‘alaba."),
}
BABUR_ROUTES = [
    ("Farg‘onadan Kobulga (1494–1504)", "kochish", "#2d7a4f", 1494, 1504,
     "Taxt uchun kurash va Movarounnahrdan chiqib ketish.",
     [("andijon", 1494), ("samarqand", 1497), ("sarpul", 1501), ("kobul", 1504)]),
    ("Samarqandni qaytarish (1511–1512)", "harbiy", "#8e3b2f", 1511, 1512,
     "Safaviylar yordamida Samarqandni qayta olish urinishi.",
     [("kobul", 1511), ("samarqand", 1511), ("kobul", 1512)]),
    ("Hindiston yurishi (1525–1527)", "harbiy", "#b3261e", 1525, 1527,
     "Beshinchi va hal qiluvchi yurish.",
     [("kobul", 1525), ("panipat", 1526), ("dehli", 1526), ("agra", 1526), ("xonva", 1527), ("agra", 1527)]),
]

SAMPLES = [
    {
        "title": "Amir Temur yurishlari (1370–1405)", "era": "XIV–XV asrlar",
        "description": "Sohibqironning poytaxti Samarqanddan boshlangan asosiy harbiy yurishlari: Xorazm, Eron, Oltin O‘rda, "
                       "Hindiston, Shom va Kichik Osiyo. Vaqt shkalasini «Ijro» bilan boshlang — yurishlar yil sayin chiziladi.",
        "sources": "B. Ahmedov. Amir Temur. Toshkent, 1995\nShomiy, Nizomiddin. Zafarnoma\nYazdiy, Sharafiddin Ali. Zafarnoma",
        "places": TEMUR_PLACES, "routes": TEMUR_ROUTES, "tree_root": "Temur",
    },
    {
        "title": "Buyuk Ipak yo‘li — O‘rta Osiyo tarmoqlari", "era": "mil. av. II asr – XV asr",
        "description": "Qashqardan O‘rta yer dengizigacha bo‘lgan karvon yo‘llari, shimoliy va janubiy tarmoqlar hamda "
                       "Chjan Szyan elchiligi. Miloddan avvalgi yillar manfiy son bilan saqlanadi.",
        "sources": "Frankopan, P. The Silk Roads. 2015\nO‘zbekiston milliy ensiklopediyasi, «Buyuk Ipak yo‘li» maqolasi",
        "places": SILK_PLACES, "routes": SILK_ROUTES, "tree_root": None,
    },
    {
        "title": "Zahiriddin Muhammad Bobur yo‘li (1494–1530)", "era": "XV–XVI asrlar",
        "description": "Andijondan Agragacha: taxt uchun kurash, Kobul davlati va Hindistonda Boburiylar saltanatining barpo etilishi.",
        "sources": "Bobur, Zahiriddin Muhammad. Boburnoma\nDale, S. The Garden of the Eight Paradises. 2004",
        "places": BABUR_PLACES, "routes": BABUR_ROUTES, "tree_root": None,
    },
]


class Command(BaseCommand):
    help = "Namunaviy tarixiy xaritalarni yaratadi (Amir Temur, Ipak yo'li, Bobur)."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **opts):
        removed = self.clear()
        if opts["clear"]:
            self.stdout.write(self.style.SUCCESS(f"O'chirildi: {removed} ta namunaviy xarita."))
            return
        owner, created = User.objects.get_or_create(username=OWNER, defaults={"first_name": "e-Shajara", "last_name": "namunalari"})
        if created:
            owner.set_unusable_password()
            owner.save()
            UserProfile.objects.get_or_create(user=owner, defaults={"role": "ixlosmand"})

        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "basemap.jpg"
            width, height = draw_basemap(base)
            with transaction.atomic():
                for sample in SAMPLES:
                    self.make(owner, sample, base, width, height)
        self.stdout.write(self.style.SUCCESS(f"Tayyor: {len(SAMPLES)} ta namunaviy xarita."))

    def clear(self):
        n = 0
        for hmap in HistoricalMap.objects.filter(is_sample=True):
            storage, name = hmap.image.storage, hmap.image.name
            hmap.delete()
            if name:
                storage.delete(name)
            n += 1
        return n

    def make(self, owner, sample, base, width, height):
        tree = None
        root_person = None
        if sample["tree_root"]:
            tree = Tree.objects.filter(root_person__last_name__icontains=sample["tree_root"], kind="talimiy").first()
            if tree:
                root_person = tree.root_person
        hmap = HistoricalMap(owner=owner, title=sample["title"], era=sample["era"], description=sample["description"],
                             sources=sample["sources"], visibility="public", is_sample=True, tree=tree,
                             image_width=width, image_height=height)
        with open(base, "rb") as fh:
            hmap.image.save("map.jpg", File(fh), save=False)
        hmap.save()

        ids = {}
        for key, (name, kind, lat, lon, year, year_end, text) in sample["places"].items():
            x, y = fraction(lat, lon)
            person = root_person if root_person and kind in ("tugilgan", "vafot") else None
            ids[key] = MapPlace.objects.create(map=hmap, name=name, kind=kind, x=x, y=y, year=year, year_end=year_end,
                                               description=text, person=person).id
        for name, kind, color, start, end, text, stops in sample["routes"]:
            MapRoute.objects.create(map=hmap, name=name, kind=kind, color=color, year_start=start, year_end=end,
                                    description=text, stops=[{"place": ids[k], "year": y} for k, y in stops])
        self.stdout.write(f"  · {hmap.title}: {len(ids)} joy, {len(sample['routes'])} yo'nalish"
                          + (f", «{tree.name}» shajarasiga bog'landi" if tree else ""))
