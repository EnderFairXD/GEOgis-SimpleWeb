from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='mapa'),
    path('api/jugadores/', views.jugadores_geojson, name='jugadores_geojson'),
    path('api/jugadores/<int:pk>/cercanos/', views.jugadores_cercanos, name='jugadores_cercanos'),
    path('api/jugadores/<int:pk>/ubicacion/', views.actualizar_ubicacion_jugador,
         name='actualizar_ubicacion_jugador'),
]
