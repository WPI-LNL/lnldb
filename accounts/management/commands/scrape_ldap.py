from django.core.management.base import BaseCommand
from django.db.transaction import atomic
from ...models import User
from ... import ldap


class Command(BaseCommand):
    help = "Searches ldap for info on users without it"

    def handle(self, *args, **options):
        users_needing_update = User.objects.filter(first_name="", last_name="")
        num_updated = 0
        with atomic():
            for u in users_needing_update:
                try:
                    ldap.fill_in_user(u)
                    u.save()
                    num_updated += 1
                except Exception:
                    self.stderr.write("Error in '%s'" % str(u))
                    raise
        self.stdout.write("%d users updated." % num_updated)
