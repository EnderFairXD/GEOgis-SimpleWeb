import json

from django.contrib.auth.models import Permission, User
from django.contrib.gis.geos import Point
from django.core.management import call_command
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from .models import Jugador, Puntuacion, Videojuego


class ActualizarUbicacionTests(TestCase):
    def setUp(self):
        self.jugador = Jugador.objects.create(
            alias='Nexo', nombre='Ana Pérez', ip='192.0.2.10',
            ubicacion=Point(-3.70, 40.42, srid=4326),
        )
        self.url = reverse('actualizar_ubicacion_jugador', args=[self.jugador.pk])

        self.editor = User.objects.create_user('editor', password='x')
        self.editor.user_permissions.add(Permission.objects.get(codename='change_jugador'))
        self.sin_permiso = User.objects.create_user('mirón', password='x')

    def mover(self, datos, url=None):
        cuerpo = datos if isinstance(datos, str) else json.dumps(datos)
        return self.client.post(url or self.url, cuerpo, content_type='application/json')

    def test_anonimo_no_puede_mover_jugadores(self):
        respuesta = self.mover({'lat': 48.85, 'lng': 2.35})

        self.assertEqual(respuesta.status_code, 403)
        self.jugador.refresh_from_db()
        self.assertAlmostEqual(self.jugador.ubicacion.x, -3.70)

    def test_usuario_sin_permiso_no_puede_mover_jugadores(self):
        self.client.force_login(self.sin_permiso)

        respuesta = self.mover({'lat': 48.85, 'lng': 2.35})

        self.assertEqual(respuesta.status_code, 403)
        self.jugador.refresh_from_db()
        self.assertAlmostEqual(self.jugador.ubicacion.x, -3.70)

    def test_editor_guarda_la_nueva_ubicacion(self):
        self.client.force_login(self.editor)

        respuesta = self.mover({'lat': 48.85, 'lng': 2.35})

        self.assertEqual(respuesta.status_code, 200)
        self.jugador.refresh_from_db()
        self.assertAlmostEqual(self.jugador.ubicacion.x, 2.35)  # longitud
        self.assertAlmostEqual(self.jugador.ubicacion.y, 48.85)  # latitud

    def test_coordenadas_fuera_de_rango(self):
        self.client.force_login(self.editor)

        respuesta = self.mover({'lat': 95, 'lng': 2.35})

        self.assertEqual(respuesta.status_code, 400)

    def test_json_no_valido(self):
        self.client.force_login(self.editor)

        respuesta = self.mover('esto no es json')

        self.assertEqual(respuesta.status_code, 400)

    def test_jugador_inexistente(self):
        self.client.force_login(self.editor)
        url = reverse('actualizar_ubicacion_jugador', args=[9999])

        respuesta = self.mover({'lat': 48.85, 'lng': 2.35}, url=url)

        self.assertEqual(respuesta.status_code, 404)

    def test_solo_acepta_post(self):
        self.client.force_login(self.editor)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 405)


class MapaTests(TestCase):
    def test_anonimo_no_ve_el_modo_arrastrar(self):
        respuesta = self.client.get('/')

        self.assertFalse(respuesta.context['puede_editar'])

    def test_editor_ve_el_modo_arrastrar(self):
        editor = User.objects.create_user('editor', password='x')
        editor.user_permissions.add(Permission.objects.get(codename='change_jugador'))
        self.client.force_login(editor)

        respuesta = self.client.get('/')

        self.assertTrue(respuesta.context['puede_editar'])


class ApiJugadoresTests(TestCase):
    def setUp(self):
        self.con_ubicacion = Jugador.objects.create(
            alias='ConUbicacion', nombre='A', ip='192.0.2.1', plataforma='PS5',
            ubicacion=Point(2.17, 41.39, srid=4326),
        )
        Jugador.objects.create(alias='SinUbicacion', nombre='B', ip='192.0.2.2')
        juego = Videojuego.objects.create(nombre='Tetris', tipo='Puzle')
        Puntuacion.objects.create(jugador=self.con_ubicacion, videojuego=juego, puntos=300)

    def test_devuelve_geojson_solo_con_jugadores_con_ubicacion(self):
        respuesta = self.client.get('/api/jugadores/')

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertEqual(datos['type'], 'FeatureCollection')
        self.assertEqual([f['properties']['alias'] for f in datos['features']], ['ConUbicacion'])

    def test_cada_jugador_lleva_su_posicion_y_su_ficha(self):
        feature = self.client.get('/api/jugadores/').json()['features'][0]

        self.assertEqual(feature['geometry'], {'type': 'Point', 'coordinates': [2.17, 41.39]})
        self.assertEqual(feature['properties'], {
            'id': self.con_ubicacion.pk,
            'alias': 'ConUbicacion',
            'nombre': 'A',
            'plataforma': 'PS5',
            'historial_juegos': [{'titulo': 'Tetris', 'puntos': 300}],
        })

    def test_no_expone_la_ip(self):
        respuesta = self.client.get('/api/jugadores/')

        self.assertNotContains(respuesta, '192.0.2.1')


class JugadoresCercanosTests(TestCase):
    def setUp(self):
        crear = lambda alias, lng, lat: Jugador.objects.create(
            alias=alias, nombre=alias, ip='192.0.2.1', ubicacion=Point(lng, lat, srid=4326))
        self.madrid = crear('Madrid', -3.7038, 40.4168)
        crear('Barcelona', 2.1734, 41.3851)  # ~505 km
        crear('Valencia', -0.3763, 39.4699)  # ~302 km
        crear('Berlin', 13.4050, 52.5200)    # ~1870 km
        Jugador.objects.create(alias='SinUbicacion', nombre='X', ip='192.0.2.1')

    def cercanos(self, jugador, **params):
        return self.client.get(f'/api/jugadores/{jugador.pk}/cercanos/', params)

    def test_devuelve_los_jugadores_dentro_del_radio_ordenados_por_distancia(self):
        respuesta = self.cercanos(self.madrid, km=1000)

        self.assertEqual(respuesta.status_code, 200)
        cercanos = respuesta.json()['cercanos']
        self.assertEqual([c['alias'] for c in cercanos], ['Valencia', 'Barcelona'])
        self.assertAlmostEqual(cercanos[0]['distancia_km'], 302, delta=5)
        self.assertAlmostEqual(cercanos[1]['distancia_km'], 505, delta=5)

    def test_un_radio_mayor_incluye_jugadores_mas_lejanos(self):
        cercanos = self.cercanos(self.madrid, km=2000).json()['cercanos']

        self.assertEqual([c['alias'] for c in cercanos], ['Valencia', 'Barcelona', 'Berlin'])

    def test_radio_por_defecto_de_500_km(self):
        datos = self.cercanos(self.madrid).json()

        self.assertEqual(datos['radio_km'], 500)
        self.assertEqual([c['alias'] for c in datos['cercanos']], ['Valencia'])

    def test_radio_no_valido(self):
        for km in ['abc', '0', '-5', '50000']:
            with self.subTest(km=km):
                self.assertEqual(self.cercanos(self.madrid, km=km).status_code, 400)

    def test_jugador_inexistente(self):
        respuesta = self.client.get('/api/jugadores/9999/cercanos/')

        self.assertEqual(respuesta.status_code, 404)

    def test_jugador_sin_ubicacion(self):
        sin_ubicacion = Jugador.objects.get(alias='SinUbicacion')

        self.assertEqual(self.cercanos(sin_ubicacion).status_code, 400)


class CargarDemoTests(TestCase):
    def test_crea_jugadores_con_ubicacion_y_puntuaciones(self):
        call_command('cargar_demo', verbosity=0)

        self.assertGreaterEqual(Jugador.objects.count(), 10)
        self.assertFalse(Jugador.objects.filter(ubicacion__isnull=True).exists())
        self.assertGreater(Videojuego.objects.count(), 0)
        self.assertGreater(Puntuacion.objects.count(), 0)

    def test_ejecutarlo_dos_veces_no_duplica_datos(self):
        call_command('cargar_demo', verbosity=0)
        totales = (Jugador.objects.count(), Videojuego.objects.count(), Puntuacion.objects.count())

        call_command('cargar_demo', verbosity=0)

        self.assertEqual(
            (Jugador.objects.count(), Videojuego.objects.count(), Puntuacion.objects.count()),
            totales,
        )


class PuntuacionTests(TestCase):
    def test_no_se_repite_el_mismo_juego_para_un_jugador(self):
        jugador = Jugador.objects.create(alias='Nexo', nombre='A', ip='192.0.2.1')
        juego = Videojuego.objects.create(nombre='Tetris', tipo='Puzle')
        Puntuacion.objects.create(jugador=jugador, videojuego=juego, puntos=10)

        with self.assertRaises(IntegrityError):
            Puntuacion.objects.create(jugador=jugador, videojuego=juego, puntos=20)


class AdminJugadorTests(TestCase):
    def setUp(self):
        admin = User.objects.create_superuser('admin', password='x')
        self.client.force_login(admin)
        self.juegos = [Videojuego.objects.create(nombre=f'Juego {i}', tipo='T') for i in range(3)]

    def crear_jugadores(self, cuantos):
        for i in range(cuantos):
            jugador = Jugador.objects.create(alias=f'J{Jugador.objects.count()}', nombre='N', ip='192.0.2.1')
            for juego in self.juegos[:2]:
                Puntuacion.objects.create(jugador=jugador, videojuego=juego)

    def consultas_del_listado(self):
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get('/admin/main/jugador/')
        self.assertEqual(respuesta.status_code, 200)
        return len(consultas)

    def test_el_listado_no_hace_una_consulta_por_jugador(self):
        self.crear_jugadores(2)
        con_dos = self.consultas_del_listado()

        self.crear_jugadores(6)

        self.assertEqual(self.consultas_del_listado(), con_dos)

    def test_el_listado_muestra_cuantos_juegos_tiene_cada_jugador(self):
        self.crear_jugadores(1)

        respuesta = self.client.get('/admin/main/jugador/')

        self.assertContains(respuesta, '<td class="field-total_juegos">2</td>', html=True)
