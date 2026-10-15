import tempfile

from django.core.management.base import BaseCommand

from main.importacion import URL_MUNICIPIOS, descargar, importar_municipios
from main.models import Estacion


class Command(BaseCommand):
    help = ('Importa los municipios de España (límites y población 2023 de Eurostat GISCO) y asigna '
            'a cada estación el municipio que la contiene. Se puede ejecutar varias veces.')

    def add_arguments(self, parser):
        parser.add_argument('--fichero', help='Fichero LAU (GeoPackage o GeoJSON) ya descargado')

    def handle(self, *args, **options):
        with tempfile.TemporaryDirectory(prefix='gisco_') as carpeta:
            ruta = options['fichero']
            if not ruta:
                self.stdout.write(f'Descargando {URL_MUNICIPIOS}')
                ruta = descargar(URL_MUNICIPIOS, carpeta)
            resultado = importar_municipios(ruta)

        self.stdout.write(self.style.SUCCESS(f'Importados {resultado["municipios"]} municipios.'))

        n = resultado['junto_al_limite']
        if n:
            texto = '1 estación' if n == 1 else f'{n} estaciones'
            self.stdout.write(f'Hay {texto} junto al límite de su municipio: los límites simplificados '
                              'la dejan en el municipio vecino o en el mar. No es un error.')

        errores = resultado['posibles_errores']
        if errores:
            texto = '1 estación' if len(errores) == 1 else f'{len(errores)} estaciones'
            self.stdout.write(self.style.WARNING(
                f'Hay {texto} a más de {Estacion.TOLERANCIA_LIMITE_KM} km del municipio de su código '
                '(posible error en los datos del MITECO):'))
            for estacion, km in errores:
                donde = estacion.municipio_geo.nombre if estacion.municipio_geo else 'ningún municipio'
                distancia = f'{km:.1f}'.replace('.', ',')
                self.stdout.write(f'  - {estacion.nombre} (cae en {donde}, a {distancia} km de {estacion.municipio})')
