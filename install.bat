@echo off
echo 🚀 Instalando y configurando proyecto AselvIA...
echo.

REM Verificar si Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python no está instalado o no está en el PATH
    echo    Por favor instala Python 3.8+ desde https://python.org
    pause
    exit /b 1
)

REM Verificar si pip está disponible
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo ❌ pip no está disponible
    echo    Por favor reinstala Python con pip incluido
    pause
    exit /b 1
)

echo ✅ Python encontrado
echo.

REM Ejecutar script de configuración
python setup.py

echo.
echo ⚠️ IMPORTANTE: No olvides configurar tu OPENAI_API_KEY en el archivo .env
echo.
pause
