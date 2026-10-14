import random

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import Jugador, Puntuacion, Videojuego

VIDEOJUEGOS = [
    ('Rocket League', 'Deportes'),
    ('Minecraft', 'Sandbox'),
    ('Elden Ring', 'RPG'),
    ('Mario Kart 8', 'Carreras'),
    ('Tetris', 'Puzle'),
    ('Hollow Knight', 'Metroidvania'),
    ('Fortnite', 'Battle royale'),
    ('Stardew Valley', 'Simulación'),
]

# Datos ficticios. Las IP son de los rangos reservados para documentación (RFC 5737).
# (alias, nombre, plataforma, ip, longitud, latitud)
JUGADORES = [
    ('Nexo', 'Ana Pérez', 'STEAM', '192.0.2.10', -3.7038, 40.4168),        # Madrid
    ('Kraken', 'Luis Martín', 'PS5', '192.0.2.11', 2.1734, 41.3851),       # Barcelona
    ('Aurora', 'Marta Gil', 'XBOX', '192.0.2.12', -0.3763, 39.4699),       # Valencia
    ('Zafiro', 'Pablo Ruiz', 'PS4', '192.0.2.13', -5.9845, 37.3891),       # Sevilla
    ('Bruma', 'Irene Soto', 'STEAM', '192.0.2.14', -8.5448, 42.8782),      # Santiago
    ('Lince', 'Hugo Navarro', 'PIRATA', '198.51.100.20', -2.9350, 43.2630),  # Bilbao
    ('Pixel', 'Claire Dubois', 'STEAM', '198.51.100.21', 2.3522, 48.8566),   # París
    ('Rayo', 'João Silva', 'PS5', '198.51.100.22', -9.1393, 38.7223),        # Lisboa
    ('Glaciar', 'Lena Weber', 'XBOX', '198.51.100.23', 13.4050, 52.5200),    # Berlín
    ('Ámbar', 'Giulia Rossi', 'STEAM', '198.51.100.24', 12.4964, 41.9028),   # Roma
    ('Vórtice', 'Tom Baker', 'PS4', '203.0.113.30', -0.1276, 51.5072),       # Londres
    ('Nébula', 'Eva Novak', 'STEAM', '203.0.113.31', 14.4378, 50.0755),      # Praga
    ('Cometa', 'Sven Lund', 'XBOX', '203.0.113.32', 18.0686, 59.3293),       # Estocolmo
    ('Eco', 'Daan de Vries', 'PS5', '203.0.113.33', 4.9041, 52.3676),        # Ámsterdam
    ('Sombra', 'Nikos Pappas', 'PIRATA', '203.0.113.34', 23.7275, 37.9838),  # Atenas
]


class Command(BaseCommand):
    help = 'Carga jugadores, videojuegos y puntuaciones de ejemplo. Se puede ejecutar varias veces.'

    @transaction.atomic
    def handle(self, *args, **options):
        azar = random.Random(42)  # misma semilla, mismos datos en cada ejecución

        juegos = [
            Videojuego.objects.update_or_create(nombre=nombre, defaults={'tipo': tipo})[0]
            for nombre, tipo in VIDEOJUEGOS
        ]

        for alias, nombre, plataforma, ip, lng, lat in JUGADORES:
            jugador, _ = Jugador.objects.update_or_create(
                alias=alias,
                defaults={
                    'nombre': nombre,
                    'plataforma': plataforma,
                    'ip': ip,
                    'ubicacion': Point(lng, lat, srid=4326),
                },
            )
            for juego in azar.sample(juegos, k=azar.randint(2, 4)):
                Puntuacion.objects.update_or_create(
                    jugador=jugador, videojuego=juego,
                    defaults={'puntos': azar.randrange(100, 10000, 50)},
                )

        self.stdout.write(self.style.SUCCESS(
            f'Datos de ejemplo cargados: {len(JUGADORES)} jugadores y {len(VIDEOJUEGOS)} videojuegos.'
        ))
