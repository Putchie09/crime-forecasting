"""
Suavizamiento Exponencial Simple (Simple Exponential Smoothing).

Assigns exponentially decreasing weights to past observations.
Recent observations receive more weight than older ones.

Model: S(t) = α·Y(t) + (1-α)·S(t-1)
  where α ∈ (0, 1) is the smoothing parameter.

The optimal α is found by minimizing the Sum of Squared Errors.
"""

import numpy as np
from scipy.optimize import minimize_scalar
from typing import List


def _compute_smoothed(values: np.ndarray, alpha: float) -> np.ndarray:
    """Compute exponentially smoothed series."""
    n = len(values)
    smoothed = np.zeros(n)
    smoothed[0] = values[0]  # Initialize with first observation
    for t in range(1, n):
        smoothed[t] = alpha * values[t] + (1 - alpha) * smoothed[t - 1]
    return smoothed


def _sse(alpha: float, values: np.ndarray) -> float:
    """Sum of Squared Errors for optimization."""
    smoothed = _compute_smoothed(values, alpha)
    errors = values[1:] - smoothed[:-1]  # one-step-ahead errors
    return float(np.sum(errors ** 2))


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Fit an exponential smoothing model with optimal alpha and generate forecasts.

    Args:
        values: Historical time series values.
        n_forecast: Number of future periods to forecast.

    Returns:
        dict with fitted values, forecasts, metrics, and parameters.
    """
    n = len(values)
    if n < 3:
        raise ValueError("Se necesitan al menos 3 períodos de datos para suavizamiento exponencial.")

    y = np.array(values, dtype=float)

    # Find optimal alpha via bounded optimization
    result = minimize_scalar(
        _sse,
        args=(y,),
        bounds=(0.01, 0.99),
        method='bounded',
        options={'xatol': 1e-6},
    )
    alpha = float(result.x)

    # Compute smoothed series
    smoothed = _compute_smoothed(y, alpha)

    # In-sample fitted values (one-step-ahead forecasts)
    fitted = np.zeros(n)
    fitted[0] = smoothed[0]
    fitted[1:] = smoothed[:-1]

    # Future forecast: all periods receive the last smoothed value
    last_smooth = smoothed[-1]
    forecast = np.full(n_forecast, last_smooth)

    # Clip negatives
    fitted = np.maximum(fitted, 0)
    forecast = np.maximum(forecast, 0)

    # Metrics over all points (consistent with other methods)
    errors = np.abs(y - fitted)
    mae = float(np.mean(errors))
    mse = float(np.mean((y - fitted) ** 2))
    rmse = float(np.sqrt(mse))
    mean_y = float(np.mean(y)) if np.mean(y) != 0 else 1.0
    accuracy = max(0.0, float((1 - mae / mean_y) * 100))

    return {
        'method_name': 'Suavizamiento Exponencial',
        'method_key': 'exponential_smoothing',
        'fitted': fitted.tolist(),
        'forecast': forecast.tolist(),
        'mae': round(mae, 4),
        'mse': round(mse, 4),
        'rmse': round(rmse, 4),
        'accuracy': round(accuracy, 2),
        'params': {
            'alpha': round(alpha, 4),
            'initial_value': round(float(y[0]), 4),
            'last_smoothed': round(float(last_smooth), 4),
        },
        'description': f'α = {alpha:.4f} (optimizado por mínimos cuadrados)',
    }
