import os
import requests
import datetime
from flask import Flask, render_template, redirect, url_for, flash, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_super_secret_key_change_in_production'
# SQLite database configuration
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Database Model
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user:
            flash('Email address already exists', 'danger')
            return redirect(url_for('signup'))
            
        user_by_name = User.query.filter_by(username=username).first()
        if user_by_name:
            flash('Username already exists', 'danger')
            return redirect(url_for('signup'))

        new_user = User(
            username=username, 
            email=email, 
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )

        db.session.add(new_user)
        db.session.commit()

        flash('Signup successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = True if request.form.get('remember') else False

        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.password_hash, password):
            flash('Please check your login details and try again.', 'danger')
            return redirect(url_for('login'))

        login_user(user, remember=remember)
        return redirect(url_for('dashboard'))

    return render_template('login.html')

def get_weather_description(code):
    descriptions = {
        0: "Clear sky ☀️",
        1: "Mainly clear 🌤️", 2: "Partly cloudy ⛅", 3: "Overcast ☁️",
        45: "Fog 🌫️", 48: "Depositing rime fog 🌫️",
        51: "Light drizzle 🌧️", 53: "Moderate drizzle 🌧️", 55: "Dense drizzle 🌧️",
        61: "Slight rain 🌧️", 63: "Moderate rain 🌧️", 65: "Heavy rain 🌧️",
        66: "Freezing rain 🌧️❄️", 67: "Heavy freezing rain 🌧️❄️",
        71: "Slight snow 🌨️", 73: "Moderate snow 🌨️", 75: "Heavy snow 🌨️",
        77: "Snow grains 🌨️",
        80: "Slight rain showers 🌧️", 81: "Moderate rain showers 🌧️", 82: "Violent rain showers 🌧️",
        85: "Slight snow showers 🌨️", 86: "Heavy snow showers 🌨️",
        95: "Thunderstorm ⛈️", 96: "Thunderstorm with slight hail ⛈️❄️", 99: "Thunderstorm with heavy hail ⛈️❄️"
    }
    return descriptions.get(code, "Unknown 🤔")

def get_weather_emoji(code):
    emojis = {
        0: "☀️", 1: "🌤️", 2: "⛅", 3: "☁️",
        45: "🌫️", 48: "🌫️",
        51: "🌧️", 53: "🌧️", 55: "🌧️",
        61: "🌧️", 63: "🌧️", 65: "🌧️",
        66: "🌧️❄️", 67: "🌧️❄️",
        71: "🌨️", 73: "🌨️", 75: "🌨️",
        77: "🌨️",
        80: "🌧️", 81: "🌧️", 82: "🌧️",
        85: "🌨️", 86: "🌨️",
        95: "⛈️", 96: "⛈️❄️", 99: "⛈️❄️"
    }
    return emojis.get(code, "🤔")

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    weather_data = None
    error_message = None
    
    if request.method == 'POST':
        city = request.form.get('city')
        if city:
            try:
                import urllib.parse
                safe_city = urllib.parse.quote(city)
                
                # 1. Try Open-Meteo Geocoding first
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={safe_city}&count=5&language=en&format=json"
                geo_resp = requests.get(geo_url, timeout=5).json()
                
                lat, lon, country, city_name = None, None, '', ''
                
                if 'results' in geo_resp and len(geo_resp['results']) > 0:
                    # If multiple results, prioritize India if present to support finding local regions easily
                    indian_results = [r for r in geo_resp['results'] if r.get('country_code', '').upper() == 'IN']
                    best_result = indian_results[0] if indian_results else geo_resp['results'][0]
                    
                    lat = best_result['latitude']
                    lon = best_result['longitude']
                    country = best_result.get('country', '')
                    city_name = best_result.get('name', city)
                else:
                    # 1b. Fallback to Nominatim OpenStreetMap (supports very deep search including small Indian villages)
                    nom_url = f"https://nominatim.openstreetmap.org/search?q={safe_city}&format=json&limit=1"
                    nom_resp = requests.get(nom_url, headers={'User-Agent': 'WeatherAppFullstack/1.0'}, timeout=5).json()
                    
                    if nom_resp and len(nom_resp) > 0:
                        lat = float(nom_resp[0]['lat'])
                        lon = float(nom_resp[0]['lon'])
                        display_name = nom_resp[0].get('display_name', city)
                        d_parts = display_name.split(', ')
                        city_name = d_parts[0]
                        country = d_parts[-1] if len(d_parts) > 1 else ''

                if lat is not None and lon is not None:
                    # 2. Fetch weather data via Open-Meteo Forecast API
                    weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&daily=weathercode,temperature_2m_max,temperature_2m_min&timezone=auto"
                    weather_resp = requests.get(weather_url, timeout=5).json()
                    
                    if 'current_weather' in weather_resp:
                        cw = weather_resp['current_weather']
                        
                        daily_forecast = []
                        if 'daily' in weather_resp:
                            daily_data = weather_resp['daily']
                            for i in range(len(daily_data['time'])):
                                date_str = daily_data['time'][i]
                                date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
                                day_name = date_obj.strftime('%A')
                                if i == 0: day_name = "Today"
                                elif i == 1: day_name = "Tomorrow"
                                
                                daily_forecast.append({
                                    'day': day_name,
                                    'date': date_obj.strftime('%b %d'),
                                    'max_temp': round(daily_data['temperature_2m_max'][i]),
                                    'min_temp': round(daily_data['temperature_2m_min'][i]),
                                    'emoji': get_weather_emoji(daily_data['weathercode'][i]),
                                    'desc': get_weather_description(daily_data['weathercode'][i]).split(' ')[0] # just the first word for UI fitting
                                })

                        weather_data = {
                            'city': city_name,
                            'country': country,
                            'temperature': cw['temperature'],
                            'windspeed': cw['windspeed'],
                            'weathercode': cw['weathercode'],
                            'description': get_weather_description(cw['weathercode']),
                            'forecast': daily_forecast
                        }
                else:
                    error_message = f"Could not find the location: {city}"
            except Exception as e:
                error_message = "Error fetching weather data. Please try again later."
                
    return render_template('dashboard.html', name=current_user.username, weather_data=weather_data, error=error_message)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='127.0.0.1', port=5000)
