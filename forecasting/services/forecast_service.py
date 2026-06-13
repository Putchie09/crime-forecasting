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


def generate_forecast(canton: str, delito: str, n_months: int) -> dict:
    """
    Main forecasting entry point.

    Runs all four quantitative models on the filtered time series,
    compares performance metrics, selects the best model by MAE (DMA),
    and returns structured results ready for template rendering.
    """
    # 0. Normalize display label
    is_all_delitos = delito.upper() == ALL_DELITOS_TOKEN
    display_delito = 'Todos los delitos' if is_all_delitos else delito

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
    best_forecast_values = [round(v) for v in best_result['forecast']]
    forecast_table = []
    for label, val in zip(forecast_labels, best_forecast_values):
        yr_f, mo_f = int(label[:4]), int(label[5:7])
        forecast_table.append({
            'period': label,
            'month_name': MONTH_NAMES_FULL_ES.get(mo_f, ''),
            'year': yr_f,
            'value': val,
        })

    # 7. Generate automatic interpretation
    interpretation = _generate_interpretation(
        canton=canton,
        delito=display_delito,
        values=values,
        best_result=best_result,
        forecast_values=best_forecast_values,
        n_months=n_months,
        is_all_delitos=is_all_delitos,
    )

    # Composition breakdown (only when querying all crime types)
    composition_data = _compute_delito_composition(canton) if is_all_delitos else []

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
        'is_all_delitos': is_all_delitos,
        'composition_data': composition_data,
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
