"""
Suavizamiento Exponencial Simple (Simple Exponential Smoothing).

Asigna pesos decrecientes exponencialmente a las observaciones pasadas.
Las observaciones recientes tienen más peso que las antiguas.

Modelo: S(t) = α·Y(t) + (1-α)·S(t-1)
  donde α ∈ (0, 1) es el parámetro de suavizado.

El α óptimo se encuentra minimizando la suma de errores cuadrados.
"""

import numpy as np
from scipy.optimize import minimize_scalar
from typing import List


def _compute_smoothed(values: np.ndarray, alpha: float) -> np.ndarray:
    """Calcula la serie suavizada exponencialmente."""
    n = len(values)
    smoothed = np.zeros(n)
    smoothed[0] = values[0]  # Inicializa con la primera observación
    for t in range(1, n):
        smoothed[t] = alpha * values[t] + (1 - alpha) * smoothed[t - 1]
    return smoothed


def _sse(alpha: float, values: np.ndarray) -> float:
    """Suma de errores cuadrados para la optimización."""
    smoothed = _compute_smoothed(values, alpha)
    errors = values[1:] - smoothed[:-1]  # errores de un paso adelante
    return float(np.sum(errors ** 2))


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Ajusta un modelo de suavizamiento exponencial con α óptimo y genera pronósticos.

    Args:
        values: Valores históricos de la serie de tiempo.
        n_forecast: Cantidad de períodos futuros a pronosticar.

    Returns:
        dict con valores ajustados, pronósticos, métricas y parámetros.
    """
    n = len(values)
    if n < 3:
        raise ValueError("Se necesitan al menos 3 períodos de datos para suavizamiento exponencial.")

    y = np.array(values, dtype=float)

    # Encuentra el α óptimo con optimización acotada
    result = minimize_scalar(
        _sse,
        args=(y,),
        bounds=(0.01, 0.99),
        method='bounded',
        options={'xatol': 1e-6},
    )
    alpha = float(result.x)

    # Calcula la serie suavizada
    smoothed = _compute_smoothed(y, alpha)

    # Valores ajustados dentro de la muestra (pronósticos de un paso adelante)
    fitted = np.zeros(n)
    fitted[0] = smoothed[0]
    fitted[1:] = smoothed[:-1]

    # Pronóstico futuro: todos los períodos usan el último valor suavizado
    last_smooth = smoothed[-1]
    forecast = np.full(n_forecast, last_smooth)

    # Elimina valores negativos
    fitted = np.maximum(fitted, 0)
    forecast = np.maximum(forecast, 0)

    # Errores de un paso adelante: y[t] vs smoothed[t-1], excluyendo t=0 porque
    # fitted[0] == y[0] por construcción y eso reduciría artificialmente el MAE.
    osa_errors = y[1:] - smoothed[:-1]
    mae = float(np.mean(np.abs(osa_errors)))
    mse = float(np.mean(osa_errors ** 2))
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
