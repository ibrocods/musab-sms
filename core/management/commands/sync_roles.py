from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

from core.permissions import ROLE_CAPABILITIES


class Command(BaseCommand):
    help = "Creates the staff roles and attaches their capabilities. Safe to run again."

    def handle(self, *args, **options):
        for role, capabilities in ROLE_CAPABILITIES.items():
            group, _ = Group.objects.get_or_create(name=role)
            perms = Permission.objects.filter(
                content_type__app_label='core', codename__in=capabilities,
            )
            group.permissions.set(perms)

            found = set(perms.values_list('codename', flat=True))
            missing = set(capabilities) - found
            if missing:
                self.stderr.write(f'{role}: missing {sorted(missing)}. Run migrate first.')
            self.stdout.write(f'{role}: {len(found)} capabilities')