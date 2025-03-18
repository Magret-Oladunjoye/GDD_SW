# Description: Backend server for calculating Growing Degree Days (GDD) based on historical weather data.
import json
import sqlite3
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})  # Allow all origins temporarily

# OpenWeatherMap API Key (Replace with your own key)
API_KEY = "d430decf8af0dba498b77d7772b7ea49"
HISTORY_API_URL = "https://history.openweathermap.org/data/2.5/history/city"

# Initialize logging
logging.basicConfig(level=logging.DEBUG)

# Define Plant Growth Stages Based on GDD
GROWTH_STAGES = [
    (0, 100, "Bud Development"),
    (101, 350, "Flowering"),
    (351, 700, "Fruit Set"),
    (701, 1200, "Pit Hardening"),
    (1201, 1800, "Oil Accumulation"),
    (1801, float("inf"), "Maturity & Harvest")
]

@app.route("/")
def home():
    return "GDD Backend is running!"

# Function to determine plant growth stage
def get_growth_stage(total_gdd):
    for lower, upper, stage in GROWTH_STAGES:
        if lower <= total_gdd <= upper:
            return stage
    return "Unknown Stage"

# Function to calculate GDD
def calculate_gdd(tmax, tmin, base_temp):
    avg_temp = (tmax + tmin) / 2
    return max(0, avg_temp - base_temp)  # GDD should never be negative

# Function to get latitude and longitude from city name
def get_lat_lon_from_location(location):
    geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={API_KEY}"
    response = requests.get(geocode_url).json()
    if response:
        return response[0]["lat"], response[0]["lon"]
    return None, None

@app.route('/gdd', methods=['GET'])
def get_gdd():
    location = request.args.get("location", "Larnaca")
    base_temp = float(request.args.get("base_temp", 10))
    start_date = request.args.get("start_date")

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

    # Fetch temperature data for each day from start_date to today
    for days_since in range((datetime.now().date() - start_date).days + 1):
        date_to_fetch = start_date + timedelta(days=days_since)

        # Convert to Unix timestamps (start and end of the day)
        start_timestamp = int(datetime.combine(date_to_fetch, datetime.min.time()).timestamp())
        end_timestamp = start_timestamp + 86400  # 24 hours later

        # Fetch historical weather data from OpenWeatherMap's History API
        params = {
            "lat": lat,
            "lon": lon,
            "appid": API_KEY,
            "units": "metric",
            "start": start_timestamp,
            "end": end_timestamp,
            "type": "hour"  # Important: Fetch hourly historical data
        }
        response = requests.get(HISTORY_API_URL, params=params)
        data = response.json()

        if response.status_code != 200 or "list" not in data:
            print(f"No data for {date_to_fetch.strftime('%Y-%m-%d')}")
            continue

        try:
            # Extract min and max temp directly
            tmin = min(entry["main"]["temp_min"] for entry in data["list"])
            tmax = max(entry["main"]["temp_max"] for entry in data["list"])

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
    response = requests.get(HISTORY_API_URL, params=params)
    data = response.json()

    # Log response for debugging
    print(json.dumps(data, indent=4))  # Print in readable JSON format

    return jsonify(data)  # Return full response for manual verification

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
