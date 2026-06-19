"""
Servicio de inicio: importación automática del conjunto de datos al arrancar Django.

Llamado desde ForecastingConfig.ready() cada vez que se inicia el servidor.
Decide si ejecutar la canalización completa de importación según:
  1. Si la base de datos contiene registros de delitos (vacía → importar)
  2. Si la hora de modificación del archivo Excel es más reciente que la última importación

Esto significa que el usuario solo debe:
  - Reemplazar datasets/Estadisticas.xlsx con una nueva versión
  - Reiniciar el servidor
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def run_auto_import(dataset_path: Path) -> None:
    """
    Ejecuta la canalización completa de datos si el conjunto ha cambiado o la BD está vacía.
    Registra el resultado en DataImportLog para que los siguientes arranques puedan omitir la importación.
    """
    from forecasting.models import DataImportLog, CrimeRecord

    dataset_path = Path(dataset_path)

    if not dataset_path.exists():
        logger.warning(
            '[Auto-import] %s no encontrado. '
            'Coloque Estadisticas.xlsx en datasets/ y reinicie el servidor.',
            dataset_path,
        )
        return

    current_mtime = dataset_path.stat().st_mtime
    db_empty = not CrimeRecord.objects.exists()
    last_log = DataImportLog.objects.order_by('-imported_at').first()

    if not db_empty and last_log is not None and current_mtime <= last_log.file_mtime:
        logger.info('[Auto-import] Dataset sin cambios — omitiendo importación.')
        return

    if db_empty:
        reason = 'base de datos vacía (primera ejecución)'
    elif last_log is None:
        reason = 'sin historial de importación previo'
    else:
        reason = 'archivo Excel modificado desde última importación'

    logger.info('[Auto-import] Iniciando pipeline — %s', reason)

    from forecasting.services.data_service import (
        load_dataset,
        build_monthly_series,
        import_to_database,
    )

    df, _audit = load_dataset(dataset_path)
    series = build_monthly_series(df)
    result = import_to_database(df, series)

    DataImportLog.objects.create(
        file_path=str(dataset_path),
        file_mtime=current_mtime,
        crime_records=result['crime_records'],
        monthly_series=result['monthly_series'],
    )

    logger.info(
        '[Auto-import] Completado: %s registros de delitos, %s series mensuales.',
        f'{result["crime_records"]:,}',
        f'{result["monthly_series"]:,}',
    )
