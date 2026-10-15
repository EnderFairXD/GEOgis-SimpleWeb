import tempfile
from io import StringIO

from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from main.ine import nombre_provincia
from main.models import Estacion, Municipio

from . import ficheros
from .test_api import crear_estacion

# Dos municipios contiguos: Madrid encima de Getafe (rectángulos simplificados)
MADRID = ficheros.rectangulo(-3.9, 40.3, -3.5, 40.6)
GETAFE = ficheros.rectangulo(-3.8, 40.2, -3.6, 40.3)


class NombreProvinciaTests(SimpleTestCase):
    def test_nombre_segun_el_codigo_ine(self):
        self.assertEqual(nombre_provincia('28079'), 'Madrid')
        self.assertEqual(nombre_provincia('35016'), 'Las Palmas')
        self.assertEqual(nombre_provincia('07040'), 'Illes Balears')
        self.assertEqual(nombre_provincia('52001'), 'Melilla')


class ImportarMunicipiosTests(TestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)

    def importar(self, municipios):
        ruta = ficheros.geojson_municipios(self.carpeta.name, municipios)
        salida = StringIO()
        call_command('importar_municipios', fichero=str(ruta), stdout=salida)
        return salida.getvalue()

    def test_crea_los_municipios_de_espana_con_sus_datos(self):
        self.importar([
            ficheros.municipio('28079', 'Madrid', MADRID, poblacion=3_332_035),
            ficheros.municipio('PT1106', 'Lisboa', ficheros.rectangulo(-9.2, 38.7, -9.1, 38.8), pais='PT'),
        ])

        m = Municipio.objects.get()
        self.assertEqual((m.codigo, m.nombre, m.provincia, m.poblacion), ('28079', 'Madrid', 'Madrid', 3_332_035))

    def test_calcula_el_area_con_el_poligono_y_no_con_la_columna_de_gisco(self):
        # La columna AREA_KM2 de GISCO no cuadra con los polígonos de España: se ignora.
        # 0,4° x 0,3° a 40,45° de latitud: unos 33,9 km x 33,3 km.
        self.importar([ficheros.municipio('28079', 'Madrid', MADRID, area=5521.0)])

        self.assertAlmostEqual(Municipio.objects.get().area_km2, 1129, delta=10)

    def test_guarda_multipoligonos_y_su_version_simplificada(self):
        self.importar([ficheros.municipio('28079', 'Madrid', MADRID)])

        m = Municipio.objects.get()
        self.assertEqual(m.geometria.geom_type, 'MultiPolygon')
        self.assertEqual(m.geometria_mapa.geom_type, 'MultiPolygon')

    def test_acepta_municipios_formados_por_varios_poligonos(self):
        self.importar([ficheros.municipio('35016', 'Las Palmas de Gran Canaria',
                                          ficheros.rectangulo(-15.5, 28.0, -15.4, 28.2), multi=True)])

        self.assertEqual(Municipio.objects.get().provincia, 'Las Palmas')

    def test_importar_otra_vez_actualiza_sin_duplicar(self):
        self.importar([ficheros.municipio('28079', 'Madrid', MADRID, poblacion=1)])

        self.importar([ficheros.municipio('28079', 'Madrid', MADRID, poblacion=2)])

        self.assertEqual(Municipio.objects.get().poblacion, 2)

    def test_asigna_a_cada_estacion_el_municipio_que_la_contiene(self):
        dentro = crear_estacion(28079008, 'ESCUELAS AGUIRRE', -3.68, 40.42)
        fuera = crear_estacion(45168001, 'TOLEDO', -4.02, 39.86)

        self.importar([ficheros.municipio('28079', 'Madrid', MADRID)])

        dentro.refresh_from_db()
        fuera.refresh_from_db()
        self.assertEqual(dentro.municipio_geo.codigo, '28079')
        self.assertIsNone(fuera.municipio_geo)

    def test_avisa_de_estaciones_lejos_del_municipio_de_su_codigo(self):
        # El código 28065xxx dice Getafe, pero las coordenadas caen en Madrid, a unos 17 km de Getafe.
        crear_estacion(28065001, 'GETAFE', -3.7, 40.45)

        salida = self.importar([ficheros.municipio('28079', 'Madrid', MADRID),
                                ficheros.municipio('28065', 'Getafe', GETAFE)])

        self.assertEqual(Estacion.objects.get().municipio_geo.codigo, '28079')
        self.assertIn('1 estación a más de 1 km del municipio de su código', salida)
        self.assertIn('GETAFE (cae en Madrid', salida)

    def test_las_estaciones_junto_a_un_limite_no_se_consideran_errores(self):
        # A unos 200 m al norte del límite de Getafe: los límites simplificados la dejan en Madrid.
        crear_estacion(28065001, 'GETAFE', -3.7, 40.302)

        salida = self.importar([ficheros.municipio('28079', 'Madrid', MADRID),
                                ficheros.municipio('28065', 'Getafe', GETAFE)])

        self.assertNotIn('a más de 1 km', salida)
        self.assertIn('1 estación junto al límite de su municipio', salida)


class AsignarMunicipioAlMoverEstacionesTests(TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = ficheros.geojson_municipios(carpeta.name, [ficheros.municipio('28079', 'Madrid', MADRID),
                                                          ficheros.municipio('28065', 'Getafe', GETAFE)])
        call_command('importar_municipios', fichero=str(ruta), stdout=StringIO())

    def test_importar_estaciones_les_asigna_su_municipio(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        ruta = ficheros.excel_metainformacion(carpeta.name, [
            ficheros.estacion(28065001, 'GETAFE', 40.25, -3.7)])

        call_command('importar_estaciones', fichero=str(ruta), stdout=StringIO())

        self.assertEqual(Estacion.objects.get().municipio_geo.codigo, '28065')

    def test_al_corregir_la_ubicacion_cambia_de_municipio(self):
        from django.contrib.auth.models import Permission, User
        estacion = crear_estacion(28065001, 'GETAFE', -3.7, 40.45)
        editor = User.objects.create_user('editor', password='x')
        editor.user_permissions.add(Permission.objects.get(codename='change_estacion'))
        self.client.force_login(editor)

        respuesta = self.client.post(f'/api/estaciones/{estacion.pk}/ubicacion/',
                                     {'lat': 40.25, 'lng': -3.7}, content_type='application/json')

        self.assertEqual(respuesta.status_code, 200)
        estacion.refresh_from_db()
        self.assertEqual(estacion.municipio_geo.codigo, '28065')
        self.assertEqual(Point(-3.7, 40.25, srid=4326).coords, estacion.ubicacion.coords)
