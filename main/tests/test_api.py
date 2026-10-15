import datetime
import json

from django.contrib.auth.models import Permission, User
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.urls import reverse

from main.models import Contaminante, Estacion, MedicionMensual


def crear_estacion(codigo, nombre, lng, lat, **otros):
    datos = {
        'codigo': codigo, 'codigo_europeo': f'ES{codigo % 10000:04d}A', 'nombre': nombre,
        'municipio': nombre.title(), 'provincia': 'PROVINCIA', 'comunidad': 'COMUNIDAD', 'red': 'Red',
        'tipo': 'FONDO', 'area': 'URBANA', 'altitud': 600, 'fecha_alta': datetime.date(2000, 1, 1),
        'ubicacion': Point(lng, lat, srid=4326),
    }
    datos.update(otros)
    return Estacion.objects.create(**datos)


def crear_editor():
    editor = User.objects.create_user('editor', password='x')
    editor.user_permissions.add(Permission.objects.get(codename='change_estacion'))
    return editor


class MapaTests(TestCase):
    def test_anonimo_no_ve_el_modo_arrastrar(self):
        self.assertFalse(self.client.get('/').context['puede_editar'])

    def test_editor_ve_el_modo_arrastrar(self):
        self.client.force_login(crear_editor())

        self.assertTrue(self.client.get('/').context['puede_editar'])


class ApiEstacionesTests(TestCase):
    def setUp(self):
        self.madrid = crear_estacion(28079008, 'ESCUELAS AGUIRRE', -3.68222, 40.42167, tipo='TRAFICO')
        crear_estacion(28079099, 'CERRADA', -3.7, 40.4, fecha_baja=datetime.date(2020, 1, 1))
        no2 = Contaminante.objects.create(codigo=8, abreviatura='NO2', nombre='DIÓXIDO DE NITRÓGENO', unidad='µg/m3')
        MedicionMensual.objects.create(estacion=self.madrid, contaminante=no2, anno=2024, mes=1, media=40, num_datos=700)

    def test_geojson_con_las_estaciones_activas(self):
        respuesta = self.client.get(reverse('estaciones_geojson'))

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos['type'], 'FeatureCollection')
        self.assertEqual([f['properties']['nombre'] for f in datos['features']], ['ESCUELAS AGUIRRE'])

    def test_cada_estacion_lleva_su_posicion_y_datos_basicos(self):
        feature = self.client.get(reverse('estaciones_geojson')).json()['features'][0]

        self.assertEqual(feature['geometry'], {'type': 'Point', 'coordinates': [-3.68222, 40.42167]})
        self.assertEqual(feature['properties'], {
            'id': self.madrid.pk,
            'nombre': 'ESCUELAS AGUIRRE',
            'municipio': 'Escuelas Aguirre',
            'provincia': 'PROVINCIA',
            'tipo': 'TRAFICO',
        })

    def test_el_mapa_no_descarga_las_mediciones(self):
        respuesta = self.client.get(reverse('estaciones_geojson'))

        self.assertNotContains(respuesta, 'mediciones')


class DetalleEstacionTests(TestCase):
    def setUp(self):
        self.estacion = crear_estacion(28079004, 'PLAZA DE ESPAÑA', -3.7122567, 40.4238823,
                                       tipo='TRAFICO', area='URBANA', altitud=637)
        self.no2 = Contaminante.objects.create(codigo=8, abreviatura='NO2', nombre='DIÓXIDO DE NITRÓGENO', unidad='µg/m3')
        self.so2 = Contaminante.objects.create(codigo=1, abreviatura='SO2', nombre='DIÓXIDO DE AZUFRE', unidad='µg/m3')
        self.estacion.contaminantes.set([self.no2, self.so2])
        for mes, media, horas in [(2, 35.5, 300), (1, 40.25, 700)]:
            MedicionMensual.objects.create(estacion=self.estacion, contaminante=self.no2, periodicidad='HORARIA',
                                           anno=2024, mes=mes, media=media, num_datos=horas)

    def detalle(self, pk=None):
        return self.client.get(reverse('detalle_estacion', args=[pk or self.estacion.pk]))

    def test_datos_de_la_estacion(self):
        datos = self.detalle().json()

        self.assertEqual(datos['nombre'], 'PLAZA DE ESPAÑA')
        self.assertEqual(datos['tipo'], 'Tráfico')
        self.assertEqual(datos['area'], 'Urbana')
        self.assertEqual(datos['altitud'], 637)

    def test_coordenadas_en_grados_y_en_utm(self):
        coordenadas = self.detalle().json()['coordenadas']

        self.assertEqual(coordenadas['wgs84'], {'lat': 40.4238823, 'lng': -3.7122567})
        utm = coordenadas['utm']
        self.assertEqual((utm['epsg'], utm['huso']), (25830, 30))
        self.assertAlmostEqual(utm['x'], 439579.33, delta=1)
        self.assertAlmostEqual(utm['y'], 4475049.26, delta=1)

    def test_contaminantes_con_sus_medias_mensuales_ordenadas(self):
        contaminantes = self.detalle().json()['contaminantes']

        self.assertEqual([c['abreviatura'] for c in contaminantes], ['SO2', 'NO2'])
        no2 = contaminantes[1]
        self.assertEqual((no2['nombre'], no2['unidad']), ('DIÓXIDO DE NITRÓGENO', 'µg/m3'))
        self.assertEqual(no2['mediciones'], [
            {'anno': 2024, 'mes': 1, 'media': 40.2, 'periodicidad': 'HORARIA', 'num_datos': 700,
             'cobertura': 0.94, 'pocos_datos': False},
            {'anno': 2024, 'mes': 2, 'media': 35.5, 'periodicidad': 'HORARIA', 'num_datos': 300,
             'cobertura': 0.43, 'pocos_datos': True},
        ])
        self.assertEqual(contaminantes[0]['mediciones'], [])

    def test_estacion_inexistente(self):
        self.assertEqual(self.detalle(pk=9999).status_code, 404)


class EstacionesCercanasTests(TestCase):
    def setUp(self):
        self.madrid = crear_estacion(28079004, 'MADRID', -3.7038, 40.4168)
        crear_estacion(45168001, 'TOLEDO', -4.0273, 39.8628)       # ~67 km
        crear_estacion(46250001, 'VALENCIA', -0.3763, 39.4699)     # ~303 km
        crear_estacion(8019001, 'BARCELONA', 2.1734, 41.3851)      # ~507 km
        crear_estacion(28079099, 'CERRADA', -3.70, 40.42, fecha_baja=datetime.date(2020, 1, 1))

    def cercanas(self, **params):
        return self.client.get(reverse('estaciones_cercanas', args=[self.madrid.pk]), params)

    def test_estaciones_dentro_del_radio_ordenadas_por_distancia(self):
        cercanas = self.cercanas(km=400).json()['cercanas']

        self.assertEqual([c['nombre'] for c in cercanas], ['TOLEDO', 'VALENCIA'])

    def test_distancia_sobre_el_elipsoide(self):
        # Referencia geodésica (WGS84): 303,17 km. Sobre una esfera saldría 302,56 km.
        valencia = self.cercanas(km=400).json()['cercanas'][1]

        self.assertAlmostEqual(valencia['distancia_km'], 303.17, delta=0.1)

    def test_radio_por_defecto_de_25_km(self):
        datos = self.cercanas().json()

        self.assertEqual(datos['radio_km'], 25)
        self.assertEqual(datos['cercanas'], [])

    def test_no_incluye_estaciones_cerradas(self):
        nombres = [c['nombre'] for c in self.cercanas(km=10).json()['cercanas']]

        self.assertNotIn('CERRADA', nombres)

    def test_radio_no_valido(self):
        for km in ['abc', '0', '-5', '1001']:
            with self.subTest(km=km):
                self.assertEqual(self.cercanas(km=km).status_code, 400)

    def test_estacion_inexistente(self):
        respuesta = self.client.get(reverse('estaciones_cercanas', args=[9999]))

        self.assertEqual(respuesta.status_code, 404)


class CorregirUbicacionTests(TestCase):
    def setUp(self):
        self.estacion = crear_estacion(10151001, 'PLASENCIA', -6.14722, 40.07778)
        self.url = reverse('corregir_ubicacion', args=[self.estacion.pk])

    def mover(self, datos):
        cuerpo = datos if isinstance(datos, str) else json.dumps(datos)
        return self.client.post(self.url, cuerpo, content_type='application/json')

    def test_anonimo_no_puede_mover_estaciones(self):
        self.assertEqual(self.mover({'lat': 40.04374, 'lng': -6.08481}).status_code, 403)
        self.estacion.refresh_from_db()
        self.assertAlmostEqual(self.estacion.ubicacion.x, -6.14722)

    def test_usuario_sin_permiso_no_puede_mover_estaciones(self):
        self.client.force_login(User.objects.create_user('miron', password='x'))

        self.assertEqual(self.mover({'lat': 40.04374, 'lng': -6.08481}).status_code, 403)

    def test_editor_corrige_la_ubicacion_y_recibe_las_coordenadas_utm(self):
        self.client.force_login(crear_editor())

        respuesta = self.mover({'lat': 40.04374, 'lng': -6.08481})

        self.assertEqual(respuesta.status_code, 200)
        self.estacion.refresh_from_db()
        self.assertAlmostEqual(self.estacion.ubicacion.x, -6.08481)
        self.assertAlmostEqual(self.estacion.ubicacion.y, 40.04374)
        self.assertEqual(respuesta.json()['utm']['epsg'], 25829)
        self.assertTrue(self.estacion.ubicacion_corregida)

    def test_coordenadas_fuera_de_rango(self):
        self.client.force_login(crear_editor())

        self.assertEqual(self.mover({'lat': 95, 'lng': 0}).status_code, 400)

    def test_fuera_de_espana(self):
        self.client.force_login(crear_editor())

        self.assertEqual(self.mover({'lat': 41.9, 'lng': 12.5}).status_code, 400)  # Roma

    def test_json_no_valido(self):
        self.client.force_login(crear_editor())

        self.assertEqual(self.mover('esto no es json').status_code, 400)

    def test_solo_acepta_post(self):
        self.client.force_login(crear_editor())

        self.assertEqual(self.client.get(self.url).status_code, 405)
