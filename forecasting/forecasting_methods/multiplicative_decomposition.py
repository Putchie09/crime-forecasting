"""
Descomposición Multiplicativa (Multiplicative Decomposition).

Descompone la serie de tiempo en tres componentes:
    Y(t) = T(t) × S(t) × I(t)
  donde:
    T(t) = componente de tendencia (regresión lineal sobre promedio móvil centrado)
    S(t) = componente estacional (índices mensuales de la serie sin tendencia)
    I(t) = componente irregular / residual

Pronóstico: Ŷ(t) = T(t) × S(t)

Este método captura simultáneamente tendencia y estacionalidad,
produciendo pronósticos más precisos para series con patrones fuertes.
"""
import numpy as np
from typing import List


def _centered_moving_average(y: np.ndarray, period: int = 12) -> np.ndarray:
    """
    Calcula el promedio móvil centrado.
    Para períodos pares (12 meses): usa el método 2×MA — promedio de dos MAs
    consecutivos para un centrado correcto.
    Para períodos impares: usa una ventana simétrica sencilla.
    """
    n = len(y)
    cma = np.full(n, np.nan)
    half = period // 2

    if period % 2 == 0:
        # Paso 1: calcula promedios móviles de longitud igual al período
        ma = np.full(n, np.nan)
        for i in range(n - period + 1):
            ma[i] = np.mean(y[i:i + period])
        # Paso 2: centra promediando dos MAs consecutivos (2×MA)
        for i in range(n - period):
            cma[i + half] = (ma[i] + ma[i + 1]) / 2
    else:
        for i in range(half, n - half):
            cma[i] = np.mean(y[i - half:i + half + 1])

    return cma


def fit_and_forecast(
    values: List[float],
    n_forecast: int,
    start_year: int,
    start_month: int,
) -> dict:
    """
    Ajusta un modelo de descomposición multiplicativa y genera pronósticos.

    Args:
        values: Valores históricos mensuales de la serie de tiempo.
        n_forecast: Cantidad de períodos futuros a pronosticar.
        start_year: Año de la primera observación.
        start_month: Mes de la primera observación (1–12).

    Returns:
        dict con valores ajustados, pronósticos, métricas y componentes estacionales.
    """
    n = len(values)
    if n < 12:
        raise ValueError("Se necesitan al menos 12 meses para la descomposición multiplicativa.")

    y = np.array(values, dtype=float)

    # Reemplaza ceros para evitar divisiones inválidas (agrega un pequeño epsilon)
    y_safe = np.where(y == 0, 0.01, y)

    # Paso 1: Promedio móvil centrado (estimación de tendencia)
    cma = _centered_moving_average(y_safe, period=12)

    # Paso 2: razones estacional-irregular
    si_ratios = y_safe / np.where(np.isnan(cma), 1.0, cma)

    # Paso 3: índices estacionales mensuales (mediana de ratios SI por mes)
    months = []
    yr, mo = start_year, start_month
    for _ in range(n):
        months.append(mo)
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1

    months = np.array(months)
    seasonal_indices = {}
    for m in range(1, 13):
        mask = months == m
        valid = si_ratios[mask & ~np.isnan(si_ratios)]
        if len(valid) > 0:
            seasonal_indices[m] = float(np.median(valid))
        else:
            seasonal_indices[m] = 1.0

    # Normaliza para que los índices sumen 12 (datos mensuales)
    si_sum = sum(seasonal_indices.values())
    if si_sum > 0:
        for m in seasonal_indices:
            seasonal_indices[m] *= 12.0 / si_sum

    # Paso 4: Desestacionaliza
    si_array = np.array([seasonal_indices[m] for m in months])
    si_array = np.where(si_array == 0, 1.0, si_array)
    y_deseason = y_safe / si_array

    # Paso 5: Ajusta tendencia lineal a la serie desestacionalizada
    t = np.arange(1, n + 1, dtype=float)
    t_mean = t.mean()
    yd_mean = y_deseason.mean()
    b = np.sum((t - t_mean) * (y_deseason - yd_mean)) / np.sum((t - t_mean) ** 2)
    a = yd_mean - b * t_mean

    trend_vals = a + b * t

    # Paso 6: Ajustado = Tendencia × Estacionalidad
    fitted = trend_vals * si_array
    # Restaura posiciones originales de cero
    fitted = np.where(y == 0, 0.0, fitted)
    fitted = np.maximum(fitted, 0)

    # Paso 7: Pronostica períodos futuros
    forecast = []
    future_months = []
    yr_f, mo_f = yr, mo
    for i in range(1, n_forecast + 1):
        t_f = n + i
        trend_f = a + b * t_f
        si_f = seasonal_indices.get(mo_f, 1.0)
        forecast.append(max(0.0, trend_f * si_f))
        future_months.append(mo_f)
        mo_f += 1
        if mo_f > 12:
            mo_f = 1

    forecast = np.array(forecast)

    # Métricas (usa y original, no y_safe)
    errors = np.abs(y - fitted)
    mae = float(np.mean(errors))
    mse = float(np.mean((y - fitted) ** 2))
    rmse = float(np.sqrt(mse))
    mean_y = float(np.mean(y)) if float(np.mean(y)) != 0 else 1.0
    accuracy = max(0.0, float((1 - mae / mean_y) * 100))

    return {
        'method_name': 'Descomposición Multiplicativa',
        'method_key': 'multiplicative_decomposition',
        'fitted': fitted.tolist(),
        'forecast': forecast.tolist(),
        'mae': round(mae, 4),
        'mse': round(mse, 4),
        'rmse': round(rmse, 4),
        'accuracy': round(accuracy, 2),
        'params': {
            'trend_intercept': round(float(a), 4),
            'trend_slope': round(float(b), 4),
            'seasonal_indices': {str(k): round(v, 4) for k, v in seasonal_indices.items()},
        },
        'description': 'Y(t) = T(t) × S(t) — tendencia lineal con estacionalidad multiplicativa',
    }
