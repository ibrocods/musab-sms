import json
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.utils import timezone

from .attendance import non_school_reason, save_register
from .models import Assessment, ClassSubject, SchoolClass, Student, Subject, Term
from .scoring import save_score

DEMO_PREFIX = 'demo_'
DEMO_PASSWORD = 'DemoPass123!'
DEMO_SESSION = '2099/2100'
DEMO_TERM_NUMBER = 9
DEMO_DAYS_BACK = 30

# (username, role, class the user is class teacher of)
DEMO_USERS = [
    ('demo_head', 'Head teacher', None),
    ('demo_records', 'Records officer', None),
    ('demo_class1', 'Class teacher', 'DEMO JSS1A'),
    ('demo_class2', 'Class teacher', 'DEMO JSS2B'),
    ('demo_maths', 'Subject teacher', None),
]

# Remembers which term was current before demo data took over
STATE_FILE = settings.BASE_DIR / 'demo_state.json'


def _guard():
    if settings.SETTINGS_MODULE != 'config.settings.development':
        raise RuntimeError('Demo data only works with development settings, never on the school server.')


def _restore_previous_term():
    if not STATE_FILE.exists():
        return
    pk = json.loads(STATE_FILE.read_text()).get('previous_current_term')
    STATE_FILE.unlink()
    if pk:
        term = Term.objects.filter(pk=pk).first()
        if term:
            term.is_current = True
            term.save()


def wipe_demo():
    """Delete only records flagged as demo. Real records are never matched."""
    _guard()
    Student.objects.filter(is_demo=True).delete()
    SchoolClass.objects.filter(is_demo=True).delete()
    Subject.objects.filter(is_demo=True).delete()
    Term.objects.filter(is_demo=True).delete()
    User.objects.filter(username__startswith=DEMO_PREFIX, is_superuser=False).delete()
    _restore_previous_term()


def seed_demo(students_per_class=20):
    """Wipe any old demo data, then create a fresh set with Faker."""
    _guard()
    try:
        from faker import Faker
    except ImportError:
        raise RuntimeError('Faker is not installed. Run: pip install faker')

    fake = Faker()
    wipe_demo()
    today = timezone.localdate()

    previous = Term.objects.filter(is_current=True).first()
    STATE_FILE.write_text(json.dumps({'previous_current_term': previous.pk if previous else None}))

    term = Term.objects.create(
        session=DEMO_SESSION, term_number=DEMO_TERM_NUMBER, name='DEMO Term',
        start_date=today - timedelta(days=DEMO_DAYS_BACK), end_date=today + timedelta(days=60),
        is_current=True, is_demo=True,
    )

    users = {}
    for username, role, _ in DEMO_USERS:
        user = User.objects.create_user(username, password=DEMO_PASSWORD)
        user.groups.add(Group.objects.get_or_create(name=role)[0])
        users[username] = user

    maths = Subject.objects.create(name='DEMO Mathematics', code='DMTH', is_demo=True)
    english = Subject.objects.create(name='DEMO English', code='DENG', is_demo=True)

    jss1 = SchoolClass.objects.create(
        name='DEMO JSS1A', level='JSS1', class_teacher=users['demo_class1'], is_demo=True,
    )
    jss2 = SchoolClass.objects.create(
        name='DEMO JSS2B', level='JSS2', class_teacher=users['demo_class2'], is_demo=True,
    )

    ClassSubject.objects.create(school_class=jss1, subject=maths, teacher=users['demo_maths'])
    ClassSubject.objects.create(school_class=jss1, subject=english)
    ClassSubject.objects.create(school_class=jss2, subject=maths, teacher=users['demo_maths'])

    for subject in (maths, english):
        Assessment.objects.create(subject=subject, term=term, name='Test', weight=30, max_mark=100)
        Assessment.objects.create(subject=subject, term=term, name='Exam', weight=70, max_mark=100)

    students = {jss1: [], jss2: []}
    for school_class in (jss1, jss2):
        for _ in range(students_per_class):
            student = Student.objects.create(
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                gender=random.choice(['M', 'F']),
                date_of_birth=fake.date_of_birth(minimum_age=10, maximum_age=17),
                admission_year=today.year,
                school_class=school_class,
                parent_name=fake.name(),
                parent_phone=fake.phone_number()[:30],
                parent_email=fake.email(),
                address=fake.address(),
                is_demo=True,
            )
            students[school_class].append(student)

    # Maths scores for both classes
    for school_class in (jss1, jss2):
        for assessment in Assessment.objects.filter(subject=maths, term=term):
            for student in students[school_class]:
                save_score(student, assessment, Decimal(random.randint(20, 100)), users['demo_maths'])

    # Registers for each school day in the demo term so far
    for offset in range(DEMO_DAYS_BACK, -1, -1):
        day = today - timedelta(days=offset)
        if non_school_reason(day):
            continue
        for school_class, teacher in ((jss1, 'demo_class1'), (jss2, 'demo_class2')):
            entries, notes = {}, {}
            for student in students[school_class]:
                code = random.choices(['P', 'A', 'L', 'E'], weights=[85, 7, 5, 3])[0]
                entries[student] = code
                notes[student] = 'Demo excuse' if code == 'E' else ''
            save_register(school_class, term, day, entries, users[teacher], notes=notes)

    return term