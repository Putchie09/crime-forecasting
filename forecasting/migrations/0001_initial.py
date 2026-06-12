"""
Initial migration for crime forecasting models.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='CrimeRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('delito', models.CharField(db_index=True, max_length=200, verbose_name='Delito')),
                ('sub_delito', models.CharField(blank=True, max_length=200, null=True, verbose_name='SubDelito')),
                ('fecha', models.DateField(db_index=True, verbose_name='Fecha')),
                ('hora', models.CharField(blank=True, max_length=100, null=True, verbose_name='Hora')),
                ('victima', models.CharField(blank=True, max_length=200, null=True, verbose_name='Víctima')),
                ('sub_victima', models.CharField(blank=True, max_length=300, null=True, verbose_name='SubVíctima')),
                ('edad', models.CharField(blank=True, max_length=100, null=True, verbose_name='Edad')),
                ('sexo', models.CharField(blank=True, db_index=True, max_length=50, null=True, verbose_name='Sexo')),
                ('nacionalidad', models.CharField(blank=True, max_length=100, null=True, verbose_name='Nacionalidad')),
                ('provincia', models.CharField(blank=True, max_length=100, null=True, verbose_name='Provincia')),
                ('canton', models.CharField(db_index=True, max_length=100, verbose_name='Cantón')),
                ('distrito', models.CharField(blank=True, max_length=100, null=True, verbose_name='Distrito')),
            ],
            options={
                'verbose_name': 'Registro de Delito',
                'verbose_name_plural': 'Registros de Delitos',
            },
        ),
        migrations.CreateModel(
            name='MonthlySeries',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('year', models.IntegerField(db_index=True, verbose_name='Año')),
                ('month', models.IntegerField(db_index=True, verbose_name='Mes')),
                ('canton', models.CharField(db_index=True, max_length=100, verbose_name='Cantón')),
                ('delito', models.CharField(db_index=True, max_length=200, verbose_name='Delito')),
                ('total_delitos', models.IntegerField(default=0, verbose_name='Total Delitos')),
            ],
            options={
                'verbose_name': 'Serie Mensual',
                'verbose_name_plural': 'Series Mensuales',
            },
        ),
        migrations.AddIndex(
            model_name='crimerecord',
            index=models.Index(fields=['canton', 'delito', 'fecha'], name='forecasting_canton_d_fecha_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='monthlyseries',
            unique_together={('year', 'month', 'canton', 'delito')},
        ),
        migrations.AddIndex(
            model_name='monthlyseries',
            index=models.Index(fields=['canton', 'delito', 'year', 'month'], name='forecasting_canton_d_year_m_idx'),
        ),
    ]
