from django.core.management.base import BaseCommand
from api.verify_queue import process_queue


class Command(BaseCommand):
    help = "Drain api_error_verify_phone_dialer and push to SabkiApp."

    def handle(self, *args, **options):
        process_queue()
        self.stdout.write(self.style.SUCCESS("verify-queue processed."))
