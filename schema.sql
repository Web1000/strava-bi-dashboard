-- Star schema for Strava activities (PostgreSQL).
-- Apply once:  psql -d strava_analysis -f schema.sql
-- Loading is handled by pipeline.py (upserts into these tables).
-- Do not rename tables after load; Python writes directly to fact_activities.

CREATE TABLE IF NOT EXISTS dim_activity_type (
    activity_type_id SERIAL PRIMARY KEY,
    activity_type_name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS fact_activities (
    activity_id BIGINT PRIMARY KEY,
    activity_date TIMESTAMP NOT NULL,
    activity_name TEXT,
    activity_type_id INT NOT NULL REFERENCES dim_activity_type (activity_type_id),
    distance_km NUMERIC(6, 3),
    elapsed_time_min NUMERIC(8, 2),
    moving_time_sec INT,
    max_speed_kmh NUMERIC(6, 2),
    avg_speed_kmh NUMERIC(6, 2),
    elevation_gain_m NUMERIC(7, 1),
    elevation_loss_m NUMERIC(7, 1),
    elevation_low_m NUMERIC(7, 1),
    elevation_high_m NUMERIC(7, 1),
    max_grade_pct NUMERIC(5, 1),
    avg_grade_pct NUMERIC(5, 1),
    is_commute BOOLEAN,
    grade_adjusted_distance_km NUMERIC(6, 3)
);

CREATE INDEX IF NOT EXISTS idx_fact_activities_date
    ON fact_activities (activity_date);

CREATE INDEX IF NOT EXISTS idx_fact_activities_type
    ON fact_activities (activity_type_id);
