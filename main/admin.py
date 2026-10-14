from django.contrib.gis import admin
from .models import Jugador, Videojuego, Puntuacion


#CONFIGURACIÓN DE LA TABLA INTERMEDIA (PUNTUACIÓN)
# Esto crea una "mini-tabla" dentro de la ficha del jugador
class PuntuacionInline(admin.TabularInline):
    model = Puntuacion
    extra = 1
    autocomplete_fields = ['videojuego']


#CONFIGURACIÓN DEL JUGADOR (Con el mapa y la tabla de juegos)
class JugadorAdmin(admin.GISModelAdmin):
    list_display = ('alias', 'nombre', 'plataforma', 'total_juegos')
    inlines = [PuntuacionInline]
    # Metodo para ver cuántos juegos tiene cada uno
    def total_juegos(self, obj):
        return obj.juegos.count()

    total_juegos.short_description = 'Juegos Jugados'


#CONFIGURACIÓN DEL VIDEOJUEGO (Para crear el catálogo)
class VideojuegoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'tipo')
    search_fields = ('nombre',)


#REGISTRO DE TODO
admin.site.register(Jugador, JugadorAdmin)
admin.site.register(Videojuego, VideojuegoAdmin)
