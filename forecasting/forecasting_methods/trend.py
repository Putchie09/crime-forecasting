"""
Tendencia Lineal.

Calcula una línea de tendencia a partir de los datos históricos
y la utiliza para estimar períodos futuros.

Modelo: Y(t) = a + b*t
"""
import numpy as np
from typing import List, Tuple


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Calcula la tendencia lineal y genera pronósticos futuros.
    """
    n = len(values)
    if n < 2:
        raise ValueError("Se necesitan al menos 2 períodos de datos para tendencia lineal.")

    y = np.array(values, dtype=float)
    t = np.arange(1, n + 1, dtype=float) # Asigna un número consecutivo a cada período

    # Promedios utilizados para calcular la recta de tendencia
    t_mean = t.mean()
    y_mean = y.mean()

    # Calcula la pendiente de la línea de tendencia
    b = np.sum((t - t_mean) * (y - y_mean)) / np.sum((t - t_mean) ** 2)
    a = y_mean - b * t_mean # Calcula el punto donde inicia la recta de tendencia

    # Valores estimados para los datos históricos
    fitted = a + b * t

    # Pronósticos futuros
    t_future = np.arange(n + 1, n + n_forecast + 1, dtype=float)
    forecast = a + b * t_future # Proyecta la tendencia hacia los períodos futuros

    # Evita valores negativos
    fitted = np.maximum(fitted, 0)
    forecast = np.maximum(forecast, 0)

    # Cálculo de métricas
    errors = np.abs(y - fitted) # Diferencia entre los valores reales y los estimados
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
