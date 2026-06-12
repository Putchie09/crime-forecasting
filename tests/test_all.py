"""
Unit tests for the Crime Forecasting application.

Covers:
  - Data loading and cleaning
  - All four forecasting methods
  - Service orchestration
  - Model evaluation metrics
"""

import math
from django.test import TestCase, RequestFactory
from django.urls import reverse


# ─────────────────────────────────────────────────────────────────
#  Tests for forecasting methods
# ─────────────────────────────────────────────────────────────────

class TrendMethodTests(TestCase):
    """Tests for the linear trend forecasting method."""

    def setUp(self):
        from forecasting.forecasting_methods import trend
        self.trend = trend

    def test_basic_fit(self):
        """Linear trend should produce fitted values and forecast."""
        values = [10, 12, 14, 16, 18, 20, 22, 24]
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        self.assertIn('fitted', result)
        self.assertIn('forecast', result)
        self.assertEqual(len(result['fitted']), 8)
        self.assertEqual(len(result['forecast']), 3)

    def test_perfect_linear_series(self):
        """For a perfect linear series, fitted values should nearly match actual."""
        values = [float(i * 5) for i in range(1, 13)]
        result = self.trend.fit_and_forecast(values, n_forecast=6)
        self.assertAlmostEqual(result['mae'], 0.0, places=5)

    def test_forecast_monotone_increase(self):
        """Upward trend series should project increasing forecasts."""
        values = [10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        f = result['forecast']
        self.assertGreater(f[1], f[0])
        self.assertGreater(f[2], f[1])

    def test_no_negative_forecasts(self):
        """Forecast values should never be negative."""
        values = [100, 80, 60, 40, 20, 10, 5, 3, 2, 1, 1, 1]
        result = self.trend.fit_and_forecast(values, n_forecast=6)
        for v in result['forecast']:
            self.assertGreaterEqual(v, 0)

    def test_metrics_present(self):
        """Result must include all required metric keys."""
        values = list(range(10, 22))
        result = self.trend.fit_and_forecast(values, n_forecast=3)
        for key in ('mae', 'mse', 'rmse', 'accuracy'):
            self.assertIn(key, result)

    def test_minimum_data_validation(self):
        """Should raise ValueError with fewer than 2 data points."""
        with self.assertRaises(ValueError):
            self.trend.fit_and_forecast([42], n_forecast=3)


class ExponentialSmoothingTests(TestCase):
    """Tests for the exponential smoothing method."""

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
        """For a constant series, all forecast values should be that constant."""
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
    """Tests for the seasonal index method."""

    def setUp(self):
        from forecasting.forecasting_methods import seasonal_index
        self.si = seasonal_index

    def _seasonal_values(self, years=2):
        """Generate a 2-year series with clear seasonality."""
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
    """Tests for the multiplicative decomposition method."""

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
        """Seasonal indices should sum approximately to 12."""
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
#  Tests for data service
# ─────────────────────────────────────────────────────────────────

class DataServiceTests(TestCase):
    """Tests for the data loading and processing service."""

    def test_normalize_columns_uppercase(self):
        """Uppercase column names should be normalized."""
        import pandas as pd
        from forecasting.services.data_service import normalize_columns
        df = pd.DataFrame({'DELITO': ['A'], 'FECHA': ['2023-01-01'], 'CANTON': ['B']})
        df_norm = normalize_columns(df)
        self.assertIn('Delito', df_norm.columns)
        self.assertIn('Fecha', df_norm.columns)
        self.assertIn('Canton', df_norm.columns)

    def test_clean_dataset_drops_missing_dates(self):
        """Rows with invalid dates should be removed."""
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
        """Monthly series should aggregate counts correctly."""
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
#  Tests for views
# ─────────────────────────────────────────────────────────────────

class HomeViewTests(TestCase):
    """Tests for the home page view."""

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
    """Tests for the forecast view."""

    def test_forecast_get_returns_200(self):
        response = self.client.get(reverse('forecasting:forecast'))
        self.assertEqual(response.status_code, 200)

    def test_forecast_post_missing_canton(self):
        """Posting without canton should return form errors."""
        response = self.client.post(reverse('forecasting:forecast'), {
            'canton': '',
            'delito': 'ASALTO',
            'n_months': '6',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('form_errors', response.context)

    def test_forecast_post_with_no_data(self):
        """Posting with valid params but empty DB should show error message."""
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
    """Tests for the historical data view."""

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
    """Tests for the CSV export view."""

    def test_csv_export_returns_200(self):
        response = self.client.get(reverse('forecasting:export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])

    def test_csv_content_disposition(self):
        response = self.client.get(reverse('forecasting:export_csv'))
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('.csv', response['Content-Disposition'])
