@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Sistema de Pronostico de Delitos - Alajuela

REM ================================================================
REM  INICIAR.bat
REM  Lanzador unico del Sistema de Pronostico de Delitos - Alajuela
REM  IF-7200 Metodos Cuantitativos - UCR Sede de Occidente
REM
REM  Uso: Doble clic en este archivo
REM  Requisito: Python 3.12+ instalado (con "Add to PATH" marcado)
REM ================================================================

echo.
echo  ============================================================
echo   Sistema de Pronostico de Delitos - Alajuela
echo   IF-7200 Metodos Cuantitativos - UCR Sede de Occidente
echo  ============================================================
echo.

REM ── PASO 1: Verificar Python ─────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python no encontrado en este equipo.
    echo.
    echo  Instale Python 3.12 desde:
    echo    https://www.python.org/downloads/
    echo.
    echo  IMPORTANTE: Durante la instalacion, marque la casilla
    echo  "Add Python to PATH" antes de hacer clic en Install Now.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  [OK] Python %PYVER% detectado

REM ── PASO 2: Crear entorno virtual si no existe ────────────────
if not exist "venv\" (
    echo  [->] Creando entorno virtual...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] No se pudo crear el entorno virtual.
        echo  Verifique que Python este instalado correctamente.
        pause
        exit /b 1
    )
    echo  [OK] Entorno virtual creado
) else (
    echo  [OK] Entorno virtual encontrado
)

REM ── PASO 3: Activar entorno virtual ──────────────────────────
call venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] No se pudo activar el entorno virtual.
    pause
    exit /b 1
)

REM ── PASO 4: Instalar/verificar dependencias ──────────────────
REM   Verificamos si los paquetes criticos ya estan instalados.
REM   Incluye matplotlib que estaba ausente del entorno original.
echo  [->] Verificando dependencias...
python -c "import matplotlib, django, pandas, scipy, reportlab, numpy" >nul 2>&1
if %errorlevel% neq 0 (
    echo  [->] Instalando dependencias (primera vez: 5-8 minutos)...
    echo      Por favor espere, no cierre esta ventana...
    echo.
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] Fallo la instalacion de dependencias.
        echo.
        echo  Posibles causas:
        echo    - Sin conexion a internet
        echo    - Red universitaria bloqueando descargas
        echo    - Espacio en disco insuficiente
        echo.
        echo  Intente conectarse a una red diferente y vuelva
        echo  a ejecutar este archivo.
        pause
        exit /b 1
    )
    echo.
    echo  [OK] Dependencias instaladas correctamente
) else (
    echo  [OK] Dependencias verificadas
)

REM ── PASO 5: Verificar / crear base de datos ───────────────────
REM   Si db.sqlite3 ya existe con datos (incluida en el ZIP),
REM   migrate es un no-op que toma menos de 2 segundos.
echo  [->] Verificando base de datos...
python manage.py migrate --run-syncdb -q 2>nul
if %errorlevel% neq 0 (
    echo  [ADVERTENCIA] Problema menor con las migraciones.
    echo               El sistema intentara continuar de todas formas.
) else (
    echo  [OK] Base de datos lista
)

REM ── PASO 6: Determinar puerto disponible ──────────────────────
set PORT=8000
netstat -an 2>nul | findstr /C:":8000 " | findstr /C:"LISTENING" >nul 2>&1
if %errorlevel% equ 0 (
    echo  [!] Puerto 8000 ocupado, usando puerto 8001
    set PORT=8001
)

REM ── PASO 7: Abrir navegador despues de que Django arranque ────
REM   PowerShell espera 4 segundos en segundo plano y luego
REM   abre el navegador predeterminado. El servidor corre
REM   en esta misma ventana mostrando sus logs.
start "" /B powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 4; Start-Process 'http://127.0.0.1:%PORT%'"

echo.
echo  ============================================================
echo   Sistema listo. Iniciando servidor...
echo.
echo   URL: http://127.0.0.1:%PORT%
echo.
echo   El navegador se abrira automaticamente en 4 segundos.
echo   Esta ventana debe permanecer abierta mientras usa el sistema.
echo   Para detener: presione Ctrl+C o cierre esta ventana.
echo  ============================================================
echo.

REM ── PASO 8: Iniciar servidor (bloquea esta ventana) ──────────
python manage.py runserver %PORT%

echo.
echo  Servidor detenido. Puede cerrar esta ventana.
pause
