"""
Descomposición multiplicativa

Este método separa una serie de tiempo en tendencia, estacionalidad
y variaciones:

    Y(t) = T(t) × S(t) × I(t)

La idea es quitar primero el efecto estacional, calcular una tendencia
con los datos más estables y luego volver a aplicar la estacionalidad
para generar el pronóstico.

Pronóstico:
    Ŷ(t) = T(t) × S(t)

"""
import numpy as np
from typing import List


def _centered_moving_average(y: np.ndarray, period: int = 12) -> np.ndarray:
    """
    Calcula el promedio móvil centrado

    Cuando el período es par, como ocurre con 12 meses, el promedio móvil
    queda entre dos posiciones. Por eso se promedian dos promedios móviles
    seguidos para centrar mejor el valor

    Cuando el período es impar, se usa una ventana normal alrededor del dato
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
        Ajusta un modelo de descomposición multiplicativa y genera pronósticos

        Args o parametros:
            values: datos históricos mensuales de la serie de tiempo
            n_forecast: cantidad de períodos futuros a pronosticar
            start_year: Año de la primera observación
            start_month: Mes de la primera observación, de 1 a 12

        Retorna:
            Un diccionario con los valores ajustados, los pronósticos,
            las métricas de error y los índices estacionales calculados
    """
    n = len(values)
    if n < 12:
        raise ValueError("Se necesitan al menos 12 meses para la descomposición multiplicativa.")

    y = np.array(values, dtype=float)

    # Se usa un valor pequeño en lugar de cero para evitar divisiones entre cero
    y_safe = np.where(y == 0, 0.01, y)

    # Paso 1: se calcula el promedio móvil centrado para estimar la tendencia inicial
    cma = _centered_moving_average(y_safe, period=12)

    # Paso 2: se obtienen los cocientes que combinan estacionalidad e irregularidad
    si_ratios = y_safe / np.where(np.isnan(cma), 1.0, cma)

    # Paso 3: para cada mes se calcula un índice estacional usando los cocientes válidos
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

    # Los índices se ajustan para que en conjunto representen un año completo, es decir sumen 12 (meses)
    si_sum = sum(seasonal_indices.values())
    if si_sum > 0:
        for m in seasonal_indices:
            seasonal_indices[m] *= 12.0 / si_sum

    # Paso 4: se quita el efecto estacional dividiendo cada dato entre su índice
    si_array = np.array([seasonal_indices[m] for m in months])
    si_array = np.where(si_array == 0, 1.0, si_array)
    y_deseason = y_safe / si_array

    # Paso 5: con la serie sin estacionalidad se calcula la recta de tendencia
    t = np.arange(1, n + 1, dtype=float)
    t_mean = t.mean()
    yd_mean = y_deseason.mean()
    b = np.sum((t - t_mean) * (y_deseason - yd_mean)) / np.sum((t - t_mean) ** 2)
    a = yd_mean - b * t_mean

    trend_vals = a + b * t

    # Paso 6: se reconstruyen los valores ajustados combinando tendencia y estacionalidad
    # Ajustado = Tendencia × Estacionalidad
    fitted = trend_vals * si_array
    # Restaura posiciones originales de cero
    fitted = np.where(y == 0, 0.0, fitted)
    fitted = np.maximum(fitted, 0)

    # Paso 7: se generan los pronósticos futuros usando la tendencia y el índice del mes correspondiente
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

    # Las métricas se calculan comparando los datos reales con los valores ajustados
    # Se usa y original, no y_safe
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
