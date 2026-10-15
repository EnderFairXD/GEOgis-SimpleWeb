from django.contrib.gis import admin
from django.db.models import Count

from .models import Contaminante, Estacion, MedicionMensual


class MedicionMensualInline(admin.TabularInline):
    """Medias mensuales de la estación (solo lectura: vienen de los ficheros del MITECO)."""
    model = MedicionMensual
    fields = ('contaminante', 'anno', 'mes', 'media', 'num_datos')
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Estacion)
class EstacionAdmin(admin.GISModelAdmin):
    list_display = ('nombre', 'municipio', 'provincia', 'tipo', 'area', 'num_contaminantes')
    list_filter = ('comunidad', 'tipo', 'area', 'ubicacion_corregida')
    search_fields = ('nombre', 'municipio', 'codigo', 'codigo_europeo')
    filter_horizontal = ('contaminantes',)
    inlines = [MedicionMensualInline]

    def save_model(self, request, obj, form, change):
        # Mover la estación en el mapa del admin cuenta como corrección a mano.
        if 'ubicacion' in form.changed_data:
            obj.ubicacion_corregida = True
        super().save_model(request, obj, form, change)

    def get_queryset(self, request):
        # Cuenta los contaminantes en la misma consulta del listado (sin una consulta por fila).
        return super().get_queryset(request).annotate(total_contaminantes=Count('contaminantes'))

    @admin.display(description='Contaminantes', ordering='total_contaminantes')
    def num_contaminantes(self, obj):
        return obj.total_contaminantes


@admin.register(Contaminante)
class ContaminanteAdmin(admin.ModelAdmin):
    list_display = ('abreviatura', 'nombre', 'unidad', 'codigo')
    search_fields = ('abreviatura', 'nombre')
