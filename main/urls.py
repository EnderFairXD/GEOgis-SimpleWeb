from django.urls import path

from .views import actualizar_ubicacion_jugador, index

urlpatterns = [
    path('', index),
    path('api/jugadores/<int:pk>/ubicacion/', actualizar_ubicacion_jugador,
         name='actualizar_ubicacion_jugador'),
]
