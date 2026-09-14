from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

User = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    """Authenticate with either a username or an email address in the
    'username' field of the login form."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        login = username.strip()
        try:
            # Match username exactly OR a (unique, verified) email — case-insensitive.
            user = User.objects.get(Q(username__iexact=login) | Q(email__iexact=login))
        except User.DoesNotExist:
            # Run the default hasher once to blunt timing attacks.
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # Ambiguous (a username equals someone else's email); prefer username match.
            user = User.objects.filter(username__iexact=login).first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
