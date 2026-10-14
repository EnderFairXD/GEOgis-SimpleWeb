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
    def setUp(self):
        Jugador.objects.create(alias='ConUbicacion', nombre='A', ip='192.0.2.1',
                               ubicacion=Point(2.17, 41.39, srid=4326))
        Jugador.objects.create(alias='SinUbicacion', nombre='B', ip='192.0.2.2')

    def test_solo_muestra_jugadores_con_ubicacion(self):
        respuesta = self.client.get('/')

        aliases = [f['properties']['alias']
                   for f in respuesta.context['datos_jugadores']['features']]
        self.assertEqual(aliases, ['ConUbicacion'])

    def test_anonimo_no_ve_el_modo_arrastrar(self):
        respuesta = self.client.get('/')

        self.assertFalse(respuesta.context['puede_editar'])

    def test_editor_ve_el_modo_arrastrar(self):
        editor = User.objects.create_user('editor', password='x')
        editor.user_permissions.add(Permission.objects.get(codename='change_jugador'))
        self.client.force_login(editor)

        respuesta = self.client.get('/')

        self.assertTrue(respuesta.context['puede_editar'])


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
