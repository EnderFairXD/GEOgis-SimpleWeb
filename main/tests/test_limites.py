import datetime

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from main.limites import LIMITES_ANUALES, SIN_LIMITE_ANUAL, media_anual
from main.models import Contaminante, Estacion, MedicionMensual

from .test_api import crear_estacion

NO2, SO2, O3, ARSENICO = 8, 1, 14, 17


def medicion(mes, media, num_datos, periodicidad='HORARIA', anno=2024):
    return MedicionMensual(anno=anno, mes=mes, media=media, num_datos=num_datos, periodicidad=periodicidad)


class LimitesAnualesTests(SimpleTestCase):
    def test_no2_tiene_el_limite_actual_y_el_de_2030(self):
        self.assertEqual(
            [(l.valor, l.norma, l.desde) for l in LIMITES_ANUALES[NO2]],
            [(40, 'RD 102/2011', 2010), (20, 'Directiva (UE) 2024/2881', 2030)],
        )

    def test_el_so2_solo_tiene_limite_anual_desde_2030(self):
        self.assertEqual([(l.valor, l.desde) for l in LIMITES_ANUALES[SO2]], [(20, 2030)])

    def test_los_metales_pasan_de_valor_objetivo_a_valor_limite(self):
        self.assertEqual([(l.valor, l.tipo) for l in LIMITES_ANUALES[ARSENICO]],
                         [(6, 'valor objetivo'), (6, 'valor límite')])

    def test_el_ozono_no_tiene_limite_anual(self):
        self.assertNotIn(O3, LIMITES_ANUALES)

    def test_explica_por_que_un_contaminante_no_tiene_limite_anual(self):
        self.assertIn('octohorario', SIN_LIMITE_ANUAL[O3])
        self.assertIn('no tiene límite legal', SIN_LIMITE_ANUAL[7])     # NO
        self.assertIn('vegetación', SIN_LIMITE_ANUAL[12])               # NOx
        self.assertNotIn(NO2, SIN_LIMITE_ANUAL)


class MediaAnualTests(SimpleTestCase):
    def test_media_ponderada_por_los_datos_de_cada_mes(self):
        anual = media_anual([medicion(1, 10, 100), medicion(2, 30, 300)])

        self.assertEqual((anual['anno'], anual['media'], anual['num_datos']), (2024, 25, 400))

    def test_cobertura_sobre_las_horas_del_anno_bisiesto(self):
        anual = media_anual([medicion(1, 10, 8784)])  # 366 días x 24 horas

        self.assertEqual(anual['cobertura'], 1)

    def test_valida_con_al_menos_el_90_por_ciento_de_las_horas(self):
        # RD 102/2011: la media anual necesita al menos el 90 % de los valores horarios.
        self.assertTrue(media_anual([medicion(1, 10, 7906)])['valida'])   # 90,0 % de 8784
        self.assertFalse(media_anual([medicion(1, 10, 7905)])['valida'])

    def test_las_medias_diarias_son_orientativas_con_al_menos_el_14_por_ciento_de_los_dias(self):
        # Mediciones indicativas: periodicidad mínima del 14 % (52 de 366 días).
        anual = media_anual([medicion(1, 10, 52, periodicidad='DIARIA')])

        self.assertTrue(anual['valida'])
        self.assertTrue(anual['orientativa'])
        self.assertFalse(media_anual([medicion(1, 10, 51, periodicidad='DIARIA')])['valida'])

    def test_sin_mediciones_no_hay_media(self):
        self.assertIsNone(media_anual([]))


class ApiLimitesTestCase(TestCase):
    def setUp(self):
        self.no2 = Contaminante.objects.create(codigo=8, abreviatura='NO2', nombre='DIÓXIDO DE NITRÓGENO', unidad='µg/m3')
        self.so2 = Contaminante.objects.create(codigo=1, abreviatura='SO2', nombre='DIÓXIDO DE AZUFRE', unidad='µg/m3')
        self.o3 = Contaminante.objects.create(codigo=14, abreviatura='O3', nombre='OZONO', unidad='µg/m3')

    def estacion_con_no2(self, codigo, media, horas_por_mes=732):
        """Estación con doce medias mensuales de NO2 iguales (732 h/mes = todo 2024)."""
        estacion = crear_estacion(codigo, f'E{codigo}', -3.7, 40.4, codigo_europeo=f'ES{codigo}')
        estacion.contaminantes.add(self.no2)
        for mes in range(1, 13):
            MedicionMensual.objects.create(estacion=estacion, contaminante=self.no2, anno=2024, mes=mes,
                                           media=media, num_datos=horas_por_mes, periodicidad='HORARIA')
        return estacion


class FichaConLimitesTests(ApiLimitesTestCase):
    def contaminante(self, estacion, abreviatura):
        datos = self.client.get(reverse('detalle_estacion', args=[estacion.pk])).json()
        return next(c for c in datos['contaminantes'] if c['abreviatura'] == abreviatura)

    def test_media_anual_comparada_con_cada_limite(self):
        no2 = self.contaminante(self.estacion_con_no2(1, media=30), 'NO2')

        self.assertEqual(no2['anual'], {'anno': 2024, 'media': 30.0, 'num_datos': 8784, 'periodicidad': 'HORARIA',
                                        'cobertura': 1.0, 'valida': True, 'orientativa': False})
        self.assertEqual(no2['limites'], [
            {'valor': 40, 'tipo': 'valor límite', 'norma': 'RD 102/2011', 'desde': 2010, 'supera': False},
            {'valor': 20, 'tipo': 'valor límite', 'norma': 'Directiva (UE) 2024/2881', 'desde': 2030, 'supera': True},
        ])

    def test_sin_media_anual_valida_no_se_dice_si_supera(self):
        no2 = self.contaminante(self.estacion_con_no2(1, media=50, horas_por_mes=100), 'NO2')

        self.assertFalse(no2['anual']['valida'])
        self.assertEqual([l['supera'] for l in no2['limites']], [None, None])

    def test_contaminante_sin_mediciones_ni_limite(self):
        estacion = self.estacion_con_no2(1, media=30)
        estacion.contaminantes.add(self.so2, self.o3)

        so2, o3 = self.contaminante(estacion, 'SO2'), self.contaminante(estacion, 'O3')

        self.assertIsNone(so2['anual'])
        self.assertEqual([(l['valor'], l['supera']) for l in so2['limites']], [(20, None)])
        self.assertIsNone(so2['sin_limite_anual'])
        self.assertEqual(o3['limites'], [])
        self.assertIn('octohorario', o3['sin_limite_anual'])

    def test_las_medias_pequennas_conservan_tres_decimales(self):
        estacion = self.estacion_con_no2(1, media=30)
        cadmio = Contaminante.objects.create(codigo=28, abreviatura='Cd', nombre='CADMIO', unidad='ng/m3')
        estacion.contaminantes.add(cadmio)
        MedicionMensual.objects.create(estacion=estacion, contaminante=cadmio, anno=2024, mes=1,
                                       media=0.04321, num_datos=60, periodicidad='DIARIA')

        cd = self.contaminante(estacion, 'Cd')

        self.assertEqual(cd['mediciones'][0]['media'], 0.043)
        self.assertEqual(cd['anual']['media'], 0.043)


class ResumenLimitesTests(ApiLimitesTestCase):
    def test_estaciones_que_superan_cada_limite_anual(self):
        self.estacion_con_no2(1, media=30)
        self.estacion_con_no2(2, media=45)
        self.estacion_con_no2(3, media=50, horas_por_mes=100)  # sin media anual válida: no cuenta

        datos = self.client.get(reverse('resumen_limites')).json()

        self.assertEqual(datos['anno'], 2024)
        self.assertEqual(datos['contaminantes'], [{
            'codigo': 8, 'abreviatura': 'NO2', 'nombre': 'DIÓXIDO DE NITRÓGENO', 'unidad': 'µg/m3',
            'estaciones_evaluadas': 2,
            'limites': [
                {'valor': 40, 'tipo': 'valor límite', 'norma': 'RD 102/2011', 'desde': 2010, 'estaciones_que_superan': 1},
                {'valor': 20, 'tipo': 'valor límite', 'norma': 'Directiva (UE) 2024/2881', 'desde': 2030,
                 'estaciones_que_superan': 2},
            ],
        }])

    def test_no_incluye_estaciones_cerradas(self):
        self.estacion_con_no2(1, media=45)
        cerrada = self.estacion_con_no2(2, media=45)
        Estacion.objects.filter(pk=cerrada.pk).update(fecha_baja=datetime.date(2024, 12, 31))

        datos = self.client.get(reverse('resumen_limites')).json()

        self.assertEqual(datos['contaminantes'][0]['estaciones_evaluadas'], 1)

    def test_anno_sin_datos(self):
        respuesta = self.client.get(reverse('resumen_limites'), {'anno': 1999})

        self.assertEqual(respuesta.json(), {'anno': 1999, 'contaminantes': []})
