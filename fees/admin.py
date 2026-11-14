from django.contrib import admin

from .models import FeeItem


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