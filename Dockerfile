FROM python:3.12-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Librerías de sistema que necesita GeoDjango (GDAL, GEOS y PROJ)
RUN apt-get update \
    && apt-get install -y --no-install-recommends binutils gdal-bin libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Estáticos recopilados en la imagen para que WhiteNoise los sirva comprimidos.
# DJANGO_DEBUG=1 solo para este paso: collectstatic no necesita la clave secreta.
RUN DJANGO_DEBUG=1 python manage.py collectstatic --noinput

# La aplicación no corre como root.
RUN useradd --system --uid 10001 --no-create-home geogis
USER geogis

EXPOSE 8000

# Producción: migraciones y gunicorn. Para desarrollar, docker-compose.yml lo
# cambia por runserver.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn geogis.wsgi --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-3} --access-logfile -"]
