from django.contrib import admin

from .models import RoutingStep


@admin.register(RoutingStep)
class RoutingStepAdmin(admin.ModelAdmin):
    list_display = ("part", "op_number", "name", "hold_minutes")
    list_filter = ("part",)
    ordering = ("part", "op_number")