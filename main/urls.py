from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='mapa'),
    path('api/estaciones/', views.estaciones_geojson, name='estaciones_geojson'),
    path('api/estaciones/<int:pk>/', views.detalle_estacion, name='detalle_estacion'),
    path('api/estaciones/<int:pk>/cercanas/', views.estaciones_cercanas, name='estaciones_cercanas'),
    path('api/estaciones/<int:pk>/ubicacion/', views.corregir_ubicacion, name='corregir_ubicacion'),
    path('api/cobertura/', views.cobertura, name='cobertura'),
    path('api/municipios/', views.municipios_geojson, name='municipios_geojson'),
    path('api/limites/', views.resumen_limites, name='resumen_limites'),
    path('api/simulacion/', views.simular_estacion, name='simular_estacion'),
]
