from django.apps import AppConfig


class ForecastingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'forecasting'
    verbose_name = 'Pronóstico de Criminalidad'

    def ready(self):
        """Called once Django starts — safe place for signal registration if needed."""
        pass
