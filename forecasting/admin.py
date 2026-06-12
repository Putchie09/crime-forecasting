from django.contrib import admin
from .models import CrimeRecord, MonthlySeries, DataImportLog


@admin.register(CrimeRecord)
class CrimeRecordAdmin(admin.ModelAdmin):
    list_display = ['delito', 'canton', 'fecha', 'sexo', 'nacionalidad']
    list_filter = ['canton', 'delito', 'sexo']
    search_fields = ['delito', 'canton', 'distrito']
    date_hierarchy = 'fecha'
    ordering = ['-fecha']


@admin.register(MonthlySeries)
class MonthlySeriesAdmin(admin.ModelAdmin):
    list_display = ['canton', 'delito', 'year', 'month', 'total_delitos']
    list_filter = ['canton', 'delito', 'year']
    search_fields = ['canton', 'delito']
    ordering = ['canton', 'delito', 'year', 'month']


@admin.register(DataImportLog)
class DataImportLogAdmin(admin.ModelAdmin):
    list_display = ['imported_at', 'crime_records', 'monthly_series', 'file_path']
    ordering = ['-imported_at']
    readonly_fields = ['imported_at', 'file_path', 'file_mtime', 'crime_records', 'monthly_series']
