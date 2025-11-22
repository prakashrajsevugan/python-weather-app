from flask import Flask, render_template, request, jsonify
from weather import get_current_weather
from waitress import serve
import json
from datetime import datetime, timedelta
import requests
import os
from dotenv import load_dotenv
import ai_client

load_dotenv()

app = Flask(__name__)

def get_weather_forecast(city, days=7):
    """Get extended forecast for agricultural planning"""
    request_url = f'https://api.openweathermap.org/data/2.5/forecast?appid={os.getenv("API_KEY")}&q={city}&units=imperial&cnt={days*8}'
    try:
        forecast_data = requests.get(request_url).json()
        return forecast_data
    except:
        return None

def calculate_growing_degree_days(temp_max, temp_min, base_temp=50):
    """Calculate Growing Degree Days for crop development"""
    avg_temp = (temp_max + temp_min) / 2
    gdd = max(0, avg_temp - base_temp)
    return gdd

def assess_frost_risk(temp_min, humidity):
    """Assess frost risk for crops"""
    if temp_min <= 32 and humidity > 80:
        return "High Risk"
    elif temp_min <= 36:
        return "Moderate Risk"
    return "Low Risk"

def get_irrigation_need(humidity, precipitation, temp):
    """Calculate irrigation needs"""
    if precipitation > 0.5:
        return "Low"
    elif humidity < 40 and temp > 80:
        return "High"
    elif humidity < 60:
        return "Medium"
    return "Low"

def get_uv_index(lat, lon):
    """Get UV index data"""
    try:
        uv_url = f'https://api.openweathermap.org/data/2.5/uvi?appid={os.getenv("API_KEY")}&lat={lat}&lon={lon}'
        uv_data = requests.get(uv_url).json()
        return uv_data.get('value', 0)
    except:
        return 0

def get_ai_agricultural_analysis(weather_data, forecast_data, gdd, frost_risk, uv_index, city):
    """Get AI-powered agricultural analysis by delegating to ai_client.generate_ai_analysis.

    The ai_client will call OpenAI if an API key is configured. We pass a simple climate label
    (rain, winter, sunny, etc.) so the model focuses on climate-driven precautions for farmers.
    """
    try:
        # Derive a simple climate label from current weather
        main_cond = weather_data.get('weather', [{}])[0].get('main', '').lower()
        temp = weather_data['main']['temp']

        if 'rain' in main_cond or 'drizzle' in main_cond or 'thunderstorm' in main_cond:
            climate_label = 'rain'
        elif 'snow' in main_cond or temp <= 36:
            climate_label = 'winter'
        elif 'clear' in main_cond or 'sun' in main_cond:
            climate_label = 'sunny'
        else:
            climate_label = main_cond or 'moderate'

        # Delegate to ai_client which returns a structured analysis
        ai_out = ai_client.generate_ai_analysis(climate_label=climate_label, city=city)

        # ai_client returns recommendations with 'recommendation' and 'confidence' keys.
        # Map confidence->priority for compatibility with templates
        def _priority_from_conf(c):
            try:
                c = int(c)
            except Exception:
                return 'Medium'
            if c >= 80:
                return 'High'
            if c >= 60:
                return 'Medium'
            return 'Low'

        return {
            'irrigation_analysis': {
                'recommendation': ai_out['irrigation_analysis']['recommendation'],
                'priority': _priority_from_conf(ai_out['irrigation_analysis'].get('confidence', 50))
            },
            'pest_analysis': {
                'recommendation': ai_out['pest_analysis']['recommendation'],
                'priority': _priority_from_conf(ai_out['pest_analysis'].get('confidence', 50))
            },
            'field_analysis': {
                'recommendation': ai_out['field_analysis']['recommendation'],
                'priority': _priority_from_conf(ai_out['field_analysis'].get('confidence', 50))
            },
            'crop_analysis': {
                'recommendation': ai_out['crop_analysis']['recommendation'],
                'priority': _priority_from_conf(ai_out['crop_analysis'].get('confidence', 50))
            }
        }
    except Exception:
        # Fallback simple messages
        return {
            "irrigation_analysis": {"recommendation": "Monitor soil moisture and delay irrigation if rain is expected.", "priority": "Medium"},
            "pest_analysis": {"recommendation": "Inspect fields for pests and disease if warm/wet conditions persist.", "priority": "Medium"},
            "field_analysis": {"recommendation": "Avoid heavy machinery during wet soil conditions to prevent compaction.", "priority": "Low"},
            "crop_analysis": {"recommendation": "Adjust fertilization and scouting based on crop stage.", "priority": "Medium"},
        }

@app.route('/')
@app.route('/index')
def index():
    return render_template('index.html')

@app.route('/weather')
def get_weather():
    city = request.args.get('city')
    
    if not city:
        return render_template('index.html')
    
    weather_data = get_current_weather(city)
    
    if not weather_data['cod'] == 200:
        return render_template('city-not-found.html')
    
    return render_template(
        "weather.html", 
        title=weather_data["name"], 
        status=weather_data["weather"][0]["description"].title(), 
        temp=f"{weather_data['main']['temp']:.1f}", 
        feels_like=f"{weather_data['main']['feels_like']:.1f}"
    )

@app.route('/agricultural-dashboard')
def agricultural_dashboard():
    city = request.args.get('city', 'New York')
    
    current_weather = get_current_weather(city)
    if current_weather['cod'] != 200:
        return render_template('city-not-found.html', city=city)
    
    forecast = get_weather_forecast(city, 7)
    if not forecast:
        return render_template('city-not-found.html', city=city)
    
    # Get coordinates for UV index
    lat, lon = current_weather['coord']['lat'], current_weather['coord']['lon']
    uv_index = get_uv_index(lat, lon)
    
    # Calculate current metrics
    current_temp_max = current_weather['main']['temp_max']
    current_temp_min = current_weather['main']['temp_min']
    current_humidity = current_weather['main']['humidity']
    
    current_gdd = calculate_growing_degree_days(current_temp_max, current_temp_min)
    frost_risk = assess_frost_risk(current_temp_min, current_humidity)
    irrigation_need = get_irrigation_need(current_humidity, 0, current_weather['main']['temp'])
    
    # Process forecast data
    daily_forecasts = []
    temp_data = []
    humidity_data = []
    gdd_data = []
    forecast_labels = []
    
    for i in range(0, min(len(forecast['list']), 56), 8):  # Daily data for 7 days
        day_data = forecast['list'][i]
        temp_max = day_data['main']['temp_max']
        temp_min = day_data['main']['temp_min']
        humidity = day_data['main']['humidity']
        precipitation = day_data.get('rain', {}).get('3h', 0)
        
        gdd = calculate_growing_degree_days(temp_max, temp_min)
        day_frost_risk = assess_frost_risk(temp_min, humidity)
        
        # Format date
        date_obj = datetime.fromtimestamp(day_data['dt'])
        date_formatted = date_obj.strftime('%a, %b %d')
        
        daily_forecasts.append({
            'date': day_data['dt_txt'][:10],
            'date_formatted': date_formatted,
            'temp_max': temp_max,
            'temp_min': temp_min,
            'humidity': humidity,
            'precipitation': precipitation,
            'wind_speed': day_data['wind']['speed'],
            'gdd': gdd,
            'frost_risk': day_frost_risk,
            'weather': day_data['weather'][0]['description'],
            'weather_icon': 'cloud-sun'
        })
        
        # Data for charts
        temp_data.append(round((temp_max + temp_min) / 2, 1))
        humidity_data.append(humidity)
        gdd_data.append(round(gdd, 1))
        forecast_labels.append(date_obj.strftime('%m/%d'))
    
    # Get AI Analysis
    ai_analysis = get_ai_agricultural_analysis(
        current_weather, daily_forecasts, current_gdd, frost_risk, uv_index, city
    )
    
    # Extract AI recommendations
    irrigation_recommendation = ai_analysis['irrigation_analysis']['recommendation']
    irrigation_priority = ai_analysis['irrigation_analysis']['priority']
    
    pest_recommendation = ai_analysis['pest_analysis']['recommendation']
    pest_priority = ai_analysis['pest_analysis']['priority']
    
    field_recommendation = ai_analysis['field_analysis']['recommendation']
    field_priority = ai_analysis['field_analysis']['priority']
    
    crop_recommendation = ai_analysis['crop_analysis']['recommendation']
    crop_stage = "Vegetative"  # This could be enhanced with more AI analysis
    
    # Determine weather icon
    weather_condition = current_weather['weather'][0]['main'].lower()
    weather_icon_map = {
        'clear': 'sun',
        'clouds': 'cloud',
        'rain': 'cloud-rain',
        'snow': 'snowflake',
        'thunderstorm': 'bolt'
    }
    weather_icon = weather_icon_map.get(weather_condition, 'cloud-sun')
    
    # Generate alerts
    alerts = []
    if frost_risk == "High Risk":
        alerts.append({
            'type': 'danger',
            'icon': 'exclamation-triangle',
            'message': 'Frost Warning: Protect sensitive crops tonight!'
        })
    if uv_index > 7:
        alerts.append({
            'type': 'warning',
            'icon': 'sun',
            'message': f'High UV Index ({uv_index}): Limit field work during midday'
        })
    
    return render_template('agricultural-dashboard.html', 
                         city=current_weather['name'],
                         current=current_weather,
                         forecasts=daily_forecasts,
                         uv_index=uv_index,
                         current_gdd=current_gdd,
                         frost_risk=frost_risk,
                         irrigation_need=irrigation_need,
                         weather_icon=weather_icon,
                         alerts=alerts,
                         irrigation_recommendation=irrigation_recommendation,
                         irrigation_priority=irrigation_priority,
                         pest_recommendation=pest_recommendation,
                         pest_priority=pest_priority,
                         field_recommendation=field_recommendation,
                         field_priority=field_priority,
                         crop_recommendation=crop_recommendation,
                         crop_stage=crop_stage,
                         ai_analysis=ai_analysis,  # Pass full AI analysis
                         forecast_labels=json.dumps(forecast_labels),
                         temp_data=json.dumps(temp_data),
                         humidity_data=json.dumps(humidity_data),
                         gdd_data=json.dumps(gdd_data))

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8000)