import sqlite3
from flask import Flask, request, jsonify
import requests
from datetime import datetime, timedelta

app = Flask(__name__)

# OpenWeatherMap API Key (Replace with your own key)
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

# Define Plant Growth Stages Based on GDD
GROWTH_STAGES = [
    (0, 100, "Bud devepment"),
    (101, 350, "FLowering"),
    (351, 700, "Fruit Set"),
    (701, 1200, "Pit hardening"),
    (1201, 1800, "Oil Accumulation"),
    (1801, float("inf"), "Maturity & Harvest")
]

# Function to calculate GDD
def calculate_gdd(tmax, tmin, base_temp):
    avg_temp = (tmax + tmin) / 2
    gdd = max(0, avg_temp - base_temp)  # Ensuring GDD is non-negative
    return gdd

# Function to determine plant growth stage
def get_growth_stage(total_gdd):
    for lower, upper, stage in GROWTH_STAGES:
        if lower <= total_gdd <= upper:
            return stage
    return "Unknown Stage"

@app.route('/gdd', methods=['GET'])
def get_gdd():
    location = request.args.get("location", "Larnaca")
    base_temp = request.args.get("base_temp", 10)
    start_date = request.args.get("start_date")

    print(f"Received request: location={location}, base_temp={base_temp}, start_date={start_date}")

    # Validate base temperature
    try:
        base_temp = float(base_temp)
    except ValueError:
        return jsonify({"error": "Base temperature must be a valid number."}), 400

    # Validate start date
    if not start_date:
        return jsonify({"error": "Please specify a planting start date in YYYY-MM-DD format."}), 400

    try:
        start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD."}), 400

    # Convert location to lat/lon (for One Call API)
    geocode_url = f"http://api.openweathermap.org/geo/1.0/direct?q={location}&limit=1&appid={API_KEY}"
    geo_response = requests.get(geocode_url).json()
    if not geo_response:
        return jsonify({"error": "Invalid location"}), 400
    lat, lon = geo_response[0]['lat'], geo_response[0]['lon']

    # Retrieve stored cumulative GDD if available
    conn = sqlite3.connect("gdd_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT SUM(daily_gdd) FROM gdd_records WHERE user_location=? AND planting_date=?
    """, (location, start_date))
    row = cursor.fetchone()
    total_gdd = row[0] if row and row[0] else 0

    daily_gdd_list = []
    temp_data = []  # Store raw temperatures for debugging

    for days_since in range((datetime.now().date() - start_date).days + 1):
        date_to_fetch = start_date + timedelta(days=days_since)
        timestamp = int(datetime.combine(date_to_fetch, datetime.min.time()).timestamp())

        params = {"lat": lat, "lon": lon, "dt": timestamp, "appid": API_KEY, "units": "metric"}
        response = requests.get(ONECALL_URL, params=params)
        data = response.json()

        if response.status_code != 200 or "data" not in data:
            print(f"No data for {date_to_fetch.strftime('%Y-%m-%d')}")
            continue

        try:
            tmax = max(hour["temp"] for hour in data["data"])
            tmin = min(hour["temp"] for hour in data["data"])
            gdd = calculate_gdd(tmax, tmin, base_temp)
            total_gdd += gdd
            daily_gdd_list.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "gdd": gdd})
            temp_data.append({"date": date_to_fetch.strftime("%Y-%m-%d"), "tmax": tmax, "tmin": tmin, "gdd": gdd})

            # Store the GDD record in the database
            cursor.execute("""
                INSERT INTO gdd_records (user_location, planting_date, base_temperature, record_date, daily_gdd, cumulative_gdd)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (location, start_date, base_temp, date_to_fetch, gdd, total_gdd))
            conn.commit()

            print(f"{date_to_fetch.strftime('%Y-%m-%d')}: Tmax={tmax}, Tmin={tmin}, GDD={gdd}")
        except Exception as e:
            print(f"Error processing {date_to_fetch.strftime('%Y-%m-%d')}: {e}")
            continue

    conn.close()

    plant_stage = get_growth_stage(total_gdd)
    explanation_message = f"Since planting on {start_date}, the tree has accumulated a total of {total_gdd:.2f} GDD, reaching the '{plant_stage}' stage."

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

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
