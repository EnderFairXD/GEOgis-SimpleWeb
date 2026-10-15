from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.contrib.gis.geos import Point
from django.db import IntegrityError, connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from main.admin import EstacionAdmin
from main.models import Contaminante, Estacion, MedicionMensual

from .test_api import crear_estacion


class AdminEstacionTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser('admin', password='x'))
        self.contaminantes = [
            Contaminante.objects.create(codigo=i, abreviatura=f'C{i}', nombre=f'C{i}', unidad='µg/m3')
            for i in range(3)
        ]

    def crear_estaciones(self, cuantas):
        for _ in range(cuantas):
            self.creadas = getattr(self, 'creadas', 0) + 1
            estacion = crear_estacion(28079000 + self.creadas, f'E{self.creadas}', -3.7, 40.4)
            estacion.contaminantes.set(self.contaminantes[:2])

    def consultas_del_listado(self):
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get('/admin/main/estacion/')
        self.assertEqual(respuesta.status_code, 200)
        return len(consultas)

    def test_el_listado_no_hace_una_consulta_por_estacion(self):
        self.crear_estaciones(2)
        con_dos = self.consultas_del_listado()

        self.crear_estaciones(6)

        self.assertEqual(self.consultas_del_listado(), con_dos)

    def test_el_listado_muestra_cuantos_contaminantes_mide_cada_estacion(self):
        self.crear_estaciones(1)

        respuesta = self.client.get('/admin/main/estacion/')

        self.assertContains(respuesta, '<td class="field-num_contaminantes">2</td>', html=True)


class MedicionMensualTests(TestCase):
    def test_no_se_repite_el_mismo_mes(self):
        estacion = crear_estacion(28079004, 'MADRID', -3.7, 40.4)
        no2 = Contaminante.objects.create(codigo=8, abreviatura='NO2', nombre='NO2', unidad='µg/m3')
        MedicionMensual.objects.create(estacion=estacion, contaminante=no2, anno=2024, mes=1, media=1, num_datos=1)

        with self.assertRaises(IntegrityError):
            MedicionMensual.objects.create(estacion=estacion, contaminante=no2, anno=2024, mes=1, media=2, num_datos=1)


class AdminUbicacionCorregidaTests(TestCase):
    """Mover una estación en el mapa del admin la marca como corregida a mano."""

    def guardar(self, estacion, campos_cambiados):
        formulario = type('Formulario', (), {'changed_data': campos_cambiados})()
        EstacionAdmin(Estacion, AdminSite()).save_model(None, estacion, formulario, change=True)
        estacion.refresh_from_db()

    def test_cambiar_la_ubicacion_la_marca_como_corregida(self):
        estacion = crear_estacion(28079004, 'MADRID', -3.7, 40.4)
        estacion.ubicacion = Point(-3.71, 40.41, srid=4326)

        self.guardar(estacion, ['ubicacion'])

        self.assertTrue(estacion.ubicacion_corregida)

    def test_cambiar_otros_campos_no_la_marca(self):
        estacion = crear_estacion(28079004, 'MADRID', -3.7, 40.4)
        estacion.nombre = 'OTRO NOMBRE'

        self.guardar(estacion, ['nombre'])

        self.assertFalse(estacion.ubicacion_corregida)
