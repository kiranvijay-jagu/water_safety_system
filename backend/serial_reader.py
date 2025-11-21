import serial
import time
import requests
from datetime import datetime
import os
from dotenv import load_dotenv
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from requests import Session

load_dotenv()

# ===========================
# CONFIGURATION
# ===========================
ARDUINO_PORT = os.getenv('ARDUINO_PORT', 'COM11')
BAUD_RATE = 9600
SERIAL_TIMEOUT = 1

FLASK_HOST = "localhost"
FLASK_PORT = 5000
UPDATE_URL = f"http://{FLASK_HOST}:{FLASK_PORT}/api/update-sensor-reading"
PREDICT_URL = f"http://{FLASK_HOST}:{FLASK_PORT}/api/sensor-data"

READINGS_BUFFER = 5
RETRY_DELAY = 5
HTTP_TIMEOUT = 0.3  # Short timeout for instant updates

relay_permanently_off = False

# Thread-safe queues
sensor_queue = queue.Queue()
prediction_queue = queue.Queue()
instant_update_queue = queue.Queue()

# Thread control
stop_threads = threading.Event()

# Session for connection pooling
session = Session()

# ===========================
# BACKGROUND ASYNC SENDER
# ===========================
def async_sender_worker():
    """Background worker that sends readings asynchronously without blocking"""
    print("🟣 Async Sender Thread Started")
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        while not stop_threads.is_set():
            try:
                # Get latest reading from queue (non-blocking)
                try:
                    sensor_data = instant_update_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                
                # Submit to thread pool - won't block reader thread
                executor.submit(
                    _send_update_to_flask,
                    sensor_data
                )
                
            except Exception as e:
                print(f"⚠️ Async Sender Error: {e}")
    
    print("🟣 Async Sender Thread Stopped")

def _send_update_to_flask(sensor_data):
    """Actually send the HTTP request (runs in thread pool)"""
    try:
        response = session.post(
            UPDATE_URL,
            json=sensor_data,
            timeout=HTTP_TIMEOUT
        )
        if response.status_code == 200:
            pass  # Silent success
        else:
            pass  # Skip old data silently
    except requests.Timeout:
        pass  # Skip timeout silently - data is old anyway
    except Exception:
        pass  # Silent fail - don't block

# ===========================
# ARDUINO COMMUNICATION
# ===========================
def connect_arduino():
    """Establish serial connection with Arduino"""
    try:
        print(f"🔌 Attempting to connect to Arduino on {ARDUINO_PORT}...")
        arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=SERIAL_TIMEOUT)
        time.sleep(2)
        
        arduino.flushInput()
        arduino.flushOutput()
        
        print(f"✅ Successfully connected to Arduino on {ARDUINO_PORT}")
        print(f"📡 Baud Rate: {BAUD_RATE}")
        print(f"⚡ Relay initialized: OFF (default startup state)")
        
        return arduino
    except serial.SerialException as e:
        print(f"❌ Failed to connect to Arduino: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error connecting to Arduino: {e}")
        return None

def control_hardware(arduino, result):
    """Control relay and buzzer based on risk level"""
    global relay_permanently_off
    
    if not arduino or not arduino.is_open:
        return
    
    try:
        if result and 'prediction' in result:
            quality = result['prediction']['quality']
            
            risk_level = 'low'
            if 'HIGH RISK' in quality.upper():
                risk_level = 'high'
            elif 'MEDIUM RISK' in quality.upper():
                risk_level = 'medium'
            
            if risk_level == 'high' and not relay_permanently_off:
                arduino.write(b"RELAY:ON\n")
                time.sleep(0.1)
                relay_permanently_off = True
                print(f"   ⚡ Relay turned ON PERMANENTLY (High Risk detected)")
            
            if risk_level in ['medium', 'high']:
                arduino.write(b"BUZZER:ON\n")
                time.sleep(0.1)
                print(f"   🚨 Buzzer activated ({risk_level.upper()} risk)")
            
            if relay_permanently_off:
                print(f"   ⚡ Relay Status: ON (Permanent)")
            else:
                print(f"   ⚡ Relay Status: OFF (Normal)")
            
    except Exception as e:
        print(f"⚠️ Error controlling hardware: {e}")

def send_to_arduino(arduino, result):
    """Send ML prediction results to Arduino for LCD display"""
    if not arduino or not arduino.is_open:
        return
    
    try:
        if result and 'prediction' in result:
            quality = result['prediction']['quality']
            confidence = result['prediction']['confidence']
            
            quality_text = f"{quality[:12]} {confidence}%"
            arduino.write(f"RISK:{quality_text}\n".encode())
            time.sleep(0.15)
            
            if result.get('disease_risks') and len(result['disease_risks']) > 0:
                top_disease = result['disease_risks'][0]
                disease_name = top_disease['name'][:16]
                arduino.write(f"ISSUE:{disease_name}\n".encode())
                time.sleep(0.15)
            else:
                arduino.write(f"ISSUE:Safe to use\n".encode())
                time.sleep(0.15)
                
            print(f"   📟 LCD updated with results")
            
    except Exception as e:
        print(f"⚠️ Error sending to Arduino: {e}")

# ===========================
# DATA PARSING
# ===========================
def parse_sensor_line(line):
    """Parse sensor data line from Arduino"""
    try:
        values = line.split(',')
        
        if len(values) != 4:
            return None
        
        turbidity = float(values[0])
        tds = float(values[1])
        ph = float(values[2])
        temp = float(values[3])
        
        if not (0 <= turbidity <= 100):
            return None
        if not (0 <= tds <= 2000):
            return None
        if not (0 <= ph <= 14):
            return None
        if not (-10 <= temp <= 100):
            return None
        
        return {
            'turbidity': turbidity,
            'tds': tds,
            'ph': ph,
            'temperature': temp
        }
        
    except (ValueError, IndexError):
        return None
    except Exception:
        return None

# ===========================
# THREAD 1: ARDUINO READER (REAL-TIME)
# ===========================
def arduino_reader_thread(arduino):
    """
    Thread 1: Continuously reads from Arduino every second
    Sends instant updates to Flask asynchronously (non-blocking)
    Queues data for prediction thread
    """
    print("🔵 Thread 1: Arduino Reader Started")
    reading_count = 0
    sensor_buffer = []
    
    while not stop_threads.is_set():
        try:
            if arduino.in_waiting > 0:
                line = arduino.readline().decode('utf-8', errors='ignore').strip()
                
                if line:
                    sensor_data = parse_sensor_line(line)
                    
                    if sensor_data:
                        reading_count += 1
                        timestamp = datetime.now().strftime('%H:%M:%S')
                        
                        # Add timestamp to sensor data
                        sensor_data_with_time = sensor_data.copy()
                        sensor_data_with_time['time'] = timestamp
                        
                        # Display reading with timestamp
                        print(f"[{timestamp}] Reading #{reading_count}: "
                              f"Turbidity={sensor_data['turbidity']:.2f} NTU, "
                              f"TDS={sensor_data['tds']:.0f} ppm, "
                              f"pH={sensor_data['ph']:.2f}, "
                              f"Temp={sensor_data['temperature']:.1f}°C")
                        
                        # Queue for async send (no blocking)
                        instant_update_queue.put(sensor_data_with_time)
                        
                        # Add to buffer for prediction
                        sensor_buffer.append(sensor_data_with_time)
                        
                        # Queue for prediction every 5 readings
                        if len(sensor_buffer) >= READINGS_BUFFER:
                            prediction_queue.put({
                                'data': sensor_buffer[-1],  # Latest reading
                                'count': reading_count,
                                'time': timestamp
                            })
                            sensor_buffer = []
            
            time.sleep(0.1)
            
        except Exception as e:
            print(f"❌ Arduino Reader Error: {e}")
            time.sleep(1)
    
    print("🔵 Thread 1: Arduino Reader Stopped")

# ===========================
# THREAD 2: ML PREDICTION (BACKGROUND)
# ===========================
def prediction_thread(arduino):
    """
    Thread 2: Handles ML predictions in background
    Processes queued sensor data without blocking real-time readings
    """
    print("🟢 Thread 2: Prediction Handler Started")
    prediction_count = 0
    
    while not stop_threads.is_set():
        try:
            prediction_item = prediction_queue.get(timeout=1)
            
            if prediction_item:
                prediction_count += 1
                avg_data = prediction_item['data']
                reading_count = prediction_item['count']
                reading_time = prediction_item['time']
                
                print()
                print(f"{'='*70}")
                print(f"📤 PREDICTION #{prediction_count} at {reading_time}")
                print(f"{'='*70}")
                
                print(f"   Sensor Values (from reading at {reading_time}):")
                print(f"   • Turbidity: {avg_data['turbidity']:.2f} NTU")
                print(f"   • TDS: {avg_data['tds']:.0f} ppm")
                print(f"   • pH: {avg_data['ph']:.2f}")
                print(f"   • Temperature: {avg_data['temperature']:.1f}°C")
                print()
                
                try:
                    response = requests.post(PREDICT_URL, json=avg_data, timeout=10)
                    
                    if response.status_code == 200:
                        result = response.json()
                        
                        print(f"🎯 ML PREDICTION RESULTS:")
                        print(f"   Overall Quality: {result['prediction']['quality']}")
                        print(f"   Confidence: {result['prediction']['confidence']}%")
                        
                        if result.get('health_risks', {}).get('risk_factors'):
                            risk_factors = result['health_risks']['risk_factors']
                            if risk_factors and risk_factors[0] != "All OK":
                                print()
                                print(f"   ⚠️ PARAMETERS OUT OF RANGE:")
                                for factor in risk_factors:
                                    print(f"      • {factor}")
                        
                        if result.get('disease_risks'):
                            print()
                            print(f"   Disease Risk Analysis:")
                            for disease in result['disease_risks']:
                                emoji = "🚨" if disease['level'] == 'high' else "⚠️" if disease['level'] == 'medium' else "✅"
                                print(f"   {emoji} {disease['name']}: {disease['risk_percent']}% ({disease['status']})")
                        
                        print()
                        print(f"   🔧 HARDWARE CONTROL:")
                        control_hardware(arduino, result)
                        
                        print()
                        send_to_arduino(arduino, result)
                    else:
                        print(f"⚠️ Prediction failed: HTTP {response.status_code}")
                        
                except requests.Timeout:
                    print(f"❌ Prediction timeout")
                except Exception as e:
                    print(f"❌ Prediction error: {e}")
                
                print(f"{'='*70}")
                print(f"✅ Prediction complete - Arduino reading continues...")
                print(f"{'='*70}")
                print()
                
        except queue.Empty:
            continue
        except Exception as e:
            print(f"❌ Prediction Thread Error: {e}")
            time.sleep(1)
    
    print("🟢 Thread 2: Prediction Handler Stopped")

# ===========================
# MAIN MONITORING LOOP
# ===========================
def main():
    """Main function: Starts three threads"""
    global relay_permanently_off
    
    print("=" * 70)
    print("🌊 Smart Water Quality Monitor - Non-Blocking Async Architecture")
    print("=" * 70)
    print()
    
    arduino = connect_arduino()
    if not arduino:
        print("\n❌ Cannot proceed without Arduino connection")
        return
    
    try:
        arduino.write(b"RISK:System Ready\n")
        time.sleep(0.1)
        arduino.write(b"ISSUE:Reading...\n")
    except:
        pass
    
    print()
    print("📊 MULTITHREADED ARCHITECTURE")
    print(f"   • Thread 1: Arduino Reader (every 1 second)")
    print(f"   • Thread 2: ML Predictions (every 5 readings)")
    print(f"   • Thread 3: Async HTTP Sender (background, non-blocking)")
    print(f"   • HTTP Timeout: {HTTP_TIMEOUT}s (skip old data)")
    print(f"   • Timestamps: Every reading tracked with HH:MM:SS")
    print(f"   • Arduino Port: {ARDUINO_PORT}")
    print("   • Press Ctrl+C to stop")
    print("-" * 70)
    print()
    
    # Start all three threads
    sender_thread = threading.Thread(target=async_sender_worker, daemon=True)
    reader_thread = threading.Thread(target=arduino_reader_thread, args=(arduino,), daemon=True)
    predict_thread = threading.Thread(target=prediction_thread, args=(arduino,), daemon=True)
    
    sender_thread.start()
    reader_thread.start()
    predict_thread.start()
    
    try:
        while True:
            time.sleep(1)
    
    except KeyboardInterrupt:
        print("\n")
        print("=" * 70)
        print("🛑 STOPPING MONITORING SYSTEM")
        print("=" * 70)
        
        stop_threads.set()
        
        reader_thread.join(timeout=2)
        predict_thread.join(timeout=2)
        sender_thread.join(timeout=2)
        
        print("   ✅ All threads stopped")
        print("=" * 70)
        
        try:
            arduino.write(b"RISK:System Off\n")
            time.sleep(0.1)
            arduino.write(b"ISSUE:Goodbye!\n")
        except:
            pass
    
    finally:
        session.close()
        if arduino and arduino.is_open:
            arduino.close()
            print("🔌 Arduino connection closed")
        print("👋 Goodbye!")

# ===========================
# ENTRY POINT
# ===========================
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🌊 NON-BLOCKING ASYNC WATER QUALITY MONITORING")
    print("=" * 70)
    print("\n⚙️ Configuration:")
    print(f"   • Architecture: Triple-threaded (Reader + Predictor + Async Sender)")
    print(f"   • Sensor Reading: Every 1 second (Thread 1)")
    print(f"   • ML Prediction: Every 5 readings (Thread 2)")
    print(f"   • Async HTTP Send: Background (Thread 3, non-blocking)")
    print(f"   • HTTP Timeout: {HTTP_TIMEOUT}s (skip old readings)")
    print(f"   • Timestamps: HH:MM:SS format for all readings")
    print(f"   • Arduino Port: {ARDUINO_PORT}")
    print(f"   • Flask API: {UPDATE_URL}")
    print("=" * 70 + "\n")
    
    try:
        response = requests.get(f"http://{FLASK_HOST}:{FLASK_PORT}", timeout=2)
        print("✅ Flask server detected - Starting monitoring...\n")
        main()
    except:
        print("\n⚠️ Flask server not detected!")
        print(f"   Cannot reach http://{FLASK_HOST}:{FLASK_PORT}")
        print("\n   Please start Flask server first:")
        print("   Command: python app.py")