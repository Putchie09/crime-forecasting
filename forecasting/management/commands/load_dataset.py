"""
Management command: load_dataset

Usage:
    python manage.py load_dataset
    python manage.py load_dataset --path /path/to/Estadisticas.xlsx

Reads the OIJ Excel dataset, cleans it, builds the monthly time series,
and imports everything into the SQLite database.
"""

import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from forecasting.services.data_service import (
    load_dataset,
    build_monthly_series,
    import_to_database,
)


class Command(BaseCommand):
    help = 'Carga el dataset de criminalidad desde Excel y lo importa a la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            type=str,
            default=None,
            help='Ruta al archivo Excel/CSV del dataset (por defecto usa settings.DATASET_PATH)',
        )

    def handle(self, *args, **options):
        path = options.get('path')
        if path:
            dataset_path = Path(path)
        else:
            dataset_path = settings.DATASET_PATH

        self.stdout.write(f"📂 Cargando dataset desde: {dataset_path}")

        if not dataset_path.exists():
            raise CommandError(
                f"❌ Archivo no encontrado: {dataset_path}\n"
                f"   Copie el archivo Estadisticas.xlsx a la carpeta 'datasets/' del proyecto."
            )

        try:
            self.stdout.write("🔄 Leyendo y limpiando datos...")
            df = load_dataset(dataset_path)
            self.stdout.write(self.style.SUCCESS(f"   ✓ {len(df)} registros válidos"))

            self.stdout.write("📊 Construyendo series de tiempo mensuales...")
            series = build_monthly_series(df)
            self.stdout.write(self.style.SUCCESS(f"   ✓ {len(series)} combinaciones cantón-delito-mes"))

            self.stdout.write("💾 Importando a la base de datos...")
            result = import_to_database(df, series)

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("✅ Dataset importado exitosamente:"))
            self.stdout.write(f"   - Registros de delitos: {result['crime_records']:,}")
            self.stdout.write(f"   - Series mensuales: {result['monthly_series']:,}")
            self.stdout.write("")
            self.stdout.write("🚀 Puede iniciar el servidor con: python manage.py runserver")

        except FileNotFoundError as e:
            raise CommandError(str(e))
        except Exception as e:
            raise CommandError(f"Error durante la importación: {e}")
