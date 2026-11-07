/*
  MNHS Review Center - ESP32 access point trial
  Board: ESP32 Dev Module (WROOM-32) - Arduino IDE, ESP32 core 3.x
  Students join MNHS-Review, then open http://192.168.4.50:5000
*/

#include <WiFi.h>
#include "esp_wifi.h"

static const char *AP_SSID = "MNHS-Review";
static const char *AP_PASS = "review2026";
static const IPAddress AP_IP(192, 168, 4, 1);
static const IPAddress AP_GATEWAY(192, 168, 4, 1);
static const IPAddress AP_MASK(255, 255, 255, 0);
static const uint8_t AP_CHANNEL = 1;   // Globe router sits on channel 8
static const uint8_t MAX_CLIENTS = 8;

static void printClients() {
  wifi_sta_list_t stations;
  if (esp_wifi_ap_get_sta_list(&stations) != ESP_OK) return;
  Serial.printf("clients: %d\n", stations.num);
  for (int i = 0; i < stations.num; i++) {
    const uint8_t *m = stations.sta[i].mac;
    Serial.printf("  %02X:%02X:%02X:%02X:%02X:%02X  rssi %d dBm\n",
                  m[0], m[1], m[2], m[3], m[4], m[5], stations.sta[i].rssi);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("\nMNHS Review Center AP trial");

  WiFi.persistent(false);
  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);

  if (!WiFi.softAPConfig(AP_IP, AP_GATEWAY, AP_MASK)) {
    Serial.println("AP config failed - halting");
    while (true) delay(1000);
  }

  if (!WiFi.softAP(AP_SSID, AP_PASS, AP_CHANNEL, false, MAX_CLIENTS)) {
    Serial.println("AP start failed - halting");
    while (true) delay(1000);
  }

  Serial.printf("SSID:     %s\n", AP_SSID);
  Serial.printf("Channel:  %u\n", AP_CHANNEL);
  Serial.printf("AP IP:    %s\n", WiFi.softAPIP().toString().c_str());
  Serial.println("Desktop:  http://192.168.4.50:5000");
  Serial.println("Phones:   http://192.168.4.50:5000");
}

void loop() {
  static uint32_t lastPrint = 0;
  if (millis() - lastPrint >= 5000) {
    lastPrint = millis();
    printClients();
  }
}
