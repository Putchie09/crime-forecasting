from django.contrib import admin
from .models import CrimeRecord, MonthlySeries


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
