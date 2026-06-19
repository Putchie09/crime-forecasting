"""
Funciones utilitarias usadas en la aplicación de pronóstico.
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MONTH_NAMES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Setiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}

MONTH_NAMES_SHORT_ES = {
    1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic',
}


def generate_period_labels(
    start_year: int,
    start_month: int,
    n_periods: int,
    fmt: str = 'YYYY-MM',
) -> List[str]:
    """
    Genera una lista de etiquetas de período.

    Args:
        start_year: Año de inicio.
        start_month: Mes de inicio (1-12).
        n_periods: Cantidad de períodos a generar.
        fmt: Formato — 'YYYY-MM' o 'MMM YYYY'.

    Returns:
        Lista de cadenas de período formateadas.
    """
    labels = []
    yr, mo = start_year, start_month
    for _ in range(n_periods):
        if fmt == 'YYYY-MM':
            labels.append(f"{yr}-{mo:02d}")
        elif fmt == 'MMM YYYY':
            labels.append(f"{MONTH_NAMES_SHORT_ES.get(mo, mo)} {yr}")
        else:
            labels.append(f"{yr}-{mo:02d}")
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
    return labels


def add_months(year: int, month: int, delta: int) -> Tuple[int, int]:
    """
    Suma meses a un par (año, mes).

    Args:
        year: Año base.
        month: Mes base (1-12).
        delta: Cantidad de meses a sumar (puede ser negativa).

    Returns:
        Tupla (nuevo_año, nuevo_mes).
    """
    total = (year - 1) * 12 + (month - 1) + delta
    return (total // 12 + 1, total % 12 + 1)


def percentage_change(old_val: float, new_val: float) -> Optional[float]:
    """
    Calcula el cambio porcentual entre old_val y new_val.
    Devuelve None si old_val es cero.
    """
    if old_val == 0:
        return None
    return ((new_val - old_val) / old_val) * 100.0


def format_metric(value: float, decimals: int = 4) -> str:
    """Formatea un valor numérico a un número fijo de decimales."""
    try:
        return f"{float(value):.{decimals}f}"
    except (TypeError, ValueError):
        return str(value)


def clamp(value: float, min_val: float = 0.0, max_val: float = 100.0) -> float:
    """Restringe un valor entre un mínimo y un máximo."""
    return max(min_val, min(max_val, value))


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide de forma segura, devolviendo el valor por defecto si el denominador es cero."""
    if denominator == 0:
        return default
    return numerator / denominator
