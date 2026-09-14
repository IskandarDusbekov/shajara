import datetime
import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm

from .models import (
    INVITE_TTL_CHOICES, MEMBER_ROLE_CHOICES, REGION_CHOICES, RELATION_CHOICES, TREE_KIND_CHOICES,
    USER_ROLE_CHOICES, VISIBILITY_CHOICES, ConnectionRequest, Person, Tree,
)

User = get_user_model()


def _validate_unique_email(email, exclude_user=None):
    email = email.strip().lower()
    qs = User.objects.filter(email__iexact=email)
    if exclude_user:
        qs = qs.exclude(pk=exclude_user.pk)
    if qs.exists():
        raise forms.ValidationError("Bu email boshqa hisobga bog'langan.")
    return email


class RegisterForm(forms.Form):
    first_name = forms.CharField(label="Ismingiz", max_length=100)
    last_name = forms.CharField(label="Familyangiz", max_length=100, required=False)
    username = forms.CharField(label="Foydalanuvchi nomi", max_length=150)
    email = forms.EmailField(label="Email (ixtiyoriy)", required=False)
    region = forms.ChoiceField(label="Qaysi viloyatdansiz?", choices=REGION_CHOICES, required=False)
    role = forms.ChoiceField(label="Platformadan nima uchun foydalanasiz?", choices=USER_ROLE_CHOICES,
                             required=False)
    password1 = forms.CharField(label="Parol", widget=forms.PasswordInput, min_length=6)
    password2 = forms.CharField(label="Parolni takrorlang", widget=forms.PasswordInput)

    def clean_username(self):
        username = self.cleaned_data["username"].strip().lower()
        if not username.replace("_", "").replace("-", "").isalnum():
            raise forms.ValidationError(
                "Foydalanuvchi nomi faqat lotin harflari, raqamlar, _ va - dan iborat bo'lsin."
            )
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Bu foydalanuvchi nomi band.")
        return username

    def clean_email(self):
        email = self.cleaned_data.get("email", "")
        if not email:
            return ""
        return _validate_unique_email(email)

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parollar mos kelmadi.")
        return cleaned


class RegionForm(forms.Form):
    region = forms.ChoiceField(label="Viloyatingiz", choices=REGION_CHOICES, required=False)
    role = forms.ChoiceField(label="Kimsiz", choices=[("", "— tanlanmagan —")] + USER_ROLE_CHOICES,
                             required=False)


class EmailForm(forms.Form):
    """Set or change the account email (before sending a verification code)."""
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={
        "class": "stack-input", "placeholder": "email@example.com", "autocomplete": "email",
    }))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_email(self):
        return _validate_unique_email(self.cleaned_data["email"], exclude_user=self.user)


class OTPForm(forms.Form):
    code = forms.CharField(label="Tasdiqlash kodi", max_length=6, widget=forms.TextInput(attrs={
        "class": "stack-input", "placeholder": "6 xonali kod", "inputmode": "numeric",
        "autocomplete": "one-time-code", "maxlength": "6",
    }))

    def clean_code(self):
        return self.cleaned_data["code"].strip()


class PasswordResetRequestForm(forms.Form):
    login = forms.CharField(label="Foydalanuvchi nomi yoki email", widget=forms.TextInput(attrs={
        "class": "stack-input", "placeholder": "Foydalanuvchi nomi yoki email", "autocomplete": "username",
    }))


class SetNewPasswordForm(forms.Form):
    password1 = forms.CharField(label="Yangi parol", min_length=6, widget=forms.PasswordInput(attrs={
        "class": "stack-input", "placeholder": "Yangi parol",
    }))
    password2 = forms.CharField(label="Yangi parolni takrorlang", widget=forms.PasswordInput(attrs={
        "class": "stack-input", "placeholder": "Yangi parolni takrorlang",
    }))

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Parollar mos kelmadi.")
        return cleaned


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Foydalanuvchi nomi")
    password = forms.CharField(label="Parol", widget=forms.PasswordInput)


class TreeCreateForm(forms.Form):
    kind = forms.ChoiceField(label="Shajara turi", choices=TREE_KIND_CHOICES, initial="oilaviy",
                             widget=forms.RadioSelect)
    subject = forms.CharField(label="Fan / mavzu", max_length=150, required=False,
                              widget=forms.TextInput(attrs={
                                  "class": "field", "placeholder": "Masalan: O'zbekiston tarixi, 7-sinf",
                              }))
    era = forms.CharField(label="Davr", max_length=100, required=False,
                          widget=forms.TextInput(attrs={"class": "field", "placeholder": "Masalan: XIV–XVI asrlar"}))
    tree_name = forms.CharField(label="Shajara nomi", max_length=150,
                                 widget=forms.TextInput(attrs={
                                     "class": "field", "placeholder": "Masalan: Mening oilam yoki Amir Temur shajarasi",
                                 }))
    description = forms.CharField(label="Tavsif (ixtiyoriy)", required=False,
                                   widget=forms.Textarea(attrs={"class": "field", "rows": 2}))
    visibility = forms.ChoiceField(label="Ko'rinishi", choices=VISIBILITY_CHOICES, initial="private",
                                    widget=forms.Select(attrs={"class": "field"}))
    first_name = forms.CharField(label="Boshlang'ich shaxs ismi", max_length=100,
                                  widget=forms.TextInput(attrs={"class": "field", "placeholder": "Ismi"}))
    last_name = forms.CharField(label="Familyasi", max_length=100, required=False,
                                 widget=forms.TextInput(attrs={"class": "field", "placeholder": "Familyasi (ixtiyoriy)"}))
    gender = forms.ChoiceField(choices=[("erkak", "Erkak"), ("ayol", "Ayol")])


class TreeImportForm(forms.Form):
    kind = forms.ChoiceField(label="Shajara turi", choices=TREE_KIND_CHOICES, initial="oilaviy",
                             widget=forms.Select(attrs={"class": "field"}))
    tree_name = forms.CharField(label="Shajara nomi", max_length=150,
                                 widget=forms.TextInput(attrs={"class": "field", "placeholder": "Shajaraga nom bering"}))
    visibility = forms.ChoiceField(label="Ko'rinishi", choices=VISIBILITY_CHOICES, initial="private",
                                    widget=forms.Select(attrs={"class": "field"}))
    backup_file = forms.FileField(label="JSON fayl", widget=forms.ClearableFileInput(attrs={"class": "stack-input"}))


class TreeSettingsForm(forms.ModelForm):
    class Meta:
        model = Tree
        fields = ["name", "kind", "description", "visibility", "subject", "era", "sources"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "field"}),
            "kind": forms.Select(attrs={"class": "field"}),
            "visibility": forms.Select(attrs={"class": "field"}),
            "description": forms.Textarea(attrs={"class": "field", "rows": 3}),
            "subject": forms.TextInput(attrs={"class": "field", "placeholder": "Masalan: O'zbekiston tarixi, 7-sinf"}),
            "era": forms.TextInput(attrs={"class": "field", "placeholder": "Masalan: XIV–XVI asrlar"}),
            "sources": forms.Textarea(attrs={
                "class": "field", "rows": 4,
                "placeholder": "Har bir manbani yangi qatordan yozing, masalan:\nB. Ahmedov. Amir Temur. 1995\nhttps://…",
            }),
        }


def normalise_year(raw, approx=False, label="Yil"):
    """'1956', "~1956", "taxminan 1956", "1956?" -> "1956" or "~1956".
    A guess is kept with a leading "~" so cards can show it as such."""
    value = (raw or "").strip()
    if not value:
        return ""
    found = re.search(r"\d{3,4}", value)
    leftover = re.sub(r"\d{3,4}|~|\?|taxminan|taxm\.?|yillar|yil|y\.|[\s.,-]", "", value, flags=re.I)
    if not found or leftover:
        raise forms.ValidationError(f"{label}ni raqam bilan yozing, masalan: 1956")
    year = int(found.group())
    if year > datetime.date.today().year:
        raise forms.ValidationError(f"{label} kelajakda bo'lishi mumkin emas.")
    approx = approx or "~" in value or "?" in value or "taxm" in value.lower()
    return f"~{year}" if approx else str(year)


class PersonForm(forms.ModelForm):
    """Years are typed as plain digits with a "taxminan" tick beside them;
    birth date is optional and, when given, decides the birth year."""

    def _year_parts(self, name):
        if self.is_bound:
            raw = self.data.get(name, "")
            approx = bool(self.data.get(f"{name}_approx")) or "~" in raw
        else:
            raw = getattr(self.instance, name, "") or ""
            approx = "~" in raw or "taxm" in raw.lower()
        found = re.search(r"\d{3,4}", raw)
        return (found.group() if found else ("" if not self.is_bound else raw.strip())), approx

    @property
    def birth_year_digits(self):
        return self._year_parts("birth_year")[0]

    @property
    def birth_year_approx(self):
        return self._year_parts("birth_year")[1]

    @property
    def death_year_digits(self):
        return self._year_parts("death_year")[0]

    @property
    def death_year_approx(self):
        return self._year_parts("death_year")[1]

    def clean_birth_year(self):
        return normalise_year(self.cleaned_data.get("birth_year"), bool(self.data.get("birth_year_approx")),
                              "Tug'ilgan yil")

    def clean_death_year(self):
        return normalise_year(self.cleaned_data.get("death_year"), bool(self.data.get("death_year_approx")),
                              "Vafot etgan yil")

    def clean_birth_date(self):
        date = self.cleaned_data.get("birth_date")
        if date and date > datetime.date.today():
            raise forms.ValidationError("Tug'ilgan sana kelajakda bo'lishi mumkin emas.")
        return date

    def clean(self):
        cleaned = super().clean()
        date = cleaned.get("birth_date")
        if date:
            cleaned["birth_year"] = str(date.year)
        born = re.search(r"\d{3,4}", cleaned.get("birth_year") or "")
        died = re.search(r"\d{3,4}", cleaned.get("death_year") or "")
        if born and died and int(died.group()) < int(born.group()):
            self.add_error("death_year", "Vafot yili tug'ilgan yildan oldin bo'lishi mumkin emas.")
        return cleaned

    class Meta:
        model = Person
        fields = ["first_name", "last_name", "patronymic", "gender", "birth_date", "birth_year", "death_year",
                  "birth_region", "birth_district", "birth_village",
                  "occupation", "location", "bio", "photo"]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "field", "placeholder": "Ismi"}),
            "last_name": forms.TextInput(attrs={"class": "field", "placeholder": "Familyasi"}),
            "birth_date": forms.DateInput(attrs={"class": "field", "type": "date"}),
            "birth_year": forms.TextInput(attrs={"class": "field", "placeholder": "Aniq sanasi noma'lum bo'lsa, taxminiy yil"}),
            "death_year": forms.TextInput(attrs={"class": "field", "placeholder": "Vafot etgan yili (ixtiyoriy)"}),
            "occupation": forms.TextInput(attrs={"class": "field", "placeholder": "Kasbi"}),
            "location": forms.TextInput(attrs={"class": "field", "placeholder": "Yashash joyi"}),
            "bio": forms.Textarea(attrs={"class": "field", "placeholder": "Qisqacha ma'lumot", "rows": 3}),
        }


class StoryForm(forms.Form):
    text = forms.CharField(
        label="Hikoya", widget=forms.Textarea(attrs={
            "class": "field", "placeholder": "Bu odam haqida bir voqea yoki xotira yozing...", "rows": 4,
        }),
    )


class CommentForm(forms.Form):
    text = forms.CharField(
        label="Izoh", max_length=1000,
        widget=forms.Textarea(attrs={"class": "field", "placeholder": "Fikringizni yozing...", "rows": 3}),
    )


class InviteForm(forms.Form):
    role = forms.ChoiceField(label="Qanday huquq beriladi", choices=MEMBER_ROLE_CHOICES, initial="muharrir")
    ttl = forms.ChoiceField(label="Havola amal qilish muddati", choices=INVITE_TTL_CHOICES, initial="7")


class MemberRoleForm(forms.Form):
    role = forms.ChoiceField(choices=MEMBER_ROLE_CHOICES)


class ConnectionRequestForm(forms.Form):
    tree = forms.ModelChoiceField(queryset=Tree.objects.none(), label="Qaysi shajarangiz orqali bog'lanasiz")
    message = forms.CharField(
        label="Xabar", max_length=300, required=False,
        widget=forms.TextInput(attrs={
            "class": "field",
            "placeholder": "Masalan: Men sizning jiyaningizman",
        }),
    )

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tree"].queryset = Tree.objects.filter(owner=owner) if owner else Tree.objects.none()


class AcceptRequestForm(forms.Form):
    anchor = forms.ModelChoiceField(queryset=Person.objects.none(), label="Mening shajaramdagi odam")
    relation = forms.ChoiceField(choices=RELATION_CHOICES, label="U bu odamning kimi bo'ladi?")

    def __init__(self, *args, tree_person_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Person.objects.filter(pk__in=tree_person_ids or []).order_by("first_name")
        self.fields["anchor"].queryset = qs
