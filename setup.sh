#!/usr/bin/env bash
# ==========================================================
# setup.sh — Configura y arranca el proyecto por primera vez
# ==========================================================
# Uso:
#   chmod +x setup.sh
#   ./setup.sh
#
# Requisitos: Python 3.12+, pip, el archivo datasets/Estadisticas.xlsx

set -e

echo ""
echo "════════════════════════════════════════════════════"
echo "   Criminalidad Alajuela — Setup inicial"
echo "════════════════════════════════════════════════════"
echo ""

# 1. Verificar Python 3.12+
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python detectado: $PYTHON_VERSION"

# 2. Crear entorno virtual
if [ ! -d "venv" ]; then
    echo "→ Creando entorno virtual..."
    python3 -m venv venv
    echo "✓ Entorno virtual creado"
else
    echo "✓ Entorno virtual ya existe"
fi

# 3. Activar y actualizar pip
source venv/bin/activate
pip install --upgrade pip -q

# 4. Instalar dependencias
echo "→ Instalando dependencias (puede tardar 1-2 minutos)..."
pip install -r requirements.txt -q
echo "✓ Dependencias instaladas"

# 5. Verificar dataset
if [ ! -f "datasets/Estadisticas.xlsx" ]; then
    echo ""
    echo "⚠️  ATENCIÓN: No se encontró el dataset."
    echo "   Copie el archivo Estadisticas.xlsx a la carpeta 'datasets/':"
    echo "   cp /ruta/al/Estadisticas.xlsx datasets/Estadisticas.xlsx"
    echo ""
fi

# 6. Migrar base de datos
echo "→ Ejecutando migraciones..."
python manage.py migrate --run-syncdb -q
echo "✓ Base de datos lista"

# 7. Cargar dataset si existe
if [ -f "datasets/Estadisticas.xlsx" ]; then
    echo "→ Cargando dataset..."
    python manage.py load_dataset
else
    echo "⚠️  Dataset no encontrado — omitiendo carga."
    echo "   Cuando agregue el archivo, ejecute: python manage.py load_dataset"
fi

echo ""
echo "════════════════════════════════════════════════════"
echo "✅  Proyecto listo!"
echo ""
echo "   Inicie el servidor con:"
echo "   source venv/bin/activate"
echo "   python manage.py runserver"
echo ""
echo "   Abra el navegador en: http://127.0.0.1:8000"
echo "════════════════════════════════════════════════════"
echo ""
