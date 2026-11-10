from django.contrib import admin
from django.utils import timezone
from .models import (
    AuditLog, GradeBand, SchoolClass, SchoolProfile, Student, Subject, ClassSubject,
    Assessment, Term, TemporaryGrant, Score, ResultLock, AttendanceRecord
)

class SuperuserOnlyAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'motto')

    def has_add_permission(self, request):
        return not SchoolProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TemporaryGrant)
class TemporaryGrantAdmin(admin.ModelAdmin):
    list_display = ('user', 'capability', 'reason', 'starts_at', 'ends_at', 'revoked_at')
    list_filter = ('capability', 'revoked_at')
    actions = ['revoke_selected']

    def save_model(self, request, obj, form, change):
        if not change:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description='Revoke selected grants now')
    def revoke_selected(self, request, queryset):
        # Save each grant one at a time, so the audit log records each revoke
        now = timezone.now()
        for grant in queryset.filter(revoked_at__isnull=True):
            grant.revoked_at = now
            grant.save()


@admin.register(SchoolClass)
class SchoolClassAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'stream', 'class_teacher', 'is_active')
    list_filter = ('level', 'is_active')
    search_fields = ('name',)


@admin.register(Student)
class StudentAdmin(SuperuserOnlyAdmin):
    list_display = ('student_id', 'last_name', 'first_name', 'school_class', 'is_archived')
    list_filter = ('school_class', 'is_archived')
    search_fields = ('student_id', 'first_name', 'last_name')
    readonly_fields = ('student_id', 'created_at', 'archived_at')


@admin.register(AuditLog)
class AuditLogAdmin(SuperuserOnlyAdmin):
    list_display = ('timestamp', 'username', 'action', 'model_name', 'object_repr')
    list_filter = ('action', 'model_name')
    search_fields = ('username', 'object_repr')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

@admin.register(GradeBand)
class GradeBandAdmin(admin.ModelAdmin):
    list_display = ('grade', 'remark', 'min_score')

@admin.register(Term)
class TermAdmin(admin.ModelAdmin):
    list_display = ('name', 'session', 'term_number', 'start_date', 'end_date', 'is_current')
    list_filter = ('session', 'is_current')


from django.core.exceptions import ValidationError as DjangoValidationError
from .assessments import check_weights


class ClassSubjectInline(admin.TabularInline):
    model = ClassSubject
    extra = 1


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')
    inlines = [ClassSubjectInline]


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ('subject', 'term', 'name', 'max_mark', 'weight')
    list_filter = ('term', 'subject')

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        try:
            check_weights(obj.subject, obj.term)
        except DjangoValidationError as error:
            # Show the problem to the user without losing the saved row
            self.message_user(request, ' '.join(error.messages), level='WARNING')


@admin.register(ClassSubject)
class ClassSubjectAdmin(admin.ModelAdmin):
    list_display = ('school_class', 'subject', 'teacher')
    list_filter = ('school_class', 'subject')


@admin.register(Score)
class ScoreAdmin(SuperuserOnlyAdmin):
    list_display = ('student', 'assessment', 'score', 'entered_by', 'updated_at')
    list_filter = ('assessment__term', 'assessment__subject')
    search_fields = ('student__student_id', 'student__last_name')


@admin.register(ResultLock)
class ResultLockAdmin(admin.ModelAdmin):
    # Locks are set through the Scores pages so every change has a reason
    list_display = ('class_subject', 'term', 'is_locked', 'locked_by', 'locked_at', 'unlocked_by', 'unlocked_at')
    list_filter = ('is_locked', 'term')
    readonly_fields = (
        'class_subject', 'term', 'is_locked', 'locked_by', 'locked_at',
        'unlocked_by', 'unlocked_at', 'unlock_reason',
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(SuperuserOnlyAdmin):
    list_display = ('date', 'student', 'school_class', 'status', 'marked_by')
    list_filter = ('date', 'school_class', 'status')
    search_fields = ('student__student_id', 'student__last_name')