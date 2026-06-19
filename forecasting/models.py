"""
Modelos para la aplicación de Pronóstico de Criminalidad.

Almacena tanto los registros brutos de delitos como las series temporales
mensuales agregadas.
"""

from django.db import models


class CrimeRecord(models.Model):
    """
    Registro bruto de delito del dataset del OIJ.
    Cada fila representa un evento criminal reportado.
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
    Conteos mensuales agregados de delitos por cantón y tipo de delito.
    Esta es la serie de tiempo usada por los modelos de pronóstico.
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
        """Devuelve una cadena de período formateada como '2024-01'."""
        return f"{self.year}-{self.month:02d}"


class DataImportLog(models.Model):
    """
    Registra cada importación de dataset automática o manual.
    Usado por el servicio de arranque para detectar si el archivo Excel
    cambió desde la última importación, evitando reprocesos innecesarios.
    """
    imported_at = models.DateTimeField(auto_now_add=True, verbose_name='Importado en')
    file_path = models.CharField(max_length=500, verbose_name='Ruta del archivo')
    file_mtime = models.FloatField(verbose_name='Timestamp de modificación del archivo')
    crime_records = models.IntegerField(verbose_name='Registros importados')
    monthly_series = models.IntegerField(verbose_name='Series mensuales generadas')

    class Meta:
        verbose_name = 'Registro de Importación'
        verbose_name_plural = 'Registros de Importación'
        ordering = ['-imported_at']

    def __str__(self):
        return f"Importación {self.imported_at.strftime('%Y-%m-%d %H:%M')} — {self.crime_records:,} registros"
