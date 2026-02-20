from django.contrib import admin

from .models import Commune, Patrimoine, Province, Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = ("nom_region", "code_region")
    search_fields = ("nom_region",)


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("nom_province", "type_province", "id_region")
    list_filter = ("type_province", "id_region")
    search_fields = ("nom_province",)


@admin.register(Commune)
class CommuneAdmin(admin.ModelAdmin):
    list_display = ("nom_commune", "type_commune", "id_province")
    list_filter = ("type_commune", "id_province__id_region")
    search_fields = ("nom_commune",)


@admin.register(Patrimoine)
class PatrimoineAdmin(admin.ModelAdmin):
    list_display = ("nom_fr", "type_patrimoine", "statut", "id_commune", "created_by", "created_at")
    list_filter = ("type_patrimoine", "statut", "id_commune__id_province__id_region")
    search_fields = ("nom_fr", "nom_ar")
    readonly_fields = ("centroid_geom", "created_at", "updated_at", "created_by")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
