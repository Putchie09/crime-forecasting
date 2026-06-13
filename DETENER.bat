@echo off
cd /d "%~dp0"
title Detener Servidor

REM ================================================================
REM  DETENER.bat
REM  Detiene el servidor Django si esta corriendo en segundo plano.
REM
REM  Uso normal: Presionar Ctrl+C en la ventana de INICIAR.bat
REM  Uso alternativo: Ejecutar este archivo si la ventana se cerro
REM  accidentalmente y el puerto sigue ocupado.
REM ================================================================

echo.
echo  Buscando servidor Django en puertos 8000 y 8001...
echo.

set ENCONTRADO=0

REM Buscar procesos en puerto 8000
for /f "tokens=5" %%P in ('netstat -aon 2^>nul ^| findstr /C:":8000 " ^| findstr /C:"LISTENING"') do (
    if "%%P" neq "0" (
        taskkill /F /PID %%P >nul 2>&1
        if !errorlevel! equ 0 (
            echo  [OK] Proceso en puerto 8000 detenido (PID: %%P)
            set ENCONTRADO=1
        )
    )
)

REM Buscar procesos en puerto 8001
for /f "tokens=5" %%P in ('netstat -aon 2^>nul ^| findstr /C:":8001 " ^| findstr /C:"LISTENING"') do (
    if "%%P" neq "0" (
        taskkill /F /PID %%P >nul 2>&1
        if !errorlevel! equ 0 (
            echo  [OK] Proceso en puerto 8001 detenido (PID: %%P)
            set ENCONTRADO=1
        )
    )
)

if "%ENCONTRADO%"=="0" (
    echo  No se encontro ningun servidor activo en los puertos 8000 o 8001.
    echo  Es posible que ya este detenido.
)

echo.
pause
