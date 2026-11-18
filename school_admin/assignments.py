from django.core.exceptions import ValidationError

TEACHER_ROLES = {'Class teacher', 'Subject teacher'}


def find_conflicts(current_pk, class_led, teaching):
    """Assignments already held by someone other than this person."""
    conflicts = []
    if class_led and class_led.class_teacher_id not in (None, current_pk):
        conflicts.append(
            f'{class_led.name} already has a class teacher: {class_led.class_teacher.get_username()}.'
        )
    for link in teaching:
        if link.teacher_id not in (None, current_pk):
            conflicts.append(
                f'{link.subject.name} in {link.school_class.name} is taught by {link.teacher.get_username()}.'
            )
    return conflicts


def check_conflicts(current_pk, class_led, teaching, replace):
    conflicts = find_conflicts(current_pk, class_led, teaching)
    if conflicts and not replace:
        raise ValidationError(
            conflicts + ['Tick "Replace current teachers" to move these to this person.']
        )


def apply_assignments(user, class_led, teaching):
    if class_led:
        class_led.class_teacher = user
        class_led.save()
    for link in teaching:
        link.teacher = user
        link.save()