from django.core.management.base import BaseCommand, CommandError

from core.demo import DEMO_PASSWORD, DEMO_USERS, seed_demo, wipe_demo


class Command(BaseCommand):
    help = 'Create or remove demo data for browser testing. Real records are never touched.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['seed', 'wipe'])
        parser.add_argument('--students', type=int, default=20, help='Students per class (seed only)')

    def handle(self, *args, **options):
        try:
            if options['action'] == 'wipe':
                wipe_demo()
                self.stdout.write(self.style.SUCCESS('Demo data removed. Your real records were not touched.'))
                return
            seed_demo(options['students'])
        except RuntimeError as error:
            raise CommandError(str(error))

        self.stdout.write(self.style.SUCCESS('Demo data created.'))
        for username, role, _ in DEMO_USERS:
            self.stdout.write(f'  {username:<14} {role:<16} password: {DEMO_PASSWORD}')