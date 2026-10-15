from django.contrib.gis.geos import Point
from django.test import SimpleTestCase

from main.geo import coordenadas_utm, sistema_utm


class SistemaUtmTests(SimpleTestCase):
    """Cada punto de España se proyecta en el huso UTM que le corresponde."""

    def test_huso_segun_la_zona(self):
        casos = {
            'A Coruña': ((-8.4115, 43.3623), (25829, 29)),
            'Madrid': ((-3.7038, 40.4168), (25830, 30)),
            'Ceuta': ((-5.3162, 35.8894), (25830, 30)),
            'Barcelona': ((2.1734, 41.3851), (25831, 31)),
            'Palma': ((2.6502, 39.5696), (25831, 31)),
            # Canarias usa su propio datum (REGCAN95), en el huso 28
            'Las Palmas': ((-15.4134, 28.1235), (4083, 28)),
        }
        for lugar, ((lng, lat), esperado) in casos.items():
            with self.subTest(lugar=lugar):
                self.assertEqual(sistema_utm(lng, lat), esperado)


class CoordenadasUtmTests(SimpleTestCase):
    def test_coinciden_con_las_oficiales_del_ayuntamiento_de_madrid(self):
        # Plaza de España: el Ayuntamiento publica X 439579,3291 / Y 4475049,263 en ETRS89 UTM 30N
        utm = coordenadas_utm(Point(-3.7122567, 40.4238823, srid=4326))

        self.assertEqual((utm['epsg'], utm['huso']), (25830, 30))
        self.assertAlmostEqual(utm['x'], 439579.33, delta=1)
        self.assertAlmostEqual(utm['y'], 4475049.26, delta=1)

    def test_no_modifica_el_punto_original(self):
        punto = Point(2.1734, 41.3851, srid=4326)

        coordenadas_utm(punto)

        self.assertEqual((punto.srid, punto.x, punto.y), (4326, 2.1734, 41.3851))
