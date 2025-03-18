# Description: Backend server for calculating Growing Degree Days (GDD) based on historical weather data.
import json
import sqlite3
from flask import Flask, request, jsonify, make_response
import requests
from flask_cors import CORS
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins temporarily

# OpenWeatherMap API Key (Replace with your own key)
API_KEY = "8517c8118b2e0866ca72db95fa7a7148"
ONECALL_URL = "https://api.openweathermap.org/data/3.0/onecall/timemachine"

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

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

# Define Plant Growth Stages Based on GDD
GROWTH_STAGES = [
    (0, 100, "Bud Development"),
    (101, 350, "Flowering"),
    (351, 700, "Fruit Set"),
    (701, 1200, "Pit Hardening"),
    (1201, 1800, "Oil Accumulation"),
    (1801, float("inf"), "Maturity & Harvest")
]

# Function to calculate GDD
def calculate_gdd(tmax, tmin, base_temp):
    avg_temp = (tmax + tmin) / 2
    return max(0, avg_temp - base_temp)  # Ensuring GDD is non-negative

# Function to determine plant growth stage
def get_growth_stage(total_gdd):
    for lower, upper, stage in GROWTH_STAGES:
        if lower <= total_gdd <= upper:
            return stage
    return "Unknown Stage"

# Function to get latitude and longitude from city name
def get_lat_lon_from_location(location):
    geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={API_KEY}"
    response = requests.get(geocode_url).json()
    
    if response:
        return response[0]["lat"], response[0]["lon"]
    return None, None

@app.route("/")
def home():
    return "GDD Backend is running!"

@app.route('/gdd', methods=['GET'])
def get_gdd():
    location = request.args.get("location", "Larnaca")
    base_temp = float(request.args.get("base_temp", 10))
    start_date = request.args.get("start_date")

    logging.debug(f"Received request: location={location}, base_temp={base_temp}, start_date={start_date}")

    # Validate inputs
    if not start_date:
        return jsonify({"error": "Please specify a planting start date in YYYY-MM-DD format."}), 400

    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Convert location to lat/lon
    lat, lon = get_lat_lon_from_location(location)
    if lat is None or lon is None:
        return jsonify({"error": "Invalid location"}), 400

    total_gdd = 0
    daily_gdd_list = []
    temp_data = []

    for days_since in range((datetime.now().date() - start_date).days + 1):
        date_to_fetch = start_date + timedelta(days=days_since)
        timestamp = int(datetime.combine(date_to_fetch, datetime.min.time()).timestamp()) - (3600 * 12)

        # Fetch historical weather data from OpenWeatherMap
        params = {"lat": lat, "lon": lon, "dt": timestamp, "appid": API_KEY, "units": "metric"}
        response = requests.get(ONECALL_URL, params=params)
        data = response.json()

        # Debugging: Log full API response
        logging.debug(f"Raw API response for {date_to_fetch.strftime('%Y-%m-%d')}: {data}")

        if response.status_code != 200 or "data" not in data:
            logging.warning(f"No data for {date_to_fetch.strftime('%Y-%m-%d')}")
            continue

        try:
            # Extract morning and afternoon temperatures
            morning_temp = None
            afternoon_temp = None

            for hour in data.get("data", []):
                hour_time = datetime.utcfromtimestamp(hour["dt"]).hour
                if 5 <= hour_time <= 7:
                    morning_temp = hour["temp"]
                if 14 <= hour_time <= 16:
                    afternoon_temp = hour["temp"]

            # Ensure we have both Tmin and Tmax values
            if morning_temp is None or afternoon_temp is None:
                logging.warning(f"❌ No valid temperature readings for {date_to_fetch.strftime('%Y-%m-%d')}")
                continue

            tmin = morning_temp
            tmax = afternoon_temp
            gdd = calculate_gdd(tmax, tmin, base_temp)
            total_gdd += gdd

            daily_gdd_list.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "gdd": gdd})
            temp_data.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "tmin": tmin, "tmax": tmax, "gdd": gdd})

            logging.info(f"{date_to_fetch.strftime('%Y-%m-%d')}: Tmin={tmin}, Tmax={tmax}, GDD={gdd}")

        except Exception as e:
            logging.error(f"Error processing {date_to_fetch.strftime('%Y-%m-%d')}: {e}")
            continue

    plant_stage = get_growth_stage(total_gdd)
    explanation_message = f"Since planting on {start_date}, the tree has accumulated {total_gdd:.2f} GDD, reaching the '{plant_stage}' stage."

    return jsonify({
        "location": location,
        "latitude": lat,
        "longitude": lon,
        "total_gdd": total_gdd,
        "growth_stage": plant_stage,
        "daily_gdd": daily_gdd_list,
        "message": explanation_message,
        "temperature_debug": temp_data
    })

@app.route('/test_weather', methods=['GET'])
def test_weather():
    """Manually test weather data retrieval for debugging."""
    location = request.args.get("location", "Larnaca")
    lat, lon = get_lat_lon_from_location(location)
    if lat is None or lon is None:
        return jsonify({"error": "Invalid location"}), 400

    # Use today's date minus 1 day (yesterday) for historical weather
    date_to_fetch = datetime.now() - timedelta(days=1)
    timestamp = int(date_to_fetch.timestamp())

    params = {"lat": lat, "lon": lon, "dt": timestamp, "appid": API_KEY, "units": "metric"}
    response = requests.get(ONECALL_URL, params=params)
    data = response.json()

    # Log response for debugging
    print(json.dumps(data, indent=4))  # Print in readable JSON format

    return jsonify(data)  # Return full response for manual verification

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)

