"""
Data loading and processing service.

Reads the OIJ Excel/CSV dataset, validates, cleans, normalizes,
and builds the aggregated monthly time series stored in the database.
"""

import logging
import pandas as pd
import numpy as np
from pathlib import Path
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    'Delito', 'SubDelito', 'Fecha', 'Hora',
    'Victima', 'SubVictima', 'Edad', 'Sexo',
    'Nacionalidad', 'Provincia', 'Canton', 'Distrito',
}

# Possible alternative column name spellings in real OIJ exports
COLUMN_ALIASES = {
    'DELITO': 'Delito',
    'SUBDELITO': 'SubDelito',
    'FECHA': 'Fecha',
    'HORA': 'Hora',
    'VICTIMA': 'Victima',
    'SUBVICTIMA': 'SubVictima',
    'EDAD': 'Edad',
    'SEXO': 'Sexo',
    'NACIONALIDAD': 'Nacionalidad',
    'PROVINCIA': 'Provincia',
    'CANTON': 'Canton',
    'DISTRITO': 'Distrito',
}

# Cantones que pertenecen a la provincia de Alajuela según división territorial de Costa Rica.
# Se usan como respaldo cuando el campo Provincia está vacío.
CANTONES_ALAJUELA = {
    'ALAJUELA', 'SAN RAMÓN', 'GRECIA', 'SAN MATEO', 'ATENAS',
    'NARANJO', 'PALMARES', 'POÁS', 'OROTINA', 'SAN CARLOS',
    'ZARCERO', 'SARCHÍ', 'UPALA', 'LOS CHILES', 'GUATUSO',
    'RÍO CUARTO',
    # Variantes sin tildes
    'SAN RAMON', 'POAS', 'SARCHI', 'RIO CUARTO',
}


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, handling case and accent variants."""
    rename_map = {}
    for col in df.columns:
        upper = col.strip().upper().replace('Ó', 'O').replace('Í', 'I').replace('É', 'E').replace('Á', 'A').replace('Ú', 'U')
        if upper in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[upper]
    return df.rename(columns=rename_map)


def load_dataset(path: Path = None) -> tuple[pd.DataFrame, list]:
    """
    Load dataset from Excel or CSV.
    Returns (clean_df, audit_report) where audit_report is a list of dicts
    describing each cleaning step and its row impact.
    """
    if path is None:
        path = settings.DATASET_PATH

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")

    logger.info(f"Loading dataset from {path}")

    suffix = path.suffix.lower()
    if suffix in ('.xlsx', '.xls', '.xlsm'):
        df = _read_excel_all_sheets(path)
    elif suffix == '.csv':
        df = None
        for enc in ('utf-8', 'latin-1', 'cp1252'):
            try:
                df = pd.read_csv(path, dtype=str, encoding=enc, sep=None, engine='python')
                break
            except UnicodeDecodeError:
                continue
        if df is None:
            raise ValueError("No se pudo decodificar el archivo CSV con ninguna codificación conocida.")
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    df = normalize_columns(df)

    # Validate required columns
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        logger.warning(f"Columnas no encontradas: {missing}. Se continúa con las columnas disponibles.")

    return clean_dataset(df)


def _read_excel_all_sheets(path: Path) -> pd.DataFrame:
    """
    Read all sheets from an Excel file and concatenate them.

    Logs a sheet-by-sheet breakdown so it's visible if rows are split across
    multiple sheets (a common OIJ Excel format pattern).
    """
    all_sheets = pd.read_excel(path, dtype=str, sheet_name=None)

    logger.info(f"Hojas en el archivo Excel: {list(all_sheets.keys())}")

    frames = []
    for sheet_name, sheet_df in all_sheets.items():
        rows = len(sheet_df)
        cols = list(sheet_df.columns)
        logger.info(f"  Hoja '{sheet_name}': {rows:,} filas × {len(cols)} columnas — {cols}")
        if rows > 0:
            frames.append(sheet_df)

    if not frames:
        raise ValueError("El archivo Excel no contiene datos en ninguna hoja.")

    if len(frames) == 1:
        return frames[0].reset_index(drop=True)

    # Multiple sheets: concatenate only sheets that share the same columns as the first
    reference_cols = set(frames[0].columns)
    compatible = [frames[0]]
    skipped = []
    for sheet_df in frames[1:]:
        if set(sheet_df.columns) == reference_cols:
            compatible.append(sheet_df)
        else:
            skipped.append(sheet_df.shape)

    if skipped:
        logger.warning(
            f"{len(skipped)} hoja(s) omitida(s) por tener columnas distintas: {skipped}"
        )

    result = pd.concat(compatible, ignore_index=True)
    logger.info(f"Total tras concatenar hojas compatibles: {len(result):,} filas")
    return result


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """
    Clean and normalize the dataset.

    Cleaning strategy: only discard records that make it impossible to build
    the time series (invalid date, missing canton, missing crime type).
    All secondary fields (Hora, Sexo, Edad, Victima, etc.) are kept as-is
    and stored as NULL when absent — they are never grounds for row elimination.

    Returns:
        (cleaned_df, audit_report)
        audit_report: list of dicts with keys:
            rule, justification, before, after, dropped, pct, classification
    """
    initial = len(df)
    audit = []
    logger.info(f"[Auditoría] Dataset inicial: {initial:,} registros × {len(df.columns)} columnas")

    # ── 1. Normalizar espacios en columnas de texto ──────────────────────────
    # NaN se convierte a la cadena 'nan' aquí; se revierte en el paso siguiente.
    str_cols = df.select_dtypes(include='object').columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    # ── 2. Unificar representaciones nulas ───────────────────────────────────
    # Convierte strings vacíos y variantes de nulo a np.nan real.
    df.replace({'nan': np.nan, 'None': np.nan, '': np.nan}, inplace=True)

    # ── Diagnóstico: nulos en columnas clave ANTES de filtrar ────────────────
    # Estos datos se incluyen en el audit para que el comando pueda imprimirlos.
    _key_cols = ['Fecha', 'Delito', 'Canton', 'Provincia']
    _null_entries = []
    for col in _key_cols:
        if col in df.columns:
            n_null = int(df[col].isna().sum())
            _null_entries.append({'tipo': 'nulos', 'col': col, 'nulos': n_null,
                                  'pct': round(n_null / initial * 100, 1) if initial else 0,
                                  'present': True})
        else:
            _null_entries.append({'tipo': 'nulos', 'col': col, 'nulos': None, 'pct': None, 'present': False})
    # Agregar listado de columnas disponibles para detectar alias no resueltos
    _null_entries.append({'tipo': 'columnas', 'nombres': list(df.columns)})
    audit.extend(_null_entries)

    # ── 3. Parsear y validar fechas ──────────────────────────────────────────
    _before = len(df)
    if 'Fecha' in df.columns:
        df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=False, errors='coerce')
        df = df.dropna(subset=['Fecha'])
    _after = len(df)
    audit.append(_step(
        rule='Fecha inválida o vacía',
        justification='Sin fecha no es posible construir la serie temporal mensual.',
        classification='Obligatorio',
        before=_before, after=_after, initial=initial,
    ))

    # ── 4. Eliminar registros sin tipo de delito ─────────────────────────────
    _before = len(df)
    if 'Delito' in df.columns:
        df = df.dropna(subset=['Delito'])
        df = df[df['Delito'].astype(str).str.strip().ne('')]
    _after = len(df)
    audit.append(_step(
        rule='Delito vacío',
        justification='El tipo de delito es la clave de agrupación de la serie temporal.',
        classification='Obligatorio',
        before=_before, after=_after, initial=initial,
    ))

    # ── 5. Eliminar registros sin cantón ─────────────────────────────────────
    _before = len(df)
    if 'Canton' in df.columns:
        df = df.dropna(subset=['Canton'])
        df = df[df['Canton'].astype(str).str.strip().ne('')]
    _after = len(df)
    audit.append(_step(
        rule='Canton vacío',
        justification='El cantón es la unidad geográfica de los pronósticos.',
        classification='Obligatorio',
        before=_before, after=_after, initial=initial,
    ))

    # ── 6. Normalizar mayúsculas en campos categóricos ───────────────────────
    for col in ['Delito', 'SubDelito', 'Canton', 'Provincia', 'Distrito',
                'Sexo', 'Victima', 'SubVictima', 'Edad', 'Nacionalidad']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper().str.strip()
            df[col] = df[col].replace({'NAN': np.nan})

    # ── 7. Filtrar solo provincia de Alajuela ────────────────────────────────
    # Estrategia en dos capas:
    #   a) Mantener registros donde Provincia contiene 'ALAJUELA'
    #   b) Mantener también registros donde Provincia está vacía PERO el
    #      Canton pertenece a la lista canónica de cantones de Alajuela.
    #      Esto evita descartar registros de Alajuela con error de ingreso
    #      en el campo Provincia.
    _before = len(df)
    if 'Provincia' in df.columns:
        mask_provincia = df['Provincia'].fillna('').str.contains('ALAJUELA', na=False)
        if 'Canton' in df.columns:
            mask_canton_fallback = (
                df['Provincia'].isna()
                & df['Canton'].fillna('').isin(CANTONES_ALAJUELA)
            )
            df = df[mask_provincia | mask_canton_fallback]
        else:
            df = df[mask_provincia]
    _after = len(df)
    audit.append(_step(
        rule='Provincia distinta de Alajuela (o vacía sin cantón reconocible)',
        justification=(
            'El sistema está diseñado para la provincia de Alajuela. '
            'Registros de otras provincias no aportan a los pronósticos. '
            'Registros con Provincia vacía se conservan si el Cantón pertenece a Alajuela.'
        ),
        classification='Obligatorio',
        before=_before, after=_after, initial=initial,
    ))

    final = len(df)
    logger.info(
        f"[Auditoría] Dataset limpio: {final:,} registros "
        f"({final / initial * 100:.1f}% retenidos de {initial:,})"
    )

    return df.reset_index(drop=True), audit


def _step(rule: str, justification: str, classification: str,
          before: int, after: int, initial: int) -> dict:
    """Build one audit step dict."""
    dropped = before - after
    pct_of_step = dropped / before * 100 if before else 0
    pct_of_total = dropped / initial * 100 if initial else 0
    logger.info(
        f"  [{'OK' if dropped == 0 else '–'}] {rule}: "
        f"{before:,} → {after:,}  (eliminados: {dropped:,} / {pct_of_total:.1f}% del total)"
    )
    return {
        'rule': rule,
        'justification': justification,
        'classification': classification,
        'before': before,
        'after': after,
        'dropped': dropped,
        'pct_step': round(pct_of_step, 1),
        'pct_total': round(pct_of_total, 1),
    }


def build_monthly_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate cleaned data into monthly time series.

    Returns DataFrame with columns:
        year, month, canton, delito, total_delitos
    """
    if df.empty:
        return pd.DataFrame(columns=['year', 'month', 'canton', 'delito', 'total_delitos'])

    df = df.copy()
    df['year'] = df['Fecha'].dt.year
    df['month'] = df['Fecha'].dt.month
    df['canton'] = df['Canton'].fillna('DESCONOCIDO')
    df['delito'] = df['Delito'].fillna('OTRO')

    series = (
        df.groupby(['year', 'month', 'canton', 'delito'], observed=True)
        .size()
        .reset_index(name='total_delitos')
    )

    return series.sort_values(['canton', 'delito', 'year', 'month']).reset_index(drop=True)


@transaction.atomic
def import_to_database(df: pd.DataFrame, series: pd.DataFrame) -> dict:
    """
    Persist cleaned records and monthly series to the database.
    Clears existing data before importing (full refresh strategy).

    Returns a summary dict with counts.
    """
    from forecasting.models import CrimeRecord, MonthlySeries

    logger.info("Starting database import...")

    # Clear existing data
    CrimeRecord.objects.all().delete()
    MonthlySeries.objects.all().delete()

    # Bulk insert crime records
    records = []
    for _, row in df.iterrows():
        records.append(CrimeRecord(
            delito=str(row.get('Delito', ''))[:200],
            sub_delito=str(row.get('SubDelito', ''))[:200] if pd.notna(row.get('SubDelito')) else None,
            fecha=row['Fecha'].date() if hasattr(row['Fecha'], 'date') else row['Fecha'],
            hora=str(row.get('Hora', ''))[:100] if pd.notna(row.get('Hora')) else None,
            victima=str(row.get('Victima', ''))[:200] if pd.notna(row.get('Victima')) else None,
            sub_victima=str(row.get('SubVictima', ''))[:300] if pd.notna(row.get('SubVictima')) else None,
            edad=str(row.get('Edad', ''))[:100] if pd.notna(row.get('Edad')) else None,
            sexo=str(row.get('Sexo', ''))[:50] if pd.notna(row.get('Sexo')) else None,
            nacionalidad=str(row.get('Nacionalidad', ''))[:100] if pd.notna(row.get('Nacionalidad')) else None,
            provincia=str(row.get('Provincia', ''))[:100] if pd.notna(row.get('Provincia')) else None,
            canton=str(row.get('Canton', ''))[:100],
            distrito=str(row.get('Distrito', ''))[:100] if pd.notna(row.get('Distrito')) else None,
        ))

    CrimeRecord.objects.bulk_create(records, batch_size=500)
    logger.info(f"Inserted {len(records)} crime records")

    # Bulk insert monthly series
    monthly_records = []
    for _, row in series.iterrows():
        monthly_records.append(MonthlySeries(
            year=int(row['year']),
            month=int(row['month']),
            canton=str(row['canton'])[:100],
            delito=str(row['delito'])[:200],
            total_delitos=int(row['total_delitos']),
        ))

    MonthlySeries.objects.bulk_create(monthly_records, batch_size=500)
    logger.info(f"Inserted {len(monthly_records)} monthly series records")

    return {
        'crime_records': len(records),
        'monthly_series': len(monthly_records),
    }


def get_global_series_range() -> dict | None:
    """
    Return the global (min_year, min_month, max_year, max_month) from MonthlySeries.

    Uses two-step aggregation to avoid the independent-Max pitfall: getting
    Max('year') and Max('month') separately can return a (year, month) pair
    that never existed in the data (e.g. max_year=2025, max_month=12 from a
    different year).  We always pin the month query to the correct year.
    """
    from django.db.models import Max, Min
    from forecasting.models import MonthlySeries

    agg = MonthlySeries.objects.aggregate(min_year=Min('year'), max_year=Max('year'))
    if agg['min_year'] is None:
        return None

    min_month = MonthlySeries.objects.filter(
        year=agg['min_year']
    ).aggregate(m=Min('month'))['m']

    max_month = MonthlySeries.objects.filter(
        year=agg['max_year']
    ).aggregate(m=Max('month'))['m']

    return {
        'min_year': agg['min_year'],
        'min_month': min_month,
        'max_year': agg['max_year'],
        'max_month': max_month,
    }


def get_dataset_summary() -> dict:
    """Return summary statistics for the home page KPI cards."""
    from forecasting.models import CrimeRecord, MonthlySeries

    total_records = CrimeRecord.objects.count()
    cantons = list(CrimeRecord.objects.exclude(canton='DESCONOCIDO').values_list('canton', flat=True).distinct().order_by('canton'))
    delitos = list(CrimeRecord.objects.values_list('delito', flat=True).distinct().order_by('delito'))

    fecha_min = CrimeRecord.objects.order_by('fecha').values_list('fecha', flat=True).first()
    fecha_max = CrimeRecord.objects.order_by('-fecha').values_list('fecha', flat=True).first()

    return {
        'total_records': total_records,
        'cantons': cantons,
        'delitos': delitos,
        'total_cantons': len(cantons),
        'total_delitos': len(delitos),
        'fecha_min': fecha_min,
        'fecha_max': fecha_max,
        'data_loaded': total_records > 0,
    }
