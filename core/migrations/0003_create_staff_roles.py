from django.db import migrations

ROLES = [
    'Head teacher',
    'Bursar',
    'Class teacher',
    'Subject teacher',
    'Exams officer',
    'Records officer',
    'Read-only staff',
]


def create_roles(apps, schema_editor):
    from django.contrib.auth.models import Group
    for name in ROLES:
        Group.objects.get_or_create(name=name)


def remove_roles(apps, schema_editor):
    from django.contrib.auth.models import Group
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_alter_schoolprofile_accent_colour_and_more'),
    ]

    operations = [
        migrations.RunPython(create_roles, remove_roles),
    ]