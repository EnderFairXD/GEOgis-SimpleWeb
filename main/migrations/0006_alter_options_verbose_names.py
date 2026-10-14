from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0005_alter_jugador_plataforma_alter_jugador_ubicacion'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='jugador',
            options={'verbose_name': 'Jugador', 'verbose_name_plural': 'Jugadores'},
        ),
        migrations.AlterModelOptions(
            name='puntuacion',
            options={'verbose_name': 'Puntuacion', 'verbose_name_plural': 'Puntuaciones'},
        ),
        migrations.AlterModelOptions(
            name='videojuego',
            options={'verbose_name': 'Videojuego', 'verbose_name_plural': 'Videojuegos'},
        ),
    ]
