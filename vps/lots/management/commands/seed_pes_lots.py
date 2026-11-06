from django.core.management.base import BaseCommand

from vps.lots.models import Slot
from vps.lots.pes import seed_pes_lots


class Command(BaseCommand):
    help = "Create the four PES lots and slots."

    def handle(self, *args, **options):
        created = seed_pes_lots()
        if not created:
            self.stdout.write("PES lots already present.")
            return
        slot_count = Slot.objects.filter(lot__in=created).count()
        self.stdout.write(f"Seeded {len(created)} PES lots ({slot_count} slots).")
