# CYD HTTP Client

Proyecto separado del repo `firmware/` para conectar una CYD/ESP32 a un bridge HTTP en el PC.

## Qué hace

- Conecta la placa a Wi-Fi
- Prueba `GET /health`
- Hace `POST /api/v1/register`
- Hace `POST /api/v1/heartbeat`
- Consulta `GET /api/v1/commands`
- Sube resultados con `POST /api/v1/results`

## Configuración

Edita [src/config.h](./src/config.h):

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_HOST`
- `SERVER_PORT`
- `TOKEN_ID`
- `SECRET_KEY`
- `DEVICE_ID`

## Comandos soportados

- `PING`
- `GET_IP`
- `GET_HEAP`
- `ECHO <texto>`
- `REBOOT`

## Uso

1. Instala PlatformIO.
2. Abre esta carpeta como proyecto independiente:
   `c:\Users\bodega 1\Desktop\workspace\c2\cyd_http_client`
3. Compila y flashea.
4. Abre el monitor serie a `115200`.

## Bridge esperado

El cliente apunta al bridge HTTP en:

- `GET /health`
- `POST /api/v1/register`
- `POST /api/v1/heartbeat`
- `GET /api/v1/commands?device_id=...`
- `POST /api/v1/results`

## Nota

Este cliente es intencionalmente simple y no depende de Bruce. Si luego quieres, podemos agregar pantalla TFT, LEDs o integración específica para la CYD-2432S028.
