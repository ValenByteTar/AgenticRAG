@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Ruta ABSOLUTA del proyecto
set "PROJECT_DIR=C:\Users\Valen\Desktop\Proyectos\SistemaGraniteEXP"
cd /d "%PROJECT_DIR%"

echo ==============================
echo   Iniciando Sistema (Granite Q5)
echo ==============================
echo Proyecto : %PROJECT_DIR%
echo Fecha/Hora: %DATE% %TIME%
echo.

REM Verificar venv
if not exist "%PROJECT_DIR%\.venv\Scripts\python.exe" (
  echo [ERROR] No se encontro el entorno .venv. Crea el venv e instala dependencias.
  echo        Ejemplo: py -3 -m venv .venv ^& .\.venv\Scripts\python -m pip install -r requirements.txt
  pause
  exit /b 1
)

REM Configurar variables de entorno para Ollama (GPU)
set OLLAMA_NUM_GPU=99
set OLLAMA_NUM_THREAD=12
set OLLAMA_NUM_BATCH=64
set OLLAMA_NUM_CTX=2048
set OLLAMA_FLASH_ATTENTION=1
set CUDA_VISIBLE_DEVICES=0

REM Asegurar que el modelo Granite Q5 este disponible en Ollama
where ollama >nul 2>&1
if not errorlevel 1 (
  echo Verificando modelo Granite Q5 en Ollama...
  ollama list | findstr /I "granite-3.3-8b-instruct-q5km" >nul 2>&1
  if errorlevel 1 (
    echo Descargando modelo Granite Q5 en Ollama...
    ollama pull granite-3.3-8b-instruct-q5km:latest
  ) else (
    echo Modelo Granite Q5 encontrado.
  )
) else (
  echo [ADVERTENCIA] Ollama no esta en PATH. Asegurate de tener Ollama instalado.
)

REM Verificar archivos clave
if not exist "%PROJECT_DIR%\chat.py" (
  echo [ERROR] Falta chat.py en %PROJECT_DIR%
  pause
  exit /b 1
)

echo.
echo Iniciando interfaz de consola...
echo.

REM Lanzar la interfaz de consola en una nueva ventana
start "Sistema Consola" /D "%PROJECT_DIR%" "%PROJECT_DIR%\.venv\Scripts\python.exe" "%PROJECT_DIR%\chat.py" --console

endlocal
pause
