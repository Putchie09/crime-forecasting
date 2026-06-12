import sys
import os
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Management commands where auto-import should not run.
# These commands either don't need data or run before tables exist.
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

        # Skip for management commands that don't serve web requests
        if len(argv) > 1 and argv[1] in _SKIP_AUTO_IMPORT:
            return

        # Django's dev server uses an auto-reloader that starts the process
        # twice: first the reloader parent, then the child (RUN_MAIN=true).
        # Run auto-import only in the child to avoid duplicate imports.
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
