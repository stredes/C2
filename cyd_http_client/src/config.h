#ifndef CYD_HTTP_CLIENT_CONFIG_H
#define CYD_HTTP_CLIENT_CONFIG_H

namespace cfg {
constexpr const char *WIFI_SSID = "TU_WIFI";
constexpr const char *WIFI_PASSWORD = "TU_CLAVE_WIFI";

constexpr const char *SERVER_HOST = "192.168.1.193";
constexpr uint16_t SERVER_PORT = 8080;

constexpr const char *TOKEN_ID = "cyd-local";
constexpr const char *SECRET_KEY = "cambia-esta-clave-larga";

constexpr const char *DEVICE_ID = "cyd-2432s028";
constexpr const char *DEVICE_LABEL = "CYD HTTP Client";
constexpr const char *FIRMWARE_VERSION = "cyd-http-client-0.1.0";

constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 20000;
constexpr uint32_t HEALTHCHECK_INTERVAL_MS = 30000;
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 15000;
constexpr uint32_t COMMAND_POLL_INTERVAL_MS = 5000;
} // namespace cfg

#endif
