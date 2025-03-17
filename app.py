import sqlite3
from flask import Flask, request, jsonify
import requests
from flask_cors import CORS
import logging


app = Flask(__name__)
CORS(app)

# API URLs
NCEI_API_URL = "https://www.ncei.noaa.gov/access/services/data/v1"
NCEI_STATION_SEARCH_URL = "https://www.ncei.noaa.gov/access/services/search/v1/stations"
GEONAMES_API_URL = "http://api.geonames.org/searchJSON"
GEONAMES_USERNAME = "magretolad"

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

# Growth stages
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

# Function to calculate GDD
def calculate_gdd(tmax, tmin, base_temp):
    avg_temp = (tmax + tmin) / 2
    return max(0, avg_temp - base_temp)

# Function to get latitude and longitude from city name
def get_lat_lon_from_location(location):
    params = {"q": location, "maxRows": 1, "username": GEONAMES_USERNAME}
    response = requests.get(GEONAMES_API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data.get("totalResultsCount", 0) > 0:
            lat, lon = data["geonames"][0]["lat"], data["geonames"][0]["lng"]
            return float(lat), float(lon)  # to ensure they are floats
    return None, None


# Function to find the nearest NCEI station
def get_nearest_ncei_station(lat, lon):
    params = {"bbox": f"{lat+1},{lon-1},{lat-1},{lon+1}", "dataset": "daily-summaries", "format": "json"}
    response = requests.get(NCEI_STATION_SEARCH_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if "stations" in data and len(data["stations"]) > 0:
            return data["stations"][0]["id"]
    return None

# Function to fetch temperature data from NCEI
def get_ncei_temperature(station_id, start_date, end_date):
    params = {
        "dataset": "daily-summaries",
        "dataTypes": "TMAX,TMIN",
        "stations": station_id,
        "startDate": start_date,
        "endDate": end_date,
        "units": "metric",
        "includeAttributes": "false",
        "format": "json"
    }
    response = requests.get(NCEI_API_URL, params=params)
    
    if response.status_code == 200:
        data = response.json()
        tmin_values = [entry.get("TMIN") for entry in data if "TMIN" in entry]
        tmax_values = [entry.get("TMAX") for entry in data if "TMAX" in entry]
        
        if tmin_values and tmax_values:
            avg_tmin = sum(tmin_values) / len(tmin_values)
            avg_tmax = sum(tmax_values) / len(tmax_values)
            return avg_tmin, avg_tmax
    return None, None

logging.basicConfig(level=logging.DEBUG)

@app.route("/calculate_gdd", methods=["GET"])
def calculate_gdd_endpoint():
    location = request.args.get("location")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    base_temp = request.args.get("base_temp", "10")

    logging.debug(f"Received request: location={location}, start_date={start_date}, end_date={end_date}, base_temp={base_temp}")

    lat, lon = get_lat_lon_from_location(location)
    logging.debug(f"GeoNames API Response: lat={lat}, lon={lon}")

    if lat is None or lon is None:
        return jsonify({"error": "Invalid location or GeoNames API issue"}), 400

    station_id = get_nearest_ncei_station(lat, lon)
    logging.debug(f"NCEI Station Found: {station_id}")

    if station_id is None:
        return jsonify({"error": "No nearby NCEI station found"}), 400

    tmin, tmax = get_ncei_temperature(station_id, start_date, end_date)
    logging.debug(f"NCEI Temperature Data: tmin={tmin}, tmax={tmax}")

    if tmin is None or tmax is None:
        return jsonify({"error": "Could not fetch temperature data from NCEI"}), 400

    gdd = calculate_gdd(tmax, tmin, base_temp)
    logging.debug(f"Calculated GDD: {gdd}")

    return jsonify({
        "location": location,
        "station_id": station_id,
        "start_date": start_date,
        "end_date": end_date,
        "base_temperature": base_temp,
        "GDD": gdd
    })



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)