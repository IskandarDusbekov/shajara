from django.apps import AppConfig


class ShajaraConfig(AppConfig):
    name = 'shajara'

    def ready(self):
        from . import activity  # noqa: F401  (connects the login/logout signal receivers)
