import json
from collections import defaultdict

from django.contrib.gis.db.models.functions import AsGeoJSON, Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .cobertura import distancias_a_la_estacion_mas_cercana
from .geo import coordenadas_utm
from .ine import PROVINCIAS
from .models import Estacion, Municipio

PERMISO_EDITAR = 'main.change_estacion'
RADIO_POR_DEFECTO_KM = 25
RADIO_COBERTURA_POR_DEFECTO_KM = 10
RADIO_MAXIMO_KM = 1000
# Más municipios que estos en la zona visible serían una respuesta demasiado pesada para el mapa.
MAXIMO_MUNICIPIOS = 2500
# Rectángulo que contiene España, Canarias incluida (longitud, latitud)
LIMITES_ESPANA = {'lng': (-18.5, 4.6), 'lat': (27.4, 44.0)}


def error(mensaje, estado):
    return JsonResponse({'status': 'error', 'msg': mensaje}, status=estado)


def estaciones_activas():
    return Estacion.objects.filter(fecha_baja__isnull=True)


def leer_radio(request, por_defecto):
    """Radio ?km= de la petición, o None si no es válido."""
    try:
        km = float(request.GET.get('km', por_defecto))
    except ValueError:
        return None
    return km if 0 < km <= RADIO_MAXIMO_KM else None


def porcentaje(parte, total):
    return round(100 * parte / total, 1) if total else 0.0


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


def municipio_segun_coordenadas(estacion):
    """Municipio que contiene la estación según sus coordenadas y si cuadra con el de su código."""
    if estacion.municipio_geo is None:
        return None
    km = estacion.km_al_municipio_declarado()
    return {
        'codigo': estacion.municipio_geo.codigo,
        'nombre': estacion.municipio_geo.nombre,
        'coincide': km == 0,
        'distancia_al_declarado_km': None if km is None else round(km, 1),
        'posible_error': km is not None and km > Estacion.TOLERANCIA_LIMITE_KM,
    }


@require_GET
def detalle_estacion(request, pk):
    """Ficha de una estación: datos, coordenadas (WGS84 y UTM) y medias mensuales por contaminante."""
    try:
        estacion = Estacion.objects.select_related('municipio_geo').prefetch_related('contaminantes').get(pk=pk)
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
        'municipio_geo': municipio_segun_coordenadas(estacion),
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
    km = leer_radio(request, RADIO_POR_DEFECTO_KM)
    if km is None:
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


@require_GET
def cobertura(request):
    """Población y municipios a menos de ?km= de una estación activa, en total y por provincia."""
    km = leer_radio(request, RADIO_COBERTURA_POR_DEFECTO_KM)
    if km is None:
        return error(f'El radio debe estar entre 0 y {RADIO_MAXIMO_KM} km', 400)

    distancias = distancias_a_la_estacion_mas_cercana()
    total = {'municipios': 0, 'cubiertos': 0, 'poblacion': 0, 'cubierta': 0}
    provincias = defaultdict(lambda: {'poblacion': 0, 'cubierta': 0})
    for pk, provincia, poblacion in Municipio.objects.values_list('pk', 'provincia_codigo', 'poblacion'):
        distancia = distancias.get(pk)
        cubierto = distancia is not None and distancia <= km
        total['municipios'] += 1
        total['cubiertos'] += cubierto
        total['poblacion'] += poblacion
        total['cubierta'] += poblacion * cubierto
        provincias[provincia]['poblacion'] += poblacion
        provincias[provincia]['cubierta'] += poblacion * cubierto

    resumen_provincias = sorted(
        (
            {'codigo': codigo, 'nombre': PROVINCIAS[codigo], **datos,
             'porcentaje': porcentaje(datos['cubierta'], datos['poblacion'])}
            for codigo, datos in provincias.items()
        ),
        key=lambda p: (p['porcentaje'], p['nombre']),
    )
    return JsonResponse({
        'radio_km': km,
        'municipios': {'total': total['municipios'], 'cubiertos': total['cubiertos']},
        'poblacion': {
            'total': total['poblacion'],
            'cubierta': total['cubierta'],
            'porcentaje': porcentaje(total['cubierta'], total['poblacion']),
        },
        'provincias': resumen_provincias,
    })


@require_GET
def municipios_geojson(request):
    """Municipios de la zona visible (?bbox=oeste,sur,este,norte) con la distancia a su estación
    activa más cercana, para colorear el mapa de cobertura."""
    try:
        oeste, sur, este, norte = (float(v) for v in request.GET.get('bbox', '').split(','))
    except ValueError:
        return error('bbox debe ser oeste,sur,este,norte en grados', 400)
    if not (-180 <= oeste < este <= 180 and -90 <= sur < norte <= 90):
        return error('bbox debe ser oeste,sur,este,norte en grados', 400)

    zona = Polygon.from_bbox((oeste, sur, este, norte))
    zona.srid = 4326
    municipios = Municipio.objects.filter(geometria_mapa__intersects=zona)
    if municipios.count() > MAXIMO_MUNICIPIOS:
        return error('Hay demasiados municipios en la zona: acerca el zoom', 400)

    municipios = list(municipios.annotate(forma=AsGeoJSON('geometria_mapa', precision=5))
                      .values('pk', 'codigo', 'nombre', 'poblacion', 'forma'))
    distancias = distancias_a_la_estacion_mas_cercana([m['pk'] for m in municipios])
    features = [
        {
            'type': 'Feature',
            'geometry': json.loads(m['forma']),
            'properties': {
                'codigo': m['codigo'],
                'nombre': m['nombre'],
                'poblacion': m['poblacion'],
                'distancia_km': None if distancias.get(m['pk']) is None else round(distancias[m['pk']], 1),
            },
        }
        for m in municipios
    ]
    return JsonResponse({'type': 'FeatureCollection', 'features': features})
