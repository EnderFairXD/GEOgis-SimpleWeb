import datetime
from unittest import mock

from django.contrib.gis.geos import MultiPolygon, Point, Polygon
from django.test import TestCase
from django.urls import reverse

from main.cobertura import distancias_a_la_estacion_mas_cercana
from main.models import Municipio

from . import ficheros
from .test_api import crear_estacion


def crear_municipio(codigo, nombre, oeste, sur, este, norte, poblacion):
    poligono = MultiPolygon(Polygon(ficheros.rectangulo(oeste, sur, este, norte)), srid=4326)
    return Municipio.objects.create(
        codigo=codigo, nombre=nombre, provincia_codigo=codigo[:2], poblacion=poblacion, area_km2=1,
        geometria=poligono, geometria_mapa=poligono,
    )


class CoberturaTestCase(TestCase):
    """Tres municipios en una fila de oeste a este y una estación en el centro del primero.

    A 40,4° de latitud, 0,1° de longitud son unos 8,5 km. Los términos municipales quedan a 0
    (la estación está dentro), ~12,7 y ~80,5 km de la estación.
    """

    def setUp(self):
        self.cerca = crear_municipio('28001', 'Cerca', -3.75, 40.35, -3.65, 40.45, poblacion=1000)
        self.medio = crear_municipio('28002', 'Medio', -3.55, 40.35, -3.45, 40.45, poblacion=300)
        self.lejos = crear_municipio('45001', 'Lejos', -2.75, 40.35, -2.65, 40.45, poblacion=700)
        crear_estacion(28001001, 'ESTACION', -3.70, 40.40, codigo_europeo='ES0001A')
        # Una estación cerrada dentro del municipio lejano no cuenta
        crear_estacion(45001001, 'CERRADA', -2.70, 40.40, codigo_europeo='ES0002A',
                       fecha_baja=datetime.date(2020, 1, 1))


class DistanciasTests(CoberturaTestCase):
    def test_distancia_desde_cada_termino_municipal_a_la_estacion_activa_mas_cercana(self):
        distancias = distancias_a_la_estacion_mas_cercana()

        self.assertEqual(distancias[self.cerca.pk], 0)  # la estación está dentro
        self.assertAlmostEqual(distancias[self.medio.pk], 12.7, delta=0.2)
        self.assertAlmostEqual(distancias[self.lejos.pk], 80.5, delta=0.5)

    def test_solo_de_los_municipios_pedidos(self):
        distancias = distancias_a_la_estacion_mas_cercana([self.medio.pk])

        self.assertEqual(list(distancias), [self.medio.pk])


class ApiCoberturaTests(CoberturaTestCase):
    def cobertura(self, **params):
        return self.client.get(reverse('cobertura'), params)

    def test_poblacion_y_municipios_a_menos_del_radio(self):
        datos = self.cobertura(km=25).json()

        self.assertEqual(datos['radio_km'], 25)
        self.assertEqual(datos['municipios'], {'total': 3, 'cubiertos': 2})
        self.assertEqual(datos['poblacion'], {'total': 2000, 'cubierta': 1300, 'porcentaje': 65.0})

    def test_resumen_por_provincias_de_la_peor_a_la_mejor(self):
        provincias = self.cobertura(km=25).json()['provincias']

        self.assertEqual(provincias, [
            {'codigo': '45', 'nombre': 'Toledo', 'poblacion': 700, 'cubierta': 0, 'porcentaje': 0.0},
            {'codigo': '28', 'nombre': 'Madrid', 'poblacion': 1300, 'cubierta': 1300, 'porcentaje': 100.0},
        ])

    def test_radio_por_defecto_de_10_km(self):
        datos = self.cobertura().json()

        self.assertEqual(datos['radio_km'], 10)
        self.assertEqual(datos['poblacion']['cubierta'], 1000)

    def test_radio_no_valido(self):
        for km in ['abc', '0', '1001']:
            with self.subTest(km=km):
                self.assertEqual(self.cobertura(km=km).status_code, 400)


class ApiMunicipiosTests(CoberturaTestCase):
    def municipios(self, bbox):
        return self.client.get(reverse('municipios_geojson'), {'bbox': bbox})

    def test_municipios_de_la_zona_visible_con_su_distancia(self):
        datos = self.municipios('-3.8,40.3,-3.4,40.5').json()

        self.assertEqual(datos['type'], 'FeatureCollection')
        propiedades = {f['properties']['nombre']: f['properties'] for f in datos['features']}
        self.assertEqual(set(propiedades), {'Cerca', 'Medio'})
        self.assertEqual(propiedades['Medio']['codigo'], '28002')
        self.assertEqual(propiedades['Medio']['poblacion'], 300)
        self.assertAlmostEqual(propiedades['Medio']['distancia_km'], 12.7, delta=0.2)
        self.assertEqual(datos['features'][0]['geometry']['type'], 'MultiPolygon')

    def test_bbox_no_valido(self):
        for bbox in ['', 'a,b,c,d', '1,2,3', '-3,41,-4,40']:
            with self.subTest(bbox=bbox):
                self.assertEqual(self.municipios(bbox).status_code, 400)

    def test_pide_acercar_el_zoom_si_la_zona_tiene_demasiados_municipios(self):
        with mock.patch('main.views.MAXIMO_MUNICIPIOS', 1):
            respuesta = self.municipios('-3.8,40.3,-3.4,40.5')

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn('zoom', respuesta.json()['msg'])


class FichaConMunicipioTests(TestCase):
    def test_la_ficha_dice_en_que_municipio_cae_la_estacion(self):
        madrid = crear_municipio('28079', 'Madrid', -3.9, 40.3, -3.5, 40.6, poblacion=1)
        estacion = crear_estacion(28079008, 'ESCUELAS AGUIRRE', -3.68, 40.42)

        datos = self.client.get(reverse('detalle_estacion', args=[estacion.pk])).json()

        self.assertEqual(datos['municipio_geo'], {
            'codigo': '28079', 'nombre': 'Madrid', 'coincide': True,
            'distancia_al_declarado_km': 0, 'posible_error': False,
        })
        self.assertEqual(Point(-3.68, 40.42).coords, estacion.ubicacion.coords)
        self.assertEqual(madrid.codigo, estacion.municipio_geo.codigo)

    def test_la_ficha_avisa_si_las_coordenadas_quedan_lejos_del_municipio_declarado(self):
        crear_municipio('28079', 'Madrid', -3.9, 40.3, -3.5, 40.6, poblacion=1)
        crear_municipio('28065', 'Getafe', -3.8, 40.2, -3.6, 40.3, poblacion=1)
        estacion = crear_estacion(28065001, 'GETAFE', -3.7, 40.45)

        municipio = self.client.get(reverse('detalle_estacion', args=[estacion.pk])).json()['municipio_geo']

        self.assertEqual((municipio['nombre'], municipio['coincide'], municipio['posible_error']),
                         ('Madrid', False, True))
        self.assertAlmostEqual(municipio['distancia_al_declarado_km'], 16.7, delta=0.2)
