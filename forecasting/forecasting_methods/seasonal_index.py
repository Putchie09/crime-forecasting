"""
Método de índices estacionales sin tendencia.

Calcula cuánto suele subir o bajar cada mes respecto al promedio general.
Luego usa esos índices para pronosticar los meses futuros.

Índice estacional = promedio del mes / promedio general

Un índice mayor a 1 indica que ese mes suele estar por encima del promedio.
Un índice menor a 1 indica que ese mes suele estar por debajo del promedio.
"""

import numpy as np
from typing import List

# Función que ajusta el modelo y pronostica los meses futuros
def fit_and_forecast(
    values: List[float],
    n_forecast: int,
    start_year: int,
    start_month: int,
) -> dict:
    
    n = len(values)

    # Validación de cantidad mínima de datos
    if n < 12:
        raise ValueError("Se necesitan al menos 12 meses de datos para calcular índices estacionales.")

    y = np.array(values, dtype=float) 

    # Se identifica a qué mes pertenece cada dato histórico
    months = []
    mo = start_month

    for _ in range(n):
        months.append(mo)
        mo += 1

        if mo > 12:
            mo = 1

    months = np.array(months) # array de meses correspondientes a cada dato histórico (1-12)

    # Promedio general de todos los datos
    overall_mean = np.mean(y) if np.mean(y) != 0 else 1.0

    # Índice estacional de cada mes:
    # promedio del mes / promedio general
    seasonal_indices = {}

    for m in range(1, 13): # para cada mes del año
        mask = months == m

        if mask.any():
            seasonal_indices[m] = float(np.mean(y[mask])) / overall_mean #calcula el promedio del mes y lo divide por el promedio general.
        else:
            seasonal_indices[m] = 1.0

    # Valores ajustados para comparar contra los datos históricos
    fitted = []

    for m in months:
        fitted.append(overall_mean * seasonal_indices[m]) # multiplica el promedio general por el índice estacional del mes correspondiente para obtener el valor ajustado para ese mes.

    fitted = np.array(fitted)
    fitted = np.maximum(fitted, 0)

    # Pronóstico de meses futuros
    forecast = []
    future_months = []

    mo_f = mo

    # Para cada mes futuro a pronosticar, se calcula el pronóstico multiplicando el promedio general por el índice estacional del mes correspondiente.
    for _ in range(n_forecast):
        si_f = seasonal_indices.get(mo_f, 1.0) # obtiene el índice estacional del mes futuro, o 1.0 si no existe
        forecast.append(max(0.0, overall_mean * si_f)) 
        future_months.append(mo_f)

        mo_f += 1
        if mo_f > 12:
            mo_f = 1

    forecast = np.array(forecast)

    # Métricas de error
    errors = np.abs(y - fitted) # se restan los valores ajustados a los datos históricos para obtener los errores absolutos
    mae = float(np.mean(errors))
    mse = float(np.mean((y - fitted) ** 2))
    rmse = float(np.sqrt(mse))
    accuracy = max(0.0, float((1 - mae / overall_mean) * 100))

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
            'overall_mean': round(float(overall_mean), 4),
            'seasonal_indices': {str(k): round(v, 4) for k, v in seasonal_indices.items()},
        },
        'description': 'Índices estacionales mensuales sin tendencia',
    }