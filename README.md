# GEOgis

Aplicación web con **GeoDjango**, **PostGIS** y **Leaflet**: muestra en un mapa a los jugadores
de videojuegos, con su plataforma y su historial de puntuaciones, y permite mover su ubicación
arrastrando el marcador.

## Qué hace

- **Mapa** con un marcador por jugador que tenga ubicación.
- **Ficha del jugador** al pulsar un marcador: alias, nombre, plataforma y puntuaciones por juego.
- **Modo arrastrar** (control de Geoman, arriba a la izquierda): al soltar un marcador, la nueva
  posición se guarda en la base de datos.
- **Panel de administración** de Django con mapa para editar ubicaciones, y puntuaciones por jugador.

## Requisitos

- Python 3.10+
- PostgreSQL con la extensión **PostGIS**
- Librerías del sistema de GeoDjango: GDAL, GEOS y PROJ
  ([guía oficial](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/install/))

## Puesta en marcha

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Base de datos (una sola vez)
createdb GeoDjango
psql -d GeoDjango -c "CREATE EXTENSION postgis;"

cp .env.example .env     # rellena DB_PASSWORD y DJANGO_SECRET_KEY
export $(grep -v '^#' .env | xargs)

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abre <http://127.0.0.1:8000/> para el mapa y <http://127.0.0.1:8000/admin/> para añadir
jugadores, videojuegos y puntuaciones.

## Estructura

| Ruta | Contenido |
|---|---|
| `jugadores/` | Configuración del proyecto Django |
| `main/models.py` | `Jugador` (con `PointField`), `Videojuego` y `Puntuacion` |
| `main/views.py` | Vista del mapa y endpoint para guardar la ubicación |
| `main/static/js/Main.js` | Mapa, ficha del jugador y guardado al arrastrar |

## Licencia

MIT © Javier Cortés Vidal
