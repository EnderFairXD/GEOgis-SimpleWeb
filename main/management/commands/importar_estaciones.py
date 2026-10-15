import tempfile

from django.core.management.base import BaseCommand

from main.importacion import URL_METAINFORMACION, descargar, importar_estaciones


class Command(BaseCommand):
    help = ('Importa las estaciones de calidad del aire de España y el catálogo de contaminantes '
            'desde la metainformación oficial del MITECO. Se puede ejecutar varias veces.')

    def add_arguments(self, parser):
        parser.add_argument('--fichero', help='Excel de metainformación ya descargado (si no, se descarga)')

    def handle(self, *args, **options):
        with tempfile.TemporaryDirectory(prefix='miteco_') as carpeta:
            ruta = options['fichero']
            if not ruta:
                self.stdout.write(f'Descargando {URL_METAINFORMACION}')
                ruta = descargar(URL_METAINFORMACION, carpeta)
            contaminantes, estaciones = importar_estaciones(ruta)

        self.stdout.write(self.style.SUCCESS(
            f'Importados {contaminantes} contaminantes y {estaciones} estaciones.'))
