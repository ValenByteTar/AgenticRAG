# Script para configurar Ollama con máximos recursos
# Ejecutar como Administrador

Write-Host "CONFIGURANDO OLLAMA PARA MÁXIMO RENDIMIENTO" -ForegroundColor Cyan
Write-Host ""

# Detener Ollama si está corriendo
Write-Host "1. Deteniendo Ollama..." -ForegroundColor Yellow
try {
    Stop-Process -Name "ollama" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "   ✓ Ollama detenido" -ForegroundColor Green
} catch {
    Write-Host "   ℹ Ollama no estaba corriendo" -ForegroundColor Gray
}

Write-Host ""
Write-Host "2. Configurando variables de entorno..." -ForegroundColor Yellow

# Configurar variables de entorno del usuario
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_PARALLEL", "4", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_LOADED_MODELS", "2", "User")
[Environment]::SetEnvironmentVariable("OLLAMA_MAX_QUEUE", "512", "User")

# Detectar si hay GPU NVIDIA
$hasGPU = $false
try {
    $gpu = Get-WmiObject Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
    if ($gpu) {
        $hasGPU = $true
        Write-Host "   ✓ GPU NVIDIA detectada: $($gpu.Name)" -ForegroundColor Green
        [Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU", "1", "User")
    } else {
        Write-Host "   ℹ No se detectó GPU NVIDIA (usando solo CPU)" -ForegroundColor Gray
    }
} catch {
    Write-Host "   ℹ No se pudo detectar GPU" -ForegroundColor Gray
}

Write-Host ""
Write-Host "3. Variables configuradas:" -ForegroundColor Yellow
Write-Host "   • OLLAMA_NUM_PARALLEL: 4" -ForegroundColor White
Write-Host "   • OLLAMA_MAX_LOADED_MODELS: 2" -ForegroundColor White
Write-Host "   • OLLAMA_MAX_QUEUE: 512" -ForegroundColor White
if ($hasGPU) {
    Write-Host "   • OLLAMA_NUM_GPU: 1" -ForegroundColor White
}

Write-Host ""
Write-Host "4. Reiniciando Ollama..." -ForegroundColor Yellow

# Iniciar Ollama como proceso en background
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden

Start-Sleep -Seconds 5

# Verificar que está corriendo
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 10
    Write-Host "   ✓ Ollama iniciado correctamente" -ForegroundColor Green
    Write-Host ""
    Write-Host "✅ CONFIGURACIÓN COMPLETADA" -ForegroundColor Green
    Write-Host ""
    Write-Host "Modelos disponibles:" -ForegroundColor Cyan
    $response.models | ForEach-Object {
        Write-Host "  • $($_.name)" -ForegroundColor White
    }
} catch {
    Write-Host "   ✗ Error al iniciar Ollama" -ForegroundColor Red
    Write-Host "   Por favor, inicia Ollama manualmente:" -ForegroundColor Yellow
    Write-Host "   ollama serve" -ForegroundColor White
}

Write-Host ""
Write-Host "📊 Para monitorear recursos:" -ForegroundColor Cyan
Write-Host "   Abre Administrador de Tareas → Rendimiento" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Ahora puedes ejecutar:" -ForegroundColor Cyan
Write-Host "   python chat.py" -ForegroundColor White
Write-Host ""

# Esperar input del usuario
Read-Host "Presiona ENTER para salir"
