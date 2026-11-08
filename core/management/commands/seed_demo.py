from django.core.management.base import BaseCommand
from faker import Faker


class Command(BaseCommand):
    help = "Creates demo data. Models are added later."

    def handle(self, *args, **options):
        fake = Faker()
        for _ in range(3):
            self.stdout.write(fake.name())