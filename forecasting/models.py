"""
Models for the Crime Forecasting application.

Stores both raw crime records and aggregated monthly time series.
"""

from django.db import models


class CrimeRecord(models.Model):
    """
    Raw crime record from OIJ dataset.
    Each row represents one reported criminal event.
    """
    delito = models.CharField(max_length=200, db_index=True, verbose_name='Delito')
    sub_delito = models.CharField(max_length=200, blank=True, null=True, verbose_name='SubDelito')
    fecha = models.DateField(db_index=True, verbose_name='Fecha')
    hora = models.CharField(max_length=100, blank=True, null=True, verbose_name='Hora')
    victima = models.CharField(max_length=200, blank=True, null=True, verbose_name='Víctima')
    sub_victima = models.CharField(max_length=300, blank=True, null=True, verbose_name='SubVíctima')
    edad = models.CharField(max_length=100, blank=True, null=True, verbose_name='Edad')
    sexo = models.CharField(max_length=50, blank=True, null=True, db_index=True, verbose_name='Sexo')
    nacionalidad = models.CharField(max_length=100, blank=True, null=True, verbose_name='Nacionalidad')
    provincia = models.CharField(max_length=100, blank=True, null=True, verbose_name='Provincia')
    canton = models.CharField(max_length=100, db_index=True, verbose_name='Cantón')
    distrito = models.CharField(max_length=100, blank=True, null=True, verbose_name='Distrito')

    class Meta:
        verbose_name = 'Registro de Delito'
        verbose_name_plural = 'Registros de Delitos'
        indexes = [
            models.Index(fields=['canton', 'delito', 'fecha']),
        ]

    def __str__(self):
        return f"{self.delito} – {self.canton} ({self.fecha})"


class MonthlySeries(models.Model):
    """
    Aggregated monthly crime counts by canton and crime type.
    This is the time series used by the forecasting models.
    """
    year = models.IntegerField(verbose_name='Año', db_index=True)
    month = models.IntegerField(verbose_name='Mes', db_index=True)
    canton = models.CharField(max_length=100, db_index=True, verbose_name='Cantón')
    delito = models.CharField(max_length=200, db_index=True, verbose_name='Delito')
    total_delitos = models.IntegerField(default=0, verbose_name='Total Delitos')

    class Meta:
        verbose_name = 'Serie Mensual'
        verbose_name_plural = 'Series Mensuales'
        unique_together = [('year', 'month', 'canton', 'delito')]
        indexes = [
            models.Index(fields=['canton', 'delito', 'year', 'month']),
        ]

    def __str__(self):
        return f"{self.canton} | {self.delito} | {self.year}-{self.month:02d}: {self.total_delitos}"

    @property
    def period_label(self):
        """Returns a formatted period string like '2024-01'."""
        return f"{self.year}-{self.month:02d}"
