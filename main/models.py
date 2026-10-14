from django.contrib.gis.db import models
# Create your models here.

class Jugador(models.Model):
    alias= models.CharField(max_length=100)
    nombre = models.CharField(max_length=100)
    ip = models.CharField(max_length=50)
    #ESTO ES GEODJANGO
    ubicacion = models.PointField(srid=4326, null=True, blank=False)
    #el textchoice solo se puede hacer así
    class Plataforma(models.TextChoices):
        STEAM= "STEAM"
        PS5= "PS5"
        PS4= "PS4"
        XBOX="XBOX"
        PIRATA="PIRATA"


    #Solo se eligen opciones preescritas y por defecto se elige steam
    plataforma = models.CharField(

        choices=Plataforma.choices,
        default=Plataforma.STEAM
    )

    #como es una relación MtM, se pone de la siguiente manera
    juegos = models.ManyToManyField(
        #tabla con la que se junta
        'Videojuego',
        #esto es para "juntar" la tabla puntuación , para que guarden puntos
        #sin el thorugh sería una tabla separada.
        through='Puntuacion',
        #desde la otra perspectiva
        related_name='jugadores'
    )

    class Meta:
        verbose_name = "Jugador"
        verbose_name_plural = "Jugadores"

    def __str__(self):
        return self.alias


class Videojuego(models.Model):
    nombre = models.CharField(max_length=100)
    tipo = models.CharField(max_length=50)

    class Meta:
        verbose_name = "Videojuego"
        verbose_name_plural = "Videojuegos"


    def __str__(self):
        return self.nombre

#Clase intermedia
class Puntuacion(models.Model):
    jugador = models.ForeignKey(Jugador, on_delete=models.CASCADE)
    videojuego = models.ForeignKey(Videojuego, on_delete=models.CASCADE)
    puntos = models.IntegerField(default=0)
    #meta lo que hace son reglas de la tabla
    class Meta:
        # NO DUPLICIDAD (unique)
        unique_together = ('jugador', 'videojuego')

        verbose_name = "Puntuacion"
        verbose_name_plural = "Puntuaciones"

    def __str__(self):
        return f"{self.jugador} en {self.videojuego}: {self.puntos} pts"