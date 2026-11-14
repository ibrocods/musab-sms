from django.contrib import admin

from .models import ReportComment


@admin.register(ReportComment)
class ReportCommentAdmin(admin.ModelAdmin):
    # Comments are written through the report pages so the author check applies
    list_display = ('student', 'term', 'kind', 'written_by', 'updated_at')
    list_filter = ('term', 'kind')
    search_fields = ('student__student_id', 'student__last_name')
    readonly_fields = ('student', 'term', 'kind', 'text', 'written_by', 'updated_at')

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False