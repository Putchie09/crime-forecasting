"""
Descomposición Multiplicativa (Multiplicative Decomposition).

Decomposes the time series into three components:
    Y(t) = T(t) × S(t) × I(t)
  where:
    T(t) = Trend component (linear regression on centered moving average)
    S(t) = Seasonal component (monthly indices from de-trended series)
    I(t) = Irregular / residual component

Forecast: Ŷ(t) = T(t) × S(t)

This method captures both trend and seasonality simultaneously,
producing more precise forecasts for series with strong patterns.
"""

import numpy as np
from typing import List


def _centered_moving_average(y: np.ndarray, period: int = 12) -> np.ndarray:
    """
    Compute centered moving average.
    For even period (12 months): uses the 2×MA approach — average two consecutive
    period-length MAs for proper centering (standard textbook method).
    For odd period: simple symmetric window.
    """
    n = len(y)
    cma = np.full(n, np.nan)
    half = period // 2

    if period % 2 == 0:
        # Step 1: compute period-length moving averages
        ma = np.full(n, np.nan)
        for i in range(n - period + 1):
            ma[i] = np.mean(y[i:i + period])
        # Step 2: center by averaging two consecutive MAs (2×MA)
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
    Fit a multiplicative decomposition model and generate forecasts.

    Args:
        values: Historical monthly time series values.
        n_forecast: Number of future periods to forecast.
        start_year: Year of the first observation.
        start_month: Month of the first observation (1–12).

    Returns:
        dict with fitted values, forecasts, metrics, and seasonal components.
    """
    n = len(values)
    if n < 12:
        raise ValueError("Se necesitan al menos 12 meses para la descomposición multiplicativa.")

    y = np.array(values, dtype=float)

    # Replace zeros to avoid division issues (add small epsilon)
    y_safe = np.where(y == 0, 0.01, y)

    # Step 1: Centered Moving Average (trend estimate)
    cma = _centered_moving_average(y_safe, period=12)

    # Step 2: Seasonal-Irregular ratios
    si_ratios = y_safe / np.where(np.isnan(cma), 1.0, cma)

    # Step 3: Monthly seasonal indices (median of SI ratios for each month)
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

    # Normalize so indices sum to 12 (monthly data)
    si_sum = sum(seasonal_indices.values())
    if si_sum > 0:
        for m in seasonal_indices:
            seasonal_indices[m] *= 12.0 / si_sum

    # Step 4: De-seasonalize
    si_array = np.array([seasonal_indices[m] for m in months])
    si_array = np.where(si_array == 0, 1.0, si_array)
    y_deseason = y_safe / si_array

    # Step 5: Fit linear trend to de-seasonalized series
    t = np.arange(1, n + 1, dtype=float)
    t_mean = t.mean()
    yd_mean = y_deseason.mean()
    b = np.sum((t - t_mean) * (y_deseason - yd_mean)) / np.sum((t - t_mean) ** 2)
    a = yd_mean - b * t_mean

    trend_vals = a + b * t

    # Step 6: Fitted = Trend × Seasonal
    fitted = trend_vals * si_array
    # Restore original zero positions
    fitted = np.where(y == 0, 0.0, fitted)
    fitted = np.maximum(fitted, 0)

    # Step 7: Forecast future periods
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

    # Metrics (use original y, not y_safe)
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
