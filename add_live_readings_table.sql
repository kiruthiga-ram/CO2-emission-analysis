-- ============================================================
--  ADD THIS TO YOUR co2_monitor DATABASE
--  Run in Valentina Studio or MySQL Workbench
-- ============================================================

USE co2_monitor;

-- ── LIVE SENSOR READINGS (from ESP32 devices) ───────────────
CREATE TABLE IF NOT EXISTS live_readings (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  device_id    VARCHAR(50)  NOT NULL,          -- e.g. "ESP32-001"
  location     VARCHAR(100) NOT NULL,          -- e.g. "Room A"
  co2_ppm      INT          NOT NULL,          -- from MH-Z19B
  temperature  INT          NOT NULL,          -- °C from MH-Z19B
  status       ENUM('NORMAL','WARNING','DANGER') NOT NULL,
  recorded_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_lr_device     (device_id),
  KEY idx_lr_recorded   (recorded_at),
  KEY idx_lr_dev_rec    (device_id, recorded_at)
) ENGINE=InnoDB;

-- ── VIEW: latest reading per device ─────────────────────────
CREATE OR REPLACE VIEW v_latest_live AS
SELECT
  lr.id,
  lr.device_id,
  lr.location,
  lr.co2_ppm,
  lr.temperature,
  lr.status,
  lr.recorded_at
FROM live_readings lr
WHERE lr.recorded_at = (
  SELECT MAX(lr2.recorded_at)
  FROM live_readings lr2
  WHERE lr2.device_id = lr.device_id
);
