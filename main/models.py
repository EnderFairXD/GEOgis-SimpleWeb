from django.contrib.gis.db import models


class Jugador(models.Model):
    class Plataforma(models.TextChoices):
        STEAM = 'STEAM'
        PS5 = 'PS5'
        PS4 = 'PS4'
        XBOX = 'XBOX'
        PIRATA = 'PIRATA'

    alias = models.CharField(max_length=100)
    nombre = models.CharField(max_length=100)
    ip = models.CharField(max_length=50)
    # Punto en coordenadas GPS (WGS84). GeoDjango lo guarda como (longitud, latitud).
    ubicacion = models.PointField(srid=4326, null=True, blank=False)
    plataforma = models.CharField(choices=Plataforma.choices, default=Plataforma.STEAM)
    # Relación con los videojuegos a través de Puntuacion, que guarda los puntos de cada uno.
    juegos = models.ManyToManyField('Videojuego', through='Puntuacion', related_name='jugadores')

    class Meta:
        verbose_name = 'Jugador'
        verbose_name_plural = 'Jugadores'

    def __str__(self):
        return self.alias


class Videojuego(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50)

    class Meta:
        verbose_name = 'Videojuego'
        verbose_name_plural = 'Videojuegos'

    def __str__(self):
        return self.nombre


class Puntuacion(models.Model):
    """Puntos de un jugador en un videojuego (tabla intermedia de Jugador.juegos)."""
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE)
    videojuego = models.ForeignKey(Videojuego, on_delete=models.CASCADE)
    puntos = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['jugador', 'videojuego'], name='puntuacion_unica_por_juego'),
        ]
        verbose_name = 'Puntuacion'
        verbose_name_plural = 'Puntuaciones'

    def __str__(self):
        return f'{self.jugador} en {self.videojuego}: {self.puntos} pts'
