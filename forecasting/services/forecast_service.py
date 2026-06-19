"""
Servicio principal de pronósticos.

Obtiene los datos históricos, ejecuta los modelos de pronóstico,
compara los resultados y devuelve la información que se mostrará
al usuario.
"""

import logging

import numpy as np

from forecasting.models import MonthlySeries
from forecasting.services.data_service import get_global_series_range
from forecasting.forecasting_methods import (
    trend,
    exponential_smoothing,
    seasonal_index,
    multiplicative_decomposition,
)

logger = logging.getLogger(__name__)

ALL_DELITOS_TOKEN = '__ALL__'
ALL_CANTONS_TOKEN = '__ALL_CANTONS__'

MONTH_NAMES_ES = {
    1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr',
    5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago',
    9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic',
}

MONTH_NAMES_FULL_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Setiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre',
}

# ── Umbrales para clasificar la frecuencia de los delitos ────────────────────
# Promedio mensual de delitos que determina qué modelo se aplica por tipo de delito.
FREQ_LOW_THRESHOLD = 1.0     # # Menos de 1 caso por mes  (Tendencia Lineal o promedio)
FREQ_MEDIUM_THRESHOLD = 5.0  # Entre 1 y 5 casos por mes 
                             # Más de 5 casos por mes (todos los 4 modelos, mejor por MAE)


def _add_months(year: int, month: int, delta: int):
    """Suma delta meses a (año, mes) y devuelve (nuevo_año, nuevo_mes)."""
    total_months = (year - 1) * 12 + (month - 1) + delta
    return (total_months // 12 + 1, total_months % 12 + 1)


def _get_all_delitos_series(canton: str) -> list:
    """
    Construye una serie mensual rellena con ceros que suma todos los tipos de delito para el cantón.

    La serie se extiende desde el primer mes con delitos del cantón hasta el
    final del conjunto de datos global (no solo hasta el último mes con delitos del cantón),
    asegurando que los ceros finales estén incluidos para los meses sin registros.
    """
    from django.db.models import Sum

    qs = (
        MonthlySeries.objects.exclude(canton='DESCONOCIDO')
        if canton.upper() == ALL_CANTONS_TOKEN
        else MonthlySeries.objects.filter(canton=canton.upper())
    )
    rows = list(
        qs.values('year', 'month')
        .annotate(total=Sum('total_delitos'))
        .order_by('year', 'month')
    )
    if not rows:
        return []

    data_map = {(r['year'], r['month']): r['total'] for r in rows}
    start_year, start_month = rows[0]['year'], rows[0]['month']

    global_range = get_global_series_range()
    if global_range:
        end_year, end_month = global_range['max_year'], global_range['max_month']
    else:
        end_year, end_month = rows[-1]['year'], rows[-1]['month']

    series = []
    yr, mo = start_year, start_month
    while (yr, mo) <= (end_year, end_month):
        series.append({
            'year': yr,
            'month': mo,
            'total_delitos': data_map.get((yr, mo), 0),
            'label': f"{yr}-{mo:02d}",
        })
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1
    return series


def _compute_delito_composition(canton: str) -> list:
    """Devuelve lista de diccionarios {delito, total, pct} para el cantón, ordenada por total descendente."""
    from django.db.models import Sum

    qs = (
        MonthlySeries.objects.exclude(canton='DESCONOCIDO')
        if canton.upper() == ALL_CANTONS_TOKEN
        else MonthlySeries.objects.filter(canton=canton.upper())
    )
    rows = list(
        qs.values('delito')
        .annotate(total=Sum('total_delitos'))
        .order_by('-total')
    )
    grand_total = sum(r['total'] for r in rows)
    if grand_total == 0:
        return []
    return [
        {
            'delito': r['delito'].title(),
            'total': r['total'],
            'pct': round(r['total'] / grand_total * 100, 1),
        }
        for r in rows
    ]


def get_time_series(canton: str, delito: str) -> list:
    """
    Consulta MonthlySeries para un cantón y tipo de delito específicos.
    Devuelve una lista de diccionarios: {year, month, total_delitos, label}.

    Rellena con ceros cada mes calendario desde el primer evento de este
    grupo canton/delito hasta el final del conjunto de datos global — no solo
    hasta el último evento. Esto asegura que la serie incluya meses cero finales
    (p.ej. si no ocurrió ningún delito de este tipo en los últimos 18 meses)
    para que los modelos no entrenen con un punto final erróneamente optimista.
    """
    if delito.upper() == ALL_DELITOS_TOKEN:
        return _get_all_delitos_series(canton)

    from django.db.models import Sum

    if canton.upper() == ALL_CANTONS_TOKEN:
        agg_rows = list(
            MonthlySeries.objects.exclude(canton='DESCONOCIDO')
            .filter(delito=delito.upper())
            .values('year', 'month')
            .annotate(total=Sum('total_delitos'))
            .order_by('year', 'month')
        )
        if not agg_rows:
            return []
        data_map = {(r['year'], r['month']): r['total'] for r in agg_rows}
        start_year, start_month = agg_rows[0]['year'], agg_rows[0]['month']
        fallback_end = (agg_rows[-1]['year'], agg_rows[-1]['month'])
    else:
        records = list(
            MonthlySeries.objects.filter(
                canton=canton.upper(),
                delito=delito.upper(),
            ).order_by('year', 'month')
        )
        if not records:
            return []
        data_map = {(rec.year, rec.month): rec.total_delitos for rec in records}
        start_year, start_month = records[0].year, records[0].month
        fallback_end = (records[-1].year, records[-1].month)

    global_range = get_global_series_range()
    if global_range:
        end_year, end_month = global_range['max_year'], global_range['max_month']
    else:
        end_year, end_month = fallback_end

    series = []
    yr, mo = start_year, start_month
    while (yr, mo) <= (end_year, end_month):
        series.append({
            'year': yr,
            'month': mo,
            'total_delitos': data_map.get((yr, mo), 0),
            'label': f"{yr}-{mo:02d}",
        })
        mo += 1
        if mo > 12:
            mo = 1
            yr += 1

    return series


# ── Bottom-Up helpers ─────────────────────────────────────────────────────────

def _get_crime_types_for_canton(canton: str) -> list:
    """Devuelve la lista ordenada de tipos de delito distintos para el cantón (o toda la provincia)."""
    if canton.upper() == ALL_CANTONS_TOKEN:
        return list(
            MonthlySeries.objects.exclude(canton='DESCONOCIDO')
            .values_list('delito', flat=True)
            .distinct()
            .order_by('delito')
        )
    return list(
        MonthlySeries.objects.filter(canton=canton.upper())
        .values_list('delito', flat=True)
        .distinct()
        .order_by('delito')
    )


def _classify_series(mean_monthly: float) -> str:
    """Clasifica una serie temporal según su volumen medio mensual."""
    if mean_monthly < FREQ_LOW_THRESHOLD:
        return 'baja'
    if mean_monthly < FREQ_MEDIUM_THRESHOLD:
        return 'media'
    return 'alta'


def _run_all_models_and_pick_best(
    values: list, n_months: int, series_start_year: int, series_start_month: int
) -> tuple:
    """Ejecuta los cuatro modelos; devuelve (best_result, best_key) o (None, None) en caso de falla total."""
    candidates = {}
    for key, fn, extra_args in [
        ('linear_trend', trend.fit_and_forecast, []),
        ('exponential_smoothing', exponential_smoothing.fit_and_forecast, []),
        ('seasonal_index', seasonal_index.fit_and_forecast, [series_start_year, series_start_month]),
        ('multiplicative_decomposition', multiplicative_decomposition.fit_and_forecast, [series_start_year, series_start_month]),
    ]:
        try:
            candidates[key] = fn(values, n_months, *extra_args)
        except Exception:
            pass
    if not candidates:
        return None, None
    best_key = min(candidates, key=lambda k: candidates[k]['mae'])
    return candidates[best_key], best_key


def _forecast_for_crime_type(
    values: list, freq_class: str, n_months: int,
    series_start_year: int, series_start_month: int
) -> tuple:
    """
    Aplica el modelo apropiado según la clase de frecuencia de la serie.
    Devuelve (result_dict, model_key) o (None, None) si ningún modelo pudo ajustarse.
    """
    y = np.array(values, dtype=float)

    if freq_class == 'baja':
        try:
            return trend.fit_and_forecast(values, n_months), 'linear_trend'
        except Exception:
            pass
        # Recurso alternativo: pronóstico plano con la media histórica
        avg = float(np.mean(y)) if len(y) > 0 else 0.0
        fitted = np.full(len(y), avg)
        errors = y - fitted
        mae = float(np.mean(np.abs(errors)))
        mse = float(np.mean(errors ** 2))
        return {
            'method_name': 'Promedio Histórico',
            'method_key': 'historical_mean',
            'fitted': fitted.tolist(),
            'forecast': [max(0.0, avg)] * n_months,
            'mae': round(mae, 4),
            'mse': round(mse, 4),
            'rmse': round(float(np.sqrt(mse)), 4),
            'accuracy': 0.0,
        }, 'historical_mean'

    if freq_class == 'media':
        try:
            return exponential_smoothing.fit_and_forecast(values, n_months), 'exponential_smoothing'
        except Exception:
            pass
        # Recurso alternativo: tendencia lineal
        try:
            return trend.fit_and_forecast(values, n_months), 'linear_trend'
        except Exception:
            pass
        return None, None

    # 'alta' — ejecutar los cuatro modelos y elegir el mejor por DMA
    return _run_all_models_and_pick_best(values, n_months, series_start_year, series_start_month)


def run_all_crime_types_forecast(canton: str, n_months: int) -> dict:
    """
    Pronóstico agregado Bottom-Up para todos los tipos de delito en un cantón (o toda la provincia).

    Pasos:
      1. Enumerar todos los tipos de delito con registros en el cantón.
      2. Clasificar cada serie por volumen mensual (baja / media / alta).
      3. Aplicar el modelo apropiado según la clase.
      4. Sumar los pronósticos individuales → total Bottom-Up.
      5. Devolver resultados estructurados para la plantilla.
    """
    is_all_cantons = canton.upper() == ALL_CANTONS_TOKEN
    display_canton = 'Provincia de Alajuela' if is_all_cantons else canton.title()

    crime_types = _get_crime_types_for_canton(canton)
    if not crime_types:
        return {
            'error': f'No se encontraron datos para {display_canton}.',
            'series': [],
        }

    aggregate_series = _get_all_delitos_series(canton)
    if not aggregate_series:
        return {
            'error': f'No se pudieron obtener datos históricos para {display_canton}.',
            'series': [],
        }

    historical_labels = [row['label'] for row in aggregate_series]
    historical_values = [row['total_delitos'] for row in aggregate_series]
    last_year = aggregate_series[-1]['year']
    last_month = aggregate_series[-1]['month']

    # Construye las etiquetas del período de pronóstico
    forecast_labels = []
    yr, mo = last_year, last_month
    for _ in range(n_months):
        yr, mo = _add_months(yr, mo, 1)
        forecast_labels.append(f"{yr}-{mo:02d}")

    bottom_up = np.zeros(n_months)
    breakdown = []
    warnings = []

    for delito in crime_types:
        series_data = get_time_series(canton, delito)
        if not series_data:
            warnings.append(f"Sin datos históricos para '{delito.title()}' — omitido.")
            continue

        values = [row['total_delitos'] for row in series_data]
        if len(values) < 2:
            warnings.append(f"'{delito.title()}' tiene menos de 2 períodos de datos — omitido.")
            continue

        series_start_year = series_data[0]['year']
        series_start_month = series_data[0]['month']
        mean_monthly = float(np.mean(values))
        freq_class = _classify_series(mean_monthly)

        result, model_key = _forecast_for_crime_type(
            values, freq_class, n_months, series_start_year, series_start_month
        )

        if result is None:
            warnings.append(f"'{delito.title()}' no pudo ser modelado — omitido.")
            continue

        forecast_vals = np.array(result['forecast'])
        bottom_up += forecast_vals

        breakdown.append({
            'crime_type': delito.title(),
            'model_used': result['method_name'],
            'model_key': model_key,
            'dma': result['mae'],
            'forecast_avg': round(float(np.mean(forecast_vals)), 2),
            'frequency_class': freq_class,
            'contribution_pct': 0.0,
        })

        if freq_class == 'baja':
            warnings.append(
                f"'{delito.title()}' clasificada como baja frecuencia "
                f"(media mensual: {mean_monthly:.2f}) — se aplicó {result['method_name']}."
            )

    if not breakdown:
        return {
            'error': 'No fue posible modelar ningún tipo de delito para este cantón.',
            'series': aggregate_series,
        }

    # Calcular porcentajes de contribución
    total_avg = float(np.mean(bottom_up))
    for item in breakdown:
        item['contribution_pct'] = (
            round(item['forecast_avg'] / total_avg * 100, 1) if total_avg > 0 else 0.0
        )
    breakdown.sort(key=lambda x: x['contribution_pct'], reverse=True)

    # Construye la tabla de pronóstico (misma estructura que generate_forecast)
    forecast_table = []
    for i, label in enumerate(forecast_labels):
        yr_f, mo_f = int(label[:4]), int(label[5:7])
        raw_val = round(max(0.0, float(bottom_up[i])), 2)
        forecast_table.append({
            'period': label,
            'month_name': MONTH_NAMES_FULL_ES.get(mo_f, ''),
            'year': yr_f,
            'value': round(max(0.0, float(bottom_up[i]))),
            'value_raw': raw_val,
        })

    # Interpretación
    recent_avg = (
        float(np.mean(historical_values[-6:])) if len(historical_values) >= 6
        else float(np.mean(historical_values))
    )
    forecast_avg_val = float(np.mean(bottom_up))
    pct_change = (
        (forecast_avg_val - recent_avg) / recent_avg * 100
        if recent_avg > 0 else 0.0
    )
    direction = "aumento" if pct_change >= 0 else "disminución"
    abs_pct = abs(round(pct_change, 1))
    canton_title = canton.title()
    n_types = len(breakdown)

    # Peak projected month
    peak_idx = int(np.argmax(bottom_up))
    peak_label_bu = forecast_labels[peak_idx]
    peak_month_name = MONTH_NAMES_FULL_ES.get(int(peak_label_bu[5:7]), '')
    peak_year = peak_label_bu[:4]
    peak_count = round(float(bottom_up[peak_idx]))
    top_delito = breakdown[0]['crime_type'] if breakdown else ''

    # Nivel de riesgo relativo al promedio histórico
    hist_mean = float(np.mean(historical_values)) if historical_values else 0.0
    if hist_mean > 0:
        ratio = forecast_avg_val / hist_mean
        risk_level = 'Alto' if ratio > 1.20 else ('Bajo' if ratio < 0.80 else 'Medio')
    else:
        risk_level = 'Medio'

    interpretation = (
        f"El sistema proyecta aproximadamente <strong>{round(forecast_avg_val, 1)}</strong> "
        f"delitos mensuales en total para los próximos {n_months} meses en {display_canton}, "
        f"utilizando el método <em>Bottom-Up</em> sobre "
        f"<strong>{n_types}</strong> tipos de delito modelados individualmente. "
        f"Nivel de riesgo proyectado: <strong>{risk_level}</strong>. "
        f"El mes de mayor incidencia proyectada es <strong>{peak_month_name} {peak_year}</strong> "
        f"con aproximadamente {peak_count} eventos. "
        f"El tipo de delito con mayor peso es <em>{top_delito}</em>. "
    )
    if pct_change > 15:
        interpretation += (
            f"Se proyecta un {direction} del {abs_pct}% respecto al promedio reciente. "
            f"Se recomienda reforzar los operativos de seguridad en {canton_title}, "
            f"prestando especial atención en {peak_month_name} {peak_year} "
            f"y priorizando acciones sobre '{top_delito}'."
        )
    elif pct_change < -10:
        interpretation += (
            f"Se proyecta una reducción del {abs_pct}% respecto al promedio reciente. "
            f"Podría indicar efectividad de las medidas preventivas actuales en {canton_title}. "
            f"Se recomienda evaluar qué estrategias aplicadas antes de {peak_month_name} "
            f"pueden mantenerse o replicarse."
        )
    else:
        interpretation += (
            f"El comportamiento proyectado se mantiene relativamente estable "
            f"(variación de {pct_change:+.1f}% respecto al promedio reciente). "
            f"Se recomienda mantener vigilancia especial en {peak_month_name} {peak_year} "
            f"({peak_count} eventos proyectados) y continuar con las estrategias de prevención vigentes."
        )

    return {
        'success': True,
        'canton': display_canton,
        'delito': 'Todos los delitos',
        'is_all_delitos': True,
        'is_aggregated_forecast': True,
        'n_months': n_months,

        'historical_labels': historical_labels,
        'historical_values': historical_values,
        'forecast_labels': forecast_labels,
        'bottom_up_forecast': [round(max(0.0, v), 2) for v in bottom_up.tolist()],
        'bottom_up_avg': round(forecast_avg_val, 1),
        'n_crime_types': n_types,

        'breakdown': breakdown,
        'warnings': warnings,
        'forecast_table': forecast_table,
        'composition_data': _compute_delito_composition(canton),
        'interpretation': interpretation,
    }


def generate_forecast(canton: str, delito: str, n_months: int) -> dict:
    """
    Punto de entrada principal del pronóstico.

    Ejecuta los cuatro modelos cuantitativos sobre la serie temporal filtrada,
    compara métricas de desempeño, selecciona el mejor modelo por MAE (DMA).

    Cuando delito == ALL_DELITOS_TOKEN, pasa al método run_all_crime_types_forecast
    que utiliza un enfoque Bottom-Up.
    """
    
    # 0. Normalizar nombres
    is_all_delitos = delito.upper() == ALL_DELITOS_TOKEN
    is_all_cantons = canton.upper() == ALL_CANTONS_TOKEN
    display_delito = 'Todos los delitos' if is_all_delitos else delito
    display_canton = 'Provincia de Alajuela' if is_all_cantons else canton

    # Si se seleccionaron todos los delitos se debe usar otro método
    if is_all_delitos:
        return run_all_crime_types_forecast(canton, n_months)


    # 1. Cargar los datos históricos en serie temporal
    series_data = get_time_series(canton, delito)

    if not series_data:
        return {
            'error': f'No se encontraron datos para {canton} / {display_delito} en el período seleccionado.',
            'series': [],
        }

    #separa los datos en números y meses
    values = [row['total_delitos'] for row in series_data]
    labels = [row['label'] for row in series_data]
    n = len(values)

    start_year = series_data[0]['year']
    start_month = series_data[0]['month']
    last_year = series_data[-1]['year']
    last_month = series_data[-1]['month']

    # 2. Ejecutar todos los modelos y guarda los resultados en un diccionario
    results = {}
    errors_map = {}

    # Tendencia Lineal
    try:
        results['linear_trend'] = trend.fit_and_forecast(values, n_months)
    except Exception as e:
        errors_map['linear_trend'] = str(e)
        logger.warning(f"Tendencia lineal falló: {e}")

    # Suavizamiento Exponencial
    try:
        results['exponential_smoothing'] = exponential_smoothing.fit_and_forecast(values, n_months)
    except Exception as e:
        errors_map['exponential_smoothing'] = str(e)
        logger.warning(f"Suavizamiento exponencial falló: {e}")

    # Índices Estacionales
    try:
        results['seasonal_index'] = seasonal_index.fit_and_forecast(
            values, n_months, start_year, start_month
        )
    except Exception as e:
        errors_map['seasonal_index'] = str(e)
        logger.warning(f"Índices estacionales falló: {e}")

    # Descomposición Multiplicativa 
    try:
        results['multiplicative_decomposition'] = multiplicative_decomposition.fit_and_forecast(
            values, n_months, start_year, start_month
        )
    except Exception as e:
        errors_map['multiplicative_decomposition'] = str(e)
        logger.warning(f"Descomposición multiplicativa falló: {e}")

    if not results:
        return {
            'error': 'Todos los modelos fallaron. Verifique que haya suficientes datos.',
            'model_errors': errors_map,
            'series': series_data,
        }

    # 3. Selecciona el mejor modelo por DMA (menor)
    best_key = min(results, key=lambda k: results[k]['mae'])
    best_result = results[best_key]

    # Prepara los parámetros del modelo para mostrar en la plantilla
    best_params = best_result.get('params', {})
    best_seasonal_list = []
    #Si el mejor método usa esstacionalidad prepara los datos por mes para mostrarlos
    if best_key in ('seasonal_index', 'multiplicative_decomposition'):
        si = best_params.get('seasonal_indices', {}) # obtener indices estacionales, ej: "1": 0.8
        for k, v in sorted(si.items(), key=lambda x: int(x[0])):
            month_idx = int(k) # convertir mes a número
            best_seasonal_list.append({
                'month_num': k,
                'month_name': MONTH_NAMES_ES.get(month_idx, k),
                'value': v,
            })

    # 4. Construye las etiquetas del período de pronóstico
    # Ej. 2026-01
    forecast_labels = []
    yr, mo = last_year, last_month
    for i in range(n_months):
        yr, mo = _add_months(yr, mo, 1)
        forecast_labels.append(f"{yr}-{mo:02d}")

    # 5. Construye la tabla comparativa de métricas (todos los métodos)
    metrics_comparison = []
    for key, res in results.items():
        metrics_comparison.append({
            'method': res['method_name'],
            'method_key': key,
            'mae': res['mae'],
            'mse': res['mse'],
            'rmse': res['rmse'],
            'accuracy': res['accuracy'],
            'is_best': key == best_key,
        })
    metrics_comparison.sort(key=lambda x: x['mae'])

    # 6. Construye la tabla de pronóstico para el mejor modelo
    best_forecast_raw = [round(max(0.0, v), 2) for v in best_result['forecast']] # valores redondeados a 2 decimales
    best_forecast_values = [round(v) for v in best_result['forecast']] # vaalores redondeados a enteros
    
    forecast_table = []
    for label, val, val_raw in zip(forecast_labels, best_forecast_values, best_forecast_raw):
        yr_f, mo_f = int(label[:4]), int(label[5:7])
        forecast_table.append({
            'period': label,
            'month_name': MONTH_NAMES_FULL_ES.get(mo_f, ''),
            'year': yr_f,
            'value': val,
            'value_raw': val_raw,
        })

    # 7. Genera interpretación automática
    interpretation = _generate_interpretation(
        canton=display_canton,
        delito=display_delito,
        values=values,
        best_result=best_result,
        forecast_values=best_forecast_values,
        n_months=n_months,
        is_all_delitos=False,
        forecast_labels=forecast_labels,
    )

    # 8. Construye los datos de pronóstico por método para Chart.js
    methods_chart_data = {}
    for key, res in results.items():
        methods_chart_data[key] = {
            'name': res['method_name'],
            'fitted': [round(v, 2) for v in res['fitted']],
            'forecast': [round(v, 2) for v in res['forecast']],
            'mae': res['mae'],
        }

    return {
        'success': True,
        'canton': display_canton,
        'delito': display_delito,
        'is_all_delitos': False,
        'is_aggregated_forecast': False,
        'composition_data': [],
        'n_months': n_months,

        # Series históricas
        'series': series_data,
        'historical_labels': labels,
        'historical_values': values,

        # Forecast labels
        'forecast_labels': forecast_labels,

        # Mejor modelo
        'best_method': best_result['method_name'],
        'best_method_key': best_key,
        'best_forecast': best_forecast_values,
        'best_forecast_raw': best_forecast_raw,
        'best_fitted': [round(v, 2) for v in best_result['fitted']],
        'best_mae': best_result['mae'],
        'best_accuracy': best_result['accuracy'],
        'best_params': best_params,
        'best_description': best_result.get('description', ''),
        'best_seasonal_list': best_seasonal_list,

        # Datos de todos los métodos
        'metrics_comparison': metrics_comparison,
        'methods_chart_data': methods_chart_data,
        'forecast_table': forecast_table,
        'model_errors': errors_map,

        # Texto de interpretación
        'interpretation': interpretation,
    }


def _generate_interpretation(
    canton: str,
    delito: str,
    values: list,
    best_result: dict,
    forecast_values: list,
    n_months: int,
    is_all_delitos: bool = False,
    forecast_labels: list | None = None,
) -> str:
    """
    Genera una interpretación automática en español de los resultados del pronóstico.
    """
    if not values or not forecast_values:
        return "No hay datos suficientes para generar una interpretación."

    # Compara el pronóstico contra el promedio reciente
    recent_avg = np.mean(values[-6:]) if len(values) >= 6 else np.mean(values)
    forecast_avg = np.mean(forecast_values)

    # Calcula el porcentaje de cambio entre el histórico reciente y el pronóstico
    if recent_avg > 0:
        pct_change = ((forecast_avg - recent_avg) / recent_avg) * 100
    else:
        pct_change = 0.0

    direction = "aumento" if pct_change >= 0 else "disminución"
    abs_pct = abs(round(pct_change, 1))

    canton_title = canton.title()
    method_name = best_result['method_name']
    mae = best_result['mae']
    accuracy = best_result['accuracy']

    # Identifica el mes con mayor cantidad proyectada
    peak_idx = int(np.argmax(forecast_values))
    peak_count = round(float(forecast_values[peak_idx]))
    if forecast_labels and peak_idx < len(forecast_labels):
        peak_lbl = forecast_labels[peak_idx]
        peak_month_name = MONTH_NAMES_FULL_ES.get(int(peak_lbl[5:7]), '')
        peak_year = peak_lbl[:4]
        peak_str = f"{peak_month_name} {peak_year} ({peak_count} casos)"
    else:
        peak_str = f"el mes {peak_idx + 1} ({peak_count} casos)"

    # Clasifica el riesgo comparando el pronóstico con el promedio histórico general
    hist_mean = float(np.mean(values)) if values else 0.0
    if hist_mean > 0:
        ratio = float(forecast_avg) / hist_mean
        risk_level = 'Alto' if ratio > 1.20 else ('Bajo' if ratio < 0.80 else 'Medio')
    else:
        risk_level = 'Medio'

    if is_all_delitos:
        # Caso especial para índices estacionales, ya que este método no usa tendencia
        if best_result.get('method_key') == 'seasonal_index':
            interpretation = (
                f"El pronóstico promedio para los próximos {n_months} meses es "
                f"{abs_pct}% {'mayor' if pct_change >= 0 else 'menor'} que el promedio histórico mensual, "
                f"principalmente por el efecto estacional de los meses proyectados. "
                f"Nivel de riesgo proyectado: <strong>{risk_level}</strong>. "
                f"El mes de mayor incidencia proyectada es <strong>{peak_str}</strong>. "
                f"El método con mejor desempeño fue <strong>{method_name}</strong> "
                f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
            )
        else:
            interpretation = (
                f"El sistema proyecta aproximadamente <strong>{round(forecast_avg, 1)}</strong> delitos mensuales "
                f"para los próximos {n_months} meses en el cantón de {canton_title}, "
                f"considerando todos los tipos de delito registrados. "
                f"Nivel de riesgo proyectado: <strong>{risk_level}</strong>. "
                f"El mes de mayor incidencia proyectada es <strong>{peak_str}</strong>. "
                f"El método con mejor desempeño fue <strong>{method_name}</strong> "
                f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
            )
        # Ajusta la recomendación según el cambio proyectado
        if pct_change > 15:
            interpretation += (
                f"Se recomienda reforzar los operativos de seguridad en {canton_title}, "
                f"con especial atención en {peak_str}."
            )
        elif pct_change < -10:
            if best_result.get('method_key') == 'seasonal_index':
                interpretation += (
                    f"El pronóstico indica una disminución respecto al promedio histórico, "
                    f"probablemente por los meses de menor estacionalidad proyectados. "
                    f"Se recomienda evaluar las estrategias aplicadas para entender mejor el patrón." 
                )
            else:
                interpretation += (
                    f"Se proyecta una reducción del {abs_pct}% respecto al promedio reciente. "
                    f"Podría indicar efectividad de las medidas preventivas actuales. "
                    f"Se recomienda evaluar qué estrategias mantener para sostener la tendencia."
                )
        else:
            interpretation += (
                f"El comportamiento proyectado se mantiene relativamente estable "
                f"(variación de {pct_change:+.1f}% respecto al promedio reciente). "
                f"Se recomienda mantener vigilancia especial en {peak_str} "
                f"y continuar con las estrategias de prevención vigentes."
            )
    else:
        delito_title = delito.lower()
        if best_result.get('method_key') == 'seasonal_index':
            interpretation = (
                f"El pronóstico promedio para los próximos {n_months} meses es "
                f"{abs_pct}% {'mayor' if pct_change >= 0 else 'menor'} que el promedio histórico mensual, "
                f"principalmente por el efecto estacional de los meses proyectados. "
                f"Nivel de riesgo proyectado: <strong>{risk_level}</strong>. "
                f"El mes de mayor incidencia proyectada es <strong>{peak_str}</strong>. "
                f"El método con mejor desempeño fue <strong>{method_name}</strong> "
                f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
            )
        else:
            interpretation = (
                f"Se proyecta un {direction} del {abs_pct}% en los casos de {delito_title} "
                f"para los próximos {n_months} meses en el cantón de {canton_title}. "
                f"Nivel de riesgo proyectado: <strong>{risk_level}</strong>. "
                f"El mes de mayor incidencia proyectada es <strong>{peak_str}</strong>. "
                f"El método con mejor desempeño fue <strong>{method_name}</strong> "
                f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
            )
        if pct_change > 15:
            interpretation += (
                f"Se recomienda reforzar los operativos de seguridad en {canton_title} "
                f"para el tipo de delito '{delito_title}', "
                f"concentrando esfuerzos preventivos en {peak_str}."
            )
        elif pct_change < -10:
            if best_result.get('method_key') == 'seasonal_index':
                interpretation += (
                    f"El pronóstico indica una disminución respecto al promedio histórico, "
                    f"probablemente por los meses de menor estacionalidad proyectados. "
                    f"Se recomienda evaluar las estrategias aplicadas para entender mejor el patrón."
                )
            else:
                interpretation += (
                    f"La tendencia sugiere una reducción sostenida, lo cual podría indicar "
                    f"efectividad de las medidas preventivas actuales en {canton_title}. "
                    f"Se recomienda evaluar las estrategias aplicadas en el período anterior a {peak_str}."
                )
        else:
            interpretation += (
                f"El comportamiento proyectado se mantiene relativamente estable. "
                f"Se recomienda mantener vigilancia especial en {peak_str} "
                f"y continuar con las estrategias de prevención actuales."
            )
    # Nota adicional para suavizamiento exponencial cuando el pronóstico es constante
    if best_result.get('method_key') == 'exponential_smoothing' and forecast_values:
        if len(set(forecast_values)) <= 1:
            interpretation += (
                f" <em>Nota: el Suavizamiento Exponencial Simple genera un pronóstico "
                f"constante de {forecast_values[0]} casos/mes, ya que este método "
                f"no modela tendencia ni estacionalidad.</em>"
            )

    return interpretation
