from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_role_groups(sender, using="default", **kwargs):
    """Seed the three role groups after every migrate.

    A signal is used instead of a data migration so that the custom user model
    (issue #23) can still be created in this app's first migration.
    """
    from django.contrib.auth.models import Group

    from vps.accounts.roles import Role

    for role in Role:
        Group.objects.using(using).get_or_create(name=role.value)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "vps.accounts"

    def ready(self):
        post_migrate.connect(create_role_groups, sender=self)
