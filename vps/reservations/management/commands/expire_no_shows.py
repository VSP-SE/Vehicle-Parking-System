"""FR-RES-05: run from the scheduler every minute."""

from django.core.management.base import BaseCommand

from vps.reservations.services import expire_no_shows


class Command(BaseCommand):
    help = "Expire reservations more than 15 minutes past their start and charge no-shows."

    def handle(self, *args, **options):
        count = expire_no_shows()
        self.stdout.write(f"Expired {count} no-show reservations.")
