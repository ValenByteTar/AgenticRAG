@echo off
REM ========================================================================
REM Script de inicio de Ollama OPTIMIZADO para RTX 4050 + Ryzen 5 7535HS
REM ========================================================================

echo.
echo ========================================================================
echo   CONFIGURACION OPTIMIZADA DE OLLAMA
echo ========================================================================
echo.
echo Hardware detectado:
echo   - GPU: RTX 4050 (6GB VRAM)
echo   - CPU: Ryzen 5 7535HS (6 cores / 12 threads)
echo   - RAM: 32GB DDR5
echo.

REM Configuración de GPU
set OLLAMA_NUM_GPU=99
set CUDA_VISIBLE_DEVICES=0

REM Configuración de CPU (MAXIMA UTILIZACION)
set OLLAMA_NUM_THREAD=12
set OLLAMA_NUM_PARALLEL=4

REM Configuración de memoria
set OLLAMA_MAX_LOADED_MODELS=1
set OLLAMA_FLASH_ATTENTION=1

REM Batch size optimizado
set OLLAMA_NUM_BATCH=1024

REM Contexto
set OLLAMA_NUM_CTX=4096

echo Configuracion aplicada:
echo   - num_gpu: 99 (todas las capas en GPU)
echo   - num_thread: 12 (TODOS los threads)
echo   - num_parallel: 4 (procesamiento paralelo)
echo   - num_batch: 1024 (batch grande)
echo   - flash_attention: activado
echo.
echo ========================================================================
echo   INICIANDO OLLAMA...
echo ========================================================================
echo.

REM Detener Ollama si está corriendo
taskkill /F /IM ollama.exe 2>nul
timeout /t 2 /nobreak >nul

REM Iniciar Ollama con configuración optimizada
start "Ollama Server" ollama serve

echo.
echo Ollama iniciado con configuracion optimizada.
echo Espera 5 segundos para que el servidor este listo...
timeout /t 5 /nobreak >nul

echo.
echo ========================================================================
echo   LISTO! Ahora puedes iniciar el servidor web:
echo   python chat.py
echo ========================================================================
echo.
pause
