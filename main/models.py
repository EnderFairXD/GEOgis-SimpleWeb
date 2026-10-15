import calendar

from django.contrib.gis.db import models


class Contaminante(models.Model):
    """Magnitud medida por las redes de calidad del aire (catálogo del MITECO)."""
    codigo = models.PositiveSmallIntegerField(unique=True, help_text='Código de magnitud del MITECO')
    abreviatura = models.CharField(max_length=10)
    nombre = models.CharField(max_length=100)
    unidad = models.CharField(max_length=10)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Contaminante'
        verbose_name_plural = 'Contaminantes'

    def __str__(self):
        return self.abreviatura


class Estacion(models.Model):
    class Tipo(models.TextChoices):
        FONDO = 'FONDO', 'Fondo'
        INDUSTRIAL = 'INDUSTRIAL', 'Industrial'
        TRAFICO = 'TRAFICO', 'Tráfico'

    class Area(models.TextChoices):
        URBANA = 'URBANA', 'Urbana'
        SUBURBANA = 'SUBURBANA', 'Suburbana'
        RURAL = 'RURAL', 'Rural'

    codigo = models.PositiveIntegerField(unique=True, help_text='Código local: provincia, municipio y estación')
    codigo_europeo = models.CharField(max_length=10, unique=True, help_text='Código EoI de la Agencia Europea')
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=200, blank=True)
    municipio = models.CharField(max_length=100)
    provincia = models.CharField(max_length=50)
    comunidad = models.CharField(max_length=50)
    red = models.CharField(max_length=100)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    area = models.CharField(max_length=10, choices=Area.choices)
    altitud = models.IntegerField(help_text='Metros sobre el nivel del mar')
    fecha_alta = models.DateField()
    fecha_baja = models.DateField(null=True, blank=True)
    # Geografía WGS84: PostGIS mide las distancias sobre el elipsoide, exactas en toda España.
    ubicacion = models.PointField(geography=True, srid=4326)
    ubicacion_corregida = models.BooleanField(
        default=False, help_text='Corregida a mano: al volver a importar no se sustituye por la del MITECO')
    contaminantes = models.ManyToManyField(Contaminante, related_name='estaciones', blank=True)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Estación'
        verbose_name_plural = 'Estaciones'

    def __str__(self):
        return f'{self.nombre} ({self.municipio})'


class MedicionMensual(models.Model):
    """Media mensual de un contaminante en una estación, calculada al importar."""

    class Periodicidad(models.TextChoices):
        HORARIA = 'HORARIA', 'Horaria'  # analizadores automáticos: un valor por hora
        DIARIA = 'DIARIA', 'Diaria'     # captadores: un valor por día muestreado

    # Una media horaria con menos de este porcentaje de horas válidas se considera poco fiable.
    COBERTURA_MINIMA = 0.75

    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name='mediciones')
    contaminante = models.ForeignKey(Contaminante, on_delete=models.CASCADE, related_name='mediciones')
    anno = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    media = models.FloatField()
    num_datos = models.PositiveIntegerField(help_text='Valores válidos con los que se calculó la media')
    periodicidad = models.CharField(max_length=7, choices=Periodicidad.choices, default=Periodicidad.HORARIA,
                                    help_text='Si la media sale de los datos horarios o de los diarios')

    class Meta:
        ordering = ['estacion', 'contaminante', 'anno', 'mes']
        constraints = [
            models.UniqueConstraint(fields=['estacion', 'contaminante', 'anno', 'mes'],
                                    name='medicion_unica_por_mes'),
        ]
        verbose_name = 'Medición mensual'
        verbose_name_plural = 'Mediciones mensuales'

    def __str__(self):
        return f'{self.estacion} · {self.contaminante} {self.mes:02d}/{self.anno}: {self.media:.1f}'

    @property
    def cobertura(self):
        """Parte del mes con datos válidos (de 0 a 1): horas o días, según la periodicidad."""
        dias = calendar.monthrange(self.anno, self.mes)[1]
        posibles = dias * 24 if self.periodicidad == self.Periodicidad.HORARIA else dias
        return self.num_datos / posibles

    @property
    def pocos_datos(self):
        """Solo se aplica a las medias horarias: los captadores diarios de metales o benzo(a)pireno
        muestrean unos pocos días al mes por diseño."""
        return self.periodicidad == self.Periodicidad.HORARIA and self.cobertura < self.COBERTURA_MINIMA
