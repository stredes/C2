# CYD Backend

Backend HTTP local para recibir conexiones desde una CYD/ESP32 y manejar:

- `GET /health`
- `POST /api/v1/register`
- `POST /api/v1/heartbeat`
- `GET /api/v1/commands?device_id=...`
- `POST /api/v1/results`
- `GET /api/v1/status`

Esta implementacion usa solo la libreria estandar de Python, asi que funciona bien como backend liviano en Windows, Linux o Termux sin depender de Flask/FastAPI.

## Estructura

- `config/backend.json`: configuracion del backend
- `config/backend.termux.json.example`: ejemplo de configuracion para Termux/Nokia
- `app/server.py`: servidor HTTP
- `scripts/run_backend.py`: arranque del backend
- `scripts/run_backend_termux.sh`: arranque rapido para Termux
- `scripts/queue_command.py`: encola comandos para una CYD
- `scripts/monitor_tui.py`: panel ASCII para estado, puertos, logs y comandos
- `data/`: estado persistente y logs del backend
- `requirements.txt`: sin dependencias externas

## Uso

1. Revisa `config/backend.json`.
2. Inicia el backend:

```powershell
python scripts/run_backend.py
```

3. Prueba el healthcheck:

```powershell
curl http://127.0.0.1:8080/health
```

4. Encola un comando:

```powershell
python scripts/queue_command.py --device cyd-2432s028 --command PING
```

5. Abre el panel ASCII:

```powershell
python scripts/monitor_tui.py
```

## Uso en Termux

1. Instala Python si aun no lo tienes:

```bash
pkg update -y
pkg install -y python git
```

2. Copia o clona esta carpeta en el telefono.

3. En la raiz de `cyd_backend`, crea tu config local:

```bash
cp config/backend.termux.json.example config/backend.termux.json
```

4. Si quieres, cambia `port`, `token_id` o `secret_key` dentro de `config/backend.termux.json`.

5. Levanta el backend:

```bash
bash scripts/run_backend_termux.sh
```

6. Prueba desde el mismo Nokia:

```bash
curl http://127.0.0.1:8000/health
```

7. Prueba desde otro equipo de tu red usando la IP del telefono:

```bash
curl http://IP_DEL_NOKIA:8000/health
```

Notas para Android/Termux:

- Si Android mata procesos en segundo plano, usa `tmux` para dejarlo corriendo.
- La API autenticada sigue usando `X-Token-Id` y `X-Secret-Key`.
- Si el Nokia sera el backend principal de la red local, te conviene fijar una IP reservada en el router.

Desde ese panel puedes:

- ver si el backend responde y si la API autenticada esta disponible
- revisar dispositivos registrados y si quedaron `stale`
- detectar puertos serie del sistema
- ver logs y resultados recientes en tiempo real
- editar `host` y `port` del backend
- editar `SERVER_HOST` y `SERVER_PORT` del cliente CYD
- encolar comandos para el dispositivo

## Headers requeridos

Todos los endpoints `/api/v1/*` requieren:

```text
X-Token-Id: cyd-local
X-Secret-Key: cambia-esta-clave-larga
```

## Desde la CYD

Configura tu cliente/firmware para apuntar a:

- host: IP del PC en la red local
- puerto: `8080`
- token: `cyd-local`
- secret: `cambia-esta-clave-larga`

## Arranque minimo recomendado

En Termux:

```bash
cd ~/cyd_backend
cp config/backend.termux.json.example config/backend.termux.json
tmux new -s cyd
bash scripts/run_backend_termux.sh
```
