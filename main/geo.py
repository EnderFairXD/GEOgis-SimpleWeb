"""Sistemas de referencia UTM oficiales en España (ETRS89, y REGCAN95 en Canarias)."""
import math

# EPSG por huso: ETRS89 / UTM 29N, 30N y 31N en la Península, Baleares, Ceuta y Melilla.
EPSG_ETRS89_UTM = {29: 25829, 30: 25830, 31: 25831}
# Canarias usa el datum REGCAN95, en el huso 28.
EPSG_REGCAN95_UTM_28 = 4083


def sistema_utm(lng, lat):
    """Devuelve (EPSG, huso) del sistema UTM oficial para un punto de España."""
    if lng < -13 and lat < 30:
        return EPSG_REGCAN95_UTM_28, 28
    huso = math.floor((lng + 180) / 6) + 1
    return EPSG_ETRS89_UTM[huso], huso


def coordenadas_utm(punto):
    """Coordenadas en metros del punto (WGS84) en su huso UTM, sin modificar el original."""
    epsg, huso = sistema_utm(punto.x, punto.y)
    proyectado = punto.transform(epsg, clone=True)
    return {'epsg': epsg, 'huso': huso, 'x': round(proyectado.x, 2), 'y': round(proyectado.y, 2)}
