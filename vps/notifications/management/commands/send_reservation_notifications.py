from django.core.management.base import BaseCommand

from vps.notifications.services import process_pending_notifications


class Command(BaseCommand):
    help = "Send pending reservation notification emails."

    def handle(self, *args, **options):
        result = process_pending_notifications()

        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {result['sent']} notification(s); failed {result['failed']} attempt(s)."
            )
        )
