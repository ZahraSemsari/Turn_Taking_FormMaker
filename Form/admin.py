from django.contrib import admin
from .models import *

class FieldModelInline(admin.StackedInline):
    model = FieldModel
    extra = 0


@admin.register(FormModel)
class FormModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "is_public",
        "created_at",
    )
    list_filter = (
        "is_public",
        "created_at",
    )
    search_fields = (
        "title",
        "slug",
    )
    prepopulated_fields = {
        "slug": ("title",)
    }

    readonly_fields = ("share_link",)

    inlines = [FieldModelInline]


@admin.register(FieldModel)
class FieldModelAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "field_type",
        "form",
        "is_required",
    )
    list_filter = (
        "field_type",
        "is_required",
    )
    search_fields = (
        "name",
        "label",
    )
    ordering = ("form", "order_index")


class FieldResponseInline(admin.TabularInline):
    model = FieldResponse
    extra = 0
    readonly_fields = (
        "response_fields",
        "value",
    )

@admin.register(AllResponse)
class AllResponseAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "form",
        "submitted_at",
    )
    list_filter = (
        "form",
        "submitted_at",
    )
    date_hierarchy = "submitted_at"
    inlines = [
        FieldResponseInline
    ]
