import json

from django.contrib.gis.geos import Point
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Jugador


@ensure_csrf_cookie
def index(request):
    """Mapa con todos los jugadores que tienen ubicación."""
    jugadores = (
        Jugador.objects.exclude(ubicacion__isnull=True)
        .prefetch_related('puntuacion_set__videojuego')
    )

    features = []
    for jugador in jugadores:
        features.append({
            'type': 'Feature',
            'geometry': json.loads(jugador.ubicacion.geojson),
            'properties': {
                'id': jugador.pk,
                'nombre': jugador.nombre,
                'alias': jugador.alias,
                'plataforma': jugador.plataforma,
                'historial_juegos': [
                    {'titulo': p.videojuego.nombre, 'puntos': p.puntos}
                    for p in jugador.puntuacion_set.all()
                ],
            },
        })

    geojson = {'type': 'FeatureCollection', 'features': features}
    return render(request, 'main/Main.html', {'datos_jugadores': geojson})


@require_POST
def actualizar_ubicacion_jugador(request, pk):
    """Guarda la nueva posición de un jugador tras arrastrar su marcador.

    Espera un JSON con {"lat": <float>, "lng": <float>}.
    """
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
