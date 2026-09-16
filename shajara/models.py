import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

OTP_TTL = timedelta(minutes=3)
OTP_MAX_ATTEMPTS = 3

# Length of the random, URL-safe key that identifies a tree in its URLs.
# 16 random bytes -> 22 base64url characters -> far too large to enumerate.
TREE_KEY_BYTES = 16
TREE_KEY_LENGTH = 22


def make_tree_key():
    """An unguessable, URL-safe identifier used in place of the database id."""
    return secrets.token_urlsafe(TREE_KEY_BYTES)


GENDER_CHOICES = [
    ("erkak", "Erkak"),
    ("ayol", "Ayol"),
]

REQUEST_STATUS_CHOICES = [
    ("pending", "Kutilmoqda"),
    ("accepted", "Qabul qilingan"),
    ("declined", "Rad etilgan"),
]

REGION_CHOICES = [
    ("", "— tanlanmagan —"),
    ("Andijon viloyati", "Andijon viloyati"),
    ("Buxoro viloyati", "Buxoro viloyati"),
    ("Farg'ona viloyati", "Farg'ona viloyati"),
    ("Jizzax viloyati", "Jizzax viloyati"),
    ("Xorazm viloyati", "Xorazm viloyati"),
    ("Namangan viloyati", "Namangan viloyati"),
    ("Navoiy viloyati", "Navoiy viloyati"),
    ("Qashqadaryo viloyati", "Qashqadaryo viloyati"),
    ("Qoraqalpog'iston Respublikasi", "Qoraqalpog'iston Respublikasi"),
    ("Samarqand viloyati", "Samarqand viloyati"),
    ("Sirdaryo viloyati", "Sirdaryo viloyati"),
    ("Surxondaryo viloyati", "Surxondaryo viloyati"),
    ("Toshkent viloyati", "Toshkent viloyati"),
    ("Toshkent shahri", "Toshkent shahri"),
    ("Boshqa", "Boshqa (O'zbekistondan tashqari)"),
]

RELATION_CHOICES = [
    ("ota", "Otasi"),
    ("ona", "Onasi"),
    ("farzand", "Farzandi"),
    ("akauka", "Aka/uka, opa/singili"),
    ("turmush", "Turmush o'rtog'i"),
]


class Family(models.Model):
    """A parental unit: a father and/or mother and their children."""

    father = models.ForeignKey(
        "Person", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="families_as_father",
    )
    mother = models.ForeignKey(
        "Person", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="families_as_mother",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def has_slot(self, slot):
        return bool(getattr(self, "father" if slot == "ota" else "mother"))

    def __str__(self):
        return f"Oila #{self.pk}"


class Person(models.Model):
    first_name = models.CharField("Ismi", max_length=100)
    last_name = models.CharField("Familyasi", max_length=100, blank=True)
    patronymic = models.CharField(
        "Otasining ismi", max_length=100, blank=True,
        help_text="Masalan: Ahmadovich yoki Ahmad o'g'li",
    )
    gender = models.CharField("Jinsi", max_length=5, choices=GENDER_CHOICES)
    birth_date = models.DateField("Tug'ilgan sana", null=True, blank=True)
    birth_year = models.CharField("Tug'ilgan yili (taxminiy)", max_length=20, blank=True)
    death_year = models.CharField("Vafot etgan yili", max_length=20, blank=True)
    occupation = models.CharField("Kasbi", max_length=150, blank=True)
    location = models.CharField("Yashash joyi", max_length=150, blank=True)
    birth_region = models.CharField("Tug'ilgan viloyati", max_length=60, blank=True, choices=REGION_CHOICES)
    birth_district = models.CharField("Tug'ilgan tumani", max_length=100, blank=True)
    birth_village = models.CharField("Tug'ilgan qishloq/mahalla", max_length=150, blank=True)
    bio = models.TextField("Qisqacha ma'lumot", blank=True)
    photo = models.ImageField("Surati", upload_to="people/", blank=True, null=True)

    child_family = models.ForeignKey(
        Family, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="children",
        help_text="Bu odam farzand bo'lgan oila",
    )

    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="added_people",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Shaxs"
        verbose_name_plural = "Shaxslar"

    def __str__(self):
        return self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def full_name_with_patronymic(self):
        return " ".join(x for x in (self.last_name, self.first_name, self.patronymic) if x)

    @property
    def birth_place(self):
        return ", ".join(x for x in (self.birth_village, self.birth_district, self.birth_region) if x)

    @property
    def display_year(self):
        if self.birth_date:
            return str(self.birth_date.year)
        return self.birth_year

    def parent_families(self):
        """Every family (marriage) where this person is a father or mother."""
        return Family.objects.filter(Q(father=self) | Q(mother=self)).order_by("id")

    def spouses(self):
        """List of (family, spouse_person_or_None) for every marriage."""
        result = []
        for fam in self.parent_families():
            other = fam.mother if fam.father_id == self.pk else fam.father
            result.append((fam, other))
        return result

    def siblings(self):
        if not self.child_family_id:
            return Person.objects.none()
        return self.child_family.children.exclude(pk=self.pk)


class PersonStory(models.Model):
    """A memory/story about a person, contributed by anyone in their tree."""

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="stories")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="stories_written"
    )
    text = models.TextField("Hikoya")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Hikoya"
        verbose_name_plural = "Hikoyalar"

    def __str__(self):
        return f"{self.person} haqida hikoya #{self.pk}"


VISIBILITY_CHOICES = [
    ("private", "Shaxsiy"),
    ("public", "Ommaviy"),
]

# What a tree is for. A family tree is built together by relatives; a
# learning tree maps a dynasty or a historical figure for study and teaching.
TREE_KIND_CHOICES = [
    ("oilaviy", "Oilaviy shajara"),
    ("talimiy", "Ta'limiy shajara"),
]

# Who the person signing up is — used to tailor the start page and hints.
USER_ROLE_CHOICES = [
    ("oila", "Oilam shajarasini tuzmoqchiman"),
    ("abituriyent", "Abituriyentman"),
    ("talaba", "Talabaman"),
    ("oqituvchi", "O'qituvchiman"),
    ("ixlosmand", "Tarix ixlosmandiman"),
]

LEARNER_ROLES = ("abituriyent", "talaba", "oqituvchi", "ixlosmand")


def preview_upload_to(instance, filename):
    """Random names: the file is only ever handed out through a view that
    checks access, and its name must not be guessable either."""
    return f"previews/{secrets.token_hex(16)}.png"


class Tree(models.Model):
    """A single family tree: one owner, one anchor (root) person, its own
    visibility. A user may own several — their own family, plus e.g. a
    historical figure's tree built for study."""

    public_id = models.CharField(
        "Havola kaliti", max_length=TREE_KEY_LENGTH, unique=True,
        default=make_tree_key, editable=False, db_index=True,
        help_text="Shajara URL manzilida ishlatiladigan tasodifiy kalit",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trees"
    )
    root_person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="rooted_trees"
    )
    name = models.CharField("Nomi", max_length=150)
    description = models.TextField("Tavsif", blank=True)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default="private")
    kind = models.CharField("Turi", max_length=10, choices=TREE_KIND_CHOICES, default="oilaviy", db_index=True)
    subject = models.CharField(
        "Fan / mavzu", max_length=150, blank=True,
        help_text="Masalan: O'zbekiston tarixi — Temuriylar davri",
    )
    era = models.CharField("Davr", max_length=100, blank=True, help_text="Masalan: XIV–XVI asrlar")
    sources = models.TextField(
        "Manbalar", blank=True,
        help_text="Darslik, kitob yoki maqolalar — har birini yangi qatordan yozing",
    )
    # A picture of the tree, made on the map by the owner or an editor. It is
    # shown when an invite link is shared (messenger previews) and on the
    # invite page, so people see what they are being invited to.
    preview_image = models.ImageField("Ko'rinish rasmi", upload_to=preview_upload_to, blank=True, null=True)
    preview_updated_at = models.DateTimeField(null=True, blank=True)
    # Card positions the owner saved on the map: {"<person id>": [x, y]}.
    # Empty means the board arranges itself.
    layout = models.JSONField("Xarita tartibi", default=dict, blank=True)
    # Open (SEO) pages: an admin picks public learning trees to show at
    # /shajaralar/<slug>/ without signing in, for search engines and visitors.
    is_featured = models.BooleanField("Ochiq sahifada ko'rsatilsin", default=False, db_index=True)
    slug = models.SlugField("Ochiq sahifa manzili", max_length=160, unique=True, null=True, blank=True)
    seo_description = models.CharField(
        "Qidiruv tizimlari uchun tavsif", max_length=300, blank=True,
        help_text="Google natijasida sarlavha ostida chiqadigan 1–2 gap (70–160 belgi)",
    )
    public_views = models.PositiveIntegerField("Ochiq sahifa ko'rishlari", default=0)
    featured_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Shajara"
        verbose_name_plural = "Shajaralar"

    def __str__(self):
        return self.name

    @property
    def url_key(self):
        """What every {% url %} tag and redirect passes instead of the pk."""
        return self.public_id

    @property
    def is_public(self):
        return self.visibility == "public"

    @property
    def is_learning(self):
        return self.kind == "talimiy"

    @property
    def can_be_featured(self):
        """Only public learning trees go on open pages: family trees hold
        living people, whose details must never reach search engines."""
        return self.is_public and self.is_learning

    @property
    def is_open_page(self):
        return self.is_featured and bool(self.slug) and self.can_be_featured

    @property
    def source_list(self):
        return [line.strip() for line in self.sources.splitlines() if line.strip()]

    @property
    def gratitude_count(self):
        return self.gratitudes.count()

    @property
    def comment_count(self):
        return self.comments.count()


class TreeComment(models.Model):
    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tree_comments"
    )
    text = models.TextField("Izoh", max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Izoh"
        verbose_name_plural = "Izohlar"

    def __str__(self):
        return f"{self.author}: {self.tree}"


class TreeGratitude(models.Model):
    """The 🙏 reaction — a quieter, single-toggle alternative to a 'like'."""

    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="gratitudes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tree_gratitudes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("tree", "user")

    def __str__(self):
        return f"{self.user} -> {self.tree}"


class ConnectionRequest(models.Model):
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_requests"
    )
    from_tree = models.ForeignKey(
        "Tree", null=True, blank=True, on_delete=models.CASCADE, related_name="sent_requests",
        help_text="Qaysi shajarangiz orqali bog'lanmoqchisiz",
    )
    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="received_requests"
    )
    message = models.CharField("Xabar", max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=REQUEST_STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.status})"


# Someone counts as online if a page of theirs loaded within this window.
ONLINE_WINDOW = timedelta(minutes=5)


class UserProfile(models.Model):
    """Extra per-account data the built-in User model doesn't hold."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    email_verified = models.BooleanField("Email tasdiqlangan", default=False)
    region = models.CharField("Viloyati", max_length=60, blank=True, choices=REGION_CHOICES)
    role = models.CharField("Kimsiz", max_length=12, blank=True, choices=USER_ROLE_CHOICES)
    last_seen = models.DateTimeField("Oxirgi faollik", null=True, blank=True, db_index=True)
    tour_done = models.BooleanField("Tanishuv qo'llanmasi ko'rilgan", default=False)

    @property
    def is_online(self):
        return bool(self.last_seen and timezone.now() - self.last_seen <= ONLINE_WINDOW)

    @property
    def is_learner(self):
        return self.role in LEARNER_ROLES

    def __str__(self):
        return f"{self.user.username} profili"


# ============================================================ collaboration --

MEMBER_ROLE_CHOICES = [
    ("muharrir", "Muharrir"),
    ("kuzatuvchi", "Kuzatuvchi"),
]

MEMBER_ROLE_HELP = {
    "muharrir": "Odam qo'shadi, ma'lumotlarni tahrirlaydi, hikoya yozadi",
    "kuzatuvchi": "Shajarani ko'radi, hikoya va izoh yozadi, test ishlaydi",
}


class TreeMember(models.Model):
    """Someone the owner let into a tree: a relative helping to fill in the
    family, or a student in a teacher's learning tree."""

    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tree_memberships")
    role = models.CharField("Huquqi", max_length=12, choices=MEMBER_ROLE_CHOICES, default="muharrir")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["joined_at"]
        unique_together = ("tree", "user")
        verbose_name = "Shajara a'zosi"
        verbose_name_plural = "Shajara a'zolari"

    def __str__(self):
        return f"{self.user} @ {self.tree} ({self.role})"

    @property
    def can_edit(self):
        return self.role == "muharrir"


def make_invite_token():
    return secrets.token_urlsafe(24)


INVITE_TTL_CHOICES = [
    ("1", "1 kun"),
    ("7", "7 kun"),
    ("30", "30 kun"),
    ("0", "Muddatsiz"),
]


class TreeInvite(models.Model):
    """A secret link that lets whoever opens it join a tree with a given
    role. The owner can share it anywhere (Telegram, SMS) and revoke it."""

    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="invites")
    token = models.CharField(max_length=40, unique=True, default=make_invite_token, editable=False)
    role = models.CharField(max_length=12, choices=MEMBER_ROLE_CHOICES, default="muharrir")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    uses = models.PositiveIntegerField(default=0)
    revoked = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Taklif havolasi"
        verbose_name_plural = "Taklif havolalari"

    def __str__(self):
        return f"{self.tree} taklifi ({self.role})"

    @property
    def is_expired(self):
        return bool(self.expires_at and timezone.now() > self.expires_at)

    @property
    def is_active(self):
        return not self.revoked and not self.is_expired


EXPORT_KIND_CHOICES = [
    ("pdf", "PDF kitob"),
    ("png", "PNG rasm"),
    ("svg", "SVG rasm"),
]

# No 0/O, 1/I/L: the code is read off paper and typed by hand.
EXPORT_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def make_export_code():
    return "".join(secrets.choice(EXPORT_CODE_ALPHABET) for _ in range(10))


class ExportRecord(models.Model):
    """Every PDF book or tree picture carries a code and a QR link to a public
    check page. Anyone holding a printout can confirm it really came from
    the platform, when, from which tree and how complete it was then."""

    code = models.CharField(max_length=10, unique=True, default=make_export_code, editable=False)
    tree = models.ForeignKey(Tree, null=True, on_delete=models.SET_NULL, related_name="exports")
    tree_name = models.CharField(max_length=150)
    tree_kind = models.CharField(max_length=10, choices=TREE_KIND_CHOICES, default="oilaviy")
    root_name = models.CharField(max_length=210, blank=True)
    kind = models.CharField(max_length=5, choices=EXPORT_KIND_CHOICES)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    people_count = models.PositiveIntegerField(default=0)
    generations = models.PositiveIntegerField(default=0)
    contributors = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Eksport yozuvi"
        verbose_name_plural = "Eksport yozuvlari"

    def __str__(self):
        return f"{self.pretty_code} — {self.tree_name}"

    @property
    def pretty_code(self):
        return f"SH-{self.code[:5]}-{self.code[5:]}"


class QuizAttempt(models.Model):
    """One finished self-test on a tree — lets a teacher see how the class did."""

    tree = models.ForeignKey(Tree, on_delete=models.CASCADE, related_name="quiz_attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    score = models.PositiveSmallIntegerField()
    total = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Test natijasi"
        verbose_name_plural = "Test natijalari"

    @property
    def percent(self):
        return round(100 * self.score / self.total) if self.total else 0


# ======================================================== historical maps --

def map_upload_to(instance, filename):
    ext = "png" if str(filename).lower().endswith(".png") else "jpg"
    return f"maps/{secrets.token_hex(16)}.{ext}"


PLACE_KIND_CHOICES = [
    ("shahar", "Shahar"),
    ("poytaxt", "Poytaxt"),
    ("jang", "Jang"),
    ("voqea", "Voqea"),
    ("qarorgoh", "Qarorgoh"),
    ("tugilgan", "Tug'ilgan joy"),
    ("vafot", "Vafot etgan joy"),
    ("yodgorlik", "Yodgorlik"),
]

ROUTE_KIND_CHOICES = [
    ("harbiy", "Harbiy yurish"),
    ("savdo", "Savdo yo'li"),
    ("kochish", "Ko'chish"),
    ("sayohat", "Sayohat"),
    ("elchilik", "Elchilik"),
]


def year_label(year):
    """-329 -> 'mil. av. 329', 1398 -> '1398'."""
    if year is None:
        return ""
    return f"mil. av. {-year}" if year < 0 else str(year)


class HistoricalMap(models.Model):
    """An old (or any) map image with dated places on it and the routes that
    join them — campaigns, caravans, migrations. Used to study a period, and
    optionally tied to a tree so places can point at people in it."""

    public_id = models.CharField(max_length=TREE_KEY_LENGTH, unique=True, default=make_tree_key,
                                 editable=False, db_index=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="historical_maps")
    title = models.CharField("Nomi", max_length=150)
    era = models.CharField("Davr", max_length=100, blank=True)
    description = models.TextField("Tavsif", blank=True)
    sources = models.TextField("Manbalar", blank=True)
    image = models.ImageField("Xarita rasmi", upload_to=map_upload_to)
    image_width = models.PositiveIntegerField(default=0)
    image_height = models.PositiveIntegerField(default=0)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default="private")
    tree = models.ForeignKey(Tree, null=True, blank=True, on_delete=models.SET_NULL, related_name="historical_maps",
                             verbose_name="Bog'langan shajara")
    is_sample = models.BooleanField("Namunaviy", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Tarixiy xarita"
        verbose_name_plural = "Tarixiy xaritalar"

    def __str__(self):
        return self.title

    @property
    def url_key(self):
        return self.public_id

    @property
    def is_public(self):
        return self.visibility == "public"

    @property
    def source_list(self):
        return [line.strip() for line in self.sources.splitlines() if line.strip()]


class MapPlace(models.Model):
    """A point on the map. x and y are fractions of the image (0..1), so the
    marker stays put whatever size the picture is shown at."""

    map = models.ForeignKey(HistoricalMap, on_delete=models.CASCADE, related_name="places")
    name = models.CharField("Nomi", max_length=120)
    kind = models.CharField("Turi", max_length=12, choices=PLACE_KIND_CHOICES, default="shahar")
    x = models.FloatField()
    y = models.FloatField()
    year = models.IntegerField("Yil", null=True, blank=True, help_text="Miloddan avvalgi yillar manfiy: -329")
    year_end = models.IntegerField("Tugagan yil", null=True, blank=True)
    description = models.TextField("Tavsif", blank=True)
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="map_places")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["year", "id"]

    def __str__(self):
        return f"{self.name} ({year_label(self.year)})"


class MapRoute(models.Model):
    """A journey through places in order. `stops` is a list of
    {"place": <MapPlace id>, "year": <int or null>}."""

    map = models.ForeignKey(HistoricalMap, on_delete=models.CASCADE, related_name="routes")
    name = models.CharField("Nomi", max_length=150)
    kind = models.CharField("Turi", max_length=12, choices=ROUTE_KIND_CHOICES, default="harbiy")
    color = models.CharField("Rangi", max_length=7, default="#b3261e")
    year_start = models.IntegerField(null=True, blank=True)
    year_end = models.IntegerField(null=True, blank=True)
    description = models.TextField("Tavsif", blank=True)
    stops = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["year_start", "id"]

    def __str__(self):
        return self.name


OTP_PURPOSE_CHOICES = [
    ("verify", "Emailni tasdiqlash"),
    ("reset", "Parolni tiklash"),
]


class EmailOTP(models.Model):
    """A short-lived 6-digit one-time code sent to a user's email."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="otps"
    )
    email = models.EmailField("Email")
    code = models.CharField(max_length=6)
    purpose = models.CharField(max_length=10, choices=OTP_PURPOSE_CHOICES)
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} — {self.purpose} ({self.code})"

    @property
    def is_expired(self):
        return timezone.now() > self.created_at + OTP_TTL

    @property
    def attempts_left(self):
        return max(0, OTP_MAX_ATTEMPTS - self.attempts)

    def is_valid(self):
        return not self.consumed and not self.is_expired and self.attempts < OTP_MAX_ATTEMPTS

    @classmethod
    def issue(cls, user, email, purpose):
        """Invalidate any prior codes for this purpose and create a fresh one."""
        cls.objects.filter(user=user, purpose=purpose, consumed=False).update(consumed=True)
        code = f"{secrets.randbelow(1_000_000):06d}"
        return cls.objects.create(user=user, email=email, code=code, purpose=purpose)


# ================================================================ admin data --

ACTIVITY_CHOICES = [
    ("register", "Ro'yxatdan o'tdi"),
    ("login", "Tizimga kirdi"),
    ("login_failed", "Kirish muvaffaqiyatsiz"),
    ("logout", "Tizimdan chiqdi"),
    ("email_verified", "Emailni tasdiqladi"),
    ("password_reset", "Parolni tikladi"),
    ("tree_create", "Shajara yaratdi"),
    ("tree_import", "Shajarani JSON'dan tikladi"),
    ("tree_update", "Shajara sozlamalarini o'zgartirdi"),
    ("tree_delete", "Shajarani o'chirdi"),
    ("tree_export", "Shajarani yuklab oldi"),
    ("tree_layout", "Xarita tartibini saqladi"),
    ("invite_create", "Taklif havolasi yaratdi"),
    ("invite_revoke", "Taklif havolasini bekor qildi"),
    ("member_join", "Shajaraga qo'shildi"),
    ("member_role", "A'zo huquqini o'zgartirdi"),
    ("member_remove", "A'zoni chiqarib yubordi"),
    ("member_leave", "Shajaradan chiqdi"),
    ("quiz_finish", "Test ishladi"),
    ("map_create", "Tarixiy xarita yaratdi"),
    ("map_update", "Tarixiy xaritani o'zgartirdi"),
    ("map_delete", "Tarixiy xaritani o'chirdi"),
    ("person_add", "Shaxs qo'shdi"),
    ("person_edit", "Shaxsni tahrirladi"),
    ("person_delete", "Shaxsni o'chirdi"),
    ("story_add", "Hikoya yozdi"),
    ("comment_add", "Izoh qoldirdi"),
    ("gratitude", "Minnatdorchilik bildirdi"),
    ("request_send", "Bog'lanish so'rovi yubordi"),
    ("request_accept", "So'rovni qabul qildi"),
    ("request_decline", "So'rovni rad etdi"),
    ("admin_view_private", "Admin: shaxsiy shajarani ko'rdi"),
    ("admin_user_update", "Admin: foydalanuvchini o'zgartirdi"),
    ("admin_tree_update", "Admin: shajarani o'zgartirdi"),
    ("admin_tree_delete", "Admin: shajarani o'chirdi"),
    ("admin_match_run", "Admin: moslik qidiruvini ishga tushirdi"),
    ("admin_match_reject", "Admin: moslikni rad etdi"),
    ("admin_merge", "Admin: shaxslarni birlashtirdi"),
    ("admin_seo_update", "Admin: ochiq (SEO) sahifani o'zgartirdi"),
]


class ActivityLog(models.Model):
    """What people did, for the admin panel's audit trail."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activity",
    )
    action = models.CharField(max_length=30, choices=ACTIVITY_CHOICES, db_index=True)
    detail = models.CharField(max_length=300, blank=True)
    tree = models.ForeignKey("Tree", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    person = models.ForeignKey(Person, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Faollik"
        verbose_name_plural = "Faollik jurnali"

    def __str__(self):
        return f"{self.user or '-'}: {self.get_action_display()}"


MATCH_STATUS_CHOICES = [
    ("pending", "Ko'rib chiqilmagan"),
    ("merged", "Birlashtirilgan"),
    ("rejected", "Rad etilgan"),
]


class MatchCandidate(models.Model):
    """A hypothesis produced by cross-tree matching: two person records in
    unconnected family graphs that may describe the same human being.
    Only staff ever see these."""

    person_a = models.ForeignKey(Person, null=True, on_delete=models.SET_NULL, related_name="+")
    person_b = models.ForeignKey(Person, null=True, on_delete=models.SET_NULL, related_name="+")
    pair_key = models.CharField(max_length=40, unique=True)
    score = models.PositiveSmallIntegerField("Ishonch indeksi", db_index=True)
    breakdown = models.JSONField(default=list)
    snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=MATCH_STATUS_CHOICES, default="pending", db_index=True)
    note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-score", "-updated_at"]
        verbose_name = "Moslik nomzodi"
        verbose_name_plural = "Moslik nomzodlari"

    def __str__(self):
        return f"{self.pair_key} ({self.score}%)"

    @staticmethod
    def key_for(a_id, b_id):
        lo, hi = sorted((int(a_id), int(b_id)))
        return f"{lo}-{hi}"


class MatchRun(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    persons_scanned = models.PositiveIntegerField(default=0)
    pairs_compared = models.PositiveIntegerField(default=0)
    candidates_found = models.PositiveIntegerField(default=0)
    candidates_new = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-started_at"]


class MergeRecord(models.Model):
    """An executed merge, kept for accountability. `snapshot` holds both
    family graphs as they were before, so a mistake can be traced and
    rebuilt by hand."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+",
    )
    candidate = models.ForeignKey(
        MatchCandidate, null=True, blank=True, on_delete=models.SET_NULL, related_name="merges",
    )
    kept_person = models.ForeignKey(Person, null=True, on_delete=models.SET_NULL, related_name="+")
    kept_name = models.CharField(max_length=250)
    dropped_name = models.CharField(max_length=250)
    persons_merged = models.PositiveIntegerField(default=1)
    log = models.JSONField(default=list)
    trees = models.JSONField(default=list)
    snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
