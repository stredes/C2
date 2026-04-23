#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>
#include <esp_system.h>

#include "config.h"

namespace {
String deviceIp = "0.0.0.0";
unsigned long lastHealthcheckMs = 0;
unsigned long lastHeartbeatMs = 0;
unsigned long lastCommandPollMs = 0;
bool registerSent = false;

String serverBaseUrl() {
    return String("http://") + cfg::SERVER_HOST + ":" + String(cfg::SERVER_PORT);
}

void addAuthHeaders(HTTPClient &http) {
    http.addHeader("X-Token-Id", cfg::TOKEN_ID);
    http.addHeader("X-Secret-Key", cfg::SECRET_KEY);
    http.addHeader("Content-Type", "application/json");
}

bool connectWifi() {
    Serial.printf("Connecting WiFi SSID=%s\n", cfg::WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(cfg::WIFI_SSID, cfg::WIFI_PASSWORD);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < cfg::WIFI_CONNECT_TIMEOUT_MS) {
        delay(250);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("WiFi connection failed");
        deviceIp = "0.0.0.0";
        return false;
    }

    deviceIp = WiFi.localIP().toString();
    Serial.printf("WiFi connected, IP=%s\n", deviceIp.c_str());
    return true;
}

bool httpGet(String url, String &responseBody, int &statusCode, bool withAuth) {
    HTTPClient http;
    http.setConnectTimeout(5000);
    http.setTimeout(8000);

    if (!http.begin(url)) {
        responseBody = "http.begin failed";
        statusCode = -1;
        return false;
    }

    if (withAuth) addAuthHeaders(http);
    statusCode = http.GET();
    responseBody = statusCode > 0 ? http.getString() : http.errorToString(statusCode);
    http.end();
    return statusCode > 0 && statusCode < 400;
}

bool httpPost(String url, const String &payload, String &responseBody, int &statusCode) {
    HTTPClient http;
    http.setConnectTimeout(5000);
    http.setTimeout(8000);

    if (!http.begin(url)) {
        responseBody = "http.begin failed";
        statusCode = -1;
        return false;
    }

    addAuthHeaders(http);
    statusCode = http.POST(payload);
    responseBody = statusCode > 0 ? http.getString() : http.errorToString(statusCode);
    http.end();
    return statusCode > 0 && statusCode < 400;
}

String buildRegisterPayload() {
    JsonDocument doc;
    doc["device_id"] = cfg::DEVICE_ID;
    doc["label"] = cfg::DEVICE_LABEL;
    doc["platform"] = "esp32";
    doc["firmware"] = cfg::FIRMWARE_VERSION;
    doc["ip"] = deviceIp;

    String payload;
    serializeJson(doc, payload);
    return payload;
}

String buildHeartbeatPayload() {
    JsonDocument doc;
    doc["device_id"] = cfg::DEVICE_ID;
    doc["label"] = cfg::DEVICE_LABEL;
    doc["platform"] = "esp32";
    doc["firmware"] = cfg::FIRMWARE_VERSION;
    doc["ip"] = deviceIp;
    doc["status"] = "online";

    JsonObject metrics = doc["metrics"].to<JsonObject>();
    metrics["free_heap"] = ESP.getFreeHeap();
    metrics["rssi"] = WiFi.RSSI();

    String payload;
    serializeJson(doc, payload);
    return payload;
}

String buildResultPayload(const String &commandId, bool ok, const String &output) {
    JsonDocument doc;
    doc["device_id"] = cfg::DEVICE_ID;
    doc["command_id"] = commandId;
    doc["ok"] = ok;
    doc["output"] = output;

    String payload;
    serializeJson(doc, payload);
    return payload;
}

bool sendRegister() {
    String body;
    int statusCode = 0;
    bool ok = httpPost(serverBaseUrl() + "/api/v1/register", buildRegisterPayload(), body, statusCode);
    Serial.printf("REGISTER status=%d ok=%d\n%s\n", statusCode, ok ? 1 : 0, body.c_str());
    return ok;
}

bool sendHeartbeat() {
    String body;
    int statusCode = 0;
    bool ok = httpPost(serverBaseUrl() + "/api/v1/heartbeat", buildHeartbeatPayload(), body, statusCode);
    Serial.printf("HEARTBEAT status=%d ok=%d\n%s\n", statusCode, ok ? 1 : 0, body.c_str());
    return ok;
}

bool sendHealthcheck() {
    String body;
    int statusCode = 0;
    bool ok = httpGet(serverBaseUrl() + "/health", body, statusCode, false);
    Serial.printf("HEALTH status=%d ok=%d\n%s\n", statusCode, ok ? 1 : 0, body.c_str());
    return ok;
}

void sendCommandResult(const String &commandId, bool ok, const String &output) {
    String body;
    int statusCode = 0;
    bool posted = httpPost(serverBaseUrl() + "/api/v1/results", buildResultPayload(commandId, ok, output), body, statusCode);
    Serial.printf("RESULT status=%d ok=%d\n%s\n", statusCode, posted ? 1 : 0, body.c_str());
}

bool executeCommand(const String &command, String &output) {
    String cmd = command;
    cmd.trim();

    if (cmd.equalsIgnoreCase("PING")) {
        output = "PONG";
        return true;
    }

    if (cmd.equalsIgnoreCase("GET_IP")) {
        output = deviceIp;
        return true;
    }

    if (cmd.equalsIgnoreCase("GET_HEAP")) {
        output = String(ESP.getFreeHeap());
        return true;
    }

    if (cmd.startsWith("ECHO ")) {
        output = cmd.substring(5);
        return true;
    }

    if (cmd.equalsIgnoreCase("REBOOT")) {
        output = "Rebooting";
        return true;
    }

    output = "Unsupported command: " + cmd;
    return false;
}

void handleCommandQueue() {
    String body;
    int statusCode = 0;
    String url = serverBaseUrl() + "/api/v1/commands?device_id=" + cfg::DEVICE_ID;
    bool ok = httpGet(url, body, statusCode, true);
    Serial.printf("COMMANDS status=%d ok=%d\n%s\n", statusCode, ok ? 1 : 0, body.c_str());
    if (!ok) return;

    JsonDocument doc;
    DeserializationError error = deserializeJson(doc, body);
    if (error) {
        Serial.printf("JSON parse error: %s\n", error.c_str());
        return;
    }

    if (!doc["command"].is<JsonObject>()) return;

    JsonObject commandObj = doc["command"].as<JsonObject>();
    String commandId = commandObj["command_id"] | "";
    String command = commandObj["command"] | "";
    if (command.length() == 0 || commandId.length() == 0) return;

    String output;
    bool executed = executeCommand(command, output);
    sendCommandResult(commandId, executed, output);

    if (command.equalsIgnoreCase("REBOOT")) {
        delay(500);
        ESP.restart();
    }
}

void ensureWifi() {
    if (WiFi.status() == WL_CONNECTED) {
        deviceIp = WiFi.localIP().toString();
        return;
    }

    registerSent = false;
    connectWifi();
}
} // namespace

void setup() {
    Serial.begin(115200);
    delay(200);
    Serial.println();
    Serial.println("CYD HTTP Client booting");

    connectWifi();
    sendHealthcheck();
    registerSent = sendRegister();
}

void loop() {
    ensureWifi();
    const unsigned long now = millis();

    if (WiFi.status() != WL_CONNECTED) {
        delay(500);
        return;
    }

    if (!registerSent) {
        registerSent = sendRegister();
    }

    if (now - lastHealthcheckMs >= cfg::HEALTHCHECK_INTERVAL_MS) {
        lastHealthcheckMs = now;
        sendHealthcheck();
    }

    if (now - lastHeartbeatMs >= cfg::HEARTBEAT_INTERVAL_MS) {
        lastHeartbeatMs = now;
        sendHeartbeat();
    }

    if (now - lastCommandPollMs >= cfg::COMMAND_POLL_INTERVAL_MS) {
        lastCommandPollMs = now;
        handleCommandQueue();
    }

    delay(25);
}
