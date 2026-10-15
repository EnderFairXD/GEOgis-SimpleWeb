from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='mapa'),
    path('api/estaciones/', views.estaciones_geojson, name='estaciones_geojson'),
    path('api/estaciones/<int:pk>/', views.detalle_estacion, name='detalle_estacion'),
    path('api/estaciones/<int:pk>/cercanas/', views.estaciones_cercanas, name='estaciones_cercanas'),
    path('api/estaciones/<int:pk>/ubicacion/', views.corregir_ubicacion, name='corregir_ubicacion'),
]
