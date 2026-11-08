from django.contrib import admin

from .models import SchoolProfile


@admin.register(SchoolProfile)
class SchoolProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'motto')

    def has_add_permission(self, request):
        # Only one profile exists, so hide the "Add" button once it's created
        return not SchoolProfile.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False