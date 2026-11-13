"""Ajustes de producción.

Django lee settings.py una sola vez al arrancar, así que cada caso carga los
ajustes en un proceso aparte con el entorno que se quiere probar.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from unittest import SkipTest

from django.test import SimpleTestCase

RAIZ = Path(__file__).resolve().parents[2]

# Una clave como la que se usaría en un despliegue real: larga y variada.
CLAVE = 'p7R$x2!kQ9zL@m4Wv8#eT1yU6&nB3cF5hJ0sD-aG_oI+lK*uY^rE%wZ~qX=vC'

PRODUCCION = {
    'DJANGO_SECRET_KEY': CLAVE,
    'DJANGO_ALLOWED_HOSTS': 'geogis.example.com',
    'DJANGO_CSRF_TRUSTED_ORIGINS': 'https://geogis.example.com',
    'DJANGO_DEBUG': '0',
}

# Avisos de `check --deploy` que se aceptan a propósito: incluir los subdominios
# en HSTS o pedir la precarga en los navegadores depende del dominio de cada uno.
AVISOS_ACEPTADOS = {'security.W005', 'security.W021'}


def _entorno(extra, quitar=()):
    entorno = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
    entorno.update(extra)
    for clave in quitar:
        entorno.pop(clave, None)
    entorno['DJANGO_SETTINGS_MODULE'] = 'geogis.settings'
    return entorno


def _ajustes(extra, quitar=()):
    """Carga settings.py con ese entorno y devuelve los valores que interesan."""
    codigo = (
        'import json\n'
        'from django.conf import settings\n'
        'print(json.dumps({\n'
        '    "DEBUG": settings.DEBUG,\n'
        '    "SECRET_KEY": settings.SECRET_KEY,\n'
        '    "ALLOWED_HOSTS": settings.ALLOWED_HOSTS,\n'
        '    "CSRF_TRUSTED_ORIGINS": settings.CSRF_TRUSTED_ORIGINS,\n'
        '    "SESSION_COOKIE_SECURE": settings.SESSION_COOKIE_SECURE,\n'
        '    "CSRF_COOKIE_SECURE": settings.CSRF_COOKIE_SECURE,\n'
        '    "SECURE_SSL_REDIRECT": settings.SECURE_SSL_REDIRECT,\n'
        '    "SECURE_PROXY_SSL_HEADER": settings.SECURE_PROXY_SSL_HEADER,\n'
        '    "SECURE_HSTS_SECONDS": settings.SECURE_HSTS_SECONDS,\n'
        '    "MIDDLEWARE": settings.MIDDLEWARE,\n'
        '}))\n'
    )
    return subprocess.run(
        [sys.executable, '-c', codigo], cwd=RAIZ, env=_entorno(extra, quitar),
        capture_output=True, text=True,
    )


class AjustesDeProduccionTests(SimpleTestCase):

    def test_debug_esta_apagado_si_no_se_indica(self):
        if (RAIZ / '.env').exists():
            raise SkipTest('hay un .env local que puede fijar DJANGO_DEBUG')
        r = _ajustes({'DJANGO_SECRET_KEY': CLAVE}, quitar=['DJANGO_DEBUG'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(json.loads(r.stdout)['DEBUG'])

    def test_produccion_sin_clave_secreta_no_arranca(self):
        r = _ajustes(PRODUCCION, quitar=['DJANGO_SECRET_KEY'])
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', r.stderr)

    def test_desarrollo_sin_clave_secreta_usa_la_de_desarrollo(self):
        r = _ajustes({'DJANGO_DEBUG': '1'}, quitar=['DJANGO_SECRET_KEY'])
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)['SECRET_KEY'])

    def test_produccion_usa_cookies_seguras_y_confia_en_el_https_del_proxy(self):
        r = _ajustes(PRODUCCION)
        self.assertEqual(r.returncode, 0, r.stderr)
        a = json.loads(r.stdout)
        self.assertTrue(a['SESSION_COOKIE_SECURE'])
        self.assertTrue(a['CSRF_COOKIE_SECURE'])
        self.assertTrue(a['SECURE_SSL_REDIRECT'])
        self.assertEqual(a['SECURE_PROXY_SSL_HEADER'], ['HTTP_X_FORWARDED_PROTO', 'https'])
        self.assertGreaterEqual(a['SECURE_HSTS_SECONDS'], 31536000)

    def test_los_origenes_de_confianza_para_csrf_salen_del_entorno(self):
        r = _ajustes(PRODUCCION)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['CSRF_TRUSTED_ORIGINS'], ['https://geogis.example.com'])

    def test_desarrollo_no_fuerza_https(self):
        r = _ajustes({'DJANGO_DEBUG': '1'})
        self.assertEqual(r.returncode, 0, r.stderr)
        a = json.loads(r.stdout)
        self.assertFalse(a['SECURE_SSL_REDIRECT'])
        self.assertFalse(a['SESSION_COOKIE_SECURE'])

    def test_los_estaticos_los_sirve_whitenoise_justo_despues_de_seguridad(self):
        r = _ajustes(PRODUCCION)
        self.assertEqual(r.returncode, 0, r.stderr)
        mw = json.loads(r.stdout)['MIDDLEWARE']
        self.assertEqual(mw[:2], [
            'django.middleware.security.SecurityMiddleware',
            'whitenoise.middleware.WhiteNoiseMiddleware',
        ])

    def test_check_deploy_no_da_mas_avisos_que_los_aceptados(self):
        r = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'], cwd=RAIZ,
            env=_entorno(PRODUCCION), capture_output=True, text=True,
        )
        salida = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, salida)
        avisos = set(re.findall(r'\((security\.\w+)\)', salida))
        self.assertEqual(avisos - AVISOS_ACEPTADOS, set(), salida)
