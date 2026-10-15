from django.urls import reverse

from .test_cobertura import CoberturaTestCase


class SimulacionTests(CoberturaTestCase):
    """Con la estación real en Cerca, la población cubierta a 10 km es 1000 de 2000 (50 %)."""

    def simular(self, **params):
        return self.client.get(reverse('simular_estacion'), params)

    def test_en_que_municipio_cae_y_sus_coordenadas_utm(self):
        datos = self.simular(lat=40.40, lng=-2.70).json()

        self.assertEqual(datos['municipio'], {'codigo': '45001', 'nombre': 'Lejos', 'provincia': 'Toledo'})
        self.assertEqual(datos['ubicacion']['utm']['epsg'], 25830)

    def test_estaciones_reales_mas_cercanas(self):
        cercanas = self.simular(lat=40.40, lng=-3.60).json()['cercanas']

        # La estación cerrada de Lejos no cuenta
        self.assertEqual([c['nombre'] for c in cercanas], ['ESTACION'])
        self.assertAlmostEqual(cercanas[0]['distancia_km'], 8.5, delta=0.2)

    def test_poblacion_que_quedaria_cubierta(self):
        datos = self.simular(lat=40.40, lng=-2.70, km=10).json()

        self.assertEqual(datos['cobertura'], {
            'radio_km': 10, 'poblacion_nueva': 700, 'porcentaje_antes': 50.0, 'porcentaje_despues': 85.0,
        })
        nuevos = datos['municipios_nuevos']
        self.assertEqual(nuevos['type'], 'FeatureCollection')
        self.assertEqual([f['properties']['nombre'] for f in nuevos['features']], ['Lejos'])
        self.assertAlmostEqual(nuevos['features'][0]['properties']['distancia_actual_km'], 80.5, delta=0.5)

    def test_porcentajes_con_dos_decimales_para_que_se_vean_los_cambios_pequennos(self):
        # Con un decimal, sumar unos pocos habitantes a una población grande no cambiaría el porcentaje.
        self.medio.poblacion = 3
        self.medio.save()
        self.lejos.poblacion = 8997  # en total, 10.000 habitantes; Cerca (1000) ya está cubierto
        self.lejos.save()

        cobertura = self.simular(lat=40.40, lng=-3.50, km=10).json()['cobertura']

        self.assertEqual((cobertura['porcentaje_antes'], cobertura['porcentaje_despues']), (10.0, 10.03))

    def test_junto_a_una_estacion_real_no_cubre_a_nadie_mas(self):
        datos = self.simular(lat=40.40, lng=-3.70, km=10).json()

        self.assertEqual(datos['cobertura']['poblacion_nueva'], 0)
        self.assertEqual(datos['municipios_nuevos']['features'], [])

    def test_un_radio_mayor_alcanza_mas_municipios(self):
        # Lejos queda a ~38 km del punto y pasa a estar cubierto; Medio ya lo estaba (12,7 km)
        datos = self.simular(lat=40.40, lng=-3.20, km=50).json()

        self.assertEqual([f['properties']['nombre'] for f in datos['municipios_nuevos']['features']], ['Lejos'])

    def test_en_el_mar_no_cae_en_ningun_municipio(self):
        self.assertIsNone(self.simular(lat=36.5, lng=-1.0).json()['municipio'])

    def test_datos_no_validos(self):
        for params in [{}, {'lat': 'a', 'lng': '1'}, {'lat': 41.9, 'lng': 12.5},
                       {'lat': 40.4, 'lng': -3.7, 'km': '0'}, {'lat': 40.4, 'lng': -3.7, 'km': 'x'}]:
            with self.subTest(params=params):
                self.assertEqual(self.simular(**params).status_code, 400)
