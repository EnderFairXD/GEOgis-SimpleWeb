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
