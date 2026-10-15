from django.test import SimpleTestCase

from main.models import MedicionMensual


def medicion(periodicidad, mes, num_datos):
    return MedicionMensual(periodicidad=periodicidad, anno=2024, mes=mes, media=10, num_datos=num_datos)


class CoberturaTests(SimpleTestCase):
    """Parte del mes con datos válidos: horas para las medias horarias y días para las diarias."""

    def test_cobertura_de_una_media_horaria(self):
        self.assertEqual(medicion('HORARIA', 1, 558).cobertura, 0.75)  # enero: 744 horas

    def test_tiene_en_cuenta_los_annos_bisiestos(self):
        self.assertEqual(medicion('HORARIA', 2, 696).cobertura, 1)  # febrero de 2024: 29 días

    def test_cobertura_de_una_media_diaria(self):
        self.assertEqual(medicion('DIARIA', 4, 6).cobertura, 0.2)  # abril: 30 días


class PocosDatosTests(SimpleTestCase):
    def test_media_horaria_con_menos_del_75_por_ciento_de_las_horas(self):
        self.assertTrue(medicion('HORARIA', 1, 557).pocos_datos)
        self.assertFalse(medicion('HORARIA', 1, 558).pocos_datos)

    def test_las_medias_diarias_no_se_marcan(self):
        # Metales y benzo(a)pireno se muestrean unos pocos días al mes por diseño.
        self.assertFalse(medicion('DIARIA', 4, 6).pocos_datos)
