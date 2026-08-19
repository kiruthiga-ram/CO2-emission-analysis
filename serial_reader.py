"""
Serial Reader - reads JSON from ESP32 via USB and saves to MySQL
Run: python serial_reader.py
Install: pip install pyserial mysql-connector-python
"""

import serial
import json
import time
import mysql.connector

# ── CONFIG ──────────────────────────────────────────────────
SERIAL_PORT = "COM3"
BAUD_RATE   = 115200
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "Iamironman@3000",
    "database": "co2_monitor",
    "ssl_disabled": True,
}
# ────────────────────────────────────────────────────────────

def get_conn():
    return mysql.connector.connect(**DB_CONFIG)

def save_reading(data):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO live_readings
               (device_id, location, co2_ppm, temperature, status)
               VALUES (%s, %s, %s, %s, %s)""",
            (data["device_id"], data["location"],
             int(data["co2_ppm"]), int(data["temperature"]), data["status"])
        )
        conn.commit()
        cur.close()
        print(f"Saved: CO2={data['co2_ppm']} ppm | Temp={data['temperature']}C | {data['status']}")
    finally:
        conn.close()

def main():
    print(f"Opening {SERIAL_PORT} at {BAUD_RATE} baud...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    time.sleep(2)
    print("Listening for ESP32 data... (Ctrl+C to stop)")

    while True:
        try:
            line = ser.readline().decode("utf-8").strip()
            if not line or not line.startswith("{"):
                continue
            data = json.loads(line)
            save_reading(data)
        except json.JSONDecodeError:
            pass
        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)

    ser.close()

if __name__ == "__main__":
    main()
