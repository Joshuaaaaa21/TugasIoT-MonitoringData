#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

#define DHTPIN 17
#define DHTTYPE DHT22
#define LEDPIN 16
#define LIGHTPIN 34
#define LIGHT_ADC_MAX 4095

const char* ssid = "Wokwi-GUEST";
const char* password = "";
const char* mqtt_server = "broker.hivemq.com";
const char* topic_pub = "IF_IoT/datasensor";
const char* topic_sub = "IF_IoT/led";

WiFiClient espClient;
PubSubClient client(espClient);
DHT dht(DHTPIN, DHTTYPE);

void setup_wifi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println(" connected");
}

void callback(char* topic, byte* payload, unsigned int length) {
  if (strcmp(topic, topic_sub) == 0 && length > 0) {
    if ((char)payload[0] == '1') {
      digitalWrite(LEDPIN, HIGH);
    } else {
      digitalWrite(LEDPIN, LOW);
    }
  }
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("esp32-client-monitor")) {
      client.subscribe(topic_sub);
      Serial.println(" connected");
    } else {
      Serial.print(" failed, state=");
      Serial.println(client.state());
      delay(1000);
    }
  }
}

void setup() {
  Serial.begin(115200);
  pinMode(LEDPIN, OUTPUT);
  pinMode(LIGHTPIN, INPUT);
  dht.begin();
  
  setup_wifi();
  client.setServer(mqtt_server, 1883);
  client.setCallback(callback);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  float temp = dht.readTemperature();
  
  if (!isnan(temp)) {
    JsonDocument doc;
    doc["time"] = millis() / 1000;
    doc["temp"] = temp;
    
    int light = analogRead(LIGHTPIN);
    doc["light"] = light;

    char buffer[128];
    serializeJson(doc, buffer);
    bool published = client.publish(topic_pub, buffer);

    Serial.print("Publish ");
    Serial.print(published ? "OK " : "FAILED ");
    Serial.print("topic=");
    Serial.print(topic_pub);
    Serial.print(" payload=");
    Serial.println(buffer);
  } else {
    Serial.println("DHT22 read failed");
  }
  
  delay(2000);
}