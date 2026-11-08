from django.contrib import admin
from django.utils import timezone

from .models import SchoolProfile, TemporaryGrant


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
        queryset.filter(revoked_at__isnull=True).update(revoked_at=timezone.now())