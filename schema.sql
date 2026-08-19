-- ============================================================
--  CO2 EMISSIONS MONITOR — MySQL Schema
--  Run this FIRST in Valentina Studio or MySQL Workbench
--  Compatible with MySQL 8.0+
-- ============================================================

CREATE DATABASE IF NOT EXISTS co2_monitor
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE co2_monitor;

-- ── FACILITIES ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS facilities (
  id          INT          NOT NULL AUTO_INCREMENT,
  facility_id VARCHAR(20)  NOT NULL UNIQUE,
  name        VARCHAR(100) NOT NULL,
  location    VARCHAR(100) NOT NULL,
  zone        VARCHAR(20)  NOT NULL,
  base_load   INT          NOT NULL DEFAULT 700,
  peak_load   INT          NOT NULL DEFAULT 1400,
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB;

-- ── CO2 READINGS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS co2_readings (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  facility_id  VARCHAR(20)  NOT NULL,
  co2_ppm      INT          NOT NULL,
  temperature  DECIMAL(5,2) NOT NULL,
  humidity     DECIMAL(5,2) NOT NULL,
  flow_rate    DECIMAL(8,2) NOT NULL,
  status       ENUM('NORMAL','WARNING','DANGER') NOT NULL,
  recorded_at  DATETIME     NOT NULL,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_facility    (facility_id),
  KEY idx_recorded_at (recorded_at),
  KEY idx_status      (status),
  KEY idx_fac_rec     (facility_id, recorded_at),
  CONSTRAINT fk_facility
    FOREIGN KEY (facility_id) REFERENCES facilities(facility_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- ── ALERT EVENTS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_events (
  id           INT         NOT NULL AUTO_INCREMENT,
  facility_id  VARCHAR(20) NOT NULL,
  alert_type   ENUM('WARNING','DANGER') NOT NULL,
  co2_ppm      INT         NOT NULL,
  triggered_at DATETIME    NOT NULL,
  resolved_at  DATETIME    NULL,
  notes        TEXT        NULL,
  PRIMARY KEY  (id),
  KEY idx_ae_facility (facility_id),
  KEY idx_ae_triggered (triggered_at)
) ENGINE=InnoDB;

-- ── DAILY SUMMARY (materialised view pattern) ────────────────
CREATE TABLE IF NOT EXISTS daily_summary (
  id           INT          NOT NULL AUTO_INCREMENT,
  facility_id  VARCHAR(20)  NOT NULL,
  summary_date DATE         NOT NULL,
  avg_co2      DECIMAL(8,2) NOT NULL,
  min_co2      INT          NOT NULL,
  max_co2      INT          NOT NULL,
  reading_count INT         NOT NULL,
  danger_count  INT         NOT NULL DEFAULT 0,
  warning_count INT         NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  UNIQUE KEY uq_fac_date (facility_id, summary_date),
  KEY idx_ds_date (summary_date)
) ENGINE=InnoDB;

-- ── VIEWS ────────────────────────────────────────────────────

-- Latest reading per facility
CREATE OR REPLACE VIEW v_latest_readings AS
SELECT
  r.id,
  r.facility_id,
  f.name            AS facility_name,
  f.location,
  f.zone,
  r.co2_ppm,
  r.temperature,
  r.humidity,
  r.flow_rate,
  r.status,
  r.recorded_at
FROM co2_readings r
INNER JOIN facilities f ON f.facility_id = r.facility_id
WHERE r.recorded_at = (
  SELECT MAX(r2.recorded_at)
  FROM co2_readings r2
  WHERE r2.facility_id = r.facility_id
);

-- Monthly averages per facility
CREATE OR REPLACE VIEW v_monthly_averages AS
SELECT
  f.facility_id,
  f.name                           AS facility_name,
  DATE_FORMAT(r.recorded_at,'%Y-%m') AS month,
  ROUND(AVG(r.co2_ppm), 1)         AS avg_co2,
  MIN(r.co2_ppm)                   AS min_co2,
  MAX(r.co2_ppm)                   AS max_co2,
  COUNT(*)                         AS reading_count,
  SUM(r.status = 'DANGER')         AS danger_count,
  SUM(r.status = 'WARNING')        AS warning_count
FROM co2_readings r
JOIN facilities f ON f.facility_id = r.facility_id
GROUP BY f.facility_id, DATE_FORMAT(r.recorded_at,'%Y-%m');

-- Overall stats view
CREATE OR REPLACE VIEW v_global_stats AS
SELECT
  COUNT(*)                                          AS total_readings,
  ROUND(AVG(co2_ppm), 1)                           AS avg_co2,
  MIN(co2_ppm)                                     AS min_co2,
  MAX(co2_ppm)                                     AS max_co2,
  SUM(status = 'NORMAL')                           AS normal_count,
  SUM(status = 'WARNING')                          AS warning_count,
  SUM(status = 'DANGER')                           AS danger_count,
  ROUND(100.0 * SUM(status = 'NORMAL') / COUNT(*),1)  AS normal_pct,
  ROUND(100.0 * SUM(status = 'WARNING')/ COUNT(*),1)  AS warning_pct,
  ROUND(100.0 * SUM(status = 'DANGER') / COUNT(*),1)  AS danger_pct
FROM co2_readings;

-- ── SEED FACILITIES ──────────────────────────────────────────
INSERT IGNORE INTO facilities (facility_id, name, location, zone, base_load, peak_load) VALUES
  ('FAC-001', 'Steel Plant Alpha',    'North Industrial Park', 'Zone A', 920, 1600),
  ('FAC-002', 'Cement Works Beta',    'East Corridor',         'Zone B', 780, 1400),
  ('FAC-003', 'Power Unit Gamma',     'Central Plant',         'Zone C', 650, 1200),
  ('FAC-004', 'Chemical Plant Delta', 'South Campus',          'Zone D', 500,  950);
