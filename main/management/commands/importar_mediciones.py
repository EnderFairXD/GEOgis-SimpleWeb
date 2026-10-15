import tempfile

from django.core.management.base import BaseCommand, CommandError

from main.importacion import URLS_MEDICIONES, descargar, importar_mediciones


class Command(BaseCommand):
    help = ('Calcula las medias mensuales de los datos oficiales del MITECO (horarios y diarios) '
            'y las guarda. Requiere haber importado antes las estaciones.')

    def add_arguments(self, parser):
        parser.add_argument('--anno', type=int, default=2024, help='Año que se descarga (por defecto 2024)')
        parser.add_argument('--horario', help='ZIP de datos horarios ya descargado')
        parser.add_argument('--diario', help='ZIP de datos diarios ya descargado')

    def descargar(self, url, carpeta):
        self.stdout.write(f'Descargando {url}')
        return descargar(url, carpeta)

    def handle(self, *args, **options):
        with tempfile.TemporaryDirectory(prefix='miteco_') as carpeta:
            horario, diario = options['horario'], options['diario']
            if not (horario and diario):
                if options['anno'] not in URLS_MEDICIONES:
                    raise CommandError(f'No conozco la dirección de los datos de {options["anno"]}: '
                                       'indica los ficheros con --horario y --diario.')
                url_horario, url_diario = URLS_MEDICIONES[options['anno']]
                horario = horario or self.descargar(url_horario, carpeta)
                diario = diario or self.descargar(url_diario, carpeta)
            resultado = importar_mediciones(horario, diario)

        self.stdout.write(self.style.SUCCESS(
            f'Guardadas {resultado["mediciones"]} medias mensuales de {resultado["estaciones"]} estaciones.'))
        for clave, singular, plural in [
            ('estaciones_desconocidas', 'estación desconocida', 'estaciones desconocidas'),
            ('magnitudes_desconocidas', 'magnitud desconocida', 'magnitudes desconocidas'),
        ]:
            if resultado[clave]:
                texto = singular if resultado[clave] == 1 else plural
                self.stdout.write(self.style.WARNING(f'Ignorados los datos de {resultado[clave]} {texto}.'))
