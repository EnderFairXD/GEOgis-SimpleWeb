"""Cobertura de la red: a qué distancia queda cada término municipal de la estación activa más cercana.

Se mide hasta cualquier punto del término (0 si la estación está dentro). Así un municipio con
estación cuenta como cubierto aunque sea muy extenso; a cambio, en un municipio grande puede haber
población lejos de la estación que se da por cubierta.
"""
from django.db import connection

from .models import Estacion, Municipio

# Para cada municipio, el operador KNN `<->` recorre el índice espacial de las estaciones y da la
# más cercana sin calcular todas las distancias; después ST_Distance la mide sobre el elipsoide.
CONSULTA = f'''
    SELECT m.id, ST_Distance(m.geometria::geography, cercana.ubicacion) / 1000
    FROM {Municipio._meta.db_table} m
    LEFT JOIN LATERAL (
        SELECT e.ubicacion FROM {Estacion._meta.db_table} e
        WHERE e.fecha_baja IS NULL
        ORDER BY m.geometria::geography <-> e.ubicacion
        LIMIT 1
    ) cercana ON true
'''


def distancias_a_la_estacion_mas_cercana(municipios=None):
    """Distancia en km desde cada término municipal a la estación activa más cercana.

    Devuelve {id del municipio: km}; `municipios` limita el cálculo a esos ids.
    """
    consulta, parametros = CONSULTA, []
    if municipios is not None:
        consulta += ' WHERE m.id = ANY(%s)'
        parametros = [list(municipios)]
    with connection.cursor() as cursor:
        cursor.execute(consulta, parametros)
        return dict(cursor.fetchall())


def municipios_a_menos_de(punto, km):
    """Ids de los municipios cuyo término queda a menos de `km` del punto (sobre el elipsoide).

    El primer filtro (`&&` con un rectángulo ampliado) usa el índice espacial; en España un grado
    mide al menos unos 80 km, así que km/60 grados de margen nunca deja fuera a ningún candidato.
    """
    consulta = f'''
        SELECT id FROM {Municipio._meta.db_table}
        WHERE geometria && ST_Expand(ST_GeomFromEWKT(%s), %s)
          AND ST_DWithin(geometria::geography, ST_GeogFromText(%s), %s)
    '''
    with connection.cursor() as cursor:
        cursor.execute(consulta, [punto.ewkt, km / 60, punto.ewkt, km * 1000])
        return [fila[0] for fila in cursor.fetchall()]


def simular_estacion(punto, km):
    """Población que quedaría cubierta a `km` si hubiera una estación más en `punto`.

    Devuelve la población cubierta antes y después, y los ids de los municipios que pasarían a
    estarlo con la distancia que tienen hoy a su estación más cercana.
    """
    distancias = distancias_a_la_estacion_mas_cercana()
    poblaciones = dict(Municipio.objects.values_list('pk', 'poblacion'))

    def cubierto(pk):
        return distancias.get(pk) is not None and distancias[pk] <= km

    nuevos = [pk for pk in municipios_a_menos_de(punto, km) if not cubierto(pk)]
    antes = sum(poblacion for pk, poblacion in poblaciones.items() if cubierto(pk))
    return {
        'poblacion_total': sum(poblaciones.values()),
        'poblacion_antes': antes,
        'poblacion_despues': antes + sum(poblaciones[pk] for pk in nuevos),
        'nuevos': {pk: distancias.get(pk) for pk in nuevos},
    }
