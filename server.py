from flask import Flask, render_template, request, jsonify
from weather import get_current_weather
from waitress import serve
import json
from datetime import datetime, timedelta
import requests
import os
from dotenv import load_dotenv
import openai

load_dotenv()

app = Flask(__name__)

# Configure OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

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
    """Get AI-powered agricultural analysis using OpenAI"""
    try:
        # Prepare weather summary for AI
        current_temp = weather_data['main']['temp']
        humidity = weather_data['main']['humidity']
        wind_speed = weather_data['wind']['speed']
        precipitation = sum([day.get('precipitation', 0) for day in forecast_data[:3]])  # Next 3 days
        
        prompt = f"""
        As an agricultural AI advisor, analyze the following weather conditions for {city} and provide specific farming recommendations:

        Current Conditions:
        - Temperature: {current_temp}°F
        - Humidity: {humidity}%
        - Wind Speed: {wind_speed} mph
        - Growing Degree Days: {gdd}
        - Frost Risk: {frost_risk}
        - UV Index: {uv_index}
        - Expected precipitation (next 3 days): {precipitation} inches

        Please provide:
        1. Irrigation Management (specific timing and amount recommendations)
        2. Pest & Disease Management (specific risks and prevention measures)
        3. Field Operations (optimal timing for planting, spraying, harvesting)
        4. Crop Development Analysis (growth stage assessment and next steps)

        Format the response as JSON with keys: irrigation_analysis, pest_analysis, field_analysis, crop_analysis
        Each should include 'recommendation' and 'priority' (High/Medium/Low) fields.
        """

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert agricultural advisor with deep knowledge of crop management, weather patterns, and farming best practices."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        # Try to parse JSON response
        try:
            return json.loads(ai_response)
        except:
            # Fallback if JSON parsing fails
            return {
                "irrigation_analysis": {
                    "recommendation": "AI analysis suggests monitoring soil moisture levels closely based on current weather patterns.",
                    "priority": "Medium"
                },
                "pest_analysis": {
                    "recommendation": "Weather conditions indicate moderate pest activity. Implement preventive measures.",
                    "priority": "Medium"
                },
                "field_analysis": {
                    "recommendation": "Current conditions are suitable for most field operations with proper timing.",
                    "priority": "Good"
                },
                "crop_analysis": {
                    "recommendation": f"GDD accumulation of {gdd} indicates normal crop development progress.",
                    "priority": "Optimal"
                }
            }
            
    except Exception as e:
        print(f"AI Analysis Error: {e}")
        # Fallback recommendations
        return {
            "irrigation_analysis": {
                "recommendation": "Monitor soil moisture. Consider irrigation if no rain in next 3 days.",
                "priority": "Medium"
            },
            "pest_analysis": {
                "recommendation": "Moderate humidity levels. Monitor for fungal diseases during warm periods.",
                "priority": "Medium"
            },
            "field_analysis": {
                "recommendation": "Good conditions for field work. Plan operations during dry periods.",
                "priority": "Good"
            },
            "crop_analysis": {
                "recommendation": f"Accumulating {gdd:.1f} GDD today. Crop development on track.",
                "priority": "Optimal"
            }
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