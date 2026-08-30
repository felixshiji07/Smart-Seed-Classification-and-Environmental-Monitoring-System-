#include "esp_camera.h"
#include <WiFi.h>
#include <DHT.h>

const char* ssid     = "abcde";
const char* password = "1234567890";
void startCameraServer();

#define SOIL_PIN  12
#define DHT_PIN   14
#define DHT_TYPE  DHT22

DHT dht(DHT_PIN, DHT_TYPE);
unsigned long lastRead = 0;

void setup() {
  Serial.begin(115200);
  Serial.println("Booting...");
  pinMode(SOIL_PIN, INPUT);
  dht.begin();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0; config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0=5;  config.pin_d1=18; config.pin_d2=19; config.pin_d3=21;
  config.pin_d4=36; config.pin_d5=39; config.pin_d6=34; config.pin_d7=35;
  config.pin_xclk=0; config.pin_pclk=22; config.pin_vsync=25; config.pin_href=23;
  config.pin_sscb_sda=26; config.pin_sscb_scl=27;
  config.pin_pwdn=32; config.pin_reset=-1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size   = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count     = 1;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init FAILED: 0x%x\n", err);
    return;
  }

  sensor_t* s = esp_camera_sensor_get();
  s->set_framesize(s, FRAMESIZE_VGA);

  Serial.println("Camera OK");

  WiFi.begin(ssid, password);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.println(WiFi.localIP());
  startCameraServer();
  Serial.println("Stream ready");
}

void loop() {
  unsigned long now = millis();
  if (now - lastRead >= 3000) {
    lastRead = now;

    int state = digitalRead(SOIL_PIN);
    Serial.println(state == LOW ? "Soil Moisture: WET" : "Soil Moisture: DRY");

    float hum  = dht.readHumidity();
    float temp = dht.readTemperature();
    if (!isnan(hum) && !isnan(temp)) {
      Serial.print("Humidity: ");     Serial.print(hum);  Serial.println("%");
      Serial.print("Temperature: "); Serial.print(temp); Serial.println("C");
    } else {
      Serial.println("Humidity: --");
      Serial.println("Temperature: --");
    }
  }
}