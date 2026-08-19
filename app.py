"""
CO2 EMISSIONS MONITOR — Flask Application
Serves the website and all JSON API endpoints backed by MySQL.

Install deps:  pip install flask flask-cors mysql-connector-python python-dotenv
Run:           python app.py
"""

import os
import json
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, jsonify, render_template, request, abort
from flask_cors import CORS
import mysql.connector
from mysql.connector import pooling

# ── CONFIG ───────────────────────────────────────────────────
DB_CONFIG = {
    "host":         os.getenv("DB_HOST",     "localhost"),
    "port":         int(os.getenv("DB_PORT", "3306")),
    "user":         os.getenv("DB_USER",     "root"),
    "password":     os.getenv("DB_PASSWORD", "Iamironman@3000"),  # ← CHANGE
    "database":     os.getenv("DB_NAME",     "co2_monitor"),
    "charset":      "utf8mb4",
    "use_unicode":  True,
    "autocommit":   True,
    "ssl_disabled": True,   # ← fixes SSL cert error on Windows
}

POOL_CONFIG = {
    "pool_name": "co2_pool",
    "pool_size": 5,
    **DB_CONFIG,
}

# ── APP SETUP ─────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# Create connection pool
try:
    _pool = pooling.MySQLConnectionPool(**POOL_CONFIG)
    print("✓ MySQL connection pool created")
except Exception as e:
    print(f"✗ Pool creation failed: {e}")
    _pool = None

# ── DB HELPERS ────────────────────────────────────────────────
def get_conn():
    if _pool:
        return _pool.get_connection()
    return mysql.connector.connect(**DB_CONFIG)

def query(sql: str, params=None, many=False):
    conn = get_conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        result = cur.fetchall() if many else cur.fetchone()
        cur.close()
        return result
    finally:
        conn.close()

def serialize(obj):
    """JSON-serialise datetime / Decimal objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "__float__"):  # Decimal
        return float(obj)
    raise TypeError(f"Not serialisable: {type(obj)}")

def api_response(data, status=200):
    return app.response_class(
        response=json.dumps(data, default=serialize),
        status=status,
        mimetype="application/json",
    )

# ── PAGE ROUTES ───────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/live")
def live_monitor():
    return render_template("live_monitor.html")
# --- API: RECEIVE DATA FROM ESP32 ---
@app.route("/api/upload", methods=["POST"])
def upload_data():
    data = request.get_json()
    if not data:
        return api_response({"error": "No data received"}, status=400)

    # These variable names must match your ESP32 JSON payload
    dev_id  = data.get('device_id')
    co2     = data.get('co2_ppm')
    temp    = data.get('temperature')
    stat    = data.get('status')

    sql = """
        INSERT INTO co2_readings (facility_id, co2_ppm, temperature, status, recorded_at)
        VALUES (%s, %s, %s, %s, NOW())
    """
    query(sql, (dev_id, co2, temp, stat))
    
    return api_response({"status": "success", "message": "Data saved"}, status=201)
# ── API: FACILITIES ───────────────────────────────────────────
@app.route("/api/facilities")
def api_facilities():
    rows = query(
        "SELECT facility_id, name, location, zone, base_load, peak_load FROM facilities ORDER BY facility_id",
        many=True
    )
    return api_response(rows)

# ── API: LATEST READINGS ──────────────────────────────────────
@app.route("/api/latest")
def api_latest():
    rows = query("SELECT * FROM co2_readings ORDER BY recorded_at DESC LIMIT 10", many=True)
    return api_response(rows)

# ── API: GLOBAL STATS ─────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    row = query("SELECT * FROM v_co2_readings")
    return api_response(row)

# ── API: 24-HOUR TREND ────────────────────────────────────────
@app.route("/api/trend/24h")
def api_trend_24h():
    fac = request.args.get("facility_id")
    cutoff = datetime.now() - timedelta(hours=24)

    if fac:
        sql = """
            SELECT DATE_FORMAT(recorded_at,'%%Y-%%m-%%dT%%H:00') AS hour,
                   ROUND(AVG(co2_ppm),1) AS avg_co2,
                   facility_id
            FROM   co2_readings
            WHERE  recorded_at >= %s AND facility_id = %s
            GROUP  BY hour, facility_id
            ORDER  BY hour
        """
        rows = query(sql, (cutoff, fac), many=True)
    else:
        sql = """
            SELECT DATE_FORMAT(recorded_at,'%%Y-%%m-%%dT%%H:00') AS hour,
                   ROUND(AVG(co2_ppm),1) AS avg_co2
            FROM   co2_readings
            WHERE  recorded_at >= %s
            GROUP  BY hour
            ORDER  BY hour
        """
        rows = query(sql, (cutoff,), many=True)

    return api_response(rows)

# ── API: MONTHLY AVERAGES ─────────────────────────────────────
@app.route("/api/monthly")
def api_monthly():
    rows = query(
        "SELECT * FROM v_monthly_averages ORDER BY facility_id, month",
        many=True
    )
    return api_response(rows)

# ── API: DAILY SUMMARY (for heatmap/area chart) ───────────────
@app.route("/api/daily")
def api_daily():
    fac = request.args.get("facility_id")
    months = int(request.args.get("months", 12))
    cutoff = datetime.now() - timedelta(days=months * 30)

    if fac:
        sql = """
            SELECT summary_date, facility_id, avg_co2, min_co2, max_co2,
                   reading_count, danger_count, warning_count
            FROM   daily_summary
            WHERE  facility_id = %s AND summary_date >= %s
            ORDER  BY summary_date
        """
        rows = query(sql, (fac, cutoff.date()), many=True)
    else:
        sql = """
            SELECT summary_date, facility_id, avg_co2, min_co2, max_co2,
                   reading_count, danger_count, warning_count
            FROM   daily_summary
            WHERE  summary_date >= %s
            ORDER  BY summary_date
        """
        rows = query(sql, (cutoff.date(),), many=True)

    return api_response(rows)

# ── API: SCATTER DATA ─────────────────────────────────────────
@app.route("/api/scatter")
def api_scatter():
    fac = request.args.get("facility_id", "FAC-001")
    sql = """
        SELECT temperature, co2_ppm, status
        FROM   co2_readings
        WHERE  facility_id = %s
        ORDER  BY RAND()
        LIMIT  500
    """
    rows = query(sql, (fac,), many=True)
    return api_response(rows)

# ── API: HOURLY HEATMAP (hour-of-day vs day-of-week) ─────────
@app.route("/api/heatmap")
def api_heatmap():
    fac = request.args.get("facility_id", "FAC-001")
    sql = """
        SELECT HOUR(recorded_at)       AS hour_of_day,
               DAYOFWEEK(recorded_at)  AS day_of_week,
               ROUND(AVG(co2_ppm), 0)  AS avg_co2
        FROM   co2_readings
        WHERE  facility_id = %s
        GROUP  BY hour_of_day, day_of_week
        ORDER  BY hour_of_day, day_of_week
    """
    rows = query(sql, (fac,), many=True)
    return api_response(rows)

# ── API: STACKED ALERT EVENTS BY MONTH ────────────────────────
@app.route("/api/alerts/monthly")
def api_alerts_monthly():
    sql = """
        SELECT DATE_FORMAT(recorded_at,'%%Y-%%m') AS month,
               SUM(status = 'NORMAL')  AS normal_count,
               SUM(status = 'WARNING') AS warning_count,
               SUM(status = 'DANGER')  AS danger_count
        FROM   co2_readings
        GROUP  BY month
        ORDER  BY month
    """
    rows = query(sql, many=True)
    return api_response(rows)

# ── API: FLOW RATE BY FACILITY FOR MONTH ──────────────────────
@app.route("/api/flowrate")
def api_flowrate():
    month = request.args.get("month")
    if not month:
        month = datetime.now().strftime("%Y-%m")
    sql = """
        SELECT f.facility_id, f.name AS facility_name,
               ROUND(AVG(r.flow_rate),2) AS avg_flow
        FROM   co2_readings r
        JOIN   facilities f ON f.facility_id = r.facility_id
        WHERE  DATE_FORMAT(r.recorded_at,'%%Y-%%m') = %s
        GROUP  BY f.facility_id, f.name
        ORDER  BY f.facility_id
    """
    rows = query(sql, (month,), many=True)
    return api_response(rows)

# ── API: REPORTS (paginated, filtered) ────────────────────────
@app.route("/api/reports")
def api_reports():
    page        = max(1, int(request.args.get("page",  1)))
    per_page    = min(200, max(10, int(request.args.get("per_page", 50))))
    facility_id = request.args.get("facility_id", "")
    status      = request.args.get("status", "")
    date_from   = request.args.get("date_from", "")
    date_to     = request.args.get("date_to",   "")
    min_ppm     = request.args.get("min_ppm",   "")
    max_ppm     = request.args.get("max_ppm",   "")
    sort_col    = request.args.get("sort", "recorded_at")
    sort_dir    = "ASC" if request.args.get("dir", "desc").lower() == "asc" else "DESC"
    search      = request.args.get("search", "")

    allowed_sort = {
        "recorded_at", "co2_ppm", "temperature", "humidity",
        "flow_rate", "status", "facility_id",
    }
    if sort_col not in allowed_sort:
        sort_col = "recorded_at"

    conditions = []
    params = []

    if facility_id:
        conditions.append("r.facility_id = %s");   params.append(facility_id)
    if status:
        conditions.append("r.status = %s");         params.append(status)
    if date_from:
        conditions.append("r.recorded_at >= %s");   params.append(date_from)
    if date_to:
        conditions.append("r.recorded_at <= %s");   params.append(date_to + " 23:59:59")
    if min_ppm:
        conditions.append("r.co2_ppm >= %s");        params.append(int(min_ppm))
    if max_ppm:
        conditions.append("r.co2_ppm <= %s");        params.append(int(max_ppm))
    if search:
        conditions.append("f.name LIKE %s");         params.append(f"%{search}%")

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM   co2_readings r
        JOIN   facilities f ON f.facility_id = r.facility_id
        {where}
    """
    total_row = query(count_sql, tuple(params))
    total     = total_row["total"] if total_row else 0

    stats_sql = f"""
        SELECT ROUND(AVG(r.co2_ppm),1) AS avg_ppm,
               MIN(r.co2_ppm)          AS min_ppm,
               MAX(r.co2_ppm)          AS max_ppm,
               SUM(r.status='DANGER')  AS danger_count,
               SUM(r.status='WARNING') AS warning_count,
               SUM(r.status='NORMAL')  AS normal_count
        FROM   co2_readings r
        JOIN   facilities f ON f.facility_id = r.facility_id
        {where}
    """
    stats = query(stats_sql, tuple(params))

    offset = (page - 1) * per_page
    data_sql = f"""
        SELECT r.id,
               r.facility_id,
               f.name         AS facility_name,
               f.location,
               r.co2_ppm,
               r.temperature,
               r.humidity,
               r.flow_rate,
               r.status,
               r.recorded_at
        FROM   co2_readings r
        JOIN   facilities f ON f.facility_id = r.facility_id
        {where}
        ORDER  BY {sort_col} {sort_dir}
        LIMIT  %s OFFSET %s
    """
    rows = query(data_sql, tuple(params) + (per_page, offset), many=True)

    return api_response({
        "total":      total,
        "page":       page,
        "per_page":   per_page,
        "pages":      max(1, -(-total // per_page)),
        "stats":      stats,
        "rows":       rows,
    })

# ── API: HEALTH CHECK ─────────────────────────────────────────
@app.route("/api/health")
def api_health():
    try:
        row = query("SELECT COUNT(*) AS cnt FROM co2_readings")
        return api_response({"status": "ok", "readings": row["cnt"], "time": datetime.now()})
    except Exception as e:
        return api_response({"status": "error", "message": str(e)}, 500)

# ── LIVE READINGS API (ESP32 + MH-Z19B) ──────────────────────

@app.route("/api/live/reading", methods=["POST"])
def receive_live_reading():
    """ESP32 posts JSON here every N seconds."""
    data = request.get_json(silent=True)
    if not data:
        return api_response({"error": "No JSON body"}, 400)

    required = ("device_id", "location", "co2_ppm", "temperature", "status")
    missing = [k for k in required if k not in data]
    if missing:
        return api_response({"error": f"Missing fields: {missing}"}, 400)

    status_val = data["status"].upper()
    if status_val not in ("NORMAL", "WARNING", "DANGER"):
        return api_response({"error": "Invalid status"}, 400)

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO live_readings
               (device_id, location, co2_ppm, temperature, status)
               VALUES (%s, %s, %s, %s, %s)""",
            (data["device_id"], data["location"],
             int(data["co2_ppm"]), int(data["temperature"]), status_val)
        )
        insert_id = cur.lastrowid
        cur.close()
    finally:
        conn.close()

    return api_response({"ok": True, "id": insert_id}, 201)


@app.route("/api/live/latest", methods=["GET"])
def get_live_latest():
    """Most recent reading from every device."""
    rows = query(
        "SELECT * FROM v_latest_live ORDER BY recorded_at DESC",
        many=True
    )
    return api_response(rows or [])


@app.route("/api/live/history", methods=["GET"])
def get_live_history():
    """Last N readings — optionally filtered by device_id."""
    device_id = request.args.get("device_id")
    limit = min(int(request.args.get("limit", 60)), 1000)

    if device_id:
        rows = query(
            """SELECT id, device_id, location, co2_ppm, temperature,
                      status, recorded_at
               FROM live_readings
               WHERE device_id = %s
               ORDER BY recorded_at DESC LIMIT %s""",
            (device_id, limit), many=True
        )
    else:
        rows = query(
            """SELECT id, device_id, location, co2_ppm, temperature,
                      status, recorded_at
               FROM live_readings
               ORDER BY recorded_at DESC LIMIT %s""",
            (limit,), many=True
        )
    return api_response(rows or [])


@app.route("/api/live/trend/24h", methods=["GET"])
def get_live_trend_24h():
    """Hourly average CO2 from live_readings for last 24 hours."""
    device_id = request.args.get("device_id")
    cutoff = datetime.now() - timedelta(hours=24)
    if device_id:
        sql = """
            SELECT DATE_FORMAT(recorded_at,'%%Y-%%m-%%dT%%H:00') AS hour,
                   ROUND(AVG(co2_ppm),1) AS avg_co2
            FROM live_readings
            WHERE recorded_at >= %s AND device_id = %s
            GROUP BY hour ORDER BY hour
        """
        rows = query(sql, (cutoff, device_id), many=True)
    else:
        sql = """
            SELECT DATE_FORMAT(recorded_at,'%%Y-%%m-%%dT%%H:00') AS hour,
                   ROUND(AVG(co2_ppm),1) AS avg_co2
            FROM live_readings
            WHERE recorded_at >= %s
            GROUP BY hour ORDER BY hour
        """
        rows = query(sql, (cutoff,), many=True)
    return api_response(rows or [])
def get_live_devices():
    """All unique device IDs seen so far."""
    rows = query(
        "SELECT DISTINCT device_id, location FROM live_readings ORDER BY device_id",
        many=True
    )
    return api_response(rows or [])


@app.route("/api/live/predict", methods=["GET"])
def get_prediction():
    """Train Random Forest Classifier and predict next CO2 status."""
    from co2_predictor import predictor
    device_id = request.args.get("device_id", "ESP32-001")

    rows = query(
        """SELECT co2_ppm FROM live_readings
           WHERE device_id = %s
           ORDER BY recorded_at DESC LIMIT 100""",
        (device_id,), many=True
    )
    if not rows:
        return api_response({"error": "No data available"}, 400)

    co2_values = [r["co2_ppm"] for r in reversed(rows)]
    trained = predictor.train(co2_values)

    if not trained:
        return api_response({"error": "Not enough data (need 15+ readings)"}, 400)

    predicted_class, confidence, prob_dict = predictor.predict_next(co2_values)
    return api_response({
        "predicted_status": predicted_class,
        "confidence": confidence,
        "probabilities": prob_dict,
        "model_accuracy": predictor.accuracy,
        "trained_on": len(co2_values),
        "device_id": device_id
    })


# ── RUN ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  CO2 Emissions Monitor — Flask Server")
    print("  http://localhost:5000")
    print("=" * 50 + "\n")
    app.run(debug=True, host="0.0.0.0", port=5000)