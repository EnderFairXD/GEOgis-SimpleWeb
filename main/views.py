import json
from collections import defaultdict

from django.contrib.gis.db.models.functions import AsGeoJSON, Distance
from django.contrib.gis.geos import Point, Polygon
from django.contrib.gis.measure import D
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .cobertura import distancias_a_la_estacion_mas_cercana, simular_estacion as calcular_simulacion
from .geo import coordenadas_utm
from .ine import PROVINCIAS
from .limites import LIMITES_ANUALES, SIN_LIMITE_ANUAL, media_anual, redondear
from .models import Contaminante, Estacion, MedicionMensual, Municipio

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


def porcentaje(parte, total, decimales=1):
    return round(100 * parte / total, decimales) if total else 0.0


def punto_en_espana(lat, lng):
    """Point WGS84 si las coordenadas son números dentro de España; si no, None."""
    try:
        lat, lng = float(lat), float(lng)
    except (TypeError, ValueError):
        return None
    if not (LIMITES_ESPANA['lat'][0] <= lat <= LIMITES_ESPANA['lat'][1]
            and LIMITES_ESPANA['lng'][0] <= lng <= LIMITES_ESPANA['lng'][1]):
        return None
    return Point(lng, lat, srid=4326)


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

    mediciones = defaultdict(list)
    for m in estacion.mediciones.order_by('anno', 'mes'):
        mediciones[m.contaminante_id].append(m)

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
            datos_contaminante(c, mediciones[c.pk])
            for c in sorted(estacion.contaminantes.all(), key=lambda c: c.codigo)
        ],
    })


def datos_contaminante(contaminante, mediciones):
    """Medias mensuales de un contaminante en una estación, su media anual del último año con
    datos y cómo queda respecto a cada límite anual."""
    ultimo_anno = mediciones[-1].anno if mediciones else None
    anual = media_anual([m for m in mediciones if m.anno == ultimo_anno])
    valida = anual is not None and anual['valida']
    return {
        'abreviatura': contaminante.abreviatura,
        'nombre': contaminante.nombre,
        'unidad': contaminante.unidad,
        'mediciones': [
            {
                'anno': m.anno,
                'mes': m.mes,
                'media': redondear(m.media),
                'periodicidad': m.periodicidad,
                'num_datos': m.num_datos,
                'cobertura': round(m.cobertura, 2),
                'pocos_datos': m.pocos_datos,
            }
            for m in mediciones
        ],
        'anual': anual and {**anual, 'media': redondear(anual['media']), 'cobertura': round(anual['cobertura'], 2)},
        'sin_limite_anual': SIN_LIMITE_ANUAL.get(contaminante.codigo),
        'limites': [
            {
                'valor': limite.valor,
                'tipo': limite.tipo,
                'norma': limite.norma,
                'desde': limite.desde,
                # Solo se compara una media anual con la cobertura mínima legal
                'supera': anual['media'] > limite.valor if valida else None,
            }
            for limite in LIMITES_ANUALES.get(contaminante.codigo, [])
        ],
    }


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
        lat, lng = float(datos['lat']), float(datos['lng'])
    except (ValueError, KeyError, TypeError):
        return error('Datos no válidos', 400)

    punto = punto_en_espana(lat, lng)
    if punto is None:
        return error('La ubicación está fuera de España', 400)

    try:
        estacion = Estacion.objects.get(pk=pk)
    except Estacion.DoesNotExist:
        return error('No existe la estación', 404)

    estacion.ubicacion = punto
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


@require_GET
def resumen_limites(request):
    """Cuántas estaciones activas superan cada límite anual, por contaminante (?anno=, por defecto
    el último año con datos). Solo cuentan las medias anuales con la cobertura mínima legal."""
    try:
        anno = int(request.GET['anno']) if 'anno' in request.GET else \
            MedicionMensual.objects.aggregate(ultimo=Max('anno'))['ultimo']
    except ValueError:
        return error('anno debe ser un año', 400)

    resumen = []
    for contaminante in Contaminante.objects.filter(codigo__in=LIMITES_ANUALES).order_by('codigo'):
        por_estacion = defaultdict(list)
        for m in MedicionMensual.objects.filter(anno=anno, contaminante=contaminante,
                                                estacion__fecha_baja__isnull=True):
            por_estacion[m.estacion_id].append(m)
        medias = [a['media'] for a in map(media_anual, por_estacion.values()) if a['valida']]
        if not medias:
            continue
        resumen.append({
            'codigo': contaminante.codigo,
            'abreviatura': contaminante.abreviatura,
            'nombre': contaminante.nombre,
            'unidad': contaminante.unidad,
            'estaciones_evaluadas': len(medias),
            'limites': [
                {'valor': l.valor, 'tipo': l.tipo, 'norma': l.norma, 'desde': l.desde,
                 'estaciones_que_superan': sum(media > l.valor for media in medias)}
                for l in LIMITES_ANUALES[contaminante.codigo]
            ],
        })
    return JsonResponse({'anno': anno, 'contaminantes': resumen})


@require_GET
def simular_estacion(request):
    """¿Qué pasaría con una estación más en ?lat=&lng=? Municipio, estaciones reales más cercanas
    y población que pasaría a tener una estación a menos de ?km= (10 por defecto). No guarda nada."""
    punto = punto_en_espana(request.GET.get('lat'), request.GET.get('lng'))
    if punto is None:
        return error('Indica lat y lng de un punto de España', 400)
    km = leer_radio(request, RADIO_COBERTURA_POR_DEFECTO_KM)
    if km is None:
        return error(f'El radio debe estar entre 0 y {RADIO_MAXIMO_KM} km', 400)

    municipio = Municipio.objects.filter(geometria__contains=punto).first()
    cercanas = estaciones_activas().annotate(distancia=Distance('ubicacion', punto)).order_by('distancia')[:5]
    simulacion = calcular_simulacion(punto, km)
    nuevos = (Municipio.objects.filter(pk__in=simulacion['nuevos'])
              .annotate(forma=AsGeoJSON('geometria_mapa', precision=5))
              .order_by('-poblacion', 'nombre'))

    def km_o_nada(distancia):
        return None if distancia is None else round(distancia, 1)

    return JsonResponse({
        'ubicacion': {'lat': punto.y, 'lng': punto.x, 'utm': coordenadas_utm(punto)},
        'municipio': municipio and {'codigo': municipio.codigo, 'nombre': municipio.nombre,
                                    'provincia': municipio.provincia},
        'cercanas': [
            {'id': e.pk, 'nombre': e.nombre, 'municipio': e.municipio, 'distancia_km': round(e.distancia.km, 2)}
            for e in cercanas
        ],
        'cobertura': {
            'radio_km': km,
            'poblacion_nueva': simulacion['poblacion_despues'] - simulacion['poblacion_antes'],
            # Dos decimales: una estación suma como mucho unas décimas a la cobertura nacional
            'porcentaje_antes': porcentaje(simulacion['poblacion_antes'], simulacion['poblacion_total'], 2),
            'porcentaje_despues': porcentaje(simulacion['poblacion_despues'], simulacion['poblacion_total'], 2),
        },
        'municipios_nuevos': {
            'type': 'FeatureCollection',
            'features': [
                {
                    'type': 'Feature',
                    'geometry': json.loads(m.forma),
                    'properties': {
                        'codigo': m.codigo,
                        'nombre': m.nombre,
                        'poblacion': m.poblacion,
                        'distancia_actual_km': km_o_nada(simulacion['nuevos'][m.pk]),
                    },
                }
                for m in nuevos
            ],
        },
    })
