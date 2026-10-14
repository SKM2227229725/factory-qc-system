from django.contrib import admin

from .models import Factory, Gauge, Part, Workstation

admin.site.register(Factory)
admin.site.register(Part)


@admin.register(Workstation)
class WorkstationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "factory", "pm_due_date")
    list_filter = ("factory",)
    search_fields = ("code", "name")


@admin.register(Gauge)
class GaugeAdmin(admin.ModelAdmin):
    list_display = ("serial", "gauge_type", "calibration_expiry")
    list_filter = ("gauge_type",)
    search_fields = ("serial",)