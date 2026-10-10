@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando lo necesario para la plataforma... (puede tardar unos minutos)
python --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo No encontre Python. Instalalo desde python.org y marca la casilla "Add python.exe to PATH".
  pause
  exit /b
)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo.
echo Listo. Ahora abre la app con INICIAR.bat
pause
