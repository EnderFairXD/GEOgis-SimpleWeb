import calendar

from django.contrib.gis.db import models
from django.db import connection

from .ine import nombre_provincia


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


class Municipio(models.Model):
    """Término municipal (límites y población de Eurostat GISCO, a partir del INE)."""
    codigo = models.CharField(max_length=5, unique=True, help_text='Código INE: provincia y municipio')
    nombre = models.CharField(max_length=100)
    provincia_codigo = models.CharField(max_length=2, db_index=True)
    poblacion = models.PositiveIntegerField()
    area_km2 = models.FloatField(help_text='Calculada en la proyección de igual área ETRS89-LAEA (EPSG:3035)')
    geometria = models.MultiPolygonField(srid=4326)
    # Versión simplificada (unos 100 m) para dibujarla en el mapa sin descargar todos los vértices.
    geometria_mapa = models.MultiPolygonField(srid=4326)

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Municipio'
        verbose_name_plural = 'Municipios'

    def __str__(self):
        return f'{self.nombre} ({self.provincia})'

    @property
    def provincia(self):
        return nombre_provincia(self.provincia_codigo)


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
    # Municipio que contiene la estación según sus coordenadas (unión espacial).
    municipio_geo = models.ForeignKey(Municipio, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='estaciones', verbose_name='municipio según su ubicación')

    class Meta:
        ordering = ['codigo']
        verbose_name = 'Estación'
        verbose_name_plural = 'Estaciones'

    def __str__(self):
        return f'{self.nombre} ({self.municipio})'

    # Los límites municipales están simplificados: una estación a menos de esta distancia de su
    # municipio declarado puede caer en el vecino sin que haya ningún error en los datos.
    TOLERANCIA_LIMITE_KM = 1

    def km_al_municipio_declarado(self):
        """Distancia (sobre el elipsoide) desde la estación hasta el municipio de su código.

        0 si está dentro; None si ese municipio no está importado.
        """
        if self.municipio_geo and self.municipio_geo.codigo == self.codigo_municipio:
            return 0
        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT ST_Distance(ST_GeogFromText(%s), geometria::geography) / 1000 '
                f'FROM {Municipio._meta.db_table} WHERE codigo = %s',
                [self.ubicacion.ewkt, self.codigo_municipio],
            )
            fila = cursor.fetchone()
        return fila and fila[0]

    @property
    def codigo_municipio(self):
        """Código INE del municipio declarado por el MITECO (está dentro del código de la estación)."""
        return f'{self.codigo // 1000:05d}'

    def save(self, *args, **kwargs):
        # Cada vez que cambia la ubicación se vuelve a buscar el municipio que la contiene.
        actualizar = kwargs.get('update_fields')
        if actualizar is None or 'ubicacion' in actualizar:
            self.municipio_geo = Municipio.objects.filter(geometria__contains=self.ubicacion).first()
            if actualizar is not None:
                kwargs['update_fields'] = {*actualizar, 'municipio_geo'}
        super().save(*args, **kwargs)


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
