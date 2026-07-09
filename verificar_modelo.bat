@echo off
echo Verificando modelo qwen3-4b-rag...
echo.
ollama list | findstr qwen3-4b-rag
if %ERRORLEVEL% EQU 0 (
    echo.
    echo OK: Modelo encontrado
) else (
    echo.
    echo ERROR: Modelo no encontrado
)
