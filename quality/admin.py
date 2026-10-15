from django.contrib import admin

from .models import PDITemplate, TemplateField


class TemplateFieldInline(admin.TabularInline):
    model = TemplateField
    extra = 0
    fields = ("sequence", "name", "field_type", "nominal", "upper_tol",
              "lower_tol", "limit_value", "unit", "is_ctq")


@admin.register(PDITemplate)
class PDITemplateAdmin(admin.ModelAdmin):
    list_display = ("part", "revision", "status", "created_by", "approved_by")
    list_filter = ("status",)
    search_fields = ("part__part_number",)
    readonly_fields = ("created_by", "created_at", "approved_by", "approved_at")
    inlines = [TemplateFieldInline]