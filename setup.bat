@echo off
REM ===========================================================
REM  setup.bat — Configura y arranca el proyecto en Windows
REM ===========================================================
REM Uso: Doble-click en setup.bat   (o ejecutar desde CMD)

echo.
echo ====================================================
echo    Criminalidad Alajuela -- Setup inicial
echo ====================================================
echo.

REM 1. Verificar Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instale Python 3.12+ desde python.org
    pause
    exit /b 1
)
echo [OK] Python detectado

REM 2. Crear entorno virtual
if not exist "venv" (
    echo [->] Creando entorno virtual...
    python -m venv venv
    echo [OK] Entorno virtual creado
) else (
    echo [OK] Entorno virtual ya existe
)

REM 3. Activar entorno
call venv\Scripts\activate.bat

REM 4. Actualizar pip e instalar dependencias
echo [->] Instalando dependencias...
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo [OK] Dependencias instaladas

REM 5. Migrar base de datos
echo [->] Ejecutando migraciones...
python manage.py migrate --run-syncdb -q
echo [OK] Base de datos lista

REM 6. Cargar dataset
if exist "datasets\Estadisticas.xlsx" (
    echo [->] Cargando dataset...
    python manage.py load_dataset
) else (
    echo [!] Dataset no encontrado.
    echo     Copie Estadisticas.xlsx a la carpeta datasets\
    echo     Luego ejecute: python manage.py load_dataset
)

echo.
echo ====================================================
echo  Proyecto listo!
echo.
echo  Inicie el servidor:
echo    venv\Scripts\activate
echo    python manage.py runserver
echo.
echo  Abra: http://127.0.0.1:8000
echo ====================================================
echo.
pause
