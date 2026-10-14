import json

from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.geos import Point
from django.contrib.gis.measure import D
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import Jugador

PERMISO_EDITAR = 'main.change_jugador'
RADIO_POR_DEFECTO_KM = 500
RADIO_MAXIMO_KM = 20000  # media vuelta al mundo


@ensure_csrf_cookie
def index(request):
    """Página del mapa. Los jugadores se piden después a la API."""
    return render(request, 'main/Main.html', {
        'puede_editar': request.user.has_perm(PERMISO_EDITAR),
    })


@require_GET
def jugadores_geojson(request):
    """Todos los jugadores con ubicación, como FeatureCollection GeoJSON."""
    jugadores = (
        Jugador.objects.exclude(ubicacion__isnull=True)
        .prefetch_related('puntuacion_set__videojuego')
        .order_by('pk')
    )

    features = []
    for jugador in jugadores:
        features.append({
            'type': 'Feature',
            'geometry': json.loads(jugador.ubicacion.geojson),
            'properties': {
                'id': jugador.pk,
                'alias': jugador.alias,
                'nombre': jugador.nombre,
                'plataforma': jugador.plataforma,
                'historial_juegos': [
                    {'titulo': p.videojuego.nombre, 'puntos': p.puntos}
                    for p in jugador.puntuacion_set.all()
                ],
            },
        })

    return JsonResponse({'type': 'FeatureCollection', 'features': features})


@require_GET
def jugadores_cercanos(request, pk):
    """Jugadores a menos de ?km= kilómetros del jugador indicado, del más cercano al más lejano."""
    try:
        km = float(request.GET.get('km', RADIO_POR_DEFECTO_KM))
    except ValueError:
        km = 0
    if not 0 < km <= RADIO_MAXIMO_KM:
        return JsonResponse(
            {'status': 'error', 'msg': f'El radio debe estar entre 0 y {RADIO_MAXIMO_KM} km'}, status=400)

    try:
        jugador = Jugador.objects.get(pk=pk)
    except Jugador.DoesNotExist:
        return JsonResponse({'status': 'error', 'msg': 'No existe el jugador'}, status=404)
    if jugador.ubicacion is None:
        return JsonResponse({'status': 'error', 'msg': 'El jugador no tiene ubicación'}, status=400)

    # PostGIS calcula la distancia sobre la esfera terrestre, en metros.
    cercanos = (
        Jugador.objects.exclude(pk=jugador.pk)
        .filter(ubicacion__distance_lte=(jugador.ubicacion, D(km=km)))
        .annotate(distancia=Distance('ubicacion', jugador.ubicacion))
        .order_by('distancia')
    )

    return JsonResponse({
        'jugador': jugador.pk,
        'radio_km': km,
        'cercanos': [
            {'id': c.pk, 'alias': c.alias, 'distancia_km': round(c.distancia.km, 1)}
            for c in cercanos
        ],
    })


@require_POST
def actualizar_ubicacion_jugador(request, pk):
    """Guarda la nueva posición de un jugador tras arrastrar su marcador.

    Espera un JSON con {"lat": <float>, "lng": <float>}. Solo pueden hacerlo
    los usuarios con permiso para editar jugadores.
    """
    if not request.user.has_perm(PERMISO_EDITAR):
        return JsonResponse({'status': 'error', 'msg': 'No tienes permiso'}, status=403)

    try:
        datos = json.loads(request.body)
        lat = float(datos['lat'])
        lng = float(datos['lng'])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'status': 'error', 'msg': 'Datos no válidos'}, status=400)

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return JsonResponse({'status': 'error', 'msg': 'Coordenadas fuera de rango'}, status=400)

    try:
        jugador = Jugador.objects.get(pk=pk)
    except Jugador.DoesNotExist:
        return JsonResponse({'status': 'error', 'msg': 'No existe el jugador'}, status=404)

    # GeoDjango guarda (longitud, latitud); srid=4326 indica coordenadas GPS (WGS84).
    jugador.ubicacion = Point(lng, lat, srid=4326)
    jugador.save(update_fields=['ubicacion'])
    return JsonResponse({'status': 'ok'})
