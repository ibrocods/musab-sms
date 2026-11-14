from django.contrib import admin

from .models import FeeItem, Payment


@admin.register(FeeItem)
class FeeItemAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'term', 'school_class', 'is_active')
    list_filter = ('term', 'school_class', 'is_active')
    search_fields = ('name',)

    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        # Fee items will be linked to payments later, so they're deactivated rather than deleted
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    # Read-only. Payments are recorded and reversed through the service functions.
    list_display = ('receipt_number', 'paid_on', 'student', 'term', 'kind', 'amount', 'method', 'recorded_by')
    list_filter = ('kind', 'method', 'term', 'paid_on')
    search_fields = ('receipt_number', 'student__student_id', 'student__last_name', 'reference')

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