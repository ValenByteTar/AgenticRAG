@echo off
echo ========================================
echo Reiniciando Ollama para liberar RAM
echo ========================================
echo.

echo Deteniendo Ollama...
taskkill /F /IM ollama.exe 2>nul
taskkill /F /IM "ollama app.exe" 2>nul
timeout /t 2 /nobreak >nul

echo Limpiando procesos...
timeout /t 1 /nobreak >nul

echo Iniciando Ollama...
start "" "C:\Users\Valen\AppData\Local\Programs\Ollama\ollama app.exe"
timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo Ollama reiniciado - RAM liberada
echo ========================================
echo.
pause
