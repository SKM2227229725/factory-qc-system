from django.contrib import admin

from .models import RawMaterialIntake, SupplierNonConformance


@admin.register(RawMaterialIntake)
class RawMaterialIntakeAdmin(admin.ModelAdmin):
    list_display = (
        "heat_number", "supplier", "material_grade",
        "quantity", "status", "received_at",
    )
    list_filter = ("status", "material_grade", "supplier")
    search_fields = ("heat_number", "supplier", "po_number")


@admin.register(SupplierNonConformance)
class SNCRAdmin(admin.ModelAdmin):
    list_display = ("id", "intake", "raised_by", "created_at")
    search_fields = ("intake__heat_number",)