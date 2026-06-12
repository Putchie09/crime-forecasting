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


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names, handling case and accent variants."""
    rename_map = {}
    for col in df.columns:
        upper = col.strip().upper().replace('Ó', 'O').replace('Í', 'I').replace('É', 'E').replace('Á', 'A').replace('Ú', 'U')
        if upper in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[upper]
    return df.rename(columns=rename_map)


def load_dataset(path: Path = None) -> pd.DataFrame:
    """
    Load dataset from Excel or CSV.
    Returns clean DataFrame with standardized columns.
    """
    if path is None:
        path = settings.DATASET_PATH

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found at {path}")

    logger.info(f"Loading dataset from {path}")

    suffix = path.suffix.lower()
    if suffix in ('.xlsx', '.xls', '.xlsm'):
        df = pd.read_excel(path, dtype=str)
    elif suffix == '.csv':
        # Try common encodings for Spanish text
        for enc in ('utf-8', 'latin-1', 'cp1252'):
            try:
                df = pd.read_csv(path, dtype=str, encoding=enc, sep=None, engine='python')
                break
            except UnicodeDecodeError:
                continue
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    df = normalize_columns(df)

    # Validate required columns
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        # Try partial match – perhaps columns exist but renamed
        logger.warning(f"Missing columns: {missing}. Will proceed with available columns.")

    return clean_dataset(df)


def clean_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and normalize the dataset:
    - Strip whitespace from string fields
    - Parse and validate dates
    - Uppercase categorical fields
    - Drop invalid/incomplete rows
    """
    logger.info(f"Raw dataset shape: {df.shape}")

    # Strip whitespace from all string columns
    str_cols = df.select_dtypes(include='object').columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()

    # Remove rows where any value is literally 'nan' or empty
    df.replace({'nan': np.nan, 'None': np.nan, '': np.nan}, inplace=True)

    # Parse dates – handle multiple formats
    if 'Fecha' in df.columns:
        df['Fecha'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce')
        invalid_dates = df['Fecha'].isna().sum()
        if invalid_dates > 0:
            logger.warning(f"Dropped {invalid_dates} rows with invalid/missing dates")
        df = df.dropna(subset=['Fecha'])

    # Require Delito and Canton
    for col in ['Delito', 'Canton']:
        if col in df.columns:
            df = df.dropna(subset=[col])
            df = df[df[col].astype(str).str.strip().ne('')]

    # Uppercase categorical fields for consistency
    for col in ['Delito', 'SubDelito', 'Canton', 'Provincia', 'Distrito',
                'Sexo', 'Victima', 'SubVictima', 'Edad', 'Nacionalidad']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.upper().str.strip()
            df[col] = df[col].replace({'NAN': np.nan})

    # Filter only Alajuela province if column exists
    if 'Provincia' in df.columns:
        df = df[df['Provincia'].fillna('').str.contains('ALAJUELA', na=False)]

    logger.info(f"Clean dataset shape: {df.shape}")
    return df.reset_index(drop=True)


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


def get_dataset_summary() -> dict:
    """Return summary statistics for the home page KPI cards."""
    from forecasting.models import CrimeRecord, MonthlySeries

    total_records = CrimeRecord.objects.count()
    cantons = list(CrimeRecord.objects.values_list('canton', flat=True).distinct().order_by('canton'))
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
