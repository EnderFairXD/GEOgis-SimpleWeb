"""Ficheros de prueba con el mismo formato que los del MITECO, generados en una carpeta temporal."""
import io
import zipfile
from pathlib import Path

from openpyxl import Workbook

CABECERA_ESTACIONES = [
    'COD_LOCAL', 'PROVINCIA', 'MUNICIPIO', 'ESTACION', 'COD_ESTACION_DEM', 'N_RED', 'NOMBRE',
    'FECHA_INI', 'FECHA_FIN', 'LATITUD_G', 'LONGITUD_G', 'ALTITUD', 'N_CCAA', 'N_PROVINCIA',
    'N_MUNICIPIO', 'TIPO_ESTACION', 'TIPO_AREA', 'TIPO_SUBAREA_RURAL', 'EST', 'ZONA', 'DIRECCION',
]

MAGNITUDES = [
    (1, 'DIÓXIDO DE AZUFRE', 'SO2', 'µg/m3', 'Contaminantes con valor legislado'),
    (8, 'DIÓXIDO DE NITRÓGENO', 'NO2', 'µg/m3', 'Contaminantes con valor legislado'),
    (10, 'PARTÍCULAS < 10 µm', 'PM10', 'µg/m3', 'Contaminantes con valor legislado'),
]


def estacion(cod_local, nombre, lat, lng, **otros):
    """Fila de la hoja Estaciones_2024 con valores razonables por defecto."""
    fila = {
        'COD_LOCAL': cod_local,
        'PROVINCIA': cod_local // 1_000_000,
        'MUNICIPIO': cod_local // 1000 % 1000,
        'ESTACION': cod_local % 1000,
        'COD_ESTACION_DEM': f'ES{cod_local % 10000:04d}A',
        'N_RED': 'Red de prueba',
        'NOMBRE': nombre,
        'FECHA_INI': '1998-12-01 00:00:00.000',
        'FECHA_FIN': None,
        'LATITUD_G': lat,
        'LONGITUD_G': lng,
        'ALTITUD': 650,
        'N_CCAA': 'MADRID',
        'N_PROVINCIA': 'MADRID',
        'N_MUNICIPIO': 'MADRID',
        'TIPO_ESTACION': 'TRAFICO',
        'TIPO_AREA': 'URBANA',
        'DIRECCION': 'Calle de prueba, 1',
    }
    fila.update(otros)
    return [fila.get(columna) for columna in CABECERA_ESTACIONES]


def excel_metainformacion(carpeta, estaciones):
    libro = Workbook()
    hoja = libro.active
    hoja.title = 'Magnitudes'
    hoja.append(['MAGNITUD', 'NOMBRE', 'ABREVIATURA', 'UNIDAD', 'GRUPO'])
    for magnitud in MAGNITUDES:
        hoja.append(magnitud)
    hoja = libro.create_sheet('Estaciones_2024')
    hoja.append(CABECERA_ESTACIONES)
    for fila in estaciones:
        hoja.append(fila)
    ruta = Path(carpeta) / 'Metainformacion.xlsx'
    libro.save(ruta)
    return ruta


def zip_csv(carpeta, nombre, ficheros):
    """ZIP con CSV separados por ';' como los del MITECO. `ficheros` es {nombre: [filas]}."""
    ruta = Path(carpeta) / nombre
    with zipfile.ZipFile(ruta, 'w') as zf:
        for nombre_csv, filas in ficheros.items():
            texto = io.StringIO()
            for fila in filas:
                texto.write(';'.join('' if v is None else str(v) for v in fila) + '\n')
            zf.writestr(nombre_csv, '﻿' + texto.getvalue())
    return ruta


def cabecera_horaria():
    return (['PROVINCIA', 'MUNICIPIO', 'ESTACION', 'MAGNITUD', 'PUNTO_MUESTREO', 'ANNO', 'MES', 'DIA']
            + [f'H{h:02d}' for h in range(1, 25)])


def fila_horaria(cod_local, magnitud, anno, mes, dia, valores):
    """Fila de un día; `valores` son las horas con dato (las demás quedan vacías)."""
    horas = list(valores) + [None] * (24 - len(valores))
    return [cod_local // 1_000_000, cod_local // 1000 % 1000, cod_local % 1000, magnitud,
            f'{cod_local:08d}_{magnitud}_8', anno, mes, dia] + horas


def cabecera_diaria():
    return (['PROVINCIA', 'MUNICIPIO', 'ESTACION', 'MAGNITUD', 'PUNTO_MUESTREO', 'ANNO', 'MES']
            + [f'D{d:02d}' for d in range(1, 32)])


def fila_diaria(cod_local, magnitud, anno, mes, valores, punto='A'):
    """Fila de un mes; `valores` son los días con dato (los demás quedan vacíos)."""
    dias = list(valores) + [None] * (31 - len(valores))
    return [cod_local // 1_000_000, cod_local // 1000 % 1000, cod_local % 1000, magnitud,
            f'{cod_local:08d}_{magnitud}_{punto}', anno, mes] + dias
