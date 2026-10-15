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
    contaminantes = models.ManyToManyField(Contaminante, related_name='estaciones', blank=True)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Estación'
        verbose_name_plural = 'Estaciones'

    def __str__(self):
        return f'{self.nombre} ({self.municipio})'


class MedicionMensual(models.Model):
    """Media mensual de un contaminante en una estación, calculada al importar."""
    estacion = models.ForeignKey(Estacion, on_delete=models.CASCADE, related_name='mediciones')
    contaminante = models.ForeignKey(Contaminante, on_delete=models.CASCADE, related_name='mediciones')
    anno = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    media = models.FloatField()
    num_datos = models.PositiveIntegerField(help_text='Valores válidos con los que se calculó la media')

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
