"""
Forecasting Service – orchestrates all quantitative models.

Retrieves the monthly time series from the database,
runs all four forecasting methods, compares their performance,
and returns a structured results dictionary for the views.
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

# ── Volume-based series classification thresholds ────────────────────────────
# Mean monthly crimes that determine which model is applied per crime type.
FREQ_LOW_THRESHOLD = 1.0     # mean < 1   → low frequency  (Linear Trend or mean)
FREQ_MEDIUM_THRESHOLD = 5.0  # 1 ≤ mean < 5 → medium freq  (SES)
                             # mean ≥ 5   → high frequency (all 4 models, best by MAE)


def _add_months(year: int, month: int, delta: int):
    """Add delta months to (year, month), returning (new_year, new_month)."""
    total_months = (year - 1) * 12 + (month - 1) + delta
    return (total_months // 12 + 1, total_months % 12 + 1)


def _get_all_delitos_series(canton: str) -> list:
    """
    Build a zero-filled monthly series summing all crime types for the canton.

    The series extends from the canton's first crime month to the global dataset
    end (not just the canton's last crime month), ensuring trailing zeros are
    included for months where no crimes were recorded.
    """
    from django.db.models import Sum

    rows = list(
        MonthlySeries.objects.filter(canton=canton.upper())
        .values('year', 'month')
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
    """Return list of {delito, total, pct} dicts for the canton, sorted by total desc."""
    from django.db.models import Sum

    rows = list(
        MonthlySeries.objects.filter(canton=canton.upper())
        .values('delito')
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
    Query MonthlySeries for a specific canton and crime type.
    Returns list of dicts: {year, month, total_delitos, label}.

    Zero-fills every calendar month from the first event for this
    canton/delito group to the global dataset end — not just to the
    last event.  This ensures the series includes trailing zero months
    (e.g. if no crime of this type occurred in the final 18 months of
    the dataset) so models are not trained on a falsely optimistic endpoint.
    """
    if delito.upper() == ALL_DELITOS_TOKEN:
        return _get_all_delitos_series(canton)

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

    global_range = get_global_series_range()
    if global_range:
        end_year, end_month = global_range['max_year'], global_range['max_month']
    else:
        end_year, end_month = records[-1].year, records[-1].month

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
    """Return sorted list of distinct crime type strings for the canton."""
    return list(
        MonthlySeries.objects.filter(canton=canton.upper())
        .values_list('delito', flat=True)
        .distinct()
        .order_by('delito')
    )


def _classify_series(mean_monthly: float) -> str:
    """Classify a time series by its mean monthly volume."""
    if mean_monthly < FREQ_LOW_THRESHOLD:
        return 'baja'
    if mean_monthly < FREQ_MEDIUM_THRESHOLD:
        return 'media'
    return 'alta'


def _run_all_models_and_pick_best(
    values: list, n_months: int, series_start_year: int, series_start_month: int
) -> tuple:
    """Run all four models; return (best_result, best_key) or (None, None) on total failure."""
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
    Apply the model appropriate for the series frequency class.
    Returns (result_dict, model_key) or (None, None) if no model could fit.
    """
    y = np.array(values, dtype=float)

    if freq_class == 'baja':
        try:
            return trend.fit_and_forecast(values, n_months), 'linear_trend'
        except Exception:
            pass
        # Fallback: flat forecast at historical mean
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
        # Fallback to linear trend
        try:
            return trend.fit_and_forecast(values, n_months), 'linear_trend'
        except Exception:
            pass
        return None, None

    # 'alta' — run all four and pick best by MAE
    return _run_all_models_and_pick_best(values, n_months, series_start_year, series_start_month)


def run_all_crime_types_forecast(canton: str, n_months: int) -> dict:
    """
    Bottom-Up aggregated forecast for all crime types in a canton.

    Steps:
      1. Enumerate all crime types with records in the canton.
      2. Classify each series by monthly volume (low / medium / high).
      3. Apply the appropriate model per class.
      4. Sum individual forecasts → Bottom-Up total.
      5. Return structured results for the template.
    """
    crime_types = _get_crime_types_for_canton(canton)
    if not crime_types:
        return {
            'error': f'No se encontraron datos para el cantón {canton.title()}.',
            'series': [],
        }

    aggregate_series = _get_all_delitos_series(canton)
    if not aggregate_series:
        return {
            'error': f'No se pudieron obtener datos históricos para {canton.title()}.',
            'series': [],
        }

    historical_labels = [row['label'] for row in aggregate_series]
    historical_values = [row['total_delitos'] for row in aggregate_series]
    last_year = aggregate_series[-1]['year']
    last_month = aggregate_series[-1]['month']

    # Build forecast period labels
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

    # Fill contribution percentages
    total_avg = float(np.mean(bottom_up))
    for item in breakdown:
        item['contribution_pct'] = (
            round(item['forecast_avg'] / total_avg * 100, 1) if total_avg > 0 else 0.0
        )
    breakdown.sort(key=lambda x: x['contribution_pct'], reverse=True)

    # Build forecast table (same structure as generate_forecast)
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

    # Interpretation
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

    interpretation = (
        f"El sistema proyecta aproximadamente <strong>{round(forecast_avg_val)}</strong> "
        f"delitos mensuales en total para los próximos {n_months} meses en el cantón de "
        f"{canton_title}, utilizando el método <em>Bottom-Up</em> sobre "
        f"<strong>{n_types}</strong> tipos de delito modelados individualmente. "
    )
    if pct_change > 15:
        interpretation += (
            f"Se proyecta un {direction} del {abs_pct}% respecto al promedio reciente. "
            f"Se recomienda reforzar los operativos de seguridad en {canton_title}."
        )
    elif pct_change < -10:
        interpretation += (
            f"Se proyecta una reducción del {abs_pct}% respecto al promedio reciente. "
            f"Podría indicar efectividad de las medidas preventivas actuales en {canton_title}."
        )
    else:
        interpretation += (
            f"El comportamiento proyectado se mantiene relativamente estable "
            f"(variación de {pct_change:+.1f}% respecto al promedio reciente). "
            f"Se recomienda continuar con las estrategias de prevención vigentes."
        )

    return {
        'success': True,
        'canton': canton,
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
    Main forecasting entry point.

    Runs all four quantitative models on the filtered time series,
    compares performance metrics, selects the best model by MAE (DMA),
    and returns structured results ready for template rendering.

    When delito == ALL_DELITOS_TOKEN, delegates to run_all_crime_types_forecast
    which uses a Bottom-Up approach instead of naive aggregation.
    """
    # 0. Normalize display label
    is_all_delitos = delito.upper() == ALL_DELITOS_TOKEN
    display_delito = 'Todos los delitos' if is_all_delitos else delito

    # Branch: Bottom-Up pipeline for all crime types
    if is_all_delitos:
        return run_all_crime_types_forecast(canton, n_months)

    # 1. Retrieve time series
    series_data = get_time_series(canton, delito)

    if not series_data:
        return {
            'error': f'No se encontraron datos para {canton} / {display_delito} en el período seleccionado.',
            'series': [],
        }

    values = [row['total_delitos'] for row in series_data]
    labels = [row['label'] for row in series_data]
    n = len(values)

    start_year = series_data[0]['year']
    start_month = series_data[0]['month']
    last_year = series_data[-1]['year']
    last_month = series_data[-1]['month']

    # 2. Run all models
    results = {}
    errors_map = {}

    # --- Tendencia Lineal ---
    try:
        results['linear_trend'] = trend.fit_and_forecast(values, n_months)
    except Exception as e:
        errors_map['linear_trend'] = str(e)
        logger.warning(f"Tendencia lineal falló: {e}")

    # --- Suavizamiento Exponencial ---
    try:
        results['exponential_smoothing'] = exponential_smoothing.fit_and_forecast(values, n_months)
    except Exception as e:
        errors_map['exponential_smoothing'] = str(e)
        logger.warning(f"Suavizamiento exponencial falló: {e}")

    # --- Índices Estacionales ---
    try:
        results['seasonal_index'] = seasonal_index.fit_and_forecast(
            values, n_months, start_year, start_month
        )
    except Exception as e:
        errors_map['seasonal_index'] = str(e)
        logger.warning(f"Índices estacionales falló: {e}")

    # --- Descomposición Multiplicativa ---
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

    # 3. Select best model by MAE (lowest)
    best_key = min(results, key=lambda k: results[k]['mae'])
    best_result = results[best_key]

    # Prepare model parameters for template display
    best_params = best_result.get('params', {})
    best_seasonal_list = []
    if best_key in ('seasonal_index', 'multiplicative_decomposition'):
        si = best_params.get('seasonal_indices', {})
        for k, v in sorted(si.items(), key=lambda x: int(x[0])):
            month_idx = int(k)
            best_seasonal_list.append({
                'month_num': k,
                'month_name': MONTH_NAMES_ES.get(month_idx, k),
                'value': v,
            })

    # 4. Build forecast period labels
    forecast_labels = []
    yr, mo = last_year, last_month
    for i in range(n_months):
        yr, mo = _add_months(yr, mo, 1)
        forecast_labels.append(f"{yr}-{mo:02d}")

    # 5. Build comparison metrics table (all methods)
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

    # 6. Build forecast table for best model
    best_forecast_raw = [round(max(0.0, v), 2) for v in best_result['forecast']]
    best_forecast_values = [round(v) for v in best_result['forecast']]
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

    # 7. Generate automatic interpretation
    interpretation = _generate_interpretation(
        canton=canton,
        delito=display_delito,
        values=values,
        best_result=best_result,
        forecast_values=best_forecast_values,
        n_months=n_months,
        is_all_delitos=False,
    )

    # 8. Build per-method forecast data for Chart.js
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
        'canton': canton,
        'delito': display_delito,
        'is_all_delitos': False,
        'is_aggregated_forecast': False,
        'composition_data': [],
        'n_months': n_months,

        # Historical series
        'series': series_data,
        'historical_labels': labels,
        'historical_values': values,

        # Forecast labels
        'forecast_labels': forecast_labels,

        # Best model
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

        # All methods data
        'metrics_comparison': metrics_comparison,
        'methods_chart_data': methods_chart_data,
        'forecast_table': forecast_table,
        'model_errors': errors_map,

        # Interpretation text
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
) -> str:
    """
    Generate an automatic Spanish-language interpretation of the forecast results.
    """
    if not values or not forecast_values:
        return "No hay datos suficientes para generar una interpretación."

    recent_avg = np.mean(values[-6:]) if len(values) >= 6 else np.mean(values)
    forecast_avg = np.mean(forecast_values)

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

    if is_all_delitos:
        interpretation = (
            f"El sistema proyecta aproximadamente <strong>{round(forecast_avg)}</strong> delitos mensuales "
            f"para los próximos {n_months} meses en el cantón de {canton_title}, "
            f"considerando todos los tipos de delito registrados. "
            f"El método con mejor desempeño fue <strong>{method_name}</strong> "
            f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
        )
        if pct_change > 15:
            interpretation += (
                f"Se proyecta un {direction} del {abs_pct}% respecto al promedio reciente. "
                f"Se recomienda reforzar los operativos de seguridad en {canton_title}."
            )
        elif pct_change < -10:
            interpretation += (
                f"Se proyecta una reducción del {abs_pct}% respecto al promedio reciente. "
                f"Podría indicar efectividad de las medidas preventivas actuales."
            )
        else:
            interpretation += (
                f"El comportamiento proyectado se mantiene relativamente estable "
                f"(variación de {pct_change:+.1f}% respecto al promedio reciente). "
                f"Se recomienda continuar con las estrategias de prevención vigentes."
            )
    else:
        delito_title = delito.lower()
        interpretation = (
            f"Se proyecta un {direction} del {abs_pct}% en los casos de {delito_title} "
            f"para los próximos {n_months} meses en el cantón de {canton_title}. "
            f"El método con mejor desempeño fue <strong>{method_name}</strong> "
            f"con una DMA de {mae:.2f} y una precisión del {accuracy:.1f}%. "
        )
        if pct_change > 15:
            interpretation += (
                f"Se recomienda reforzar los operativos de seguridad en {canton_title} "
                f"especialmente para el tipo de delito '{delito_title}'."
            )
        elif pct_change < -10:
            interpretation += (
                f"La tendencia sugiere una reducción sostenida, lo cual podría indicar "
                f"efectividad de las medidas preventivas actuales en {canton_title}."
            )
        else:
            interpretation += (
                f"El comportamiento proyectado se mantiene relativamente estable. "
                f"Se recomienda continuar con las estrategias de prevención actuales."
            )

    if best_result.get('method_key') == 'exponential_smoothing' and forecast_values:
        if len(set(forecast_values)) <= 1:
            interpretation += (
                f" <em>Nota: el Suavizamiento Exponencial Simple genera un pronóstico "
                f"constante de {forecast_values[0]} casos/mes, ya que este método "
                f"no modela tendencia ni estacionalidad.</em>"
            )

    return interpretation
