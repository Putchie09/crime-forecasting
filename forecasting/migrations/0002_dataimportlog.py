from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecasting', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='DataImportLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imported_at', models.DateTimeField(auto_now_add=True, verbose_name='Importado en')),
                ('file_path', models.CharField(max_length=500, verbose_name='Ruta del archivo')),
                ('file_mtime', models.FloatField(verbose_name='Timestamp de modificación del archivo')),
                ('crime_records', models.IntegerField(verbose_name='Registros importados')),
                ('monthly_series', models.IntegerField(verbose_name='Series mensuales generadas')),
            ],
            options={
                'verbose_name': 'Registro de Importación',
                'verbose_name_plural': 'Registros de Importación',
                'ordering': ['-imported_at'],
            },
        ),
    ]
