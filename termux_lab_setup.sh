#!/data/data/com.termux/files/usr/bin/bash
set -eu

LAB_ENV_FILE="$HOME/.termux-lab.env"
BASHRC_FILE="$HOME/.bashrc"

print_step() {
  printf '\n==> %s\n' "$1"
}

prompt_default() {
  prompt_text="$1"
  default_value="$2"
  printf "%s [%s]: " "$prompt_text" "$default_value"
  IFS= read -r user_value
  if [ -z "$user_value" ]; then
    printf '%s' "$default_value"
  else
    printf '%s' "$user_value"
  fi
}

append_once() {
  file_path="$1"
  marker="$2"
  block_content="$3"

  if [ -f "$file_path" ] && grep -Fq "$marker" "$file_path"; then
    return 0
  fi

  {
    printf '\n%s\n' "$block_content"
  } >> "$file_path"
}

print_step "Actualizando Termux e instalando paquetes base"
pkg update -y
pkg upgrade -y
pkg install -y openssh git python nmap curl tmux

print_step "Recopilando datos del laboratorio"
LAB_PC_USER="$(prompt_default "Usuario SSH del PC del laboratorio" "$USER")"
LAB_PC_IP="$(prompt_default "IP del PC con cyd_backend" "192.168.1.193")"
RPI_USER="$(prompt_default "Usuario SSH de la Raspberry" "pi")"
RPI_IP="$(prompt_default "IP de la Raspberry" "192.168.1.100")"
CYD_DEVICE_ID="$(prompt_default "Device ID de la CYD" "cyd-2432s028")"
BACKEND_PORT="$(prompt_default "Puerto HTTP del backend CYD" "8080")"
TOKEN_ID="$(prompt_default "Token ID del backend" "cyd-local")"
SECRET_KEY="$(prompt_default "Secret del backend" "cambia-esta-clave-larga")"
BACKEND_DIR_WIN="$(prompt_default "Ruta Windows de cyd_backend en el PC" "C:\\Users\\bodega 1\\Desktop\\workspace\\c2\\cyd_backend")"

print_step "Guardando variables del laboratorio en $LAB_ENV_FILE"
cat > "$LAB_ENV_FILE" <<EOF
export LAB_PC_USER="$LAB_PC_USER"
export LAB_PC_IP="$LAB_PC_IP"
export RPI_USER="$RPI_USER"
export RPI_IP="$RPI_IP"
export CYD_DEVICE_ID="$CYD_DEVICE_ID"
export CYD_BACKEND_PORT="$BACKEND_PORT"
export CYD_TOKEN_ID="$TOKEN_ID"
export CYD_SECRET_KEY="$SECRET_KEY"
export CYD_BACKEND_DIR_WIN="$BACKEND_DIR_WIN"
EOF

print_step "Preparando clave SSH"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -f "$HOME/.ssh/id_ed25519" -N ""
else
  printf 'La clave SSH ya existe en %s\n' "$HOME/.ssh/id_ed25519"
fi

print_step "Instalando helpers en $BASHRC_FILE"
append_once "$BASHRC_FILE" "# >>> termux-lab-setup >>>" "$(cat <<'EOF'
# >>> termux-lab-setup >>>
if [ -f "$HOME/.termux-lab.env" ]; then
  . "$HOME/.termux-lab.env"
fi

alias labpc='ssh "$LAB_PC_USER@$LAB_PC_IP"'
alias rpi='ssh "$RPI_USER@$RPI_IP"'
alias labscan='nmap -sn 192.168.1.0/24'
alias cydhealth='curl -fsS "http://$LAB_PC_IP:$CYD_BACKEND_PORT/health"'

cydstatus() {
  curl -fsS \
    -H "X-Token-Id: $CYD_TOKEN_ID" \
    -H "X-Secret-Key: $CYD_SECRET_KEY" \
    "http://$LAB_PC_IP:$CYD_BACKEND_PORT/api/v1/status"
}

cydlogs() {
  ssh "$LAB_PC_USER@$LAB_PC_IP" \
    "Get-Content -Path \"$CYD_BACKEND_DIR_WIN\\data\\backend.log\" -Tail 40"
}

cydserver() {
  ssh -t "$LAB_PC_USER@$LAB_PC_IP" \
    "cd \"$CYD_BACKEND_DIR_WIN\"; python .\\scripts\\run_backend.py"
}

cydpanel() {
  ssh -t "$LAB_PC_USER@$LAB_PC_IP" \
    "cd \"$CYD_BACKEND_DIR_WIN\"; python .\\scripts\\monitor_tui.py"
}

cydcmd() {
  if [ $# -lt 1 ]; then
    printf 'Uso: cydcmd COMANDO\n'
    return 1
  fi
  command_text="$*"
  ssh "$LAB_PC_USER@$LAB_PC_IP" \
    "cd \"$CYD_BACKEND_DIR_WIN\"; python .\\scripts\\queue_command.py --device \"$CYD_DEVICE_ID\" --command \"$command_text\""
}

cydcopykey() {
  cat "$HOME/.ssh/id_ed25519.pub"
}
# <<< termux-lab-setup <<<
EOF
)"

print_step "Resumen"
printf 'PC laboratorio : %s@%s\n' "$LAB_PC_USER" "$LAB_PC_IP"
printf 'Raspberry      : %s@%s\n' "$RPI_USER" "$RPI_IP"
printf 'Backend CYD    : http://%s:%s\n' "$LAB_PC_IP" "$BACKEND_PORT"
printf 'Device ID CYD  : %s\n' "$CYD_DEVICE_ID"

print_step "Clave publica SSH"
cat "$HOME/.ssh/id_ed25519.pub"

print_step "Comandos disponibles despues de ejecutar: source ~/.bashrc"
printf '%s\n' \
  "labpc       -> abrir SSH al PC del laboratorio" \
  "rpi         -> abrir SSH a la Raspberry" \
  "labscan     -> escanear la red local" \
  "cydhealth   -> consultar /health" \
  "cydstatus   -> consultar /api/v1/status" \
  "cydlogs     -> ver ultimos logs del backend" \
  "cydserver   -> levantar backend remoto" \
  "cydpanel    -> abrir panel ASCII remoto" \
  "cydcmd PING -> encolar comando a la CYD" \
  "cydcopykey  -> mostrar clave publica SSH"

print_step "Siguiente paso"
printf '%s\n' \
  "1. Copia la clave publica al PC y/o Raspberry en ~/.ssh/authorized_keys" \
  "2. Ejecuta: source ~/.bashrc" \
  "3. Prueba: cydhealth"
