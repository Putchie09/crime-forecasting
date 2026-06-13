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
    goto FIN
)

for /f "tokens=2" %%V in ('python --version 2^>^&1') do set PYVER=%%V
echo  [OK] Python %PYVER% detectado

REM ── PASO 2: Crear entorno virtual si no existe ────────────────
if not exist "venv\" (
    echo  [-^>] Creando entorno virtual...
    python -m venv venv

    if %errorlevel% neq 0 (
        echo.
        echo  [ERROR] No se pudo crear el entorno virtual.
        echo  Verifique que Python este instalado correctamente.
        goto FIN
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
    goto FIN
)

echo  [OK] Entorno virtual activado

REM ── PASO 4: Instalar/verificar dependencias ──────────────────
echo  [-^>] Verificando dependencias...
python -c "import matplotlib, django, pandas, scipy, reportlab, numpy"
if %errorlevel% equ 0 goto DEPS_OK

echo.
echo  [-^>] Instalando dependencias ^(primera vez: 5-8 minutos^)...
echo      Por favor espere, no cierre esta ventana...
echo.
pip install -r requirements.txt
if %errorlevel% neq 0 goto ERROR_DEPS
echo.
echo  [OK] Dependencias instaladas correctamente
goto DEPS_DONE

:ERROR_DEPS
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
goto FIN

:DEPS_OK
echo  [OK] Dependencias verificadas

:DEPS_DONE

REM ── PASO 5: Verificar / crear base de datos ───────────────────
echo  [-^>] Verificando base de datos...
python manage.py migrate --run-syncdb
if %errorlevel% equ 0 goto DB_OK

echo.
echo  [ERROR] Fallo la configuracion de la base de datos.
echo  Revise los mensajes de error mostrados arriba.
echo.
goto FIN

:DB_OK
echo  [OK] Base de datos lista

REM ── PASO 6: Determinar puerto disponible ──────────────────────
set PORT=8000

netstat -an 2>nul | findstr /C:":8000 " | findstr /C:"LISTENING" >nul 2>&1

if %errorlevel% equ 0 (
    echo  [!] Puerto 8000 ocupado, usando puerto 8001
    set PORT=8001
)

REM ── PASO 7: Abrir navegador despues de que Django arranque ────
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

REM ── PASO 8: Iniciar servidor ─────────────────────────────────
python manage.py runserver %PORT%
set SERVIDOR_EXIT=%errorlevel%

echo.

if %SERVIDOR_EXIT% neq 0 (
    echo  ============================================================
    echo   [ERROR] El servidor se detuvo inesperadamente.
    echo   Codigo de salida: %SERVIDOR_EXIT%
    echo.
    echo   Causas comunes:
    echo     - Error de importacion en alguno de los modulos
    echo     - Puerto ocupado por otro proceso
    echo     - Error de configuracion en settings.py
    echo     - Excepcion no controlada en Django
    echo.
    echo   Revise los mensajes de error mostrados arriba.
    echo  ============================================================
    echo.
) else (
    echo  ============================================================
    echo   Servidor detenido correctamente.
    echo  ============================================================
    echo.
)

:FIN
echo.
echo  ============================================================
echo   El programa ha finalizado.
echo.
echo   Esta ventana permanecera abierta para que pueda
echo   revisar cualquier mensaje o error.
echo  ============================================================
echo.

pause
cmd /k