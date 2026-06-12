"""
Management command: load_dataset

Usage:
    python manage.py load_dataset
    python manage.py load_dataset --path /path/to/Estadisticas.xlsx

Reads the OIJ Excel dataset, cleans it, builds the monthly time series,
and imports everything into the SQLite database.
Prints a step-by-step audit table showing how many records each cleaning
rule discards and why.
"""

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
        dataset_path = Path(path) if path else settings.DATASET_PATH

        self.stdout.write(f"Cargando dataset desde: {dataset_path}")

        if not dataset_path.exists():
            raise CommandError(
                f"Archivo no encontrado: {dataset_path}\n"
                f"   Copie el archivo Estadisticas.xlsx a la carpeta 'datasets/' del proyecto."
            )

        try:
            self.stdout.write("Leyendo y limpiando datos...")
            df, audit = load_dataset(dataset_path)

            # Separar entradas de diagnóstico de las de eliminación
            diag_entries = [e for e in audit if e.get('tipo') in ('nulos', 'columnas')]
            step_entries = [e for e in audit if 'rule' in e]

            self._print_diagnostics(diag_entries)
            self._print_audit(step_entries)

            self.stdout.write(self.style.SUCCESS(f"   {len(df):,} registros válidos para importar"))

            self.stdout.write("Construyendo series de tiempo mensuales...")
            series = build_monthly_series(df)
            self.stdout.write(self.style.SUCCESS(f"   {len(series):,} combinaciones canton-delito-mes"))

            self.stdout.write("Importando a la base de datos...")
            result = import_to_database(df, series)

            # Register the import so the auto-import check can skip next startup
            from forecasting.models import DataImportLog
            DataImportLog.objects.create(
                file_path=str(dataset_path),
                file_mtime=dataset_path.stat().st_mtime,
                crime_records=result['crime_records'],
                monthly_series=result['monthly_series'],
            )

            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Dataset importado exitosamente:"))
            self.stdout.write(f"   - Registros de delitos : {result['crime_records']:,}")
            self.stdout.write(f"   - Series mensuales     : {result['monthly_series']:,}")
            self.stdout.write("")
            self.stdout.write("Puede iniciar el servidor con: python manage.py runserver")

        except FileNotFoundError as e:
            raise CommandError(str(e))
        except Exception as e:
            raise CommandError(f"Error durante la importación: {e}")

    def _print_diagnostics(self, diag_entries: list):
        """Print null counts for key columns and available column names."""
        null_entries = [e for e in diag_entries if e.get('tipo') == 'nulos']
        col_entry = next((e for e in diag_entries if e.get('tipo') == 'columnas'), None)

        if not null_entries and not col_entry:
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))
        self.stdout.write(self.style.MIGRATE_HEADING("  DIAGNÓSTICO DE COLUMNAS CLAVE (antes de filtrar)"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))

        for entry in null_entries:
            col = entry['col']
            if not entry['present']:
                self.stdout.write(
                    self.style.ERROR(f"  [!] '{col}': COLUMNA NO ENCONTRADA - verifique el nombre en el Excel")
                )
            elif entry['nulos'] == 0:
                self.stdout.write(f"  [OK] '{col}': 0 nulos")
            else:
                n = entry['nulos']
                pct = entry['pct']
                self.stdout.write(
                    self.style.ERROR(f"  [!] '{col}': {n:,} nulos ({pct}%) - causa probable de perdida de registros")
                )

        if col_entry:
            self.stdout.write("")
            cols = col_entry['nombres']
            self.stdout.write(f"  Columnas leídas del archivo ({len(cols)}):")
            self.stdout.write(f"  {cols}")

        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))

    def _print_audit(self, audit: list):
        """Print a formatted step-by-step data cleaning audit table."""
        if not audit:
            return

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))
        self.stdout.write(self.style.MIGRATE_HEADING("  AUDITORÍA DE LIMPIEZA — REGISTROS ELIMINADOS POR REGLA"))
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))

        initial = audit[0]['before'] if audit else 0
        self.stdout.write(f"  {'Registros iniciales':<44} {initial:>8,}")
        self.stdout.write(f"  {'-' * 62}")

        for step in audit:
            dropped = step['dropped']
            rule = step['rule']
            pct = step['pct_total']
            cls = step['classification']

            if dropped == 0:
                self.stdout.write(f"  {'[OK]':<12} {rule:<38} {'0':>8}")
            else:
                self.stdout.write(
                    self.style.ERROR(f"  [ELIMINA]    {rule:<38} -{dropped:>7,}  ({pct:.1f}%)")
                )

        self.stdout.write(f"  {'-' * 62}")
        final = audit[-1]['after'] if audit else 0
        total_dropped = initial - final
        pct_retained = final / initial * 100 if initial else 0
        pct_dropped = total_dropped / initial * 100 if initial else 0

        self.stdout.write(
            f"  {'Total eliminados':<44} {total_dropped:>8,}  ({pct_dropped:.1f}%)"
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"  {'Registros finales':<44} {final:>8,}  ({pct_retained:.1f}%)"
            )
        )
        self.stdout.write(self.style.MIGRATE_HEADING("=" * 72))
        self.stdout.write("")
