"""
URL configuration for the forecasting app.
"""

from django.urls import path
from . import views

app_name = 'forecasting'

urlpatterns = [
    # Main pages
    path('', views.HomeView.as_view(), name='home'),
    path('pronosticar/', views.ForecastView.as_view(), name='forecast'),
    path('datos-historicos/', views.HistoricalView.as_view(), name='historical'),

    # Exports
    path('exportar-pdf/', views.ExportPDFView.as_view(), name='export_pdf'),
    path('exportar-csv/', views.ExportCSVView.as_view(), name='export_csv'),

    # API endpoints (JSON)
    path('api/overview-chart/', views.api_overview_chart, name='api_overview_chart'),
    path('api/time-series/', views.api_time_series, name='api_time_series'),
]
