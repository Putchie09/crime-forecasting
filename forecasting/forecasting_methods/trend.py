"""
Tendencia Lineal.

Ajusta una regresión lineal simple a la serie de tiempo y proyecta
la línea de tendencia hacia los períodos futuros.

Modelo: Y(t) = a + b*t
  donde t es el índice temporal (1, 2, 3, ...)
  a = intercepto, b = pendiente
"""
import numpy as np
from typing import List, Tuple


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Ajusta un modelo de tendencia lineal y genera pronósticos.

    Args:
        values: Valores históricos de la serie de tiempo (totales mensuales).
        n_forecast: Cantidad de períodos futuros a pronosticar.

    Returns:
        dict con claves:
            fitted: valores ajustados dentro de la muestra
            forecast: valores de pronóstico futuro
            mae: Error Medio Absoluto (DMA)
            mse: Error Cuadrático Medio
            rmse: Raíz del Error Cuadrático Medio
            accuracy: Porcentaje de precisión (1 - MAE/media)
            params: diccionario con parámetros del modelo (a, b)
    """
    n = len(values)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 períodos de datos para tendencia lineal.")

    y = np.array(values, dtype=float)
    t = np.arange(1, n + 1, dtype=float)

    # Regresión lineal OLS: b = Σ(t*y) - n*t̄*ȳ / (Σt² - n*t̄²)
    t_mean = t.mean()
    y_mean = y.mean()

    b = np.sum((t - t_mean) * (y - y_mean)) / np.sum((t - t_mean) ** 2)
    a = y_mean - b * t_mean

    # Valores ajustados (en la muestra)
    fitted = a + b * t

    # Pronóstico futuro
    t_future = np.arange(n + 1, n + n_forecast + 1, dtype=float)
    forecast = a + b * t_future

    # Limita pronósticos negativos a cero (no pueden existir crímenes negativos)
    fitted = np.maximum(fitted, 0)
    forecast = np.maximum(forecast, 0)

    # Métricas (excluyendo el primer valor para evitar sesgo de inicialización)
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
