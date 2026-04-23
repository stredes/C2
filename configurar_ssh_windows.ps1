# ============================================
# Script: configurar_ssh_windows.ps1
# Objetivo:
#   - Instalar y habilitar OpenSSH Server en Windows
#   - Abrir el puerto 22 en el firewall
#   - Crear ~/.ssh/authorized_keys para el usuario actual
#   - Agregar la clave publica generada en Termux
#   - Mostrar datos de conexion
# Requisitos:
#   - Ejecutar PowerShell como Administrador
# ============================================

$PublicKey = 'ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAACAQCnG3KRkDaV2whO7D40P/3r2Cr0shqBFbad3j719i8ayV8tTNpcSAaoLiuKeWugu080KRW44sy1XAhysrXXHLSLFhLFI9B80WBEA3jCpt+Y5aAYPX61hYAM7ZSWrfF1mqchMPdtG+//vCKuwWAz4eunEZN+Pk3eGlDY9Hg2DhV2Hn/LILlDVoHGnc4n2dRhsS/xHAeGIUJasQOWWpr5eDfwTHZevGv5cnEN0sa38KODWHBlNps11FE4E12FO+Lm9PZ2p18doTQoDakD7YhdNNbYWk9IFvyB9wMHuauNxtDyT6VcEvqjwztMNf/Sd6cFnneTOT3TLsu6yXzjKFuAz6JDWxf0/Vzwoy077VruFqg6IPVezXViyDHMM5ohEsx9BKNipyi56CYM4KU7ZYTnm8dRywlXITYNgZs9rzm7C4KgRrGGy54Ogsm4VmMuF6thDAwDWQJsJ3RqWfIyQ9odcwz+/q3T2rewOISkZ1MqKsxw4cSJfeO11VvK0Er+Td1p96XNbq5r5mRpukt9KLiGiVubSsJHsRx5k+aJrY770SUGzqbM+7ZWdGDDpR9CIY0QJx20NaYTuM7qI/fzpxeDoM7o5dU1yBPrRhP6yeVTwbjKzJvgFsD9eUsXWApBkaJ1p/8fPubLFeilaYq+vhVQ7uL6MAn/eRcMfpD6BPwswMTluw== u0_a169@localhost'

Write-Host "== Configurando OpenSSH Server en Windows ==" -ForegroundColor Cyan

$IsAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $IsAdmin) {
    Write-Error "Debes ejecutar PowerShell como Administrador."
    exit 1
}

$capability = Get-WindowsCapability -Online | Where-Object Name -like 'OpenSSH.Server*'

if ($null -eq $capability) {
    Write-Error "No se pudo consultar la capacidad OpenSSH.Server en este sistema."
    exit 1
}

if ($capability.State -ne 'Installed') {
    Write-Host "Instalando OpenSSH Server..." -ForegroundColor Yellow
    Add-WindowsCapability -Online -Name $capability.Name
} else {
    Write-Host "OpenSSH Server ya esta instalado." -ForegroundColor Green
}

Write-Host "Iniciando y habilitando servicio sshd..." -ForegroundColor Yellow
Set-Service -Name sshd -StartupType Automatic
Start-Service sshd

$ruleName = 'OpenSSH-Server-In-TCP'
$existingRule = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue

if (-not $existingRule) {
    Write-Host "Creando regla de firewall para SSH..." -ForegroundColor Yellow
    New-NetFirewallRule -Name $ruleName `
        -DisplayName 'OpenSSH Server (TCP 22)' `
        -Enabled True `
        -Direction Inbound `
        -Protocol TCP `
        -Action Allow `
        -LocalPort 22 | Out-Null
} else {
    Write-Host "La regla de firewall para SSH ya existe." -ForegroundColor Green
}

$currentUser = $env:USERNAME
$userProfile = $env:USERPROFILE
$sshDir = Join-Path $userProfile '.ssh'
$authorizedKeys = Join-Path $sshDir 'authorized_keys'

if (-not (Test-Path $sshDir)) {
    Write-Host "Creando carpeta $sshDir ..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
}

if (-not (Test-Path $authorizedKeys)) {
    Write-Host "Creando archivo authorized_keys ..." -ForegroundColor Yellow
    New-Item -ItemType File -Path $authorizedKeys -Force | Out-Null
}

$existingContent = Get-Content $authorizedKeys -ErrorAction SilentlyContinue
if ($existingContent -notcontains $PublicKey) {
    Write-Host "Agregando clave publica al archivo authorized_keys ..." -ForegroundColor Yellow
    Add-Content -Path $authorizedKeys -Value $PublicKey
} else {
    Write-Host "La clave publica ya estaba agregada." -ForegroundColor Green
}

Write-Host "Ajustando permisos..." -ForegroundColor Yellow
icacls $sshDir /inheritance:r | Out-Null
icacls $authorizedKeys /inheritance:r | Out-Null
icacls $sshDir /grant:r "${currentUser}:(F)" "SYSTEM:(F)" | Out-Null
icacls $authorizedKeys /grant:r "${currentUser}:(F)" "SYSTEM:(F)" | Out-Null

$sshdStatus = Get-Service sshd

$ips = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object {
        $_.IPAddress -notlike '127.*' -and
        $_.IPAddress -notlike '169.254*'
    } |
    Select-Object -ExpandProperty IPAddress

Write-Host ""
Write-Host "== CONFIGURACION LISTA ==" -ForegroundColor Green
Write-Host "Usuario de Windows: $currentUser" -ForegroundColor Cyan
Write-Host "Servicio sshd: $($sshdStatus.Status)" -ForegroundColor Cyan

if ($ips) {
    Write-Host "IPs detectadas:" -ForegroundColor Cyan
    $ips | ForEach-Object { Write-Host " - $_" }
} else {
    Write-Warning "No se detectaron IPs IPv4 activas."
}

Write-Host ""
Write-Host "Prueba desde tu Nokia con alguno de estos comandos:" -ForegroundColor Yellow
if ($ips) {
    foreach ($ip in $ips) {
        Write-Host "ssh $currentUser@$ip"
    }
} else {
    Write-Host "ssh $currentUser@IP_DE_TU_PC"
}

Write-Host ""
Write-Host "Si quieres ver el nombre exacto del usuario manualmente en Windows, ejecuta: whoami" -ForegroundColor DarkCyan
