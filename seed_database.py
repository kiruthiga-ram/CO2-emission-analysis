#!/usr/bin/env python3
"""
CO2 EMISSIONS MONITOR — Database Seeder
Generates 1 full year of realistic hourly readings for 4 facilities
and bulk-inserts them into MySQL.

Usage:
    pip install mysql-connector-python
    python seed_database.py

Edit the DB_CONFIG block below to match your MySQL credentials.
"""

import mysql.connector
import random
import math
from datetime import datetime, timedelta
import sys

# ── DATABASE CONFIG ── edit these ─────────────────────────────
DB_CONFIG = {
    "host": "127.0.0.1"
    "port":     3306,
    "user":     "root",        # change if different
    "password": "Iamironman@3000",   # ← CHANGE THIS
    "database": "co2_monitor",
}
# ──────────────────────────────────────────────────────────────

FACILITIES = [
    {"id": "FAC-001", "name": "Steel Plant Alpha",    "base": 920, "peak": 1600},
    {"id": "FAC-002", "name": "Cement Works Beta",    "base": 780, "peak": 1400},
    {"id": "FAC-003", "name": "Power Unit Gamma",     "base": 650, "peak": 1200},
    {"id": "FAC-004", "name": "Chemical Plant Delta", "base": 500, "peak":  950},
]

THRESHOLDS = {"warning": 800, "danger": 1100}

# Seasonal multiplier — higher in winter, lower in summer
SEASONAL = [1.15, 1.12, 1.05, 0.95, 0.88, 0.82, 0.80, 0.83, 0.90, 1.00, 1.08, 1.14]

def seasonal_mult(month: int) -> float:
    return SEASONAL[month]

def shift_mult(hour: int) -> float:
    if  6 <= hour < 14: return 1.20   # day shift
    if 14 <= hour < 22: return 1.10   # evening shift
    return 0.85                         # night shift

def day_mult(weekday: int) -> float:
    # weekday: Mon=0 … Sun=6
    return 0.72 if weekday >= 5 else 1.0

def generate_readings():
    """Yield (facility_id, co2_ppm, temperature, humidity, flow_rate, status, recorded_at)"""
    now   = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=365)
    cursor_dt = start

    total = 0
    while cursor_dt <= now:
        month   = cursor_dt.month - 1   # 0-indexed
        weekday = cursor_dt.weekday()
        hour    = cursor_dt.hour
        sm  = seasonal_mult(month)
        dm  = day_mult(weekday)
        shm = shift_mult(hour)

        for fac in FACILITIES:
            base   = fac["base"] * sm * dm * shm
            jitter = random.uniform(-60, 60)
            spike  = random.uniform(80, 220) if random.random() < 0.03 else 0
            ppm    = int(max(300, min(fac["peak"] + 150, base + jitter + spike)))

            # Temperature: base 22°C ± seasonal + random
            temp = round(22 + (sm - 1) * 8 + random.uniform(-3, 4), 1)
            # Humidity: 40–75 %
            humidity = round(40 + random.uniform(0, 35), 1)
            # Flow rate: 80–200 m³/h, seasonally weighted
            flow_rate = round(random.uniform(80, 200) * sm * dm, 2)

            if ppm >= THRESHOLDS["danger"]:
                status = "DANGER"
            elif ppm >= THRESHOLDS["warning"]:
                status = "WARNING"
            else:
                status = "NORMAL"

            yield (fac["id"], ppm, temp, humidity, flow_rate, status, cursor_dt)
            total += 1

        cursor_dt += timedelta(hours=1)

    print(f"  Generated {total:,} readings")

def build_daily_summary(conn):
    """Populate daily_summary table from co2_readings."""
    print("\n  Building daily_summary table …", end="", flush=True)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM daily_summary")
    cursor.execute("""
        INSERT INTO daily_summary
              (facility_id, summary_date, avg_co2, min_co2, max_co2,
               reading_count, danger_count, warning_count)
        SELECT facility_id,
               DATE(recorded_at),
               ROUND(AVG(co2_ppm),2),
               MIN(co2_ppm),
               MAX(co2_ppm),
               COUNT(*),
               SUM(status = 'DANGER'),
               SUM(status = 'WARNING')
        FROM   co2_readings
        GROUP  BY facility_id, DATE(recorded_at)
    """)
    conn.commit()
    cursor.close()
    print(f" done ({cursor.rowcount:,} rows)")

def main():
    print("=" * 60)
    print("  CO2 Emissions Monitor — Database Seeder")
    print("=" * 60)

    # Connect
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        print(f"\n  ✓ Connected to MySQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
    except mysql.connector.Error as e:
        print(f"\n  ✗ Connection failed: {e}")
        print("    → Check DB_CONFIG at the top of this file")
        sys.exit(1)

    cursor = conn.cursor()

    # Confirm
    cursor.execute("SELECT COUNT(*) FROM co2_readings")
    existing = cursor.fetchone()[0]
    if existing > 0:
        print(f"\n  ⚠  Table already has {existing:,} rows.")
        ans = input("     Delete and reseed? [y/N]: ").strip().lower()
        if ans != "y":
            print("  Aborted — no changes made.")
            conn.close(); sys.exit(0)
        print("  Deleting existing data …", end="", flush=True)
        cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        cursor.execute("TRUNCATE TABLE daily_summary")
        cursor.execute("TRUNCATE TABLE alert_events")
        cursor.execute("TRUNCATE TABLE co2_readings")
        cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        conn.commit()
        print(" done")

    # Generate + bulk insert
    print("\n  Generating readings …")
    BATCH = 5000
    batch = []
    inserted = 0

    sql = """
        INSERT INTO co2_readings
              (facility_id, co2_ppm, temperature, humidity, flow_rate, status, recorded_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    for row in generate_readings():
        batch.append(row)
        if len(batch) >= BATCH:
            cursor.executemany(sql, batch)
            conn.commit()
            inserted += len(batch)
            print(f"  … {inserted:,} rows inserted", end="\r", flush=True)
            batch.clear()

    if batch:
        cursor.executemany(sql, batch)
        conn.commit()
        inserted += len(batch)

    print(f"\n  ✓ Inserted {inserted:,} readings total")

    # Seed alert_events from DANGER rows
    print("  Seeding alert_events …", end="", flush=True)
    cursor.execute("""
        INSERT INTO alert_events (facility_id, alert_type, co2_ppm, triggered_at)
        SELECT facility_id, status, co2_ppm, recorded_at
        FROM   co2_readings
        WHERE  status IN ('WARNING','DANGER')
        LIMIT  10000
    """)
    conn.commit()
    print(f" done ({cursor.rowcount:,} events)")

    # Build daily summary
    build_daily_summary(conn)

    cursor.close()
    conn.close()

    print("\n" + "=" * 60)
    print("  🎉 Seed complete! Open Valentina Studio and connect")
    print(f"     to the '{DB_CONFIG['database']}' database to verify.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
