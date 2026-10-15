"""Límites legales anuales de calidad del aire y cálculo de la media anual.

Solo se comparan los valores anuales: con medias mensuales no se pueden evaluar los límites
horarios u octohorarios ni los diarios, que cuentan superaciones hora a hora o día a día.

Fuentes:
- Real Decreto 102/2011, anexo I (valores límite y valores objetivo vigentes).
- Directiva (UE) 2024/2881, anexo I (valores límite que se aplican desde el 1 de enero de 2030).
"""
import calendar
from dataclasses import dataclass

from .models import MedicionMensual

RD_102_2011 = 'RD 102/2011'
DIRECTIVA_2024 = 'Directiva (UE) 2024/2881'
VALOR_LIMITE = 'valor límite'
VALOR_OBJETIVO = 'valor objetivo'

# RD 102/2011, criterios de agregación: la media anual necesita al menos el 90 % de los valores
# horarios del año.
COBERTURA_MINIMA_HORARIA = 0.90
# RD 102/2011, objetivos de calidad de los datos: las mediciones indicativas (captadores manuales)
# tienen una periodicidad mínima del 14 % del año.
COBERTURA_MINIMA_DIARIA = 0.14


@dataclass(frozen=True)
class Limite:
    valor: float  # en la unidad del contaminante en los ficheros del MITECO
    tipo: str
    norma: str
    desde: int    # año desde el que se aplica


# Por código de magnitud del MITECO.
LIMITES_ANUALES = {
    8: [Limite(40, VALOR_LIMITE, RD_102_2011, 2010), Limite(20, VALOR_LIMITE, DIRECTIVA_2024, 2030)],      # NO2
    10: [Limite(40, VALOR_LIMITE, RD_102_2011, 2005), Limite(20, VALOR_LIMITE, DIRECTIVA_2024, 2030)],     # PM10
    9: [Limite(25, VALOR_LIMITE, RD_102_2011, 2015), Limite(10, VALOR_LIMITE, DIRECTIVA_2024, 2030)],      # PM2.5
    1: [Limite(20, VALOR_LIMITE, DIRECTIVA_2024, 2030)],                                                    # SO2
    30: [Limite(5, VALOR_LIMITE, RD_102_2011, 2010), Limite(3.4, VALOR_LIMITE, DIRECTIVA_2024, 2030)],     # benceno
    19: [Limite(0.5, VALOR_LIMITE, RD_102_2011, 2005)],                                                     # Pb (igual en 2030)
    # Metales y benzo(a)pireno (ng/m3): mismo valor, pero pasan de valor objetivo a valor límite en 2030
    17: [Limite(6, VALOR_OBJETIVO, RD_102_2011, 2013), Limite(6, VALOR_LIMITE, DIRECTIVA_2024, 2030)],     # As
    28: [Limite(5, VALOR_OBJETIVO, RD_102_2011, 2013), Limite(5, VALOR_LIMITE, DIRECTIVA_2024, 2030)],     # Cd
    62: [Limite(20, VALOR_OBJETIVO, RD_102_2011, 2013), Limite(20, VALOR_LIMITE, DIRECTIVA_2024, 2030)],   # Ni
    27: [Limite(1, VALOR_OBJETIVO, RD_102_2011, 2013), Limite(1, VALOR_LIMITE, DIRECTIVA_2024, 2030)],     # BaP
}

# Por qué no se compara con un límite anual el resto de contaminantes del catálogo del MITECO.
SIN_LIMITE_ANUAL = {
    14: 'El ozono solo tiene un valor objetivo octohorario (120 µg/m³), que no se puede evaluar con medias mensuales.',
    6: 'El monóxido de carbono solo tiene un valor límite octohorario (10 mg/m³), que no se puede evaluar con medias mensuales.',
    7: 'El monóxido de nitrógeno no tiene límite legal: se mide para calcular los óxidos de nitrógeno.',
    12: ('Los óxidos de nitrógeno solo tienen un nivel crítico anual para la vegetación (30 µg/m³), que se aplica '
         'en zonas rurales alejadas de las fuentes de emisión; no se compara aquí.'),
}


def redondear(valor):
    """Un decimal para valores desde 1 y tres por debajo: los metales y el benzo(a)pireno se miden
    en centésimas o milésimas de su unidad."""
    return round(valor, 1 if abs(valor) >= 1 else 3)


def media_anual(mediciones):
    """Media anual a partir de las medias mensuales de un año (de una estación y un contaminante).

    Se pondera por los datos de cada mes, así que coincide con la media de todos los valores del
    año. Es válida para compararla con un límite si alcanza la cobertura mínima legal; las que
    salen de datos diarios (captadores manuales) son mediciones indicativas, y por tanto orientativas.
    """
    if not mediciones:
        return None
    anno = mediciones[0].anno
    num_datos = sum(m.num_datos for m in mediciones)
    horaria = mediciones[0].periodicidad == MedicionMensual.Periodicidad.HORARIA
    dias = 366 if calendar.isleap(anno) else 365
    cobertura = num_datos / (dias * 24 if horaria else dias)
    return {
        'anno': anno,
        'media': sum(m.media * m.num_datos for m in mediciones) / num_datos,
        'num_datos': num_datos,
        'periodicidad': mediciones[0].periodicidad,
        'cobertura': cobertura,
        'valida': cobertura >= (COBERTURA_MINIMA_HORARIA if horaria else COBERTURA_MINIMA_DIARIA),
        'orientativa': not horaria,
    }
