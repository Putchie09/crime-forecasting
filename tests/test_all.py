"""
Pruebas unitarias para la aplicación de Pronóstico de Criminalidad.

Cubre:
  - Carga y limpieza de datos
  - Los cuatro métodos de pronóstico
  - Orquestación de servicios
  - Métricas de evaluación del modelo
"""

import math
from django.test import TestCase, RequestFactory
from django.urls import reverse


# ─────────────────────────────────────────────────────────────────
#  Pruebas para los métodos de pronóstico
# ─────────────────────────────────────────────────────────────────

class TrendMethodTests(TestCase):
    """Pruebas para el método de pronóstico de tendencia lineal."""

    def setUp(self):
        from forecasting.forecasting_methods import trend
        self.trend = trend

    def test_basic_fit(self):
        """La tendencia lineal debe producir valores ajustados y pronósticos."""
        values = [10, 12, 14, 16, 18, 20, 22, 24]
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        self.assertIn('fitted', result)
        self.assertIn('forecast', result)
        self.assertEqual(len(result['fitted']), 8)
        self.assertEqual(len(result['forecast']), 3)

    def test_perfect_linear_series(self):
        """Para una serie lineal perfecta, los valores ajustados deben coincidir casi con los reales."""
        values = [float(i * 5) for i in range(1, 13)]
        result = self.trend.fit_and_forecast(values, n_forecast=6)
        self.assertAlmostEqual(result['mae'], 0.0, places=5)

    def test_forecast_monotone_increase(self):
        """Una serie con tendencia ascendente debe proyectar pronósticos crecientes."""
        values = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        f = result['forecast']
        self.assertGreater(f[1], f[0])
        self.assertGreater(f[2], f[1])

    def test_no_negative_forecasts(self):
        """Los valores pronosticados nunca deben ser negativos."""
        values = [100, 80, 60, 40, 20, 10, 5, 3, 2, 1, 1, 1]
        result = self.trend.fit_and_forecast(values, n_forecast=6)
        for v in result['forecast']:
            self.assertGreaterEqual(v, 0)

    def test_metrics_present(self):
        """El resultado debe incluir todas las claves métricas requeridas."""
        values = list(range(10, 22))
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        for key in ('mae', 'mse', 'rmse', 'accuracy'):
            self.assertIn(key, result)

    def test_minimum_data_validation(self):
        """Debe lanzar ValueError con menos de 2 puntos de datos."""
        with self.assertRaises(ValueError):
            self.trend.fit_and_forecast([42], n_forecast=3)


class ExponentialSmoothingTests(TestCase):
    """Pruebas para el método de suavizamiento exponencial."""

    def setUp(self):
        from forecasting.forecasting_methods import exponential_smoothing
        self.es = exponential_smoothing

    def test_basic_output(self):
        values = [10, 11, 13, 12, 14, 15, 16, 14, 17, 18, 19, 20]
        result = self.es.fit_and_forecast(values, n_forecast=4)
        self.assertEqual(len(result['fitted']), 12)
        self.assertEqual(len(result['forecast']), 4)

    def test_alpha_in_valid_range(self):
        values = [20, 22, 21, 23, 24, 22, 25, 23, 26, 24, 27, 25]
        result = self.es.fit_and_forecast(values, n_forecast=3)
        alpha = result['params']['alpha']
        self.assertGreater(alpha, 0.0)
        self.assertLess(alpha, 1.0)

    def test_constant_series_flat_forecast(self):
        """Para una serie constante, todos los valores pronosticados deben ser ese mismo constante."""
        values = [50.0] * 10
        result = self.es.fit_and_forecast(values, n_forecast=6)
        for v in result['forecast']:
            self.assertAlmostEqual(v, 50.0, places=1)

    def test_no_negative_output(self):
        values = [5, 3, 2, 1, 1, 2, 1, 1, 1, 2, 1, 1]
        result = self.es.fit_and_forecast(values, n_forecast=4)
        for v in result['forecast']:
            self.assertGreaterEqual(v, 0)

    def test_minimum_data_validation(self):
        with self.assertRaises(ValueError):
            self.es.fit_and_forecast([10, 11], n_forecast=3)


class SeasonalIndexTests(TestCase):
    """Pruebas para el método de índice estacional."""

    def setUp(self):
        from forecasting.forecasting_methods import seasonal_index
        self.si = seasonal_index

    def _seasonal_values(self, years=2):
        """Genera una serie de 2 años con estacionalidad clara."""
        base = [10, 8, 12, 15, 18, 20, 25, 22, 18, 14, 10, 8]
        return base * years

    def test_basic_output(self):
        values = self._seasonal_values(2)
        result = self.si.fit_and_forecast(values, n_forecast=6, start_year=2022, start_month=1)
        self.assertEqual(len(result['fitted']), 24)
        self.assertEqual(len(result['forecast']), 6)

    def test_twelve_seasonal_indices(self):
        values = self._seasonal_values(2)
        result = self.si.fit_and_forecast(values, n_forecast=3, start_year=2022, start_month=1)
        indices = result['params']['seasonal_indices']
        self.assertEqual(len(indices), 12)

    def test_minimum_data_validation(self):
        with self.assertRaises(ValueError):
            self.si.fit_and_forecast([10, 11, 12], n_forecast=3, start_year=2023, start_month=1)

    def test_no_negative_forecast(self):
        values = self._seasonal_values(2)
        result = self.si.fit_and_forecast(values, n_forecast=6, start_year=2022, start_month=1)
        for v in result['forecast']:
            self.assertGreaterEqual(v, 0)


class MultiplicativeDecompositionTests(TestCase):
    """Pruebas para el método de descomposición multiplicativa."""

    def setUp(self):
        from forecasting.forecasting_methods import multiplicative_decomposition
        self.md = multiplicative_decomposition

    def _seasonal_values(self, years=2):
        base = [10, 8, 12, 15, 18, 20, 25, 22, 18, 14, 10, 8]
        return base * years

    def test_basic_output(self):
        values = self._seasonal_values(2)
        result = self.md.fit_and_forecast(values, n_forecast=6, start_year=2022, start_month=1)
        self.assertEqual(len(result['fitted']), 24)
        self.assertEqual(len(result['forecast']), 6)

    def test_seasonal_indices_normalize(self):
        """Los índices estacionales deben sumar aproximadamente 12."""
        values = self._seasonal_values(3)
        result = self.md.fit_and_forecast(values, n_forecast=3, start_year=2021, start_month=1)
        indices = result['params']['seasonal_indices']
        total = sum(float(v) for v in indices.values())
        self.assertAlmostEqual(total, 12.0, places=3)

    def test_minimum_data_validation(self):
        with self.assertRaises(ValueError):
            self.md.fit_and_forecast([1, 2, 3], n_forecast=3, start_year=2023, start_month=1)

    def test_method_name(self):
        values = self._seasonal_values(2)
        result = self.md.fit_and_forecast(values, n_forecast=3, start_year=2022, start_month=1)
        self.assertEqual(result['method_name'], 'Descomposición Multiplicativa')


# ─────────────────────────────────────────────────────────────────
#  Pruebas para el servicio de datos
# ─────────────────────────────────────────────────────────────────

class DataServiceTests(TestCase):
    """Pruebas para el servicio de carga y procesamiento de datos."""

    def test_normalize_columns_uppercase(self):
        """Los nombres de columnas en mayúsculas deben normalizarse."""
        import pandas as pd
        from forecasting.services.data_service import normalize_columns
        df = pd.DataFrame({'DELITO': ['A'], 'FECHA': ['2023-01-01'], 'CANTON': ['B']})
        df_norm = normalize_columns(df)
        self.assertIn('Delito', df_norm.columns)
        self.assertIn('Fecha', df_norm.columns)
        self.assertIn('Canton', df_norm.columns)

    def test_clean_dataset_drops_missing_dates(self):
        """Las filas con fechas inválidas deben eliminarse."""
        import pandas as pd
        from forecasting.services.data_service import clean_dataset
        df = pd.DataFrame({
            'Delito': ['ASALTO', 'ROBO'],
            'Fecha': ['2023-01-15', 'NOT_A_DATE'],
            'Canton': ['ALAJUELA', 'ALAJUELA'],
            'Provincia': ['ALAJUELA', 'ALAJUELA'],
        })
        result_df, _ = clean_dataset(df)
        self.assertEqual(len(result_df), 1)

    def test_build_monthly_series_aggregation(self):
        """La serie mensual debe agregar los conteos correctamente."""
        import pandas as pd
        from forecasting.services.data_service import build_monthly_series
        df = pd.DataFrame({
            'Fecha': pd.to_datetime(['2023-01-10', '2023-01-20', '2023-02-05']),
            'Canton': ['ALAJUELA', 'ALAJUELA', 'ALAJUELA'],
            'Delito': ['ASALTO', 'ASALTO', 'ASALTO'],
        })
        series = build_monthly_series(df)
        self.assertEqual(len(series), 2)
        jan = series[series['month'] == 1]
        self.assertEqual(int(jan['total_delitos'].values[0]), 2)


# ─────────────────────────────────────────────────────────────────
#  Pruebas para las vistas
# ─────────────────────────────────────────────────────────────────

class HomeViewTests(TestCase):
    """Pruebas para la vista de la página principal."""

    def test_home_returns_200(self):
        response = self.client.get(reverse('forecasting:home'))
        self.assertEqual(response.status_code, 200)

    def test_home_uses_correct_template(self):
        response = self.client.get(reverse('forecasting:home'))
        self.assertTemplateUsed(response, 'forecasting/home.html')
        self.assertTemplateUsed(response, 'base.html')

    def test_home_context_has_summary(self):
        response = self.client.get(reverse('forecasting:home'))
        self.assertIn('total_records', response.context)
        self.assertIn('cantons', response.context)
        self.assertIn('delitos', response.context)


class ForecastViewTests(TestCase):
    """Pruebas para la vista de pronóstico."""

    def test_forecast_get_returns_200(self):
        response = self.client.get(reverse('forecasting:forecast'))
        self.assertEqual(response.status_code, 200)

    def test_forecast_post_missing_canton(self):
        """Enviar sin canton debe devolver errores de formulario."""
        response = self.client.post(reverse('forecasting:forecast'), {
            'canton': '',
            'delito': 'ASALTO',
            'n_months': '6',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('form_errors', response.context)

    def test_forecast_post_with_no_data(self):
        """Enviar con parámetros válidos pero base de datos vacía debe mostrar mensaje de error."""
        response = self.client.post(reverse('forecasting:forecast'), {
            'canton': 'ALAJUELA',
            'delito': 'ASALTO',
            'n_months': '3',
            'date_from': '2021-01-01',
            'date_to': '2023-12-31',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get('showed_results'))


class HistoricalViewTests(TestCase):
    """Pruebas para la vista de datos históricos."""

    def test_historical_returns_200(self):
        response = self.client.get(reverse('forecasting:historical'))
        self.assertEqual(response.status_code, 200)

    def test_historical_uses_correct_template(self):
        response = self.client.get(reverse('forecasting:historical'))
        self.assertTemplateUsed(response, 'forecasting/historical.html')

    def test_historical_pagination_context(self):
        response = self.client.get(reverse('forecasting:historical'))
        self.assertIn('page_obj', response.context)
        self.assertIn('total_filtered', response.context)


class ExportCSVViewTests(TestCase):
    """Pruebas para la vista de exportación CSV."""

    def test_csv_export_returns_200(self):
        response = self.client.get(reverse('forecasting:export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_csv_content_disposition(self):
        response = self.client.get(reverse('forecasting:export_csv'))
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.csv', response['Content-Disposition'])
