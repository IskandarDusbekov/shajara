"""Namunaviy to'liq shajaralar: uchta tarixiy sulola va bitta hozirgi zamon oilasi.

    python manage.py seed_showcase --username tarixchi --password "..."
    python manage.py seed_showcase --username tarixchi --clear

Yaratiladi:
  * Temuriylar, Boburiylar, Chingiziylar — ommaviy ta'limiy shajaralar:
    tarjimai hollar, hikoyalar, manbalar. Aniq bo'lmagan yillar "~" bilan,
    manbalarda onasi aniq ko'rsatilmagan farzandlar onasiz oilaga yoziladi.
  * Karimova Madina shajarasi — 7 avlodli, to'qima (namunaviy) oila,
    tug'ilgan yillari 1900–2020 oralig'ida.

Qayta ishga tushirilsa, shu foydalanuvchining avvalgi namunalari o'chirilib,
yangidan yaratiladi.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from shajara.models import Family, HistoricalMap, MapPlace, Person, PersonStory, Tree, UserProfile

User = get_user_model()


def p(first, last="", g="erkak", b="", d="", occ="", bio="", pat="", region="", district="", village="", loc="", bdate=None):
    return {"first_name": first, "last_name": last, "gender": g, "birth_year": b, "death_year": d, "occupation": occ,
            "bio": bio, "patronymic": pat, "birth_region": region, "birth_district": district,
            "birth_village": village, "location": loc, "birth_date": bdate}


F = "ayol"

# =====================================================================  TEMURIYLAR
TEMURIYLAR = {
    "name": "Temuriylar sulolasi",
    "slug": "temuriylar",
    "seo": "Amir Temur va Temuriylar sulolasining to'liq shajarasi: Shohrux, Mirzo Ulug'bek, Husayn Boyqaro va Boburgacha — tarjimai hollar, hikoyalar va manbalar.",
    "root": "temur",
    "kind": "talimiy",
    "visibility": "public",
    "subject": "O'zbekiston tarixi",
    "era": "XIV–XVI asrlar",
    "description": (
        "Amir Temur va uning avlodlari: Movarounnahr va Xurosonni boshqargan Temuriylar sulolasi. "
        "Shajarada Temurning o'g'illari, Mirzo Ulug'bek, Husayn Boyqaro va Boburgacha bo'lgan asosiy "
        "tarmoqlar ko'rsatilgan. Manbalarda onasi aniq ko'rsatilmagan farzandlar alohida (onasi noma'lum) "
        "oilaga yozilgan."
    ),
    "sources": (
        "Sharafiddin Ali Yazdiy. Zafarnoma\n"
        "Nizomiddin Shomiy. Zafarnoma\n"
        "Ibn Arabshoh. Ajoyib al-maqdur fi navoibi Taymur\n"
        "Zahiriddin Muhammad Bobur. Boburnoma\n"
        "B. Ahmedov. Amir Temur. Toshkent, 1995\n"
        "B. F. Manz. The Rise and Rule of Tamerlane. Cambridge, 1989"
    ),
    "people": {
        "taragay": p("Muhammad Tarag'ay", "", d="1360", occ="Barlos urug'i beki",
                     region="Qashqadaryo viloyati", loc="Kesh (Shahrisabz)",
                     bio="Barlos urug'ining beklaridan, Kesh viloyatida yashagan. Manbalarda taqvodor, "
                         "ulamo va shayxlarni hurmat qilgan inson sifatida tilga olinadi. Amir Temurning otasi."),
        "tegina": p("Tegina begim", "", F, occ="Amir Temurning onasi",
                    bio="Amir Temurning onasi. Manbalarda uning nomi Tegina (Tekina) Moh begim shaklida uchraydi."),
        "temur": p("Amir", "Temur", b="1336", d="1405", bdate=date(1336, 4, 9), pat="Tarag'ay o'g'li",
                   occ="Temuriylar davlati asoschisi, sarkarda", region="Qashqadaryo viloyati",
                   district="Shahrisabz tumani", village="Xo'ja Ilg'or", loc="Samarqand",
                   bio="1336-yil 9-aprelda Kesh yaqinidagi Xo'ja Ilg'or qishlog'ida tug'ilgan. 1370-yilgi Balx "
                       "qurultoyida Movarounnahr amiri deb e'lon qilingan va poytaxtni Samarqandga ko'chirgan. "
                       "35 yil davomida Hindistondan Kichik Osiyogacha cho'zilgan ulkan davlat barpo etgan. "
                       "Samarqandni ilm-fan va me'morchilik markaziga aylantirgan. 1405-yil fevralda Xitoy "
                       "yurishi paytida O'trorda vafot etgan, Samarqanddagi Go'ri Amir maqbarasiga dafn etilgan."),
        "oljoy": p("O'ljoy Turkon og'o", "", F, d="1367", occ="Amir Temurning rafiqasi",
                   bio="Amir Husaynning singlisi, Amir Temurning dastlabki xotinlaridan. Temur va Husayn "
                       "ittifoqining ramzi bo'lgan. Uning vafotidan so'ng ikki amir o'rtasidagi munosabat buzilgan."),
        "saroymulk": p("Saroy Mulk xonim", "", F, b="~1343", d="1406", occ="Katta malika (Bibixonim)",
                       loc="Samarqand",
                       bio="Chig'atoy xoni Qozonxonning qizi, Chingizxon avlodi. Temur uni 1370-yilda xotinlikka "
                           "olgan va shu nikoh tufayli \"Ko'ragon\" — xonning kuyovi unvonini qo'llagan. "
                           "Saroyda eng yuqori mavqega ega katta malika bo'lgan, nevaralari, jumladan Ulug'bekni "
                           "tarbiyalagan. Samarqanddagi mashhur jome masjidi xalq orasida uning nomi bilan "
                           "Bibixonim masjidi deb ataladi."),
        "jahongir": p("Jahongir", "Mirzo", b="1356", d="1376", pat="Temur o'g'li", occ="Shahzoda, Temurning to'ng'ich o'g'li",
                      bio="Amir Temurning to'ng'ich o'g'li va dastlabki valiahdi. Otasining ishonchli sarkardasi "
                          "bo'lgan, biroq 20 yoshida kasallikdan vafot etgan. Shahrisabzdagi Dorus-Saodat "
                          "majmuasiga dafn etilgan."),
        "xonzoda": p("Xonzoda begim", "", F, occ="Malika",
                     bio="Xorazmning so'fiylar sulolasidan Oqsufi qo'ng'irotning qizi, asl ismi Sevinbek. Avval "
                         "Jahongir Mirzoga turmushga chiqqan, undan Muhammad Sulton tug'ilgan. Jahongir vafotidan "
                         "so'ng Mironshohga nikohlangan, bu nikohdan Xalil Sulton dunyoga kelgan."),
        "umarshayx": p("Umarshayx", "Mirzo", b="1356", d="1394", pat="Temur o'g'li", occ="Fors (Fars) hokimi",
                       bio="Amir Temurning ikkinchi o'g'li. Otasining yurishlarida faol qatnashgan, Farg'ona, keyin "
                           "Fors viloyatini boshqargan. 1394-yilda Kurdistondagi qal'alardan birini qamal qilish "
                           "paytida o'q tegib halok bo'lgan."),
        "mironshoh": p("Mironshoh", "Mirzo", b="1366", d="1408", pat="Temur o'g'li", occ="Ozarbayjon va Iroq hokimi",
                       bio="Amir Temurning uchinchi o'g'li. Xuroson, keyin Ozarbayjon va Iroqni boshqargan. Otiga "
                           "yiqilib bosh jarohati olgach, ruhiy holati og'irlashgani manbalarda qayd etilgan. 1408-yilda "
                           "Qoraqo'yunlular bilan jangda halok bo'lgan. Boburning ajdodi."),
        "shohrux": p("Shohrux", "Mirzo", b="1377", d="1447", bdate=date(1377, 8, 20), pat="Temur o'g'li",
                     occ="Temuriylar davlati hukmdori (1409–1447)", loc="Hirot",
                     bio="Amir Temurning kenja o'g'li. 1409-yildan umrining oxirigacha Temuriylar davlatini "
                         "Hirotdan turib boshqargan. Urushlardan ko'ra davlat qurilishi, savdo va madaniyatga "
                         "e'tibor bergan. Uning davrida Hirot musulmon Sharqining yirik madaniy markaziga aylangan, "
                         "Samarqandni esa o'g'li Ulug'bekka topshirgan."),
        "gavharshod": p("Gavharshod begim", "", F, b="~1378", d="1457", occ="Malika, homiy", loc="Hirot",
                        bio="Shohrux Mirzoning suyukli rafiqasi, Ulug'bek va Boysunqurning onasi. Davlat ishlariga "
                            "faol aralashgan, me'morchilik homiysi bo'lgan: Mashhaddagi Gavharshod masjidi va "
                            "Hirotdagi musallo majmuasi uning buyurtmasi bilan qurilgan. Keksa yoshida taxt uchun "
                            "kurashlar paytida Abusaid Mirzo buyrug'i bilan qatl etilgan."),
        "muhammadsulton": p("Muhammad Sulton", "Mirzo", b="1375", d="1403", pat="Jahongir o'g'li", occ="Valiahd",
                            bio="Jahongir Mirzoning o'g'li, Amir Temurning sevimli nevarasi va tayinlangan valiahdi. "
                                "1402-yilgi Anqara jangida qo'shinning bir qismiga qo'mondonlik qilgan. Jangdan so'ng "
                                "kasallanib, 1403-yilda vafot etgan. Samarqanddagi Go'ri Amir maqbarasi dastlab uning "
                                "xotirasiga qurila boshlagan."),
        "pirmuhammad": p("Pir Muhammad", "Mirzo", b="~1376", d="1407", pat="Jahongir o'g'li", occ="Qandahor va Kobul hokimi",
                         bio="Jahongir Mirzoning o'g'li. Temur vafotidan so'ng uning vasiyati bo'yicha taxt vorisi "
                             "etib tayinlangan, ammo hokimiyatni qo'lga kirita olmagan. 1407-yilda o'z vaziri "
                             "tomonidan o'ldirilgan."),
        "iskandar": p("Iskandar", "Mirzo", b="1384", d="1415", pat="Umarshayx o'g'li", occ="Fors hokimi",
                      bio="Umarshayx Mirzoning o'g'li, Sheroz va Isfahonni boshqargan. Ilm va san'at homiysi bo'lgan, "
                          "uning saroyida astronomiya va kitobat rivojlangan. Amakisi Shohruxga qarshi isyon ko'targani "
                          "uchun hokimiyatdan mahrum qilingan."),
        "boyqaro": p("Boyqaro", "Mirzo", pat="Umarshayx o'g'li", occ="Shahzoda",
                     bio="Umarshayx Mirzoning o'g'li. Hamadon va Luristonda hokimlik qilgan. Husayn Boyqaroning "
                         "bobosi — Hirot hukmdorlari tarmog'i shu shahzodadan boshlanadi."),
        "mansur": p("Mansur", "Mirzo", pat="Boyqaro o'g'li", occ="Shahzoda",
                    bio="Boyqaro Mirzoning o'g'li, Husayn Boyqaroning otasi."),
        "husayn": p("Husayn", "Boyqaro", b="1438", d="1506", pat="Mansur o'g'li", occ="Xuroson hukmdori (1469–1506)",
                    region="Boshqa", loc="Hirot",
                    bio="Temuriylarning Xurosondagi so'nggi yirik hukmdori, 1469–1506-yillarda Hirotni boshqargan. "
                        "O'zi ham \"Husayniy\" taxallusi bilan she'rlar yozgan. Bolalikdan do'sti Alisher Navoiy "
                        "bilan birga Hirotni Sharq Uyg'onish davrining markaziga aylantirgan: Abdurahmon Jomiy, "
                        "Kamoliddin Behzod, Mirxond kabi siymolar uning saroyida ijod qilgan."),
        "abubakr": p("Abu Bakr", "Mirzo", b="1382", d="1409", pat="Mironshoh o'g'li", occ="Shahzoda, sarkarda",
                     bio="Mironshohning o'g'li, jasur sarkarda sifatida tanilgan. Temur vafotidan keyingi taxt "
                         "kurashlarida Iroq va Ozarbayjon uchun kurashgan."),
        "xalil": p("Xalil Sulton", "", b="1384", d="1411", pat="Mironshoh o'g'li", occ="Samarqand hukmdori (1405–1409)",
                   loc="Samarqand",
                   bio="Mironshoh va Xonzoda begimning o'g'li. Temur vafotidan so'ng Samarqand taxtini egallagan. "
                       "Rafiqasi Shodmulk og'oga bo'lgan muhabbati va xazinani saxovat bilan sarflagani sababli "
                       "amirlarning noroziligiga uchragan. 1409-yilda hokimiyat amakisi Shohruxga o'tgan."),
        "sultonmuhammad": p("Sulton Muhammad", "Mirzo", pat="Mironshoh o'g'li", occ="Shahzoda",
                            bio="Mironshohning o'g'li, Abusaid Mirzoning otasi. Boburning ajdodlari zanjiridagi halqa."),
        "abusaid": p("Abusaid", "Mirzo", b="1424", d="1469", pat="Sulton Muhammad o'g'li",
                     occ="Temuriylar davlati hukmdori (1451–1469)", loc="Samarqand",
                     bio="Ulug'bek vafotidan keyingi notinchlikdan so'ng o'zbek xoni Abulxayrxon yordamida 1451-yilda "
                         "Samarqand taxtini egallagan. Keyinchalik Xurosonni ham birlashtirgan. 1469-yilda Oqqo'yunlular "
                         "bilan jangdan so'ng asirga olinib, qatl etilgan. Boburning bobosi."),
        "umarshayx2": p("Umarshayx", "Mirzo", b="1456", d="1494", pat="Abusaid o'g'li", occ="Farg'ona hokimi",
                        region="Andijon viloyati", loc="Axsi",
                        bio="Abusaid Mirzoning o'g'li, Farg'ona viloyatining hokimi, poytaxti Andijon. Zahiriddin "
                            "Muhammad Boburning otasi. 1494-yilda Axsi qal'asidagi kaptarxona jar yoqasi bilan qulab "
                            "tushganda halok bo'lgan."),
        "bobur": p("Zahiriddin Muhammad", "Bobur", b="1483", d="1530", bdate=date(1483, 2, 14), pat="Umarshayx o'g'li",
                   occ="Shoir, sarkarda, Boburiylar sulolasi asoschisi", region="Andijon viloyati", loc="Agra",
                   bio="Andijonda tug'ilgan. Hindistonda Boburiylar saltanatiga asos solgan. Uning avlodlari "
                       "\"Boburiylar sulolasi\" shajarasida batafsil ko'rsatilgan."),
        "ulugbek": p("Mirzo", "Ulug'bek", b="1394", d="1449", bdate=date(1394, 3, 22), pat="Shohrux o'g'li",
                     occ="Samarqand hukmdori, astronom, olim", loc="Samarqand",
                     bio="Asl ismi Muhammad Tarag'ay. 1394-yilda Sultoniyada tug'ilgan. 1409-yildan qariyb 40 yil "
                         "Movarounnahrni Samarqanddan turib boshqargan. Samarqand, Buxoro va G'ijduvonda madrasalar "
                         "qurdirgan, 1420-yillarda Samarqandda o'z davrining eng yirik rasadxonasini barpo etgan. "
                         "\"Ziji jadidi Ko'ragoniy\" asarida mingdan ortiq yulduzning o'rni aniqlangan. 1449-yilda "
                         "o'g'li Abdullatif tarafdorlari tomonidan o'ldirilgan."),
        "boysunqur": p("Boysunqur", "Mirzo", b="1397", d="1433", pat="Shohrux o'g'li", occ="Shahzoda, kitobat san'ati homiysi",
                       loc="Hirot",
                       bio="Shohrux va Gavharshodning o'g'li. Hirotda mashhur kutubxona-ustaxona tashkil etgan, u "
                           "yerda xattotlar, musavvirlar va muqovasozlar ishlagan. Uning buyurtmasi bilan 1430-yilda "
                           "ko'chirilgan \"Shohnoma\" nusxasi Sharq kitob san'atining durdonalaridan hisoblanadi."),
        "abdullatif": p("Abdullatif", "Mirzo", b="~1420", d="1450", pat="Ulug'bek o'g'li", occ="Samarqand hukmdori (1449–1450)",
                        bio="Mirzo Ulug'bekning o'g'li. Otasiga qarshi chiqib, 1449-yilda uni mag'lub etgan; Ulug'bek "
                            "uning tarafdorlari tomonidan o'ldirilgan. Taxtda olti oy o'tirgach, 1450-yilda o'zi ham "
                            "fitna qurboni bo'lgan. Xalq xotirasida \"padarkush\" nomi bilan qolgan."),
        "abulqosim": p("Abulqosim Bobur", "Mirzo", b="1422", d="1457", pat="Boysunqur o'g'li", occ="Xuroson hukmdori",
                       bio="Boysunqur Mirzoning o'g'li. Ulug'bekdan keyingi kurashlarda Xurosonni egallab, 1457-yilgacha "
                           "Hirotda hukmronlik qilgan. She'riyat va musiqani sevgan."),
    },
    "families": [
        ("taragay", "tegina", ["temur"]),
        ("temur", "oljoy", []),
        ("temur", "saroymulk", []),
        ("temur", None, ["jahongir", "umarshayx", "mironshoh", "shohrux"]),
        ("jahongir", "xonzoda", ["muhammadsulton"]),
        ("jahongir", None, ["pirmuhammad"]),
        ("mironshoh", "xonzoda", ["xalil"]),
        ("mironshoh", None, ["abubakr", "sultonmuhammad"]),
        ("umarshayx", None, ["iskandar", "boyqaro"]),
        ("boyqaro", None, ["mansur"]),
        ("mansur", None, ["husayn"]),
        ("sultonmuhammad", None, ["abusaid"]),
        ("abusaid", None, ["umarshayx2"]),
        ("umarshayx2", None, ["bobur"]),
        ("shohrux", "gavharshod", ["ulugbek", "boysunqur"]),
        ("ulugbek", None, ["abdullatif"]),
        ("boysunqur", None, ["abulqosim"]),
    ],
    "stories": {
        "temur": [
            "Balx qurultoyi (1370). Amir Husayn ustidan g'alaba qozongach, Temur Balxda qurultoy chaqirgan. "
            "Qurultoy uni Movarounnahrning oliy hukmdori deb tan olgan. Temur o'zini xon deb atamagan: "
            "Chingiziylar an'anasiga ko'ra xonlik faqat Chingizxon avlodiga tegishli edi. Shu sabab u \"amir\" "
            "unvoni bilan kifoyalangan, keyinroq Saroy Mulk xonimga uylanib, \"Ko'ragon\" — xonning kuyovi "
            "unvonini olgan.",
            "Anqara jangi (1402). Usmoniylar sultoni Boyazid I bilan to'qnashuv 1402-yil 28-iyulda Anqara "
            "yaqinida bo'lgan. Temur qo'shini Usmoniylarni tor-mor etgan, Boyazid asirga tushgan. Bu g'alaba "
            "Usmoniylar davlatini vaqtincha zaiflashtirgan va Yevropa hukmdorlarining Temurga qiziqishini "
            "oshirgan: Kastiliya qiroli Genrix III elchisi Rui Gonsales de Klavixo 1404-yilda Samarqandga kelib, "
            "shahar haqida mashhur kundalik yozib qoldirgan.",
            "So'nggi yurish. 1404-yil oxirida Temur Min imperiyasiga qarshi katta yurish boshlagan. Qahraton qishda "
            "Sirdaryodan o'tib, O'trorga yetganda og'ir kasallanib, 1405-yil fevralda vafot etgan. Jasadi "
            "Samarqandga olib kelinib, Go'ri Amir maqbarasiga qo'yilgan.",
        ],
        "saroymulk": [
            "Bibixonim masjidi. Temur Hindiston yurishidan qaytgach, 1399-yilda Samarqandda o'z davrining eng katta "
            "jome masjidini qurdira boshlagan. Masjid 1404-yilda asosan qurib bitkazilgan. Xalq orasida u Temurning "
            "katta xotini Saroy Mulk xonim — Bibixonim nomi bilan atalib kelinadi; masjid qarshisida uning maqbarasi "
            "joylashgan.",
        ],
        "shohrux": [
            "Hirot poytaxti. Shohrux Temur davlatining markazini Hirotga ko'chirgan. U yerda madrasa, xonaqoh va "
            "kutubxonalar qurilgan, Xitoy, Hindiston va Misr bilan elchilar almashilgan. 1419–1422-yillarda "
            "Shohrux elchilari Pekinga borib kelgan; elchilikda qatnashgan G'iyosiddin Naqqosh safar kundaligini "
            "yozib qoldirgan.",
        ],
        "gavharshod": [
            "Me'mor homiysi. Gavharshod begimning buyurtmasi bilan 1418-yilda Mashhaddagi Imom Rizo majmuasi "
            "yonida katta jome masjidi qurilgan. Masjid me'mori — Temuriylar davrining mashhur ustasi Qavomiddin "
            "Sheroziy. Hirotda ham uning nomi bilan madrasa va maqbaradan iborat musallo majmuasi barpo etilgan.",
        ],
        "ulugbek": [
            "Rasadxona. 1420-yillarda Samarqand yaqinidagi Ko'hak (Obirahmat) tepaligida uch qavatli rasadxona "
            "qurilgan. Uning asosiy asbobi — radiusi 40 metrdan ortiq bo'lgan ulkan sekstant (Faxriy sekstanti) "
            "qoldiqlari 1908-yilda arxeolog V. L. Vyatkin tomonidan topilgan. Ulug'bek atrofida Qozizoda Rumiy, "
            "G'iyosiddin Jamshid Koshiy, Ali Qushchi kabi olimlar ishlagan.",
            "\"Ziji jadidi Ko'ragoniy\". Rasadxonada olib borilgan kuzatuvlar natijasida 1018 ta yulduzning o'rni "
            "ko'rsatilgan jadvallar tuzilgan. Asar keyinchalik lotin tiliga tarjima qilinib, 1665-yilda Oksfordda "
            "nashr etilgan. Yulduzli yilning uzunligi ham hayratlanarli aniqlikda hisoblangan.",
            "Madrasalar. Ulug'bek Buxoro (1417), Samarqand (1417–1420) va G'ijduvon (1433) madrasalarini "
            "qurdirgan. Buxoro madrasasining eshigida \"Ilm olish har bir muslim va muslima uchun farzdir\" degan "
            "hadis yozilgani rivoyat qilinadi.",
        ],
        "boysunqur": [
            "Boysunqur kutubxonasi. Hirotdagi kitobxonada qirqqa yaqin xattot va musavvir ishlagan. U yerda "
            "tayyorlangan \"Shohnoma\" (1430) qo'lyozmasi hozir Tehrondagi Guliston saroyi kutubxonasida "
            "saqlanadi va YUNESKOning \"Jahon xotirasi\" reyestriga kiritilgan.",
        ],
        "husayn": [
            "Navoiy bilan do'stlik. Husayn Boyqaro va Alisher Navoiy yoshlikda birga tahsil olgan. Husayn taxtga "
            "chiqqach, Navoiyni muhrdor, keyin amir etib tayinlagan. Navoiy \"Majolis un-nafois\" tazkirasida "
            "sultonning she'riyatiga alohida bob bag'ishlagan, Husayn esa o'z risolasida Navoiyni yuksak baholagan.",
        ],
        "muhammadsulton": [
            "Go'ri Amir. Muhammad Sulton 1403-yilda vafot etgach, Temur Samarqandda uning uchun madrasa va xonaqoh "
            "yonida maqbara qurdirgan. 1405-yilda Temurning o'zi ham shu yerga dafn etilgan va maqbara \"Go'ri Amir\" "
            "— \"Amirning qabri\" nomini olgan. Keyinchalik u yerga Shohrux va Ulug'bek ham qo'yilgan.",
        ],
        "xalil": [
            "Shodmulk. Xalil Sulton taxtga chiqqach, sevgan rafiqasi Shodmulk og'oning ta'sirida bo'lgani, uning "
            "iltimosi bilan xazinadan katta mablag'larni tarqatgani manbalarda qayd etilgan. Amirlar bundan norozi "
            "bo'lib, 1409-yilda Xalilni hokimiyatdan chetlatgan. Keyinroq Shohrux uni Rayga hokim etib yuborgan.",
        ],
        "umarshayx2": [
            "Axsi fojiasi. Bobur \"Boburnoma\"da otasining o'limini shunday tasvirlaydi: 1494-yil iyunda Axsi "
            "qal'asida jar yoqasidagi kaptarxona qulab tushgan va Umarshayx Mirzo kaptarlari bilan birga jarga "
            "uchib ketgan. O'shanda Bobur 11 yoshda edi va shu kundan Farg'ona taxtiga o'tirgan.",
        ],
    },
}

# =====================================================================  BOBURIYLAR
BOBURIYLAR = {
    "name": "Boburiylar sulolasi",
    "slug": "boburiylar",
    "seo": "Zahiriddin Muhammad Bobur va Boburiylar shajarasi: Humoyun, Akbar, Jahongir, Shohjahon va Avrangzeb — avlodlar, rafiqalar va tarixiy hikoyalar.",
    "root": "bobur",
    "kind": "talimiy",
    "visibility": "public",
    "subject": "Jahon tarixi",
    "era": "XV–XVIII asrlar",
    "description": (
        "Zahiriddin Muhammad Bobur va uning avlodlari — Hindistonda 300 yildan ortiq hukmronlik qilgan "
        "Boburiylar sulolasi (Yevropa adabiyotida \"Buyuk Mo'g'ullar\"). Bobur, Humoyun, Akbar, Jahongir, "
        "Shohjahon va Avrangzeb avlodlari hamda ularning rafiqalari ko'rsatilgan."
    ),
    "sources": (
        "Zahiriddin Muhammad Bobur. Boburnoma\n"
        "Gulbadanbegim. Humoyunnoma\n"
        "Abulfazl Allomiy. Akbarnoma\n"
        "Nuriddin Jahongir. Tuzuki Jahongiriy\n"
        "J. F. Richards. The Mughal Empire. Cambridge, 1993\n"
        "A. Schimmel. The Empire of the Great Mughals. London, 2004"
    ),
    "people": {
        "umarshayx2": p("Umarshayx", "Mirzo", b="1456", d="1494", pat="Abusaid o'g'li", occ="Farg'ona hokimi",
                        region="Andijon viloyati", loc="Axsi",
                        bio="Temuriy shahzoda Abusaid Mirzoning o'g'li, Farg'ona hokimi. \"Boburnoma\"da u xushfe'l, "
                            "she'r va kitobni sevgan, ammo omadsiz sarkarda sifatida tasvirlangan. 1494-yilda Axsida "
                            "kaptarxona bilan jarga qulab halok bo'lgan."),
        "qutlugnigor": p("Qutlug' Nigorxonim", "", F, d="1505", occ="Malika",
                         bio="Mo'g'uliston xoni Yunusxonning qizi, Chingizxon avlodi. Bobur va Xonzoda begimning onasi. "
                             "O'g'lining barcha qiyin yillarida — Samarqanddan chekinish va Kobulga yo'lda — u bilan "
                             "birga bo'lgan. 1505-yilda Kobulda vafot etgan."),
        "bobur": p("Zahiriddin Muhammad", "Bobur", b="1483", d="1530", bdate=date(1483, 2, 14), pat="Umarshayx o'g'li",
                   occ="Shoir, sarkarda, Boburiylar sulolasi asoschisi", region="Andijon viloyati",
                   district="Andijon shahri", loc="Agra",
                   bio="1483-yil 14-fevralda Andijonda tug'ilgan. Otasi Umarshayx Mirzo tomondan Amir Temurning, "
                       "onasi tomondan Chingizxonning avlodi. 11 yoshida Farg'ona taxtiga o'tirgan, ikki marta "
                       "Samarqandni egallagan, biroq Shayboniyxon bilan kurashda Movarounnahrni tark etishga majbur "
                       "bo'lgan. 1504-yilda Kobulni olgan, 1526-yilda Panipat jangida g'alaba qozonib, Hindistonda "
                       "yangi saltanatga asos solgan. O'zbek mumtoz adabiyotining yirik vakili: \"Boburnoma\", "
                       "devon, \"Mubayyin\", \"Aruz risolasi\" muallifi. 1530-yil 26-dekabrda Agrada vafot etgan, "
                       "vasiyatiga ko'ra Kobuldagi bog'ga dafn etilgan."),
        "xonzodab": p("Xonzoda begim", "", F, b="1478", d="1545", pat="Umarshayx qizi", occ="Malika",
                      region="Andijon viloyati",
                      bio="Boburning opasi. 1501-yilda Samarqand qamalidan so'ng ukasining xavfsizligi evaziga "
                          "Shayboniyxonga nikohlab berilgan. 1510-yilda Shayboniyxon halok bo'lgach, Eron shohi Ismoil "
                          "uni izzat bilan Boburga qaytargan. Boburiylar oilasida katta obro'ga ega bo'lgan, Humoyun "
                          "davrida ham oila a'zolarini yarashtirishga harakat qilgan."),
        "oyshasulton": p("Oysha Sulton begim", "", F, occ="Malika",
                         bio="Temuriy Sulton Ahmad Mirzoning qizi, Boburning birinchi xotini. \"Boburnoma\"da Bobur "
                             "yoshlikdagi bu nikoh haqida samimiy yozgan. Keyinchalik u Boburdan ajralib ketgan."),
        "mohim": p("Mohim begim", "", F, occ="Malika, Humoyunning onasi", loc="Kobul",
                   bio="Boburning suyukli rafiqasi, Humoyunning onasi. Bobur vafotidan keyin ham saroyda katta "
                       "hurmatga ega bo'lgan, Humoyun taxtga chiqqanda katta bazm uyushtirgan."),
        "gulruh": p("Gulruh begim", "", F, occ="Malika",
                    bio="Boburning rafiqalaridan, Kamron Mirzo va Askariy Mirzoning onasi."),
        "dildor": p("Dildor begim", "", F, occ="Malika",
                    bio="Boburning rafiqalaridan, Hindol Mirzo va Gulbadanbegimning onasi."),
        "humoyun": p("Nosiriddin Muhammad", "Humoyun", b="1508", d="1556", bdate=date(1508, 3, 6), pat="Bobur o'g'li",
                     occ="Boburiylar podshohi (1530–1540, 1555–1556)", region="Boshqa", loc="Dehli",
                     bio="1508-yilda Kobulda tug'ilgan. Otasi vafotidan so'ng taxtga o'tirgan, biroq 1540-yilda "
                         "afg'on sarkardasi Sherxon Surdan mag'lub bo'lib, 15 yil surgunda yashagan. Eron shohi "
                         "Tahmasp yordamida qaytib, 1555-yilda Dehlini yana egallagan. Astronomiya va kitobni sevgan. "
                         "1556-yil yanvarda kutubxonasi zinasidan yiqilib vafot etgan. Dehlidagi maqbarasi "
                         "YUNESKO merosi ro'yxatida."),
        "kamron": p("Kamron", "Mirzo", b="1509", d="1557", pat="Bobur o'g'li", occ="Kobul va Qandahor hokimi",
                    bio="Boburning o'g'li. Akasi Humoyun bilan uzoq yillar hokimiyat talashgan. Oxiri asirga olinib, "
                        "ko'zlari ko'r qilingan va Makkaga ketishga ruxsat berilgan, o'sha yerda vafot etgan. "
                        "Turkiy va forsiy she'rlar yozgan."),
        "askariy": p("Askariy", "Mirzo", b="1516", d="1558", pat="Bobur o'g'li", occ="Shahzoda",
                     bio="Boburning o'g'li, Kamron Mirzoning tug'ishgan ukasi. Humoyunga qarshi kurashlarda ko'pincha "
                         "Kamron tarafida bo'lgan. Hajga ketib, yo'lda vafot etgan."),
        "hindol": p("Hindol", "Mirzo", b="1519", d="1551", pat="Bobur o'g'li", occ="Shahzoda",
                    bio="Boburning kenja o'g'li. Oxirgi yillarda Humoyunga sodiq qolgan va 1551-yilda Kamron Mirzo "
                        "qo'shini bilan tungi jangda halok bo'lgan. Uning qizi Ruqiya Sulton begim keyinroq Akbarning "
                        "birinchi rafiqasi bo'lgan."),
        "gulbadan": p("Gulbadanbegim", "", F, b="~1523", d="1603", pat="Bobur qizi", occ="Tarixchi, \"Humoyunnoma\" muallifi",
                      bio="Boburning qizi. Jiyani Akbarning iltimosiga ko'ra \"Humoyunnoma\" asarini yozgan — bu Sharq "
                          "tarixshunosligida ayol tomonidan yozilgan kam uchraydigan tarixiy asarlardan. Asarda saroy "
                          "ayollari hayoti, oilaviy voqealar va Humoyunning surgun yillari jonli tasvirlangan."),
        "hamida": p("Hamida Bonu begim", "", F, b="1527", d="1604", occ="Malika, Akbarning onasi",
                    bio="Humoyunning rafiqasi, Akbarning onasi. Humoyun bilan 1541-yilda, surgun yillarida turmush "
                        "qurgan. Akbar hukmronligi davrida \"Maryam Makoniy\" unvoni bilan saroyning eng hurmatli "
                        "ayoli bo'lgan."),
        "akbar": p("Jaloliddin Muhammad", "Akbar", b="1542", d="1605", bdate=date(1542, 10, 15), pat="Humoyun o'g'li",
                   occ="Boburiylar podshohi (1556–1605)", region="Boshqa", loc="Agra, Fatehpur Sikri",
                   bio="1542-yilda Sindning Umarkot shahrida, otasi surgunda bo'lgan paytda tug'ilgan. 13 yoshida "
                       "taxtga o'tirgan. Uning 49 yillik hukmronligi davrida saltanat Hindiston yarimorolining katta "
                       "qismini qamrab olgan. Mansabdorlik tizimi va yer solig'i islohotlarini joriy etgan, turli "
                       "din vakillari bilan munozaralar uyushtirgan va diniy bag'rikenglik siyosatini yuritgan. "
                       "Fatehpur Sikri shahrini qurdirgan. \"Akbarnoma\" uning davri tarixini hikoya qiladi."),
        "maryamzamoniy": p("Maryam uz-Zamoniy", "", F, b="~1542", d="1623", occ="Malika, Jahongirning onasi",
                           bio="Amber (Ambar) rojasi Bharmalning qizi, Akbarning rajput rafiqasi. 1562-yilgi bu nikoh "
                               "Boburiylar va rajput knyazliklari ittifoqining boshlanishi bo'lgan. Jahongirning onasi. "
                               "Savdo kemalariga egalik qilgan va xalqaro savdoda faol qatnashgan."),
        "jahongirp": p("Nuriddin Muhammad", "Jahongir", b="1569", d="1627", bdate=date(1569, 8, 31), pat="Akbar o'g'li",
                       occ="Boburiylar podshohi (1605–1627)", region="Boshqa", loc="Lohur, Agra",
                       bio="Asl ismi Salim, Sikri qishlog'ida shayx Salim Chishtiy xonadonida tug'ilgan. 1605-yilda taxtga chiqqach, \"Jahongir\" "
                           "— \"jahonni oluvchi\" nomini olgan. Adolat zanjiri bilan mashhur: shikoyatchilar saroy "
                           "tashqarisidagi qo'ng'iroqli zanjirni tortib, podshohga murojaat qila olgan. Tabiatni, "
                           "rassomchilikni sevgan; \"Tuzuki Jahongiriy\" xotiralarida qushlar va o'simliklarni "
                           "batafsil tasvirlagan."),
        "jagatgosain": p("Jagat Gosain", "", F, b="1573", d="1619", occ="Malika, Shohjahonning onasi",
                         bio="Marvar rojasi Udai Singhning qizi, Jahongirning rafiqasi va Shohjahonning onasi."),
        "nurjahon": p("Nurjahon", "", F, b="1577", d="1645", occ="Imperatritsa (Podshoh Begim)", loc="Lohur",
                      bio="Asl ismi Mehrunniso, eronlik amaldor G'iyosbekning qizi. 1611-yilda Jahongirga turmushga "
                          "chiqqan. Boburiylar tarixida eng qudratli ayol: uning nomidan farmonlar chiqarilgan, tangalar "
                          "zarb qilingan. Otasi uchun Agrada qurdirgan I'timod ud-Davla maqbarasi Toj Mahalga ilhom "
                          "bergan inshootlardan hisoblanadi."),
        "shohjahon": p("Shihobiddin Muhammad", "Shohjahon", b="1592", d="1666", bdate=date(1592, 1, 5), pat="Jahongir o'g'li",
                       occ="Boburiylar podshohi (1628–1658)", region="Boshqa", loc="Agra, Dehli",
                       bio="Asl ismi Xurram, Lohurda tug'ilgan. Uning davri Boburiylar me'morchiligining oltin davri "
                           "hisoblanadi: Agradagi Toj Mahal, Dehlidagi Qizil qal'a va Jome masjidi, \"Tovus taxti\" "
                           "shu davrda yaratilgan. 1657-yilda kasal bo'lib qolgach, o'g'illari o'rtasida taxt uchun "
                           "urush boshlangan; g'olib chiqqan Avrangzeb uni umrining oxirigacha Agra qal'asida saqlagan."),
        "mumtoz": p("Mumtoz Mahal", "", F, b="1593", d="1631", occ="Malika",
                    bio="Asl ismi Arjumand Bonu begim, Nurjahonning jiyani. 1612-yilda Shohjahonga turmushga chiqqan va "
                        "uning eng yaqin maslahatchisi bo'lgan. 14 farzand ko'rgan. 1631-yilda Burhonpurda o'n "
                        "to'rtinchi farzandini dunyoga keltirayotib vafot etgan. Toj Mahal uning xotirasiga qurilgan."),
        "jahonoro": p("Jahonoro begim", "", F, b="1614", d="1681", pat="Shohjahon qizi", occ="Podshoh Begim",
                      bio="Shohjahon va Mumtoz Mahalning to'ng'ich qizi. Onasi vafotidan so'ng saroyning birinchi "
                          "xonimi — Podshoh Begim bo'lgan. Otasi bilan Agra qal'asidagi asirlik yillarini birga "
                          "o'tkazgan. So'fiylik yo'lida risolalar yozgan."),
        "dorashukuh": p("Doro Shukuh", "", b="1615", d="1659", pat="Shohjahon o'g'li", occ="Valiahd, faylasuf",
                        bio="Shohjahonning to'ng'ich o'g'li va sevimli valiahdi. Tasavvuf va hind falsafasini "
                            "qiyosiy o'rgangan: \"Majma' al-bahrayn\" (\"Ikki dengizning qo'shilishi\") asarini yozgan, "
                            "Upanishadlarni forsiy tilga tarjima qildirgan. Taxt urushida Avrangzebdan yengilib, 1659-yilda "
                            "qatl etilgan."),
        "shohshuja": p("Shoh Shuja", "", b="1616", d="1661", pat="Shohjahon o'g'li", occ="Bengaliya hokimi",
                       bio="Shohjahonning ikkinchi o'g'li, uzoq yillar Bengaliyani boshqargan. Taxt urushida "
                           "Avrangzebdan yengilib, Arakan (hozirgi Myanma) tomonga qochgan va u yerda halok bo'lgan."),
        "avrangzeb": p("Muhiddin Muhammad", "Avrangzeb", b="1618", d="1707", bdate=date(1618, 11, 3), pat="Shohjahon o'g'li",
                       occ="Boburiylar podshohi (1658–1707)", region="Boshqa", loc="Aurangobod",
                       bio="Shohjahonning uchinchi o'g'li, \"Olamgir\" unvoni bilan tanilgan. Uning davrida saltanat "
                           "eng katta hududga yetgan. Qattiqqo'l va taqvodor hukmdor bo'lgan, shariat asosidagi "
                           "\"Fatavoi Olamgiriy\" qonunlar to'plamini tuzdirgan. Dekandagi uzoq urushlar davlat "
                           "xazinasini holdan toydirgan. 1707-yilda vafot etgan, Xuldoboddagi oddiy qabrga dafn etilgan."),
        "murodbaxsh": p("Murod Baxsh", "", b="1624", d="1661", pat="Shohjahon o'g'li", occ="Gujarot hokimi",
                        bio="Shohjahonning kenja o'g'li. Taxt urushida avval Avrangzeb bilan ittifoq tuzgan, biroq keyin "
                            "hibsga olinib, Gvalior qal'asida qatl etilgan."),
        "dilras": p("Dilras Bonu begim", "", F, b="~1622", d="1657", occ="Malika",
                    bio="Eronning Safaviylar xonadoniga mansub, Avrangzebning birinchi va bosh rafiqasi. Aurangobodda "
                        "unga atab qurilgan Bibi ka Maqbara Toj Mahalga o'xshashligi bilan mashhur."),
        "navobbay": p("Navob Boy", "", F, occ="Malika",
                      bio="Avrangzebning rafiqalaridan, Bahodirshoh I ning onasi."),
        "azamshoh": p("Muhammad A'zamshoh", "", b="1653", d="1707", pat="Avrangzeb o'g'li", occ="Shahzoda",
                      bio="Avrangzeb va Dilras Bonu begimning o'g'li. Otasi vafotidan so'ng o'zini podshoh deb e'lon "
                          "qilgan, ammo 1707-yilda Jojau jangida akasi Muazzam (Bahodirshoh I) qo'shinidan yengilib "
                          "halok bo'lgan."),
        "bahodirshoh": p("Bahodirshoh I", "", b="1643", d="1712", pat="Avrangzeb o'g'li", occ="Boburiylar podshohi (1707–1712)",
                         bio="Asl ismi Muazzam. Avrangzebdan keyin taxtga chiqqan. Uning qisqa hukmronligidan so'ng "
                             "saltanat tez zaiflasha boshlagan. Sulolaning so'nggi podshohi Bahodirshoh II 1857-yilgi "
                             "qo'zg'olondan keyin inglizlar tomonidan Rangunga surgun qilingan."),
    },
    "families": [
        ("umarshayx2", "qutlugnigor", ["xonzodab", "bobur"]),
        ("bobur", "oyshasulton", []),
        ("bobur", "mohim", ["humoyun"]),
        ("bobur", "gulruh", ["kamron", "askariy"]),
        ("bobur", "dildor", ["hindol", "gulbadan"]),
        ("humoyun", "hamida", ["akbar"]),
        ("akbar", "maryamzamoniy", ["jahongirp"]),
        ("jahongirp", "jagatgosain", ["shohjahon"]),
        ("jahongirp", "nurjahon", []),
        ("shohjahon", "mumtoz", ["jahonoro", "dorashukuh", "shohshuja", "avrangzeb", "murodbaxsh"]),
        ("avrangzeb", "dilras", ["azamshoh"]),
        ("avrangzeb", "navobbay", ["bahodirshoh"]),
    ],
    "stories": {
        "bobur": [
            "\"Boburnoma\". Bobur o'z hayotini 1494-yildan boshlab kundalik uslubida, ona tilida yozgan. Asarda "
            "Farg'ona, Samarqand, Kobul va Hindistonning tabiati, shaharlari, odamlari, hayvonot va o'simlik "
            "dunyosi batafsil tasvirlangan. Bobur o'z xatolari va mag'lubiyatlarini ham yashirmagan. Asar "
            "Akbar davrida fors tiliga, XIX–XX asrlarda ingliz, fransuz, nemis va boshqa tillarga tarjima qilingan.",
            "Panipat jangi (1526). 1526-yil 21-aprelda Panipat maydonida Bobur Dehli sultoni Ibrohim Lo'diy bilan "
            "to'qnashgan. Soni ancha kam bo'lgan qo'shin to'plar, piltali miltiqlar va aravalar bilan mustahkamlangan "
            "saf hamda qanotlardan aylanib zarba berish taktikasi tufayli g'alaba qozongan. Ibrohim Lo'diy jangda "
            "halok bo'lgan. Bir yildan so'ng Xonua jangida rajput hukmdori Rana Sango ham yengilgan.",
            "Vatan sog'inchi. Hindistonda yashagan yillarida Bobur Farg'ona qovunlari va uzumini sog'inib "
            "yozganini \"Boburnoma\"da qayd etadi. Agrada u Markaziy Osiyo uslubidagi bog'lar barpo ettirgan. "
            "Vasiyatiga ko'ra jasadi keyinroq Kobuldagi o'zi yaratgan bog'ga — hozirgi Bog'i Boburga ko'chirilgan.",
        ],
        "xonzodab": [
            "Qurbonlik va qaytish. 1501-yilda Shayboniyxon Samarqandni qamal qilganda, shahardan chiqib ketish "
            "sharti sifatida Xonzoda begim unga nikohlab berilgan. O'n yil o'tib, 1510-yilda Marv yaqinidagi jangda "
            "Shayboniyxon halok bo'lgach, Shoh Ismoil Xonzoda begimni Qunduzdagi Boburga hurmat bilan qaytarib "
            "yuborgan. Bobur bu uchrashuvni hayotining eng quvonchli damlaridan biri deb bilgan.",
        ],
        "humoyun": [
            "Surgun yillari. 1540-yilda Qanavj yaqinidagi jangda Sherxon Surdan yengilgan Humoyun Sind, keyin "
            "Eronga ketishga majbur bo'lgan. Surgunda, 1542-yilda, Umarkotda o'g'li Akbar tug'ilgan. Gulbadanbegim "
            "\"Humoyunnoma\"da bu yillarning og'ir kechganini, qo'shin ichidagi xiyonatlar va sahro orqali "
            "o'tishni hikoya qiladi.",
            "Kutubxona zinasi. 1556-yil yanvar oyida Humoyun Dehlidagi Sher Mandal kutubxonasi tomida yulduzlarni "
            "kuzatib turgan. Azon ovozini eshitib, tiz cho'kmoqchi bo'lganda kiyimiga oyog'i o'ralib, tosh "
            "zinadan yiqilgan va uch kundan so'ng vafot etgan.",
        ],
        "akbar": [
            "Ibodatxona munozaralari. 1575-yilda Akbar Fatehpur Sikrida maxsus bino qurdirib, u yerda "
            "sunniy va shia ulamolari, hindu, jayn, zardushtiy va nasroniy (portugal iyezuitlari) vakillarining "
            "munozaralarini tinglagan. Bu tajriba \"sulhi kull\" — hammaga tinchlik siyosatining asosiga aylangan.",
            "Bayramxon. Akbar 13 yoshda taxtga chiqqanda davlatni amalda uning otaliq-vasiysi, Humoyunning sodiq "
            "sarkardasi Bayramxon boshqargan. 1556-yilgi ikkinchi Panipat jangidagi g'alaba ham uning rahbarligida "
            "qo'lga kiritilgan. 1560-yilda Akbar hokimiyatni to'liq o'z qo'liga olgan.",
        ],
        "gulbadan": [
            "Haj safari. 1576-yilda Gulbadanbegim boshchiligidagi Boburiy xonimlar guruhi hajga yo'l olgan. Ular "
            "Makka va Madinada qariyb to'rt yil qolib, 1582-yilda qaytgan. Boburiylar xonadonida bu ayollarning "
            "bunday uzoq va mustaqil safari misli ko'rilmagan voqea bo'lgan.",
        ],
        "shohjahon": [
            "Toj Mahal. Mumtoz Mahal vafotidan so'ng Shohjahon Agrada Yamuna daryosi bo'yida maqbara qurdirishni "
            "boshlagan. Asosiy bino taxminan 1643-yilda, butun majmua 1653-yil atrofida yakunlangan. Qurilishda "
            "20 mingga yaqin usta va ishchi qatnashgani aytiladi. Bosh me'mor sifatida Ustod Ahmad Lohuriy "
            "tilga olinadi. 1983-yilda Toj Mahal YUNESKO Butunjahon merosi ro'yxatiga kiritilgan.",
            "Agra qal'asidagi yillar. 1658-yilda taxtni egallagan Avrangzeb otasini Agra qal'asida saqlagan. "
            "Rivoyatlarga ko'ra, Shohjahon umrining so'nggi sakkiz yilida qal'aning Musamman Burj ayvonidan daryo "
            "ortidagi Toj Mahalga tikilib o'tirgan. 1666-yilda vafot etgach, rafiqasining yoniga dafn etilgan.",
        ],
        "mumtoz": [
            "Burhonpur. Mumtoz Mahal eri bilan Dekan yurishida birga bo'lgan. 1631-yil iyunda Burhonpurda o'n "
            "to'rtinchi farzandi Gavharoro begimni tug'ish paytida vafot etgan. Uning jasadi avval Burhonpurdagi "
            "bog'ga vaqtincha qo'yilgan, keyin Agraga olib kelingan.",
        ],
        "dorashukuh": [
            "\"Sirri akbar\". 1657-yilda Doro Shukuh Benoras olimlari yordamida ellikka yaqin Upanishad matnini fors "
            "tiliga o'girtirgan va unga \"Sirri akbar\" (\"Eng buyuk sir\") deb nom bergan. Bu tarjima XIX asr "
            "boshida fransuz olimi Anketil-Dyuperron tomonidan lotin tilida nashr etilib, Yevropada hind falsafasi "
            "bilan tanishishning muhim manbasi bo'lgan.",
        ],
        "avrangzeb": [
            "Taxt urushi (1657–1659). Shohjahon kasal bo'lib qolgach, to'rt o'g'li o'rtasida urush boshlangan. "
            "Avrangzeb Samugarh jangida (1658) Doro Shukuhni yengib, Agrani egallagan va otasini qal'aga qamagan. "
            "Keyingi bir yil ichida raqiblarining barchasini bartaraf etib, \"Olamgir\" unvoni bilan taxtga o'tirgan.",
        ],
    },
}

# =====================================================================  CHINGIZIYLAR
CHINGIZIYLAR = {
    "name": "Chingiziylar",
    "slug": "chingiziylar",
    "seo": "Chingizxon va uning avlodlari shajarasi: Jo'chi, Chig'atoy, O'gedey, Tuluy, Botu, Xubilay va Hulagu — Mo'g'ullar imperiyasi tarixi.",
    "root": "chingiz",
    "kind": "talimiy",
    "visibility": "public",
    "subject": "Jahon tarixi",
    "era": "XII–XIV asrlar",
    "description": (
        "Chingizxon va uning avlodlari: Mo'g'ullar imperiyasi, Oltin O'rda, Chig'atoy ulusi, Yuan sulolasi va "
        "Elxoniylar davlatining asoschilari. Chingizxonning qadimiy yillari manbalarda taxminiy berilgani uchun "
        "\"~\" belgisi bilan ko'rsatilgan."
    ),
    "sources": (
        "Mo'g'ullarning maxfiy tarixi (XIII asr)\n"
        "Rashididdin. Jome' at-tavorix\n"
        "Otamalik Juvayniy. Tarixi jahongushoy\n"
        "Abulg'ozi Bahodirxon. Shajarayi turk\n"
        "J. Weatherford. Genghis Khan and the Making of the Modern World. 2004\n"
        "T. May. The Mongol Empire. Edinburgh, 2018"
    ),
    "people": {
        "yesugey": p("Yesugey bahodir", "", d="~1171", occ="Qiyot-Borjigin urug'i sardori", region="Boshqa", loc="Onon daryosi bo'yi",
                     bio="Borjigin urug'ining sardori, Temuchinning otasi. Tatarlar bilan urushlarda nom qozongan. "
                         "Rivoyatga ko'ra, o'g'lini kelajak qaynatasi Dey-Sechen qoshiga qoldirib qaytayotganda "
                         "tatarlar uni zaharlagan."),
        "hoelun": p("Ho'lun", "", F, b="~1142", occ="Chingizxonning onasi",
                    bio="O'lqunut urug'idan, Chingizxonning onasi. Eri halok bo'lgach, urug'doshlari tashlab ketgan "
                        "oilani og'ir sharoitda — ildiz, meva va baliq bilan boqib, bolalarini birlik va sabrga "
                        "o'rgatgan. \"Mo'g'ullarning maxfiy tarixi\"da dono va qat'iyatli ona sifatida tasvirlangan."),
        "chingiz": p("Chingizxon", "", b="~1162", d="1227", pat="Yesugey o'g'li", occ="Mo'g'ullar imperiyasi asoschisi",
                     region="Boshqa", loc="Mo'g'uliston",
                     bio="Asl ismi Temuchin. Otasi erta vafot etgach, qashshoqlik va quvg'inda ulg'aygan. Ko'p yillik "
                         "kurashlar natijasida dasht qabilalarini birlashtirgan va 1206-yilgi Onon qurultoyida "
                         "\"Chingizxon\" unvoni bilan umummo'g'ul xoni deb e'lon qilingan. Qo'shinni o'nlik, yuzlik, "
                         "minglik va tumanlarga bo'lgan, \"Yasa\" qonunlarini joriy etgan. 1219–1221-yillarda "
                         "Xorazmshohlar davlatini tor-mor etgan. 1227-yilda Tangut (G'arbiy Sya) yurishi paytida "
                         "vafot etgan."),
        "qasar": p("Jo'chi Qasar", "", pat="Yesugey o'g'li", occ="Sarkarda",
                   bio="Chingizxonning ukasi, o'z davrining eng mohir kamonchisi sifatida mashhur bo'lgan. Akasining "
                       "yurishlarida qatnashgan."),
        "temuge": p("Temuge O'tchigin", "", b="~1168", d="1246", pat="Yesugey o'g'li", occ="Noyon",
                    bio="Yesugey va Ho'lunning kenja o'g'li. Mo'g'ul odatiga ko'ra ota yurti va mulki kenja o'g'ilga "
                        "qolgani uchun \"O'tchigin\" — \"o'choq egasi\" deb atalgan. Chingizxon yurishga ketganda "
                        "ona yurtni boshqargan."),
        "borte": p("Bo'rte", "", F, b="~1161", d="~1230", occ="Bosh xotun (imperatritsa)",
                   bio="Qo'ng'irot urug'idan Dey-Sechenning qizi. Temuchin bilan yoshligida unashtirilgan. Merkitlar "
                       "tomonidan o'g'irlab ketilganda Temuchin ittifoqchilari bilan uni qutqargan. To'rt o'g'li — "
                       "Jo'chi, Chig'atoy, O'gedey va Tuluyning onasi, Chingizxonning eng yaqin maslahatchisi bo'lgan."),
        "jochi": p("Jo'chi", "", b="~1182", d="1227", pat="Chingizxon o'g'li", occ="G'arbiy ulus hukmdori",
                   bio="Chingizxonning to'ng'ich o'g'li. Unga Irtishdan g'arbdagi yerlar — Dashti Qipchoq ulus qilib "
                       "berilgan. Xorazm yurishida Urganch qamalida qatnashgan. Otasidan bir necha oy oldin vafot "
                       "etgan. Uning avlodlari Oltin O'rda, keyinchalik Qozon, Qrim, Sibir xonliklari hamda "
                       "Shayboniylar va Ashtarxoniylarni boshqargan."),
        "chigatoy": p("Chig'atoy", "", b="~1183", d="1242", pat="Chingizxon o'g'li", occ="Chig'atoy ulusi asoschisi",
                      bio="Chingizxonning ikkinchi o'g'li, \"Yasa\" qonunlarining eng qattiq himoyachisi sifatida "
                          "tanilgan. Unga Movarounnahr va Yettisuv ulus qilib berilgan, bu yerlar uning nomi bilan "
                          "Chig'atoy ulusi deb atalgan. Temur davrida ham turkiy adabiy til \"chig'atoy tili\" deb "
                          "yuritilgan."),
        "ogedey": p("O'gedey", "", b="~1186", d="1241", pat="Chingizxon o'g'li", occ="Buyuk xon (qoon), 1229–1241",
                    bio="Chingizxonning uchinchi o'g'li, otasi tomonidan taxt vorisi etib tayinlangan. 1229-yilda "
                        "qurultoyda buyuk xon — qoon deb saylangan. Qoraqurum poytaxtini qurdirgan, yam (pochta) "
                        "tizimini kengaytirgan. Uning davrida Shimoliy Xitoydagi Szin davlati tugatilgan va G'arbga "
                        "katta yurish boshlangan."),
        "tuluy": p("Tuluy", "", b="~1191", d="1232", pat="Chingizxon o'g'li", occ="Sarkarda",
                   bio="Chingizxonning kenja o'g'li, mohir sarkarda. Xuroson yurishida Marv va Nishopurni egallagan. "
                       "Mo'g'ul odatiga ko'ra otasining asosiy qo'shini unga meros qolgan. Uning o'g'illari Mo'nke va "
                       "Xubilay keyinchalik buyuk xon bo'lgan."),
        "orda": p("O'rda Ichen", "", b="~1204", d="1251", pat="Jo'chi o'g'li", occ="Oq O'rda sardori",
                  bio="Jo'chining to'ng'ich o'g'li. Ukasi Botuni ulus boshlig'i deb tan olgan va o'zi Sharqiy qanotni "
                      "— Oq O'rdani boshqargan."),
        "botu": p("Botu", "", b="~1207", d="1255", pat="Jo'chi o'g'li", occ="Oltin O'rda xoni",
                  bio="Jo'chining o'g'li, Oltin O'rda (Jo'chi ulusi) davlatining asoschisi. 1236–1242-yillardagi G'arbiy "
                      "yurishga boshchilik qilgan: Volga Bulg'oristoni, Rus knyazliklari, Polsha va Vengriyagacha "
                      "yetgan. Quyi Volga bo'yida Saroy shahriga asos solgan."),
        "berka": p("Berka", "", b="~1209", d="1266", pat="Jo'chi o'g'li", occ="Oltin O'rda xoni (1257–1266)",
                   bio="Jo'chining o'g'li. Chingiziylardan birinchilardan bo'lib islomni qabul qilgan. Botudan so'ng "
                       "Oltin O'rda xoni bo'lgan. Bag'dodni vayron qilgan amakivachchasi Hulaguga qarshi urushgan va "
                       "Misr mamluklari bilan ittifoq tuzgan."),
        "shayboni": p("Shayboni", "", pat="Jo'chi o'g'li", occ="Shahzoda",
                      bio="Jo'chining o'g'li. G'arbiy yurishda qatnashgan, Ural va Sibir tomonidagi yerlar uning avlodiga "
                          "tegishli bo'lgan. Uning avlodlaridan chiqqan Abulxayrxon va Muhammad Shayboniyxon XV–XVI "
                          "asrlarda Movarounnahrda Shayboniylar sulolasini barpo etgan."),
        "moatukan": p("Mo'atukan", "", d="1221", pat="Chig'atoy o'g'li", occ="Shahzoda",
                      bio="Chig'atoyning sevimli o'g'li. 1221-yilda Bamiyan qal'asi qamalida o'q tegib halok bo'lgan. "
                          "Rivoyatlarga ko'ra, g'azablangan Chingizxon shaharni butunlay vayron qilishni buyurgan."),
        "qarahulagu": p("Qora Hulagu", "", d="1252", pat="Mo'atukan o'g'li", occ="Chig'atoy ulusi xoni",
                        bio="Mo'atukanning o'g'li. Bobosi Chig'atoyning vasiyatiga ko'ra ulus xoni bo'lgan, keyin "
                            "hokimiyatdan chetlatilgan. Mo'nke xon uni qayta tiklagan, biroq u ulusiga yetib borguncha "
                            "yo'lda vafot etgan."),
        "toregene": p("To'rag'ana", "", F, d="1246", occ="Xotun, regent (1241–1246)",
                      bio="O'gedeyning xotini, Go'yukning onasi. Eri vafotidan so'ng besh yil davomida imperiyani "
                          "regent sifatida boshqargan va qurultoyda o'g'li Go'yukni xon qilib saylatgan."),
        "goyuk": p("Go'yuk", "", b="~1206", d="1248", pat="O'gedey o'g'li", occ="Buyuk xon (1246–1248)",
                   bio="O'gedeyning o'g'li. 1246-yilda buyuk xon bo'lgan. Uning taxtga o'tirish marosimida Rim papasi "
                       "elchisi Plano Karpini ham qatnashgan. Botu bilan munosabati keskin bo'lgan, unga qarshi yurish "
                       "boshlagan paytda yo'lda vafot etgan."),
        "sorqoqtani": p("Sorqoqtani begi", "", F, b="~1190", d="1252", occ="Xotun, davlat arbobi",
                        bio="Kerayit qabilasidan, nasroniy (nestorian) oiladan. Tuluyning xotini. Eri erta vafot etgach, "
                            "to'rt o'g'lini tarbiyalab, ularning buyuk xon bo'lishiga zamin yaratgan. Barcha din "
                            "vakillariga homiylik qilgan, Buxoroda madrasa qurdirgani manbalarda qayd etilgan."),
        "monke": p("Mo'nke", "", b="1209", d="1259", pat="Tuluy o'g'li", occ="Buyuk xon (1251–1259)",
                   bio="Tuluyning to'ng'ich o'g'li. 1251-yilda buyuk xon bo'lgan. Soliq tizimini tartibga solgan, "
                       "ukalari Xubilayni Xitoyga, Hulaguni G'arbga yurishga yuborgan. Sun imperiyasiga qarshi yurish "
                       "paytida vafot etgan."),
        "xubilay": p("Xubilay", "", b="1215", d="1294", pat="Tuluy o'g'li", occ="Buyuk xon, Yuan sulolasi asoschisi",
                     bio="Tuluy va Sorqoqtani begining o'g'li. 1260-yilda xon deb e'lon qilingan, ukasi Arig'bo'ga bilan "
                         "urushda g'alaba qozongan. 1271-yilda Xitoyda Yuan sulolasiga asos solgan va poytaxtni "
                         "Xonbaliqqa (hozirgi Pekin) ko'chirgan. 1279-yilda butun Xitoyni birlashtirgan. Venetsiyalik "
                         "sayyoh Marko Polo uning saroyida xizmat qilgan."),
        "hulagu": p("Hulagu", "", b="~1217", d="1265", pat="Tuluy o'g'li", occ="Elxoniylar davlati asoschisi",
                    bio="Tuluyning o'g'li. Mo'nke xon topshirig'i bilan G'arbga yurish qilgan: 1256-yilda ismoiliylar "
                        "qal'asi Alamutni egallagan, 1258-yilda Bag'dodni olib, Abbosiylar xalifaligiga barham bergan. "
                        "Eron va Iroqda Elxoniylar davlatini tuzgan. Olim Nasiriddin Tusiy uchun Marog'ada rasadxona "
                        "qurdirgan."),
        "arigboga": p("Arig'bo'ga", "", b="~1219", d="1266", pat="Tuluy o'g'li", occ="Qoraqurum hokimi",
                      bio="Tuluyning kenja o'g'li. Mo'nke vafotidan so'ng Qoraqurumda xon deb e'lon qilingan va "
                          "akasi Xubilay bilan to'rt yil urushgan. 1264-yilda taslim bo'lib, ikki yildan keyin vafot "
                          "etgan."),
        "chabi": p("Chabi xotun", "", F, b="~1225", d="1281", occ="Imperatritsa",
                   bio="Qo'ng'irot urug'idan, Xubilayning bosh xotini. Davlat ishlarida eriga maslahatchi bo'lgan, "
                       "buddizm homiysi sifatida tanilgan. Saroy kiyimlari va harbiy anjomlarni takomillashtirgani "
                       "manbalarda tilga olinadi."),
        "chinkim": p("Chinkim", "", b="1243", d="1285", pat="Xubilay o'g'li", occ="Valiahd",
                     bio="Xubilay va Chabining o'g'li, Yuan sulolasining valiahdi. Konfutsiychilik ta'limini olgan. "
                         "Otasidan oldin vafot etgan; uning o'g'li Temur O'ljaytu keyinroq imperator bo'lgan."),
        "yesunjin": p("Yesunjin xotun", "", F, occ="Xotun",
                      bio="Hulaguning xotinlaridan, Abaqa xonning onasi."),
        "doquz": p("Do'quz xotun", "", F, d="1265", occ="Bosh xotun",
                   bio="Kerayit qabilasidan, nasroniy (nestorian) malika. Hulaguning bosh xotini, u orqali Elxoniylar "
                       "saroyida nasroniylar himoyaga ega bo'lgan."),
        "abaqa": p("Abaqa", "", b="1234", d="1282", pat="Hulagu o'g'li", occ="Elxon (1265–1282)",
                   bio="Hulagu va Yesunjinning o'g'li. Otasidan keyin Elxoniylar davlatini boshqargan, Oltin O'rda va "
                       "Chig'atoy ulusi bilan urushgan, Misr mamluklariga qarshi Yevropa bilan ittifoq izlagan."),
    },
    "families": [
        ("yesugey", "hoelun", ["chingiz", "qasar", "temuge"]),
        ("chingiz", "borte", ["jochi", "chigatoy", "ogedey", "tuluy"]),
        ("jochi", None, ["orda", "botu", "berka", "shayboni"]),
        ("chigatoy", None, ["moatukan"]),
        ("moatukan", None, ["qarahulagu"]),
        ("ogedey", "toregene", ["goyuk"]),
        ("tuluy", "sorqoqtani", ["monke", "xubilay", "hulagu", "arigboga"]),
        ("xubilay", "chabi", ["chinkim"]),
        ("hulagu", "yesunjin", ["abaqa"]),
        ("hulagu", "doquz", []),
    ],
    "stories": {
        "chingiz": [
            "Onon qurultoyi (1206). Onon daryosi boshlanadigan joyda to'qqiz tug'li oq bayroq tikilib, dasht "
            "qabilalari yig'ilgan. Temuchin bu yerda \"Chingizxon\" unvoni bilan barcha kigiz o'tovli xalqlarning "
            "xoni deb e'lon qilingan. Qurultoyda sodiq safdoshlari minglik boshliqlari etib tayinlangan va "
            "keshik — xonning shaxsiy qo'riqchi qismi tuzilgan.",
            "O'tror voqeasi (1218). Chingizxon Xorazmshoh Alovuddin Muhammad bilan savdo aloqalarini yo'lga qo'yish "
            "uchun katta savdo karvonini yuborgan. O'tror hokimi G'oyirxon (Inolchiq) karvonni josuslikda ayblab, "
            "savdogarlarni o'ldirgan. Tovon so'rab kelgan elchilar ham haqoratlangan. Bu voqea 1219-yilda "
            "Movarounnahr va Xurosonga qilingan halokatli yurishga sabab bo'lgan.",
            "Jaloliddin Manguberdi. Xorazmshohning o'g'li Jaloliddin mo'g'ullarga qattiq qarshilik ko'rsatgan. "
            "1221-yilda Hind (Sind) daryosi bo'yidagi jangda yengilgach, oti bilan jardan daryoga sakrab, qarshi "
            "sohilga suzib o'tgan. Rivoyatga ko'ra, Chingizxon o'g'illariga uni ko'rsatib, \"Otaning o'g'li shunday "
            "bo'lishi kerak\" degan.",
        ],
        "borte": [
            "Merkitlar asirligi. Temuchin va Bo'rte turmush qurgach, ko'p o'tmay merkitlar o'tovlarga hujum qilib, "
            "Bo'rteni olib ketgan. Temuchin otasining anda-do'sti kerayit xoni To'g'rul va o'z anda-do'sti "
            "Jamuxa bilan birgalikda merkitlarga hujum qilib, rafiqasini qutqargan. Bu g'alaba yosh Temuchinning "
            "dashtdagi obro'sini keskin oshirgan.",
        ],
        "botu": [
            "G'arbiy yurish. 1236-yilda boshlangan yurishda Botu qo'shinlari Volga Bulg'oristonini, 1237–1240-"
            "yillarda Rus knyazliklarini, jumladan Ryazan, Vladimir va Kiyevni egallagan. 1241-yilda Legnitsa "
            "(Polsha) va Mohi (Vengriya) janglarida g'alaba qozonilgan. O'gedey qoonning vafoti haqidagi xabar "
            "kelgach, qo'shin sharqqa qaytgan.",
        ],
        "berka": [
            "Birodarlar urushi. 1258-yilda Hulagu Bag'dodni egallab, xalifa Musta'simni qatl ettirgan. Musulmon "
            "bo'lgan Berka bundan g'azablangan. Kavkazdagi yaylovlar ustidagi nizo ham qo'shilib, 1262-yilda "
            "Chingiziylarning ikki tarmog'i o'rtasida ochiq urush boshlangan — mo'g'ul xonlarining bir-biriga "
            "qarshi birinchi yirik to'qnashuvlaridan biri.",
        ],
        "xubilay": [
            "Marko Polo. Venetsiyalik savdogar Marko Polo otasi va amakisi bilan 1275-yil atrofida Xubilay saroyiga "
            "yetib kelgan va 17 yilga yaqin uning xizmatida bo'lgan. Uning Xonbaliq, qog'oz pullar va yam-pochta "
            "tizimi haqidagi hikoyalari keyinchalik \"Dunyo xilma-xilligi haqida kitob\"da yozib olingan.",
        ],
        "hulagu": [
            "Marog'a rasadxonasi. Hulagu qo'lga kiritilgan Alamut qal'asidagi olim Nasiriddin Tusiyni saroyiga "
            "olib, uning taklifi bilan 1259-yilda Marog'ada rasadxona qurdirgan. Rasadxona kutubxonasida minglab "
            "kitoblar to'plangan. Bu tajriba keyinchalik Ulug'bek rasadxonasiga ham ta'sir ko'rsatgan.",
        ],
        "ogedey": [
            "Qoraqurum. O'gedey 1235-yilda O'rxun vodiysida Qoraqurum poytaxtini devor bilan o'rab, saroy qurdirgan. "
            "Shahar turli din vakillari, savdogar va hunarmandlar yashaydigan ko'p millatli markazga aylangan. "
            "Keyinroq bu yerga kelgan flamandiyalik rohib Vilgelm Rubruk saroy oldidagi kumush \"ichimlik daraxti\" "
            "favvorasini tasvirlagan.",
        ],
        "sorqoqtani": [
            "Oqila ona. Fors tarixchisi Rashididdin Sorqoqtani begini o'z davrining eng aqlli ayoli deb ta'riflagan. "
            "U o'g'illarini o'qimishli, turli xalqlar va dinlarga hurmat bilan tarbiyalagan. Ularning to'rttalasi "
            "ham hukmdor bo'lgan: Mo'nke va Xubilay buyuk xon, Hulagu elxon, Arig'bo'ga esa Qoraqurumda xon deb "
            "e'lon qilingan.",
        ],
    },
}

# =====================================================================  HOZIRGI OILA (to'qima)
ZAMONAVIY = {
    "name": "Karimova Madina shajarasi — 7 avlod",
    "root": "madina",
    "kind": "oilaviy",
    "visibility": "private",
    "subject": "",
    "era": "1900–2020",
    "description": (
        "Namunaviy oila shajarasi: Samarqandning Urgut tumanidagi Qoratepa qishlog'idan boshlanib, Sirdaryo va "
        "Toshkentga tarqalgan yetti avlod. Barcha ismlar va voqealar to'qima — platformani sinash va PDF kitobni "
        "ko'rish uchun tuzilgan."
    ),
    "sources": "Oila xotiralari (namunaviy)",
    "people": {
        # 1-avlod
        "rahmonqul": p("Rahmonqul", "Yusupov", b="1900", d="1972", pat="Yusuf o'g'li", occ="Dehqon, mirob",
                       region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa", loc="Qoratepa",
                       bio="Qoratepa qishlog'ida tug'ilgan. Yoshligidan otasi bilan tog' etagidagi bog'larda ishlagan. "
                           "1930-yillarda tuzilgan kolxozda mirob bo'lib, qishloqqa suv keltiradigan ariqlarni "
                           "qazishda bosh-qosh bo'lgan. Uch farzandni o'stirgan."),
        "oysha": p("Oysha bibi", "Yusupova", F, b="1903", d="1986", occ="Uy bekasi, zardo'z",
                   region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa",
                   bio="Qo'shni Kamangaron qishlog'ida tug'ilgan. Mohir zardo'z bo'lgan: qishloq kelinlarining "
                       "ko'pchiligi uning tikkan do'ppi va so'zanalari bilan uzatilgan."),
        # 2-avlod
        "sobir": p("Sobir", "Rahmonqulov", b="1920", d="1995", pat="Rahmonqul o'g'li",
                   occ="Maktab o'qituvchisi, urush qatnashchisi", region="Samarqand viloyati", district="Urgut tumani",
                   village="Qoratepa", loc="Qoratepa",
                   bio="Samarqanddagi o'qituvchilar tayyorlash kursini tugatib, 1939-yilda qishloq maktabida dars bera "
                       "boshlagan. 1942-yilda frontga ketgan, 1945-yilda yaralanib qaytgan. Qirq yil davomida "
                       "Qoratepa maktabida matematika o'qitgan."),
        "hanifa": p("Hanifa", "Sobirova", F, b="1922", d="2011", occ="Hamshira",
                    region="Samarqand viloyati", district="Urgut tumani",
                    bio="Urgutda tug'ilgan. Urush yillarida Samarqanddagi evakuatsiya gospitalida hamshira bo'lib "
                        "ishlagan, keyin qishloq feldsherlik punktida xizmat qilgan."),
        "yusuf": p("Yusuf", "Rahmonqulov", b="1923", d="1943", pat="Rahmonqul o'g'li", occ="Askar",
                   region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa",
                   bio="1941-yil kuzida frontga chaqirilgan. 1943-yil yozida Kursk yoyidagi janglarda halok bo'lgan. "
                       "Ismi Urgutdagi xotira yodgorligida yozilgan."),
        "zebo": p("Zebo", "Rahmonqulova", F, b="1927", d="2008", pat="Rahmonqul qizi", occ="Tikuvchi",
                  region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa", loc="Urgut",
                  bio="Onasidan zardo'zlikni o'rgangan, Urgut tikuvchilik artelida 35 yil ishlagan."),
        # 3-avlod
        "abdulla": p("Abdulla", "Sobirov", b="1940", d="2018", pat="Sobir o'g'li", occ="Gidrotexnik muhandis",
                     region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa", loc="Guliston",
                     bio="Toshkentdagi irrigatsiya institutini tugatgan. 1960-yillarda Mirzacho'lni o'zlashtirishga "
                         "yuborilgan va oilasi bilan Gulistonga ko'chib o'tgan. Kanal va kollektorlar qurilishida "
                         "bosh muhandis bo'lib ishlagan."),
        "nodira": p("Nodira", "Sobirova", F, b="1942", occ="Buxgalter", region="Samarqand viloyati", loc="Guliston",
                    bio="Samarqandda tug'ilgan. Eri bilan Mirzacho'lga ko'chib borgan, sovxoz buxgalteriyasida ishlagan."),
        "mahmuda": p("Mahmuda", "Sobirova", F, b="1947", pat="Sobir qizi", occ="Kutubxonachi",
                     region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa", loc="Samarqand",
                     bio="Samarqand viloyat kutubxonasida qirq yildan ortiq ishlagan."),
        "rustam": p("Rustam", "Sobirov", b="1951", d="2016", pat="Sobir o'g'li", occ="Haydovchi",
                    region="Samarqand viloyati", district="Urgut tumani", village="Qoratepa", loc="Urgut",
                    bio="Urgut avtobazasida yuk mashinasi haydovchisi bo'lib ishlagan."),
        # 4-avlod
        "botir": p("Botir", "Abdullayev", b="1961", pat="Abdulla o'g'li", occ="Jarroh shifokor",
                   region="Sirdaryo viloyati", district="Guliston shahri", loc="Toshkent",
                   bio="Gulistonda tug'ilgan. Toshkent tibbiyot institutini tugatib, respublika shifoxonasida jarroh "
                       "bo'lib ishlaydi. Yigirma yildan ortiq tajribaga ega."),
        "gulnora": p("Gulnora", "Abdullayeva", F, b="1962", occ="Kimyo o'qituvchisi", region="Sirdaryo viloyati",
                     loc="Toshkent",
                     bio="Gulistonda tug'ilgan. Botir bilan maktabda birga o'qigan, 1980-yilda turmush qurgan."),
        "dilbar": p("Dilbar", "Abdullayeva", F, b="1964", pat="Abdulla qizi", occ="Farmatsevt",
                    region="Sirdaryo viloyati", district="Guliston shahri", loc="Guliston"),
        "shuhrat": p("Shuhrat", "Abdullayev", b="1969", pat="Abdulla o'g'li", occ="Tadbirkor",
                     region="Sirdaryo viloyati", district="Guliston shahri", loc="Guliston",
                     bio="Otasining uyida yashaydi, paxta tozalash sohasida kichik korxonasi bor."),
        # 5-avlod
        "dilfuza": p("Dilfuza", "Botirova", F, b="1981", pat="Botir qizi", occ="Boshlang'ich sinf o'qituvchisi",
                     region="Sirdaryo viloyati", district="Guliston shahri", loc="Toshkent",
                     bio="Toshkent pedagogika universitetini tugatgan. 2002-yildan beri Chilonzordagi maktabda "
                         "boshlang'ich sinflarga dars beradi."),
        "farhod": p("Farhod", "Karimov", b="1978", pat="Ravshan o'g'li", occ="Muhandis-quruvchi",
                    region="Toshkent viloyati", district="Chirchiq shahri", loc="Toshkent",
                    bio="Chirchiqda tug'ilgan. Toshkentdagi turar-joy majmualari qurilishida loyiha rahbari."),
        "jamshid": p("Jamshid", "Botirov", b="1984", pat="Botir o'g'li", occ="Bank xodimi",
                     region="Toshkent shahri", loc="Toshkent"),
        "laylo": p("Laylo", "Botirova", F, b="1987", occ="Tarjimon", region="Toshkent shahri", loc="Toshkent"),
        "nigora": p("Nigora", "Botirova", F, b="1990", pat="Botir qizi", occ="Dizayner",
                    region="Toshkent shahri", loc="Toshkent"),
        "ravshan": p("Ravshan", "Karimov", b="1952", d="2014", occ="Avtobus haydovchisi",
                     region="Toshkent viloyati", district="Chirchiq shahri", loc="Chirchiq",
                     bio="Chirchiq shahar avtobus parkida o'ttiz yil ishlagan."),
        "muqaddas": p("Muqaddas", "Karimova", F, b="1955", occ="Tikuvchi", region="Toshkent viloyati",
                      district="Chirchiq shahri", loc="Chirchiq"),
        # 6-avlod
        "madina": p("Madina", "Karimova", F, b="2000", bdate=date(2000, 4, 18), pat="Farhod qizi",
                    occ="Dasturchi", region="Toshkent shahri", district="Chilonzor tumani", loc="Toshkent",
                    bio="Toshkentda tug'ilgan. Axborot texnologiyalari universitetida dasturiy injiniring "
                        "yo'nalishida tahsil olgan. 2019-yilda Javlon Ergashevga turmushga chiqqan. Oila tarixini "
                        "yig'ib, ushbu shajarani tuzishni boshlagan."),
        "sardor": p("Sardor", "Karimov", b="2004", pat="Farhod o'g'li", occ="Talaba", region="Toshkent shahri",
                    loc="Toshkent"),
        "javlon": p("Javlon", "Ergashev", b="1996", occ="Dasturchi", region="Samarqand viloyati",
                    district="Samarqand shahri", loc="Toshkent",
                    bio="Samarqandda tug'ilgan, Toshkentdagi IT kompaniyada backend dasturchi."),
        "aziz": p("Aziz", "Botirov", b="2009", pat="Jamshid o'g'li", occ="O'quvchi", region="Toshkent shahri"),
        "sabina": p("Sabina", "Botirova", F, b="2013", pat="Jamshid qizi", occ="O'quvchi", region="Toshkent shahri"),
        # 7-avlod
        "oyshaxon": p("Oyshaxon", "Ergasheva", F, b="2020", bdate=date(2020, 6, 12), pat="Javlon qizi",
                      region="Toshkent shahri", district="Chilonzor tumani", loc="Toshkent",
                      bio="2020-yil iyunida, karantin kunlarida tug'ilgan. Ismi katta-katta buvisi Oysha bibi "
                          "sharafiga qo'yilgan."),
    },
    "families": [
        ("rahmonqul", "oysha", ["sobir", "yusuf", "zebo"]),
        ("sobir", "hanifa", ["abdulla", "mahmuda", "rustam"]),
        ("abdulla", "nodira", ["botir", "dilbar", "shuhrat"]),
        ("botir", "gulnora", ["dilfuza", "jamshid", "nigora"]),
        ("ravshan", "muqaddas", ["farhod"]),
        ("farhod", "dilfuza", ["madina", "sardor"]),
        ("jamshid", "laylo", ["aziz", "sabina"]),
        ("javlon", "madina", ["oyshaxon"]),
    ],
    "stories": {
        "rahmonqul": [
            "Yong'oq daraxti. Rahmonqul bobo 1935-yilda hovli etagiga yong'oq ko'chati o'tqazgan. \"Men yemasam, "
            "nevaralarim yeydi\", der ekan. O'sha daraxt hozir ham Qoratepadagi eski hovlida turibdi va har kuzda "
            "butun avlod uning mevasidan bahramand bo'ladi.",
            "Katta ariq. 1937-yilgi qurg'oqchilikda qishloq bog'lari qurib qolish xavfi tug'ilgan. Rahmonqul mirob "
            "yigitlarni to'plab, tog' soyidan ikki chaqirim ariq qazdirgan. Keksalar o'sha ariqni hanuz "
            "\"Rahmonqul ariq\" deb atashadi.",
        ],
        "yusuf": [
            "So'nggi maktub. Yusufning frontdan yozgan oltita xati oilada saqlanadi. 1943-yil iyulda yozilgan "
            "oxirgisida u onasiga shunday degan: \"Onajon, xavotir olmang. Qaytib kelsam, hovlidagi yong'oqqa "
            "arg'imchoq osib beraman\". Oradan bir oy o'tib, uning halok bo'lgani haqida qora xat kelgan.",
        ],
        "sobir": [
            "Frontdan qaytish. Sobir 1945-yil kuzida qo'ltiqtayoq bilan qishloqqa qaytgan. Stansiyadan uyigacha "
            "o'n ikki chaqirim yo'lni piyoda bosib, tongda eshikni taqillatganda, xotini Hanifa uni tanimay "
            "qolgan ekan. Keyinchalik u o'quvchilariga har yili 9-may kuni urush haqida hikoya qilib berardi.",
        ],
        "hanifa": [
            "Gospital. 1942–1944-yillarda Hanifa Samarqandga evakuatsiya qilingan gospitalda kechayu kunduz "
            "ishlagan. Yarador askarlarga oilasiga xat yozishda yordam bergan; ulardan birining Ukrainadagi "
            "onasi bilan yozishmasi urushdan keyin ham uzoq yillar davom etgan.",
        ],
        "abdulla": [
            "Mirzacho'l. 1963-yilda yosh muhandis Abdulla xotini va ikki yoshli o'g'li bilan Mirzacho'lga ko'chib "
            "borgan. Dastlabki yillarda ular yozda yerto'lada, qishda chodirda yashagan. Abdulla o'zi loyihalagan "
            "birinchi kanalga suv qo'yilgan kunni hayotining eng baxtli kuni deb eslardi.",
        ],
        "botir": [
            "Birinchi operatsiya. 1988-yilda yosh jarroh Botir tungi navbatchilikda, bo'limda katta shifokor "
            "bo'lmagan bir paytda, avtohalokatga uchragan o'smirni operatsiya qilishiga to'g'ri kelgan. Bola "
            "tuzalib ketgan va yillar o'tib o'zi ham shifokor bo'lgan. Ular hozirgacha har yili Navro'zda "
            "ko'rishib turadi.",
        ],
        "dilfuza": [
            "Yigirma yillik sinf. Dilfuza opa birinchi o'quvchilarini 2002-yilda qabul qilgan. 2022-yilda o'sha "
            "sinf o'quvchilari maktabni tugatganlariga o'n yil to'lishi munosabati bilan ustozlarini yo'qlab "
            "kelib, uning sharafiga maktab hovlisiga chinor ko'chati o'tqazishgan.",
        ],
        "madina": [
            "Shajara qanday boshlandi. 2019-yil qishida Madina buvisi Gulnoradan eski suratlar albomini so'rab "
            "olgan. Albomdagi har bir surat ortidagi ismlarni yozib chiqib, Qoratepaga borib keksa qarindoshlardan "
            "so'rab-surishtirgan. Shu tariqa yetti avlodni birlashtirgan ushbu shajara paydo bo'lgan.",
        ],
        "oyshaxon": [
            "Karantin chaqalog'i. Oyshaxon 2020-yil 12-iyunda, karantin cheklovlari davrida tug'ilgan. Katta "
            "bobosi Botir shifoxonada navbatchilikda bo'lgani uchun chevarasini birinchi marta video qo'ng'iroq "
            "orqali ko'rgan. Oiladagilar uni hazil bilan \"onlayn tug'ilgan qiz\" deb atashadi.",
        ],
    },
}

SHOWCASE = [TEMURIYLAR, BOBURIYLAR, CHINGIZIYLAR, ZAMONAVIY]


class Command(BaseCommand):
    help = "Namunaviy to'liq shajaralar: Temuriylar, Boburiylar, Chingiziylar va 7 avlodli zamonaviy oila."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="tarixchi")
        parser.add_argument("--password", help="Foydalanuvchi paroli (yangi foydalanuvchi uchun majburiy)")
        parser.add_argument("--clear", action="store_true", help="Faqat o'chirish")

    def handle(self, *args, **opts):
        username = opts["username"]
        user = User.objects.filter(username=username).first()

        if user:
            removed = self.clear(user)
            if removed:
                self.stdout.write(f"Avvalgi namunalar o'chirildi: {removed} ta shajara.")
        if opts["clear"]:
            return

        if not user:
            if not opts["password"]:
                raise CommandError("Yangi foydalanuvchi uchun --password kerak.")
            user = User.objects.create_user(username=username, password=opts["password"],
                                            first_name="Tarix", last_name="o'qituvchisi")
        elif opts["password"]:
            user.set_password(opts["password"])
            user.save()
        UserProfile.objects.update_or_create(user=user, defaults={
            "role": "oqituvchi", "region": "Samarqand viloyati", "email_verified": True, "tour_done": True})

        with transaction.atomic():
            for spec in SHOWCASE:
                tree, people = self.build(user, spec)
                self.link_maps(tree, spec, people)
                n_stories = sum(len(v) for v in spec["stories"].values())
                self.stdout.write(f"  · {tree.name}: {len(people)} shaxs, {len(spec['families'])} oila, {n_stories} hikoya")
        self.stdout.write(self.style.SUCCESS(f"Tayyor. Foydalanuvchi: {username}"))

    def clear(self, user):
        names = [spec["name"] for spec in SHOWCASE]
        trees = Tree.objects.filter(owner=user, name__in=names)
        count = trees.count()
        person_ids = set(Person.objects.filter(added_by=user).values_list("id", flat=True))
        HistoricalMap.objects.filter(tree__in=trees).update(tree=None)
        MapPlace.objects.filter(person_id__in=person_ids).update(person=None)
        trees.delete()
        Family.objects.filter(father_id__in=person_ids).delete()
        Family.objects.filter(mother_id__in=person_ids).delete()
        Person.objects.filter(id__in=person_ids).delete()
        return count

    def build(self, user, spec):
        people = {}
        for key, fields in spec["people"].items():
            people[key] = Person.objects.create(added_by=user, **fields)
        for father, mother, children in spec["families"]:
            fam = Family.objects.create(father=people[father] if father else None,
                                        mother=people[mother] if mother else None)
            for child in children:
                person = people[child]
                person.child_family = fam
                person.save(update_fields=["child_family"])
        for key, texts in spec["stories"].items():
            for text in texts:
                PersonStory.objects.create(person=people[key], author=user, text=text)
        featured = bool(spec.get("slug")) and spec["kind"] == "talimiy" and spec["visibility"] == "public"
        if featured:
            Tree.objects.filter(slug=spec["slug"]).update(slug=None, is_featured=False)
        tree = Tree.objects.create(owner=user, root_person=people[spec["root"]], name=spec["name"],
                                   description=spec["description"], visibility=spec["visibility"],
                                   kind=spec["kind"], subject=spec["subject"], era=spec["era"],
                                   sources=spec["sources"], is_featured=featured,
                                   slug=spec["slug"] if featured else None, seo_description=spec.get("seo", ""),
                                   featured_at=timezone.now() if featured else None)
        return tree, people

    def link_maps(self, tree, spec, people):
        """Namunaviy xaritalar (seed_maps) hali shajarasiz bo'lsa, mos shajaraga ulanadi."""
        title_word = {"temuriylar": "Temur", "boburiylar": "Bobur"}.get(spec["name"].split()[0].lower())
        if not title_word:
            return
        hmap = HistoricalMap.objects.filter(is_sample=True, tree__isnull=True, title__icontains=title_word).first()
        if not hmap:
            return
        hmap.tree = tree
        hmap.save(update_fields=["tree"])
        root = people[spec["root"]]
        hmap.places.filter(kind__in=("tugilgan", "vafot")).update(person=root)
