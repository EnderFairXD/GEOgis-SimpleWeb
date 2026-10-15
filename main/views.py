import json
from collections import defaultdict

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .geo import coordenadas_utm
from .models import Estacion

PERMISO_EDITAR = 'main.change_estacion'
RADIO_POR_DEFECTO_KM = 25
RADIO_MAXIMO_KM = 1000
# Rectángulo que contiene España, Canarias incluida (longitud, latitud)
LIMITES_ESPANA = {'lng': (-18.5, 4.6), 'lat': (27.4, 44.0)}


def error(mensaje, estado):
    return JsonResponse({'status': 'error', 'msg': mensaje}, status=estado)


def estaciones_activas():
    return Estacion.objects.filter(fecha_baja__isnull=True)


@ensure_csrf_cookie
def index(request):
    """Página del mapa. Las estaciones se piden después a la API."""
    return render(request, 'main/Main.html', {
        'puede_editar': request.user.has_perm(PERMISO_EDITAR),
    })


@require_GET
def estaciones_geojson(request):
    """Estaciones activas como FeatureCollection GeoJSON, con lo justo para pintar el mapa."""
    features = [
        {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': [round(e.ubicacion.x, 6), round(e.ubicacion.y, 6)]},
            'properties': {
                'id': e.pk,
                'nombre': e.nombre,
                'municipio': e.municipio,
                'provincia': e.provincia,
                'tipo': e.tipo,
            },
        }
        for e in estaciones_activas().only('nombre', 'municipio', 'provincia', 'tipo', 'ubicacion')
    ]
    return JsonResponse({'type': 'FeatureCollection', 'features': features})


@require_GET
def detalle_estacion(request, pk):
    """Ficha de una estación: datos, coordenadas (WGS84 y UTM) y medias mensuales por contaminante."""
    try:
        estacion = Estacion.objects.prefetch_related('contaminantes').get(pk=pk)
    except Estacion.DoesNotExist:
        return error('No existe la estación', 404)

    medias = defaultdict(list)
    for m in estacion.mediciones.order_by('anno', 'mes'):
        medias[m.contaminante_id].append({
            'anno': m.anno,
            'mes': m.mes,
            'media': round(m.media, 1),
            'periodicidad': m.periodicidad,
            'num_datos': m.num_datos,
            'cobertura': round(m.cobertura, 2),
            'pocos_datos': m.pocos_datos,
        })

    return JsonResponse({
        'id': estacion.pk,
        'codigo': estacion.codigo,
        'codigo_europeo': estacion.codigo_europeo,
        'nombre': estacion.nombre,
        'direccion': estacion.direccion,
        'municipio': estacion.municipio,
        'provincia': estacion.provincia,
        'comunidad': estacion.comunidad,
        'red': estacion.red,
        'tipo': estacion.get_tipo_display(),
        'area': estacion.get_area_display(),
        'altitud': estacion.altitud,
        'fecha_alta': estacion.fecha_alta,
        'coordenadas': {
            'wgs84': {'lat': estacion.ubicacion.y, 'lng': estacion.ubicacion.x},
            'utm': coordenadas_utm(estacion.ubicacion),
        },
        'contaminantes': [
            {
                'abreviatura': c.abreviatura,
                'nombre': c.nombre,
                'unidad': c.unidad,
                'mediciones': medias[c.pk],
            }
            for c in sorted(estacion.contaminantes.all(), key=lambda c: c.codigo)
        ],
    })


@require_GET
def estaciones_cercanas(request, pk):
    """Estaciones activas a menos de ?km= kilómetros, de la más cercana a la más lejana."""
    try:
        km = float(request.GET.get('km', RADIO_POR_DEFECTO_KM))
    except ValueError:
        km = 0
    if not 0 < km <= RADIO_MAXIMO_KM:
        return error(f'El radio debe estar entre 0 y {RADIO_MAXIMO_KM} km', 400)

    try:
        estacion = Estacion.objects.get(pk=pk)
    except Estacion.DoesNotExist:
        return error('No existe la estación', 404)

    # El campo es de tipo geography: PostGIS mide sobre el elipsoide WGS84, en metros.
    cercanas = (
        estaciones_activas().exclude(pk=estacion.pk)
        .filter(ubicacion__dwithin=(estacion.ubicacion, D(km=km)))
        .annotate(distancia=Distance('ubicacion', estacion.ubicacion))
        .order_by('distancia')
    )
    return JsonResponse({
        'estacion': estacion.pk,
        'radio_km': km,
        'cercanas': [
            {'id': c.pk, 'nombre': c.nombre, 'municipio': c.municipio, 'distancia_km': round(c.distancia.km, 2)}
            for c in cercanas
        ],
    })


@require_POST
def corregir_ubicacion(request, pk):
    """Guarda la posición corregida de una estación tras arrastrar su marcador.

    Espera un JSON con {"lat": <float>, "lng": <float>} y devuelve las nuevas coordenadas UTM.
    Solo pueden hacerlo los usuarios con permiso para editar estaciones.
    """
    if not request.user.has_perm(PERMISO_EDITAR):
        return error('No tienes permiso', 403)

    try:
        datos = json.loads(request.body)
        lat = float(datos['lat'])
        lng = float(datos['lng'])
    except (ValueError, KeyError, TypeError):
        return error('Datos no válidos', 400)

    if not (LIMITES_ESPANA['lat'][0] <= lat <= LIMITES_ESPANA['lat'][1]
            and LIMITES_ESPANA['lng'][0] <= lng <= LIMITES_ESPANA['lng'][1]):
        return error('La ubicación está fuera de España', 400)

    try:
        estacion = Estacion.objects.get(pk=pk)
    except Estacion.DoesNotExist:
        return error('No existe la estación', 404)

    estacion.ubicacion = Point(lng, lat, srid=4326)
    estacion.ubicacion_corregida = True  # al volver a importar no se sustituye
    estacion.save(update_fields=['ubicacion', 'ubicacion_corregida'])
    return JsonResponse({'status': 'ok', 'utm': coordenadas_utm(estacion.ubicacion)})
