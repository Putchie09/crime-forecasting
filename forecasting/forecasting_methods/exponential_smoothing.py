"""
Suavizamiento Exponencial Simple.

Asigna pesos decrecientes exponencialmente a las observaciones pasadas.
Las observaciones recientes tienen más peso que las antiguas.

Modelo: S(t) = α·Y(t) + (1-α)·S(t-1), donde
  
  Y(t) = es el dato real actual
  S(t) = valor suavizado
  α = peso
  
  α alto = reacciona rápido a los cambios
  α bajo = más estable y suave
"""

import numpy as np
from scipy.optimize import minimize_scalar
from typing import List


def _compute_smoothed(values: np.ndarray, alpha: float) -> np.ndarray:
    """Calcula la serie suavizada exponencialmente."""
    n = len(values)
    smoothed = np.zeros(n)
    smoothed[0] = values[0]  # El primer dato suavizado = primer dato real
    for t in range(1, n):
        smoothed[t] = alpha * values[t] + (1 - alpha) * smoothed[t - 1]
    return smoothed


def _sse(alpha: float, values: np.ndarray) -> float:
    """Calcula el error total para un α específico"""
    smoothed = _compute_smoothed(values, alpha) # generar serie suavizada
    errors = values[1:] - smoothed[:-1]  # calcular error: valor real actual - pronóstico anterior
    return float(np.sum(errors ** 2)) # eleva los errores al cuadrado y los suma


def fit_and_forecast(values: List[float], n_forecast: int) -> dict:
    """
    Ajusta un modelo de suavizamiento exponencial con α y genera pronósticos.

    Args:
        values: Valores históricos de la serie de tiempo.
        n_forecast: Cantidad de períodos futuros a pronosticar.

    Returns:
        dict con valores ajustados, pronósticos, métricas y parámetros.
    """
    
    # validar datos entrantes
    n = len(values)
    if n < 3:
        raise ValueError("Se necesitan al menos 3 períodos de datos para suavizamiento exponencial.")

    y = np.array(values, dtype=float) # convierte la lista a una lista de numpy (más eficiente)

    # Buscar α que minimice el error
    result = minimize_scalar(
        _sse,
        args=(y,),
        bounds=(0.01, 0.99), # α solo puede estar entre 0 y 1
        method='bounded',
        options={'xatol': 1e-6},
    )
    alpha = float(result.x)

    # Calcula la serie suavizada con el α encontrado
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

    # Errores de un paso adelante
    osa_errors = y[1:] - smoothed[:-1]
    mae = float(np.mean(np.abs(osa_errors))) # error absoluto promedio
    mse = float(np.mean(osa_errors ** 2)) # error cuandrático promedio
    rmse = float(np.sqrt(mse)) 
    mean_y = float(np.mean(y)) if np.mean(y) != 0 else 1.0

    #Error promedio dividido entre el promedio de los datos,
    #se resta de 1 y se pasa a porcentaje. Si da negativo, se pone 0
    accuracy = max(0.0, float((1 - mae / mean_y) * 100))

    return {
        'method_name': 'Suavizamiento Exponencial',
        'method_key': 'exponential_smoothing',
        'fitted': fitted.tolist(), # pronósticos que el modelo habría hecho para los datos que ya ocurrieron
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
