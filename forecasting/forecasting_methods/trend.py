"""
Tendencia Lineal (Linear Trend) Forecasting Method.

Fits a simple linear regression to the time series and projects
the trend line into future periods.

Model: Y(t) = a + b*t
  where t is the time period index (1, 2, 3, ...)
  a = intercept, b = slope
"""

import numpy as np
from typing import List, Tuple


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Fit a linear trend model and generate forecasts.

    Args:
        values: Historical time series values (monthly totals).
        n_forecast: Number of future periods to forecast.

    Returns:
        dict with keys:
            fitted: in-sample fitted values
            forecast: future forecast values
            mae: Mean Absolute Error (DMA)
            mse: Mean Squared Error
            rmse: Root Mean Squared Error
            accuracy: Accuracy percentage (1 - MAE/mean)
            params: dict with model parameters (a, b)
    """
    n = len(values)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 períodos de datos para tendencia lineal.")

    y = np.array(values, dtype=float)
    t = np.arange(1, n + 1, dtype=float)

    # OLS linear regression: b = Σ(t*y) - n*t̄*ȳ / (Σt² - n*t̄²)
    t_mean = t.mean()
    y_mean = y.mean()

    b = np.sum((t - t_mean) * (y - y_mean)) / np.sum((t - t_mean) ** 2)
    a = y_mean - b * t_mean

    # Fitted (in-sample) values
    fitted = a + b * t

    # Future forecast
    t_future = np.arange(n + 1, n + n_forecast + 1, dtype=float)
    forecast = a + b * t_future

    # Clip negative forecasts to zero (crime counts can't be negative)
    fitted = np.maximum(fitted, 0)
    forecast = np.maximum(forecast, 0)

    # Metrics (excluding first value to avoid initialization bias)
    errors = np.abs(y - fitted)
    mae = float(np.mean(errors))
    mse = float(np.mean((y - fitted) ** 2))
    rmse = float(np.sqrt(mse))
    mean_y = y_mean if y_mean != 0 else 1.0
    accuracy = max(0.0, float((1 - mae / mean_y) * 100))

    return {
        'method_name': 'Tendencia Lineal',
        'method_key': 'linear_trend',
        'fitted': fitted.tolist(),
        'forecast': forecast.tolist(),
        'mae': round(mae, 4),
        'mse': round(mse, 4),
        'rmse': round(rmse, 4),
        'accuracy': round(accuracy, 2),
        'params': {
            'intercept_a': round(float(a), 4),
            'slope_b': round(float(b), 4),
        },
        'description': f'Y(t) = {a:.2f} + {b:.2f}×t',
    }
