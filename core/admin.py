from django.contrib import admin
from django.utils import timezone
from .models import GradeBand, SchoolClass, SchoolProfile, Student, TemporaryGrant, AuditLog,  TemporaryGrant,  Term, TemporaryGrant


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