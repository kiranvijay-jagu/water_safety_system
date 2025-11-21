#include <OneWire.h>
#include <DallasTemperature.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>

// DS18B20 temperature sensor on digital pin D4
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

// Sensor pins
#define TURBIDITY_PIN A0
#define TDS_PIN A1
#define PH_PIN A2
#define BUZZER_PIN 8
#define RELAY_PIN 9

// LCD I2C
LiquidCrystal_I2C lcd(0x27, 16, 2);

// Turbidity thresholds
float turb_cleanVoltage = 2.10;
float turb_dirtyVoltage = 1.20;
float turb_cleanNTU = 0.0;
float turb_dirtyNTU = 100.0;

// TDS calibration
float tds_voltageAt0ppm = 0.0;
float tds_voltageAt1000ppm = 3.0;
float tds0 = 0.0;
float tds1000 = 1000.0;

// LCD display mode
int displayMode = 0; // 0=sensors, 1=prediction
unsigned long lastModeSwitch = 0;
unsigned long modeSwitchInterval = 3000; // Switch every 3 seconds

// Store sensor values
float current_turbidity = 0;
float current_tds = 0;
float current_ph = 7.0;
float current_temp = 25.0;

// Store prediction
String predictionRisk = "Analyzing...";
String predictionIssue = "Please wait";

// Map float function
float mapFloat(float x, float in_min, float in_max, float out_min, float out_max) {
  return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void setup() {
  Serial.begin(9600);
  sensors.begin();
  lcd.init();
  lcd.backlight();
  pinMode(BUZZER_PIN, OUTPUT);
  pinMode(RELAY_PIN, OUTPUT);
  
  // Initialize: Buzzer OFF, Relay OFF
  digitalWrite(BUZZER_PIN, LOW);
  digitalWrite(RELAY_PIN, LOW);
  
  lcd.setCursor(0,0);
  lcd.print("Water Quality");
  lcd.setCursor(0,1);
  lcd.print("Monitor Started");
  delay(2000);
  lcd.clear();
}

void loop() {
  // --- Read Turbidity ---
  int turb_raw = analogRead(TURBIDITY_PIN);
  float turb_voltage = turb_raw * 5.0 / 1023.0;
  current_turbidity = mapFloat(turb_voltage, turb_cleanVoltage, turb_dirtyVoltage, turb_cleanNTU, turb_dirtyNTU);
  if (current_turbidity < 0) current_turbidity = 0;
  if (current_turbidity > turb_dirtyNTU) current_turbidity = turb_dirtyNTU;

  // --- Read TDS ---
  int tds_raw = analogRead(TDS_PIN);
  float tds_voltage = tds_raw * 5.0 / 1023.0;
  current_tds = mapFloat(tds_voltage, tds_voltageAt0ppm, tds_voltageAt1000ppm, tds0, tds1000);
  if (current_tds < 0) current_tds = 0;
  if (current_tds > 2000) current_tds = 2000;

  // --- Read pH (Calibrated) ---
  int ph_raw = analogRead(PH_PIN);
  float ph_voltage = ph_raw * 5.0 / 1023.0;
  float neutralVoltage = 3.57;  // pH 7 reference voltage
  current_ph = 7 - ((neutralVoltage - ph_voltage) / 0.18);  // 0.18V per pH unit
  if (current_ph < 0) current_ph = 0;
  if (current_ph > 14) current_ph = 14;

  // --- Read Temperature ---
  sensors.requestTemperatures();
  current_temp = sensors.getTempCByIndex(0);

  // --- Send all values via Serial (for Python backend) ---
  Serial.print(current_turbidity, 2); Serial.print(",");
  Serial.print(current_tds, 2); Serial.print(",");
  Serial.print(current_ph, 2); Serial.print(",");
  Serial.println(current_temp, 2);

  // --- Handle commands from Python ---
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();

    if (cmd.startsWith("RISK:")) {
      predictionRisk = cmd.substring(5);
    }
    else if (cmd.startsWith("ISSUE:")) {
      predictionIssue = cmd.substring(6);
    }
    else if (cmd == "RELAY:ON") {
      digitalWrite(RELAY_PIN, HIGH);
    }
    else if (cmd == "RELAY:OFF") {
      digitalWrite(RELAY_PIN, LOW);
    }
    else if (cmd == "BUZZER:ON") {
      digitalWrite(BUZZER_PIN, HIGH);
      delay(100);  // Original short beep
      digitalWrite(BUZZER_PIN, LOW);
    }
    else if (cmd == "BUZZER:OFF") {
      digitalWrite(BUZZER_PIN, LOW);
    }
  }

  // --- Update LCD Display (Alternate between sensors and prediction) ---
  unsigned long currentTime = millis();
  if (currentTime - lastModeSwitch >= modeSwitchInterval) {
    displayMode = 1 - displayMode; // Toggle between 0 and 1
    lastModeSwitch = currentTime;
    lcd.clear();
  }

  if (displayMode == 0) {
    // Show sensor readings
    displaySensorReadings();
  } else {
    // Show prediction result
    displayPrediction();
  }

  delay(1000);
}



void displaySensorReadings() {
  // Line 1: pH and TDS
  lcd.setCursor(0, 0);
  lcd.print("pH:");
  lcd.print(current_ph, 1);
  lcd.print("  Tds:");
  lcd.print((int)current_tds);
  
  
  // Line 2: Turbidity and Temperature
  lcd.setCursor(0, 1);
  lcd.print("Trb:");
  lcd.print(current_turbidity, 1);
  lcd.print(" Tem:");
  lcd.print((int)current_temp);
  lcd.print(" C");
}

void displayPrediction() {
  // Line 1: Risk level
  lcd.setCursor(0, 0);
  lcd.print(predictionRisk);
  
  // Line 2: Issue/Disease
  lcd.setCursor(0, 1);
  lcd.print(predictionIssue);
}