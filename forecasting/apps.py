import sys
import os
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Comandos de gestión donde no debe ejecutarse auto-import.
# Estos comandos no necesitan datos o se ejecutan antes de que existan las tablas.
_SKIP_AUTO_IMPORT = {
    'migrate', 'makemigrations', 'sqlmigrate', 'showmigrations',
    'collectstatic', 'test', 'shell', 'dbshell', 'createsuperuser',
    'load_dataset', 'check', 'inspectdb', 'diffsettings',
}


class ForecastingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'forecasting'
    verbose_name = 'Pronóstico de Criminalidad'

    def ready(self):
        argv = sys.argv

        # Omitir para comandos de gestión que no sirven solicitudes web
        if len(argv) > 1 and argv[1] in _SKIP_AUTO_IMPORT:
            return

        # El servidor de desarrollo de Django usa un auto-reloader que inicia
        # el proceso dos veces: primero el padre y luego el hijo (RUN_MAIN=true).
        # Ejecutar auto-import solo en el proceso hijo para evitar importaciones duplicadas.
        if len(argv) > 1 and argv[1] == 'runserver':
            if os.environ.get('RUN_MAIN') != 'true':
                return

        try:
            from django.conf import settings
            from forecasting.services.startup_service import run_auto_import
            run_auto_import(settings.DATASET_PATH)
        except Exception as exc:
            logger.warning(
                '[Auto-import] Carga automática omitida: %s — '
                'ejecute manualmente: python manage.py load_dataset',
                exc,
            )
