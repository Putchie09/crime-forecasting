"""
Views for the Crime Forecasting application.

Three main modules:
  1. HomeView       – Overview, KPI cards, methodology cards
  2. ForecastView   – Forecast form + results (AJAX-driven)
  3. HistoricalView – Paginated, filterable data explorer
  4. ExportPDFView  – Generate and stream PDF report
  5. ExportCSVView  – Export filtered data as CSV
  6. APIViews       – JSON endpoints for Chart.js
"""

import csv
import json
import logging
from datetime import date, datetime

from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q
from django.http import (
    HttpResponse, JsonResponse, StreamingHttpResponse
)
from django.shortcuts import render
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from forecasting.models import CrimeRecord, MonthlySeries
from forecasting.services.data_service import get_dataset_summary
from forecasting.services.forecast_service import generate_forecast, get_time_series
from forecasting.services.report_service import generate_forecast_pdf

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
#  HOME
# ─────────────────────────────────────────────────────────────

class HomeView(View):
    template_name = 'forecasting/home.html'

    def get(self, request):
        summary = get_dataset_summary()

        # Build aggregated monthly series for the overview chart (all cantons)
        chart_data = _build_overview_chart()

        context = {
            **summary,
            'chart_labels': json.dumps(chart_data['labels']),
            'chart_values': json.dumps(chart_data['values']),
        }
        return render(request, self.template_name, context)


def _build_overview_chart():
    """Aggregate all monthly records into a single province-wide time series."""
    from django.db.models import Sum

    qs = (
        MonthlySeries.objects
        .values('year', 'month')
        .annotate(total=Sum('total_delitos'))
        .order_by('year', 'month')
    )

    labels = []
    values = []
    for row in qs:
        labels.append(f"{row['year']}-{row['month']:02d}")
        values.append(row['total'])

    return {'labels': labels, 'values': values}


# ─────────────────────────────────────────────────────────────
#  FORECAST
# ─────────────────────────────────────────────────────────────

class ForecastView(View):
    template_name = 'forecasting/forecast.html'

    def get(self, request):
        summary = get_dataset_summary()
        context = {
            'cantons': summary['cantons'],
            'delitos': summary['delitos'],
        }
        return render(request, self.template_name, context)

    def post(self, request):
        summary = get_dataset_summary()
        context = {
            'cantons': summary['cantons'],
            'delitos': summary['delitos'],
        }

        # Parse form inputs
        canton = request.POST.get('canton', '').strip().upper()
        delito = request.POST.get('delito', '').strip().upper()
        date_from_str = request.POST.get('date_from', '').strip()
        date_to_str = request.POST.get('date_to', '').strip()
        n_months_str = request.POST.get('n_months', '6').strip()

        # Validate
        errors = []
        if not canton:
            errors.append('Debe seleccionar un cantón.')
        if not delito:
            errors.append('Debe seleccionar un tipo de delito.')

        date_from = date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Fecha de inicio inválida.')
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append('Fecha de fin inválida.')

        try:
            n_months = max(1, min(int(n_months_str), 36))
        except ValueError:
            n_months = 6

        if errors:
            context['form_errors'] = errors
            context['form_data'] = request.POST
            return render(request, self.template_name, context)

        # Run forecast
        results = generate_forecast(canton, delito, date_from, date_to, n_months)

        context.update(results)
        context['form_data'] = request.POST
        context['showed_results'] = True

        # Serialize chart data for JavaScript
        if results.get('success'):
            context['js_historical_labels'] = json.dumps(results['historical_labels'])
            context['js_historical_values'] = json.dumps(results['historical_values'])
            context['js_forecast_labels'] = json.dumps(results['forecast_labels'])
            context['js_best_fitted'] = json.dumps(results['best_fitted'])
            context['js_best_forecast'] = json.dumps(results['best_forecast'])
            context['js_methods_data'] = json.dumps(results['methods_chart_data'])
            if results.get('composition_data'):
                context['js_composition_data'] = json.dumps(results['composition_data'])

        return render(request, self.template_name, context)


# ─────────────────────────────────────────────────────────────
#  HISTORICAL DATA EXPLORER
# ─────────────────────────────────────────────────────────────

class HistoricalView(View):
    template_name = 'forecasting/historical.html'
    PAGE_SIZE = getattr(settings, 'DATA_PAGE_SIZE', 50)

    def get(self, request):
        summary = get_dataset_summary()

        # Filter parameters
        q = request.GET.get('q', '').strip()
        canton = request.GET.get('canton', '').strip().upper()
        delito = request.GET.get('delito', '').strip().upper()
        sexo = request.GET.get('sexo', '').strip().upper()
        date_from_str = request.GET.get('date_from', '').strip()
        date_to_str = request.GET.get('date_to', '').strip()

        qs = CrimeRecord.objects.all().order_by('-fecha', 'canton')

        # Apply filters
        if q:
            qs = qs.filter(
                Q(delito__icontains=q) |
                Q(sub_delito__icontains=q) |
                Q(canton__icontains=q) |
                Q(distrito__icontains=q) |
                Q(nacionalidad__icontains=q)
            )
        if canton:
            qs = qs.filter(canton=canton)
        if delito:
            qs = qs.filter(delito=delito)
        if sexo and sexo not in ('TODOS', 'AMBOS'):
            qs = qs.filter(sexo=sexo)
        if date_from_str:
            try:
                qs = qs.filter(fecha__gte=datetime.strptime(date_from_str, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to_str:
            try:
                qs = qs.filter(fecha__lte=datetime.strptime(date_to_str, '%Y-%m-%d').date())
            except ValueError:
                pass

        total_filtered = qs.count()

        # Paginate
        paginator = Paginator(qs, self.PAGE_SIZE)
        page_num = request.GET.get('page', 1)
        try:
            page_obj = paginator.page(page_num)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)

        # Build page range for template
        current = page_obj.number
        total_pages = paginator.num_pages
        page_range = _build_page_range(current, total_pages)

        context = {
            'page_obj': page_obj,
            'total_filtered': total_filtered,
            'total_pages': total_pages,
            'page_range': page_range,
            'cantons': summary['cantons'],
            'delitos': summary['delitos'],
            # Filter values to repopulate form
            'filter_q': q,
            'filter_canton': canton,
            'filter_delito': delito,
            'filter_sexo': sexo,
            'filter_date_from': date_from_str,
            'filter_date_to': date_to_str,
        }
        return render(request, self.template_name, context)


def _build_page_range(current: int, total: int, window: int = 5):
    """Return a list of page numbers centered around current page."""
    half = window // 2
    start = max(1, current - half)
    end = min(total, current + half)
    # Adjust if near edges
    if end - start < window - 1:
        if start == 1:
            end = min(total, start + window - 1)
        else:
            start = max(1, end - window + 1)
    return list(range(start, end + 1))


# ─────────────────────────────────────────────────────────────
#  EXPORT PDF
# ─────────────────────────────────────────────────────────────

class ExportPDFView(View):

    def post(self, request):
        """
        Regenerate forecast and stream as PDF.
        Uses the same POST parameters as ForecastView.
        """
        canton = request.POST.get('canton', '').strip().upper()
        delito = request.POST.get('delito', '').strip().upper()
        date_from_str = request.POST.get('date_from', '').strip()
        date_to_str = request.POST.get('date_to', '').strip()
        n_months_str = request.POST.get('n_months', '6').strip()

        date_from = date_to = None
        if date_from_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
            except ValueError:
                pass
        if date_to_str:
            try:
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        try:
            n_months = max(1, min(int(n_months_str), 36))
        except ValueError:
            n_months = 6

        results = generate_forecast(canton, delito, date_from, date_to, n_months)

        if not results.get('success'):
            return HttpResponse(
                f"Error generando pronóstico: {results.get('error', 'Error desconocido')}",
                status=400,
                content_type='text/plain; charset=utf-8',
            )

        try:
            pdf_bytes = generate_forecast_pdf(results)
        except Exception as e:
            logger.error(f"PDF generation error: {e}")
            return HttpResponse(
                f"Error generando PDF: {str(e)}",
                status=500,
                content_type='text/plain; charset=utf-8',
            )

        delito_label = results.get('delito', delito)
        filename = f"pronostico_{canton.lower()}_{delito_label.lower().replace(' ', '_')}.pdf"
        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ─────────────────────────────────────────────────────────────
#  EXPORT CSV
# ─────────────────────────────────────────────────────────────

class ExportCSVView(View):

    def get(self, request):
        """Export filtered crime records as CSV."""
        q = request.GET.get('q', '').strip()
        canton = request.GET.get('canton', '').strip().upper()
        delito = request.GET.get('delito', '').strip().upper()
        sexo = request.GET.get('sexo', '').strip().upper()
        date_from_str = request.GET.get('date_from', '').strip()
        date_to_str = request.GET.get('date_to', '').strip()

        qs = CrimeRecord.objects.all().order_by('-fecha')

        if q:
            qs = qs.filter(
                Q(delito__icontains=q) | Q(canton__icontains=q) |
                Q(sub_delito__icontains=q) | Q(distrito__icontains=q)
            )
        if canton:
            qs = qs.filter(canton=canton)
        if delito:
            qs = qs.filter(delito=delito)
        if sexo and sexo not in ('TODOS', 'AMBOS'):
            qs = qs.filter(sexo=sexo)
        if date_from_str:
            try:
                qs = qs.filter(fecha__gte=datetime.strptime(date_from_str, '%Y-%m-%d').date())
            except ValueError:
                pass
        if date_to_str:
            try:
                qs = qs.filter(fecha__lte=datetime.strptime(date_to_str, '%Y-%m-%d').date())
            except ValueError:
                pass

        response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
        response['Content-Disposition'] = 'attachment; filename="datos_criminalidad_alajuela.csv"'

        writer = csv.writer(response)
        writer.writerow([
            'Delito', 'SubDelito', 'Fecha', 'Hora',
            'Victima', 'SubVictima', 'Edad', 'Sexo',
            'Nacionalidad', 'Provincia', 'Canton', 'Distrito',
        ])

        for rec in qs.iterator(chunk_size=500):
            writer.writerow([
                rec.delito, rec.sub_delito, rec.fecha, rec.hora,
                rec.victima, rec.sub_victima, rec.edad, rec.sexo,
                rec.nacionalidad, rec.provincia, rec.canton, rec.distrito,
            ])

        return response


# ─────────────────────────────────────────────────────────────
#  API – JSON endpoints for dynamic loading
# ─────────────────────────────────────────────────────────────

def api_overview_chart(request):
    """Return province-wide monthly totals for the home chart."""
    data = _build_overview_chart()
    return JsonResponse(data)


def api_time_series(request):
    """Return time series for a canton/delito combo (used in Forecast page)."""
    canton = request.GET.get('canton', '').upper()
    delito = request.GET.get('delito', '').upper()
    if not canton or not delito:
        return JsonResponse({'error': 'canton and delito required'}, status=400)
    series = get_time_series(canton, delito)
    return JsonResponse({'series': series})
