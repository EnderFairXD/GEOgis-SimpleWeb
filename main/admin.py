from django.contrib.gis import admin
from django.db.models import Count

from .models import Jugador, Puntuacion, Videojuego


class PuntuacionInline(admin.TabularInline):
    """Puntuaciones del jugador, editables dentro de su ficha."""
    model = Puntuacion
    extra = 1
    autocomplete_fields = ['videojuego']


@admin.register(Jugador)
class JugadorAdmin(admin.GISModelAdmin):
    list_display = ('alias', 'nombre', 'plataforma', 'total_juegos')
    inlines = [PuntuacionInline]

    def get_queryset(self, request):
        # Cuenta los juegos en la misma consulta del listado (sin una consulta por fila).
        return super().get_queryset(request).annotate(num_juegos=Count('juegos'))

    @admin.display(description='Juegos jugados', ordering='num_juegos')
    def total_juegos(self, obj):
        return obj.num_juegos


@admin.register(Videojuego)
class VideojuegoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo')
    search_fields = ('nombre',)
