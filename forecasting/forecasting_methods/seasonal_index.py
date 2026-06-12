"""
Índices Estacionales (Seasonal Indices) Forecasting Method.

Identifies recurring monthly patterns (seasonality) by computing
the ratio of each month's average to the overall average.

Steps:
  1. Compute the overall mean of the series.
  2. Compute the monthly average for each calendar month.
  3. Seasonal index(m) = monthly_avg(m) / overall_mean
  4. De-seasonalize the series, fit a linear trend.
  5. Forecast = Trend(t) × SeasonalIndex(month)
"""

import numpy as np
from typing import List
from datetime import date


def fit_and_forecast(
    values: List[float],
    n_forecast: int,
    start_year: int,
    start_month: int,
) -> dict:
    """
    Fit seasonal index model and generate forecasts.

    Args:
        values: Historical monthly time series values.
        n_forecast: Number of future periods to forecast.
        start_year: Year of the first observation.
        start_month: Month of the first observation (1–12).

    Returns:
        dict with fitted values, forecasts, metrics, and parameters.
    """
    n = len(values)
    if n < 12:
        raise ValueError("Se necesitan al menos 12 meses de datos para calcular índices estacionales.")

    y = np.array(values, dtype=float)

    # Build month indices for each observation
    months = []
    yr, mo = start_year, start_month
    for _ in range(n):
        months.append(mo)
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1

    months = np.array(months)

    # Compute seasonal indices (1–12)
    overall_mean = np.mean(y) if np.mean(y) != 0 else 1.0
    seasonal_indices = {}
    for m in range(1, 13):
        mask = months == m
        if mask.any():
            seasonal_indices[m] = float(np.mean(y[mask])) / overall_mean
        else:
            seasonal_indices[m] = 1.0  # No data for this month → neutral index

    # De-seasonalize
    si_array = np.array([seasonal_indices[m] for m in months])
    si_array = np.where(si_array == 0, 1.0, si_array)
    y_deseason = y / si_array

    # Fit linear trend to de-seasonalized series
    t = np.arange(1, n + 1, dtype=float)
    t_mean = t.mean()
    yd_mean = y_deseason.mean()
    b = np.sum((t - t_mean) * (y_deseason - yd_mean)) / np.sum((t - t_mean) ** 2)
    a = yd_mean - b * t_mean

    trend_fitted = a + b * t

    # Re-apply seasonal indices to get fitted values
    fitted = trend_fitted * si_array
    fitted = np.maximum(fitted, 0)

    # Forecast future periods
    forecast = []
    future_months = []
    yr_f, mo_f = yr, mo  # continues from where the series ended
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

    # Metrics
    errors = np.abs(y - fitted)
    mae = float(np.mean(errors))
    mse = float(np.mean((y - fitted) ** 2))
    rmse = float(np.sqrt(mse))
    mean_y = overall_mean if overall_mean != 0 else 1.0
    accuracy = max(0.0, float((1 - mae / mean_y) * 100))

    return {
        'method_name': 'Índices Estacionales',
        'method_key': 'seasonal_index',
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
        'description': 'Tendencia lineal con índices estacionales mensuales',
    }
