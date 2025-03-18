import sqlite3
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
from datetime import datetime, timedelta

app = Flask(__name__)
CORS(app)

# OpenWeatherMap API Key
API_KEY = "8517c8118b2e0866ca72db95fa7a7148"
ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect("gdd_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gdd_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_location TEXT,
            planting_date TEXT,
            base_temperature REAL,
            record_date TEXT,
            daily_gdd REAL,
            cumulative_gdd REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Function to calculate GDD
def calculate_gdd(tmax, tmin, base_temp):
    avg_temp = (tmax + tmin) / 2
    return max(0, avg_temp - base_temp)

# Function to get latitude and longitude from city name
def get_lat_lon_from_location(location):
    geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={API_KEY}"
    response = requests.get(geocode_url).json()
    
    if response and isinstance(response, list) and len(response) > 0:
        return response[0]["lat"], response[0]["lon"]
    
    return None, None

@app.route("/")
def home():
    return "GDD API is running!", 200

@app.route('/gdd', methods=['GET'])
def get_gdd():
    location = request.args.get("location", "Larnaca")
    base_temp = request.args.get("base_temp", 10)
    start_date = request.args.get("start_date")

    # Validate inputs
    if not start_date:
        return jsonify({"error": "Please specify a planting start date in YYYY-MM-DD format."}), 400

    try:
        base_temp = float(base_temp)
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid input values."}), 400

    # Convert location to lat/lon
    lat, lon = get_lat_lon_from_location(location)
    if lat is None or lon is None:
        return jsonify({"error": "Invalid location"}), 400

    total_gdd = 0
    daily_gdd_list = []
    temp_data = []

    for days_since in range((datetime.now().date() - start_date).days + 1):
        date_to_fetch = start_date + timedelta(days=days_since)
        timestamp = int(datetime.combine(date_to_fetch, datetime.min.time()).timestamp())

        # Fetch historical weather data from OpenWeatherMap
        params = {"lat": lat, "lon": lon, "dt": timestamp, "appid": API_KEY, "units": "metric"}
        response = requests.get(ONECALL_URL, params=params)

        if response.status_code != 200:
            print(f"No data for {date_to_fetch.strftime('%Y-%m-%d')}")
            continue

        try:
            data = response.json()

            if "data" not in data or not isinstance(data["data"], list):
                print(f"Skipping {date_to_fetch.strftime('%Y-%m-%d')} due to missing temperature data.")
                continue

            # Extract temperatures at 6 AM and 3 PM
            morning_temp = next((hour["temp"] for hour in data["data"] if 5 <= datetime.utcfromtimestamp(hour["dt"]).hour <= 7), None)
            afternoon_temp = next((hour["temp"] for hour in data["data"] if 14 <= datetime.utcfromtimestamp(hour["dt"]).hour <= 16), None)

            if morning_temp is None or afternoon_temp is None:
                print(f"Skipping {date_to_fetch.strftime('%Y-%m-%d')} due to missing morning or afternoon temperatures.")
                continue

            tmin = morning_temp
            tmax = afternoon_temp
            gdd = calculate_gdd(tmax, tmin, base_temp)
            total_gdd += gdd

            daily_gdd_list.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "gdd": gdd})
            temp_data.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "tmin": tmin, "tmax": tmax, "gdd": gdd})

            print(f"{date_to_fetch.strftime('%Y-%m-%d')}: Tmin={tmin}, Tmax={tmax}, GDD={gdd}")

        except Exception as e:
            print(f"Error processing {date_to_fetch.strftime('%Y-%m-%d')}: {e}")
            continue

    return jsonify({
        "location": location,
        "latitude": lat,
        "longitude": lon,
        "total_gdd": total_gdd,
        "daily_gdd": daily_gdd_list,
        "temperature_debug": temp_data
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
