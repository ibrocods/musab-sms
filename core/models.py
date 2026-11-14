from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone
from .utils import format_student_id
from .capabilities import CAPABILITIES
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator

class SchoolProfile(models.Model):
    name = models.CharField(max_length=200, default='My School')
    motto = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    primary_colour = models.CharField(
        max_length=7, default='#1F4E78',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a hex colour such as #1F4E78.')],
        help_text='Hex colour, for example #1F4E78',
    )
    accent_colour = models.CharField(
        max_length=7, default='#F2A900',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use a hex colour such as #F2A900.')],
        help_text='Hex colour, for example #F2A900',
    )
    student_id_pattern = models.CharField(
        max_length=100, default='{year}/{seq:04d}',
        help_text='Example: {year}/{seq:04d} gives 2026/0001',
    )
    receipt_pattern = models.CharField(
        max_length=100, default='RCPT-{year}-{seq:04d}',
        help_text='Receipt format. {seq} is required. Example: RCPT-{year}-{seq:04d}',
    )
    school_days = models.CharField(
        max_length=13, default='0,1,2,3,4',
        help_text='Days the school is open: 0 = Monday ... 6 = Sunday. Default is Monday to Friday.',
    )
    class Meta:
        verbose_name = 'School profile'
        # Django stores each capability as a permission. They're attached to this
        # model because it always exists, so the permissions are always created.
        permissions = list(CAPABILITIES.items())

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Only one profile is allowed per installation
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls):
        profile, _ = cls.objects.get_or_create(pk=1)
        return profile
    def clean(self):
        if '{seq' not in self.receipt_pattern:
            raise ValidationError({'receipt_pattern': 'The receipt format must include {seq}.'})
        try:
            self.receipt_pattern.format(year=2026, seq=1)
        except (KeyError, ValueError, IndexError):
            raise ValidationError({
                'receipt_pattern': 'Use only the placeholders {year} and {seq}, for example RCPT-{year}-{seq:04d}.',
            })
    def school_day_numbers(self):
        return {int(d) for d in self.school_days.split(',') if d.strip().isdigit()}


class TemporaryGrant(models.Model):
    """One capability given to one person for a fixed period, outside their role."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='temporary_grants',
    )
    capability = models.CharField(max_length=50, choices=list(CAPABILITIES.items()))
    reason = models.CharField(max_length=200, help_text='Why this is needed, for example "Bursar on leave"')
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        related_name='grants_given', editable=False,
    )
    starts_at = models.DateTimeField(default=timezone.now)
    ends_at = models.DateTimeField(help_text='The grant stops working at this time')
    revoked_at = models.DateTimeField(null=True, blank=True, help_text='Set when the grant is removed early')

    class Meta:
        ordering = ['-starts_at']

    def __str__(self):
        return f'{self.user} - {self.capability}'

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError('The end date must be after the start date.')

def current_year():
    return timezone.now().year


class SchoolClass(models.Model):
    name = models.CharField(max_length=50, unique=True, help_text='For example JSS1A or SS2 Science')
    level = models.CharField(max_length=50, blank=True, help_text='For example JSS1 or SS2')
    stream = models.CharField(max_length=50, blank=True, help_text='Optional, for example Science or Arts')
    class_teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='classes_taught',
        limit_choices_to={'groups__name': 'Class teacher'},
    )
    is_active = models.BooleanField(default=True, help_text='Untick when a class is no longer running')
    is_demo = models.BooleanField(default=False, editable=False)
    class Meta:
        ordering = ['name']
        verbose_name = 'class'
        verbose_name_plural = 'classes'

    def __str__(self):
        return self.name

    
class Student(models.Model):
    GENDER_CHOICES = [('M', 'Male'), ('F', 'Female')]

    student_id = models.CharField(max_length=50, unique=True, editable=False, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, blank=True)
    admission_year = models.PositiveIntegerField(
        default=current_year, help_text='Used in the student ID pattern',
    )
    school_class = models.ForeignKey(
        SchoolClass, on_delete=models.SET_NULL, null=True, blank=True, related_name='students',
    )
    parent_name = models.CharField(max_length=200, blank=True)
    parent_phone = models.CharField(max_length=30, blank=True)
    parent_email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    is_archived = models.BooleanField(default=False)
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_demo = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f'{self.last_name} {self.first_name} ({self.student_id})'

    def save(self, *args, **kwargs):
        if not self.student_id:
            self.student_id = self._next_student_id()
        super().save(*args, **kwargs)

    def _next_student_id(self):
        pattern = SchoolProfile.get().student_id_pattern
        if '{seq' not in pattern:
            raise ValueError('The student ID pattern must include {seq}, for example {year}/{seq:04d}.')
        # Counting every student, including archived ones, means IDs are never reused
        seq = Student.objects.filter(admission_year=self.admission_year).count() + 1
        while True:
            candidate = format_student_id(pattern, self.admission_year, seq)
            if not Student.objects.filter(student_id=candidate).exists():
                return candidate
            seq += 1

class AuditLog(models.Model):
    ACTIONS = [
        ('create', 'Created'),
        ('update', 'Changed'),
        ('delete', 'Deleted'),
        ('login', 'Signed in'),
        ('logout', 'Signed out'),
    ]

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    username = models.CharField(max_length=150, blank=True, help_text='Kept even if the account is removed')
    action = models.CharField(max_length=10, choices=ACTIONS)
    model_name = models.CharField(max_length=100)
    object_id = models.CharField(max_length=50, blank=True)
    object_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True, help_text='Field name: [old value, new value]')

    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'audit entry'
        verbose_name_plural = 'audit log'

    def __str__(self):
        return f'{self.timestamp:%Y-%m-%d %H:%M} {self.username or "system"} {self.action} {self.object_repr}'

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError('Audit entries cannot be changed.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError('Audit entries cannot be deleted.')

class GradeBand(models.Model):
    grade = models.CharField(max_length=5, help_text='For example A, B2 or F9')
    remark = models.CharField(max_length=50, help_text='For example Excellent')
    min_score = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='The lowest score that earns this grade, from 0 to 100',
    )

    class Meta:
        ordering = ['-min_score']
        constraints = [
            models.UniqueConstraint(fields=['grade'], name='unique_band_grade'),
            models.UniqueConstraint(fields=['min_score'], name='unique_band_min_score'),
        ]

    def __str__(self):
        return f'{self.grade} ({self.min_score}+) {self.remark}'
    

class Term(models.Model):
    session = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d{4}/\d{4}$', 'Use the form 2026/2027.')],
        help_text='For example 2026/2027',
    )
    term_number = models.PositiveSmallIntegerField(help_text='1, 2 or 3, depending on the school')
    name = models.CharField(max_length=50, help_text='For example First Term')
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False, help_text='Only one term can be current')
    is_demo = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ['-session', 'term_number']
        constraints = [
            models.UniqueConstraint(fields=['session', 'term_number'], name='unique_term_per_session'),
        ]

    def __str__(self):
        return f'{self.name} {self.session}'

    def clean(self):
        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError('The end date must be after the start date.')

    def save(self, *args, **kwargs):
        if self.is_current:
            # Clear the current flag on any other term, one save at a time so the audit log sees it
            for other in Term.objects.filter(is_current=True).exclude(pk=self.pk):
                other.is_current = False
                other.save()
        super().save(*args, **kwargs)

class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text='For example Mathematics')
    code = models.CharField(max_length=20, blank=True, help_text='Short code, for example MTH')
    is_active = models.BooleanField(default=True)
    is_demo = models.BooleanField(default=False, editable=False)
    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class ClassSubject(models.Model):
    """Which subject a class studies, and which teacher teaches it."""

    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='class_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='class_subjects')
    teacher = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teaching_assignments',
        limit_choices_to={'groups__name__in': ['Subject teacher', 'Class teacher']},
    )

    class Meta:
        ordering = ['school_class__name', 'subject__name']
        constraints = [
            models.UniqueConstraint(fields=['school_class', 'subject'], name='unique_class_subject'),
        ]

    def __str__(self):
        return f'{self.subject} - {self.school_class}'


class Assessment(models.Model):
    """One part of a subject's final score, such as First Test or Exam."""

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='assessments')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='assessments')
    name = models.CharField(max_length=50, help_text='For example First Test or Exam')
    max_mark = models.DecimalField(max_digits=6, decimal_places=2, default=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Share of the final score, out of 100. All weights for a subject and term must total 100.',
    )

    class Meta:
        ordering = ['term', 'subject', 'name']
        constraints = [
            models.UniqueConstraint(fields=['subject', 'term', 'name'], name='unique_assessment_name'),
        ]

    def __str__(self):
        return f'{self.subject} {self.term} - {self.name}'


    
class Score(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='scores')
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='scores')
    score = models.DecimalField(
        max_digits=6, decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Mark obtained, out of the assessment maximum',
    )
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['assessment', 'student']
        constraints = [
            models.UniqueConstraint(fields=['student', 'assessment'], name='unique_score_per_assessment'),
        ]

    def __str__(self):
        return f'{self.student} - {self.assessment}: {self.score}'

    def clean(self):
        if self.assessment_id and self.score is not None and self.score > self.assessment.max_mark:
            raise ValidationError(f'The score cannot be more than {self.assessment.max_mark}.')


class ResultLock(models.Model):
    """Whether one class's results for one subject and term are locked."""

    class_subject = models.ForeignKey(ClassSubject, on_delete=models.CASCADE, related_name='result_locks')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='result_locks')
    is_locked = models.BooleanField(default=False)
    locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    unlocked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    unlocked_at = models.DateTimeField(null=True, blank=True)
    unlock_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['class_subject', 'term'], name='unique_result_lock'),
        ]

    def __str__(self):
        state = 'locked' if self.is_locked else 'open'
        return f'{self.class_subject} {self.term} ({state})'
    

class AttendanceRecord(models.Model):
    STATUS_CHOICES = [
        ('P', 'Present'),
        ('A', 'Absent'),
        ('L', 'Late'),
        ('E', 'Excused'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance')
    school_class = models.ForeignKey(SchoolClass, on_delete=models.CASCADE, related_name='attendance')
    term = models.ForeignKey(Term, on_delete=models.CASCADE, related_name='attendance')
    date = models.DateField()
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)
    note = models.CharField(max_length=200, blank=True)
    marked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+',
    )
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'student']
        verbose_name = 'attendance record'
        constraints = [
            models.UniqueConstraint(fields=['student', 'date'], name='unique_attendance_per_day'),
        ]

    def __str__(self):
        return f'{self.student} {self.date:%Y-%m-%d}: {self.get_status_display()}'

class NonSchoolDay(models.Model):
    date = models.DateField(unique=True)
    description = models.CharField(max_length=100, help_text='For example Independence Day')

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f'{self.date:%Y-%m-%d} {self.description}'