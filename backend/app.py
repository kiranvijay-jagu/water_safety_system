"""
Smart Water Safety & Disease Alert System
Enhanced Backend - Real-time + Storage Separation
FIXED: Proper disease display, range checking, real-time streaming
"""

from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import pandas as pd
import numpy as np
import joblib
import os
import requests
from datetime import datetime
from dotenv import load_dotenv
import random
import time

load_dotenv()

app = Flask(__name__, template_folder='../templates', static_folder='../static')
CORS(app)

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'water_quality_model_best.pkl')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')

model = None
try:
    model = joblib.load(MODEL_PATH)
    print("✅ ML Model loaded successfully!")
    print(f"   Model path: {MODEL_PATH}")
except Exception as e:
    print(f"⚠️ Model not found: {e}")
    print("   Place 'water_quality_model_best.pkl' in models/ folder")

DISEASE_NAMES = [
    "Diarrhea", "Dysentery", "Typhoid", "Cholera", "Kidney Stones",
    "Skin Irritation", "Hepatitis A", "Giardiasis", "Cryptosporidiosis", "E. coli Infection"
]

DISEASE_INFO = {
    "Cholera": {
        "cause": "Caused by Vibrio cholerae bacteria in contaminated water or food.",
        "symptoms": "Severe watery diarrhea, vomiting, dehydration.",
        "precautions": "Drink safe water, practice good hygiene, wash hands, avoid raw or undercooked food.",
        "treatment": "Rehydration therapy (oral or IV), antibiotics in severe cases."
    },
    "Diarrhea": {
        "cause": "Often caused by bacteria, viruses, or parasites in contaminated water or food.",
        "symptoms": "Frequent loose stools, dehydration, abdominal cramps.",
        "precautions": "Drink boiled or filtered water, maintain hygiene, wash hands.",
        "treatment": "Hydration, electrolyte replacement, antibiotics if bacterial cause is confirmed."
    },
    # Add all others similarly...
}

TRAINED_FAQ = {
    "which water is better": "Best water: potable, treated water that meets WHO guidelines...",
    "tell about disease": "Waterborne diseases are illnesses caused by pathogenic microorganisms...",
    "ask precautions according to disease": "Precautions vary by disease — boil or filter water, wash hands...",
    "ask treatment according to disease": "Treatments: ORS, antibiotics for bacterial infections, supportive care for viral causes...",
    "ask who guidelines": "WHO: Turbidity <5 NTU; TDS <500 ppm; pH 6.5-8.5; maintain sanitation and hand hygiene."
}

latest_sensor_data = {
    'turbidity': 2.0, 'tds': 200, 'ph': 7.0, 'temperature': 25.0,
    'quality': 'Analyzing', 'diseases': [], 'disease_details': [],
    'last_reading_time': None, 'reading_count': 0, 'time': '', 'out_of_range': []
}

def predict_disease_risks(turbidity, tds, ph, temp):
    """Predict disease risks using ML model"""
    if model is None:
        return None, "Model not loaded"
    
    try:
        X_input = np.array([[turbidity, tds, ph, temp]])
        predictions = model.predict(X_input)[0]
        
        disease_results = []
        high_risk = False
        medium_risk = False
        
        for i, risk_percent in enumerate(predictions):
            if risk_percent < 40:
                status = "LOW RISK"
                risk_level = "low"
            elif risk_percent < 55:
                status = "MEDIUM RISK ⚠️"
                risk_level = "medium"
                medium_risk = True
            else:
                status = "HIGH RISK 🚨"
                risk_level = "high"
                high_risk = True
            
            disease_results.append({
                'name': DISEASE_NAMES[i],
                'risk_percent': round(float(risk_percent), 1),
                'status': status,
                'level': risk_level
            })
        
        overall_risk = "HIGH RISK 🚨" if high_risk else "MEDIUM RISK ⚠️" if medium_risk else "LOW RISK"
        return disease_results, overall_risk
    
    except Exception as e:
        print(f"Prediction error: {e}")
        return None, "Prediction failed"

def check_parameter_issues(turbidity, tds, ph, temp):
    """Check which water parameters are outside WHO safe ranges"""
    issues = []
    if turbidity > 5:
        issues.append("Turbidity High")
    if tds > 500:
        issues.append("TDS High")
    if ph < 6.5 or ph > 8.5:
        issues.append("pH Out Range")
    if temp > 50:
        issues.append("Temp High")
    return issues if issues else ["All OK"]

def log_reading(turbidity, tds, ph, temp, overall_risk, disease_results):
    """Log sensor readings to CSV file - ONLY PREDICTIONS"""
    log_file = 'data/logs.csv'
    os.makedirs('data', exist_ok=True)
    
    high_risk_diseases = [d['name'] for d in disease_results if d['level'] in ['high', 'medium']]
    diseases_str = ', '.join(high_risk_diseases) if high_risk_diseases else 'None'
    
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'turbidity': turbidity, 'tds': tds, 'ph': ph, 'temperature': temp,
        'quality': overall_risk, 'diseases': diseases_str
    }
    
    df = pd.DataFrame([log_entry])
    if os.path.exists(log_file):
        df.to_csv(log_file, mode='a', header=False, index=False)
    else:
        df.to_csv(log_file, mode='w', header=True, index=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/update-sensor-reading', methods=['POST'])
def update_sensor_reading():
    """Update sensor reading - REAL-TIME DISPLAY (no prediction, no logging)"""
    global latest_sensor_data
    
    try:
        data = request.json
        turbidity = float(data.get('turbidity', 2.0))
        tds = float(data.get('tds', 200))
        ph = float(data.get('ph', 7.0))
        temp = float(data.get('temperature', 25))
        reading_time = data.get('time', datetime.now().strftime('%H:%M:%S'))
        
        # Check parameter ranges
        out_of_range = []
        if turbidity > 5:
            out_of_range.append({'parameter': 'Turbidity', 'value': turbidity, 'unit': 'NTU', 'safe_range': '< 5', 'status': 'HIGH'})
        if tds > 500:
            out_of_range.append({'parameter': 'TDS', 'value': tds, 'unit': 'ppm', 'safe_range': '< 500', 'status': 'HIGH'})
        if ph < 6.5 or ph > 8.5:
            out_of_range.append({'parameter': 'pH', 'value': ph, 'unit': '', 'safe_range': '6.5 - 8.5', 'status': 'OUT OF RANGE'})
        if temp > 50:
            out_of_range.append({'parameter': 'Temperature', 'value': temp, 'unit': '°C', 'safe_range': '< 50', 'status': 'HIGH'})
        
        # Update live sensor data immediately
        latest_sensor_data.update({
            'turbidity': turbidity, 'tds': tds, 'ph': ph, 'temperature': temp,
            'last_reading_time': time.time(), 'time': reading_time, 'out_of_range': out_of_range
        })
        
        print(f"[{reading_time}] Sensor Reading: Turbidity={turbidity:.2f}, TDS={tds:.0f}, pH={ph:.2f}, Temp={temp:.1f}")
        
        return jsonify({
            'status': 'success',
            'message': 'Sensor reading updated (real-time)',
            'out_of_range_parameters': out_of_range,
            'reading_time': reading_time
        })
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/sensor-data', methods=['POST'])
def receive_sensor_data():
    """Receive sensor data with ML prediction - LOGS TO HISTORY"""
    global latest_sensor_data
    
    try:
        data = request.json
        turbidity = float(data.get('turbidity', 2.0))
        tds = float(data.get('tds', 200))
        ph = float(data.get('ph', 7.0))
        temp = float(data.get('temperature', 25))
        reading_time = data.get('time', datetime.now().strftime('%H:%M:%S'))
        
        disease_results, overall_risk = predict_disease_risks(turbidity, tds, ph, temp)
        
        if disease_results is None:
            return jsonify({'status': 'error', 'message': 'Model prediction failed'}), 500
        
        issues = check_parameter_issues(turbidity, tds, ph, temp)
        log_reading(turbidity, tds, ph, temp, overall_risk, disease_results)
        
        # Build out_of_range for this prediction
        out_of_range = []
        if turbidity > 5:
            out_of_range.append({'parameter': 'Turbidity', 'value': turbidity, 'unit': 'NTU', 'safe_range': '< 5', 'status': 'HIGH'})
        if tds > 500:
            out_of_range.append({'parameter': 'TDS', 'value': tds, 'unit': 'ppm', 'safe_range': '< 500', 'status': 'HIGH'})
        if ph < 6.5 or ph > 8.5:
            out_of_range.append({'parameter': 'pH', 'value': ph, 'unit': '', 'safe_range': '6.5 - 8.5', 'status': 'OUT OF RANGE'})
        if temp > 50:
            out_of_range.append({'parameter': 'Temperature', 'value': temp, 'unit': '°C', 'safe_range': '< 50', 'status': 'HIGH'})
        
        # Update global state with prediction
        latest_sensor_data = {
            'turbidity': turbidity, 'tds': tds, 'ph': ph, 'temperature': temp,
            'quality': overall_risk, 'diseases': [d['name'] for d in disease_results if d['level'] in ['high', 'medium']],
            'disease_details': disease_results, 'last_reading_time': time.time(),
            'reading_count': 0, 'time': reading_time, 'out_of_range': out_of_range
        }
        
        print(f"\n{'='*70}")
        print(f"🎯 PREDICTION at {reading_time}")
        print(f"   Quality: {overall_risk}")
        print(f"   Logged to history")
        print(f"{'='*70}\n")
        
        response = {
            'status': 'success',
            'sensor_data': {
                'turbidity': round(turbidity, 2), 'tds': round(tds, 2),
                'ph': round(ph, 2), 'temperature': round(temp, 2), 'time': reading_time
            },
            'prediction': {'quality': overall_risk, 'confidence': 95.0},
            'disease_risks': disease_results,
            'health_risks': {
                'diseases': [d['name'] for d in disease_results if d['level'] in ['high', 'medium']],
                'risk_factors': issues
            },
            'who_guidelines': {
                'turbidity': '< 5 NTU', 'tds': '< 500 ppm',
                'ph': '6.5 - 8.5', 'temperature': '< 50°C'
            },
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        return jsonify(response)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/get-latest-state', methods=['GET'])
def get_latest_state():
    """Return current sensor state with live values"""
    global latest_sensor_data
    
    return jsonify({
        'status': 'success',
        'data': latest_sensor_data
    })

@app.route('/api/chat', methods=['POST'])
def chat_with_ai():
    """AI Chatbot endpoint"""
    global latest_sensor_data

    try:
        data = request.json
        user_question = data.get('question', '')
        quality_data = data.get('quality_data', None)

        # Use latest_sensor_data if no external quality_data is provided
        if quality_data:
            sensor_data = quality_data.get('sensor_data', latest_sensor_data)
            disease_risks = quality_data.get('disease_risks', latest_sensor_data.get('disease_details', []))
            prediction = quality_data.get('prediction', {'quality': latest_sensor_data.get('quality', 'Unknown')})
            health_risks = quality_data.get('health_risks', {'diseases': latest_sensor_data.get('diseases', [])})
        else:
            sensor_data = latest_sensor_data
            disease_risks = latest_sensor_data.get('disease_details', [])
            prediction = {'quality': latest_sensor_data.get('quality', 'Unknown')}
            health_risks = {'diseases': latest_sensor_data.get('diseases', [])}

        # Update latest_sensor_data for context
        latest_sensor_data.update({
            'turbidity': sensor_data.get('turbidity', latest_sensor_data.get('turbidity', 0)),
            'tds': sensor_data.get('tds', latest_sensor_data.get('tds', 0)),
            'ph': sensor_data.get('ph', latest_sensor_data.get('ph', 0)),
            'temperature': sensor_data.get('temperature', latest_sensor_data.get('temperature', 0)),
            'quality': prediction.get('quality', latest_sensor_data.get('quality', 'Unknown')),
            'diseases': health_risks.get('diseases', []),
            'disease_details': disease_risks
        })

        # Build context string for AI
        context = (
            f"Water Quality Data: Turbidity: {latest_sensor_data.get('turbidity', 0)} NTU, "
            f"TDS: {latest_sensor_data.get('tds', 0)} ppm, "
            f"pH: {latest_sensor_data.get('ph', 0)}, "
            f"Temperature: {latest_sensor_data.get('temperature', 0)} °C, "
            f"Risk: {latest_sensor_data.get('quality', 'Unknown')}"
        )

        # Generate AI response
        response_text = generate_chat_response(user_question, context, disease_risks)

        return jsonify({
            'status': 'success',
            'question': user_question,
            'answer': response_text,
            'context': latest_sensor_data,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 400


def generate_chat_response(question, context, disease_risks=None):
    """Generate AI response based on FAQ, disease info, latest sensor data, and high-risk diseases"""
    global latest_sensor_data
    q = question.strip().lower()

    # Match trained FAQ
    for key in TRAINED_FAQ:
        if key in q:
            return TRAINED_FAQ[key]

    # Match specific disease
    for disease in DISEASE_NAMES:
        if disease.lower() in q:
            info = DISEASE_INFO.get(disease, {})
            return (
                f"{disease}\n"
                f"Cause: {info.get('cause', 'N/A')}\n"
                f"Symptoms: {info.get('symptoms', 'N/A')}\n"
                f"Precautions: {info.get('precautions', 'N/A')}\n"
                f"Treatment: {info.get('treatment', 'N/A')}"
            )

    # Specific new question: diseases caused by water
    if "what diseases" in q and "cause" in q:
        high_risk_diseases = latest_sensor_data.get('diseases', [])
        if high_risk_diseases:
            return f"🚨 This water can cause {', '.join(high_risk_diseases)}"
        else:
            return "✅ No significant waterborne disease risk detected currently."

    # Precautions
    if any(w in q for w in ["prevent", "precaution", "avoid"]):
        lines = ["💧 Water safety precautions:"]
        for d in DISEASE_NAMES:
            info = DISEASE_INFO.get(d, {})
            lines.append(f"• {d}: {info.get('precautions','N/A')}")
        return "\n".join(lines)

    # Treatments
    if any(w in q for w in ["treat", "treatment", "cure"]):
        lines = ["💊 Disease treatments:"]
        for d in DISEASE_NAMES:
            info = DISEASE_INFO.get(d, {})
            lines.append(f"• {d}: {info.get('treatment','N/A')}")
        return "\n".join(lines)

    # Safe to drink check
    quality = latest_sensor_data.get('quality','Unknown')
    if "safe" in q or "drink" in q or "consume" in q:
        if quality == "LOW RISK":
            return "✅ Water is currently SAFE to drink."
        elif "MEDIUM" in quality:
            return "⚠️ MEDIUM RISK: Boil water before use."
        else:
            return "🚨 HIGH RISK: Do NOT drink."

    return "Ask about water safety, diseases, treatment, or precautions."

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get historical readings"""
    try:
        log_file = 'data/logs.csv'
        os.makedirs('data', exist_ok=True)
        
        if not os.path.exists(log_file) or os.path.getsize(log_file) == 0:
            return jsonify({'status': 'success', 'data': []})
        
        df = pd.read_csv(log_file, encoding='utf-8')
        if df.empty:
            return jsonify({'status': 'success', 'data': []})
        
        df = df.fillna({'timestamp': '', 'turbidity': 0.0, 'tds': 0.0, 'ph': 7.0, 'temperature': 25.0, 'quality': 'Unknown', 'diseases': 'None'})
        df['turbidity'] = pd.to_numeric(df['turbidity'], errors='coerce').fillna(0.0)
        df['tds'] = pd.to_numeric(df['tds'], errors='coerce').fillna(0.0)
        df['ph'] = pd.to_numeric(df['ph'], errors='coerce').fillna(7.0)
        df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce').fillna(25.0)
        
        all_data = df.to_dict('records')
        print(f"✅ History returned: {len(all_data)} readings")
        
        return jsonify({'status': 'success', 'data': all_data, 'count': len(all_data)})
    
    except Exception as e:
        print(f"❌ Error loading history: {e}")
        return jsonify({'status': 'error', 'message': str(e), 'data': []}), 400

@app.route('/api/graph-data', methods=['GET'])
def get_graph_data():
    """Get data for graphs"""
    try:
        log_file = 'data/logs.csv'
        os.makedirs('data', exist_ok=True)
        
        if not os.path.exists(log_file):
            return jsonify({'status': 'success', 'data': {'timestamps': [], 'turbidity': [], 'tds': [], 'ph': [], 'temperature': [], 'quality': []}})
        
        df = pd.read_csv(log_file)
        if df.empty:
            return jsonify({'status': 'success', 'data': {'timestamps': [], 'turbidity': [], 'tds': [], 'ph': [], 'temperature': [], 'quality': []}})
        
        recent_data = df.tail(20).fillna({'timestamp': '', 'turbidity': 0.0, 'tds': 0.0, 'ph': 7.0, 'temperature': 25.0, 'quality': 'Unknown'})
        
        graph_data = {
            'timestamps': recent_data['timestamp'].tolist(),
            'turbidity': recent_data['turbidity'].tolist(),
            'tds': recent_data['tds'].tolist(),
            'ph': recent_data['ph'].tolist(),
            'temperature': recent_data['temperature'].tolist(),
            'quality': recent_data['quality'].tolist()
        }
        
        return jsonify({'status': 'success', 'data': graph_data})
    
    except Exception as e:
        print(f"❌ Error loading graph data: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Clear history"""
    try:
        log_file = 'data/logs.csv'
        os.makedirs('data', exist_ok=True)
        
        df = pd.DataFrame(columns=['timestamp', 'turbidity', 'tds', 'ph', 'temperature', 'quality', 'diseases'])
        df.to_csv(log_file, mode='w', header=True, index=False)
        
        print("✅ History cleared")
        return jsonify({'status': 'success', 'message': 'History cleared'})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 400

@app.route('/api/simulate', methods=['GET'])
def simulate_data():
    """Simulate sensor data"""
    scenarios = [
        {'turbidity': 1.5, 'tds': 150, 'ph': 7.2, 'temperature': 22},
        {'turbidity': 2.0, 'tds': 180, 'ph': 7.0, 'temperature': 24},
        {'turbidity': 6.0, 'tds': 450, 'ph': 6.8, 'temperature': 26},
        {'turbidity': 15.0, 'tds': 800, 'ph': 5.5, 'temperature': 32},
    ]
    
    scenario = random.choice(scenarios)
    scenario['turbidity'] += random.uniform(-0.5, 0.5)
    scenario['tds'] += random.uniform(-20, 20)
    scenario['ph'] += random.uniform(-0.2, 0.2)
    scenario['temperature'] += random.uniform(-1, 1)
    
    return jsonify({'status': 'success', 'data': scenario})

@app.route('/api/debug-logs', methods=['GET'])
def debug_logs():
    """Debug endpoint"""
    try:
        log_file = 'data/logs.csv'
        
        info = {
            'file_exists': os.path.exists(log_file),
            'file_path': os.path.abspath(log_file),
            'directory_exists': os.path.exists('data'),
        }
        
        if os.path.exists(log_file):
            file_size = os.path.getsize(log_file)
            info['file_size'] = file_size
            
            if file_size > 0:
                df = pd.read_csv(log_file)
                info['row_count'] = len(df)
                info['columns'] = df.columns.tolist()
                info['sample_data'] = df.head(3).to_dict('records') if not df.empty else []
            else:
                info['file_size'] = 0
                info['row_count'] = 0
        
        return jsonify({'status': 'success', 'info': info})
    
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print("=" * 60)
    print("🌊 Smart Water Safety & Disease Alert System")
    print("=" * 60)
    print(f"✅ Flask Backend Starting...")
    print(f"📊 Dashboard: http://localhost:5000")
    print(f"🔬 ML Model: {'Loaded ✅' if model else 'Not Found ❌'}")
    print(f"📡 Real-time updates: Every 1 second")
    print(f"💾 Auto-logging: Predictions only")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)