import datetime
import tempfile
from io import StringIO

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import TestCase

from main.models import Contaminante, Estacion, MedicionMensual

from . import ficheros

MADRID = 28079008
BARCELONA = 8019043


class ImportarEstacionesTests(TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def importar(self, estaciones):
        ruta = ficheros.excel_metainformacion(self.carpeta.name, estaciones)
        salida = StringIO()
        call_command('importar_estaciones', fichero=str(ruta), stdout=salida)
        return salida.getvalue()

    def test_crea_las_estaciones_con_sus_datos(self):
        self.importar([
            ficheros.estacion(MADRID, 'ESCUELAS AGUIRRE', 40.42167, -3.68222,
                              COD_ESTACION_DEM='ES0118A', ALTITUD=672, DIRECCION='C/ Alcalá'),
        ])

        e = Estacion.objects.get(codigo=MADRID)
        self.assertEqual(e.codigo_europeo, 'ES0118A')
        self.assertEqual(e.nombre, 'ESCUELAS AGUIRRE')
        self.assertEqual((e.municipio, e.provincia, e.comunidad), ('MADRID', 'MADRID', 'MADRID'))
        self.assertEqual((e.tipo, e.area, e.altitud), ('TRAFICO', 'URBANA', 672))
        self.assertEqual(e.direccion, 'C/ Alcalá')
        self.assertEqual(e.fecha_alta, datetime.date(1998, 12, 1))
        self.assertIsNone(e.fecha_baja)
        self.assertAlmostEqual(e.ubicacion.x, -3.68222)  # longitud
        self.assertAlmostEqual(e.ubicacion.y, 40.42167)  # latitud

    def test_crea_el_catalogo_de_contaminantes(self):
        self.importar([])

        no2 = Contaminante.objects.get(codigo=8)
        self.assertEqual((no2.abreviatura, no2.nombre, no2.unidad), ('NO2', 'DIÓXIDO DE NITRÓGENO', 'µg/m3'))
        self.assertEqual(Contaminante.objects.count(), len(ficheros.MAGNITUDES))

    def test_guarda_la_fecha_de_baja_de_las_estaciones_cerradas(self):
        self.importar([
            ficheros.estacion(MADRID, 'CERRADA', 40.4, -3.7, FECHA_FIN='2024-06-30 00:00:00.000'),
        ])

        self.assertEqual(Estacion.objects.get(codigo=MADRID).fecha_baja, datetime.date(2024, 6, 30))

    def test_respeta_las_ubicaciones_corregidas_a_mano(self):
        self.importar([ficheros.estacion(MADRID, 'NOMBRE VIEJO', 40.4, -3.7)])
        Estacion.objects.filter(codigo=MADRID).update(ubicacion=Point(-3.65, 40.45, srid=4326),
                                                      ubicacion_corregida=True)

        self.importar([ficheros.estacion(MADRID, 'NOMBRE NUEVO', 40.4, -3.7)])

        e = Estacion.objects.get(codigo=MADRID)
        self.assertEqual(e.nombre, 'NOMBRE NUEVO')  # el resto de datos sí se actualiza
        self.assertEqual((e.ubicacion.x, e.ubicacion.y), (-3.65, 40.45))

    def test_dice_cuantas_ubicaciones_corregidas_conserva(self):
        self.importar([ficheros.estacion(MADRID, 'MADRID', 40.4, -3.7)])
        Estacion.objects.update(ubicacion_corregida=True)

        salida = self.importar([ficheros.estacion(MADRID, 'MADRID', 40.4, -3.7)])

        self.assertIn('1 ubicación corregida a mano', salida)

    def test_importar_otra_vez_actualiza_sin_duplicar(self):
        self.importar([ficheros.estacion(MADRID, 'NOMBRE VIEJO', 40.4, -3.7)])

        self.importar([ficheros.estacion(MADRID, 'NOMBRE NUEVO', 40.4, -3.7)])

        self.assertEqual(Estacion.objects.count(), 1)
        self.assertEqual(Estacion.objects.get().nombre, 'NOMBRE NUEVO')
        self.assertEqual(Contaminante.objects.count(), len(ficheros.MAGNITUDES))


class ImportarMedicionesTests(TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        ruta = ficheros.excel_metainformacion(self.carpeta.name, [
            ficheros.estacion(MADRID, 'MADRID', 40.42, -3.68),
            ficheros.estacion(BARCELONA, 'BARCELONA', 41.39, 2.15, N_CCAA='CATALUÑA'),
        ])
        call_command('importar_estaciones', fichero=str(ruta), stdout=StringIO())
        self.madrid = Estacion.objects.get(codigo=MADRID)
        self.no2 = Contaminante.objects.get(abreviatura='NO2')
        self.pm10 = Contaminante.objects.get(abreviatura='PM10')

    def importar(self, horarios=(), diarios=()):
        horario = ficheros.zip_csv(self.carpeta.name, 'HH.zip', {
            'NO2_HH_2024.csv': [ficheros.cabecera_horaria(), *horarios]})
        diario = ficheros.zip_csv(self.carpeta.name, 'DD.zip', {
            'PM10_DD_2024.csv': [ficheros.cabecera_diaria(), *diarios]})
        salida = StringIO()
        call_command('importar_mediciones', horario=str(horario), diario=str(diario), stdout=salida)
        return salida.getvalue()

    def test_media_mensual_de_los_valores_horarios(self):
        self.importar(horarios=[
            ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [10, 20]),
            ficheros.fila_horaria(MADRID, 8, 2024, 1, 2, [30, 40, 50]),
        ])

        m = MedicionMensual.objects.get(estacion=self.madrid, contaminante=self.no2, anno=2024, mes=1)
        self.assertEqual((m.media, m.num_datos), (30.0, 5))

    def test_una_medicion_por_mes(self):
        self.importar(horarios=[
            ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [10]),
            ficheros.fila_horaria(MADRID, 8, 2024, 2, 1, [20]),
        ])

        meses = list(MedicionMensual.objects.filter(estacion=self.madrid).values_list('mes', 'media'))
        self.assertEqual(meses, [(1, 10.0), (2, 20.0)])

    def test_media_mensual_de_los_valores_diarios_de_todos_los_puntos_de_muestreo(self):
        self.importar(diarios=[
            ficheros.fila_diaria(MADRID, 10, 2024, 3, [20, 40], punto='A'),
            ficheros.fila_diaria(MADRID, 10, 2024, 3, [60], punto='M'),
        ])

        m = MedicionMensual.objects.get(estacion=self.madrid, contaminante=self.pm10, mes=3)
        self.assertEqual((m.media, m.num_datos), (40.0, 3))

    def test_si_hay_datos_horarios_no_se_mezclan_con_los_diarios(self):
        horario = ficheros.zip_csv(self.carpeta.name, 'HH.zip', {
            'PM10_HH_2024.csv': [ficheros.cabecera_horaria(),
                                 ficheros.fila_horaria(MADRID, 10, 2024, 3, 1, [10, 30])]})
        diario = ficheros.zip_csv(self.carpeta.name, 'DD.zip', {
            'PM10_DD_2024.csv': [ficheros.cabecera_diaria(),
                                 ficheros.fila_diaria(MADRID, 10, 2024, 3, [100])]})

        call_command('importar_mediciones', horario=str(horario), diario=str(diario), stdout=StringIO())

        m = MedicionMensual.objects.get(estacion=self.madrid, contaminante=self.pm10, mes=3)
        self.assertEqual((m.media, m.num_datos), (20.0, 2))

    def test_descarta_valores_negativos(self):
        self.importar(horarios=[ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [-1, 10, 20])])

        m = MedicionMensual.objects.get(estacion=self.madrid, contaminante=self.no2)
        self.assertEqual((m.media, m.num_datos), (15.0, 2))

    def test_anota_que_contaminantes_mide_cada_estacion(self):
        self.importar(
            horarios=[ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [10])],
            diarios=[ficheros.fila_diaria(MADRID, 10, 2024, 1, [20])],
        )

        self.assertEqual(set(self.madrid.contaminantes.values_list('abreviatura', flat=True)), {'NO2', 'PM10'})
        self.assertFalse(Estacion.objects.get(codigo=BARCELONA).contaminantes.exists())

    def test_ignora_estaciones_que_no_estan_en_el_catalogo_y_lo_dice(self):
        salida = self.importar(horarios=[ficheros.fila_horaria(99999999, 8, 2024, 1, 1, [10])])

        self.assertFalse(MedicionMensual.objects.exists())
        self.assertIn('1 estación desconocida', salida)

    def test_importar_otra_vez_actualiza_sin_duplicar(self):
        self.importar(horarios=[ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [10])])

        self.importar(horarios=[ficheros.fila_horaria(MADRID, 8, 2024, 1, 1, [50])])

        self.assertEqual(MedicionMensual.objects.count(), 1)
        self.assertEqual(MedicionMensual.objects.get().media, 50.0)
