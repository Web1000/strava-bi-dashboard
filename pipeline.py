"""Clean a Strava activities.csv export and upsert it into Postgres (or SQLite)."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

MS_TO_KMH = 3.6
M_TO_KM = 1 / 1000
SEC_TO_MIN = 1 / 60

# Elapsed-time cap. 24 hours drops legitimate ultras; 72 hours still catches
# frozen GPS sessions that never auto-stopped.
MAX_ELAPSED_MIN = 72 * 60

# Average-speed caps by activity family. These are GPS-sanity checks, not
# performance standards. A single global 45 km/h cutoff is too low for cycling:
# fast group rides, time trials, descents, and e-bikes routinely average above
# that, while a 45 km/h *average* on a run is almost always a GPS glitch.
MAX_AVG_SPEED_KMH = {
    "run": 24.0,  # faster than a world-class marathon average (~21 km/h)
    "virtual run": 24.0,
    "trail run": 24.0,
    "walk": 10.0,
    "hike": 15.0,
    "swim": 8.0,
    "ride": 80.0,
    "virtual ride": 80.0,
    "e-bike ride": 80.0,
    "mountain bike ride": 70.0,
    "gravel ride": 80.0,
    "handcycle": 50.0,
    "water sport": 30.0,
    "kayak": 20.0,
    "canoe": 20.0,
    "row": 25.0,
    "stand up paddling": 15.0,
    "workout": None,
    "weight training": None,
    "yoga": None,
}

# Unknown types: do not reuse the old 45 km/h global cap.
DEFAULT_MAX_AVG_SPEED_KMH = 80.0

FACT_COLUMNS = [
    "activity_id",
    "activity_date",
    "activity_name",
    "activity_type_id",
    "distance_km",
    "elapsed_time_min",
    "moving_time_sec",
    "max_speed_kmh",
    "avg_speed_kmh",
    "elevation_gain_m",
    "elevation_loss_m",
    "elevation_low_m",
    "elevation_high_m",
    "max_grade_pct",
    "avg_grade_pct",
    "is_commute",
    "grade_adjusted_distance_km",
]


def meters_per_second_to_kmh(speed_ms: pd.Series) -> pd.Series:
    return (speed_ms * MS_TO_KMH).round(2)


def meters_to_km(distance_m: pd.Series) -> pd.Series:
    return (distance_m * M_TO_KM).round(3)


def seconds_to_minutes(elapsed_sec: pd.Series) -> pd.Series:
    return (elapsed_sec * SEC_TO_MIN).round(2)


def max_avg_speed_kmh_for(activity_type: str) -> float | None:
    key = str(activity_type).strip().lower()
    if key in MAX_AVG_SPEED_KMH:
        return MAX_AVG_SPEED_KMH[key]
    if "ride" in key or "bike" in key:
        return 80.0
    if "run" in key:
        return 24.0
    if "swim" in key:
        return 8.0
    return DEFAULT_MAX_AVG_SPEED_KMH


def _series(df: pd.DataFrame, name: str) -> pd.Series:
    col = df[name]
    if isinstance(col, pd.DataFrame):
        return col.iloc[:, 0]
    return col


def clean_activities(input_path: str | Path) -> pd.DataFrame:
    """Map Strava export columns into analysis units and drop GPS outliers.

    Unit assumptions (Strava bulk export `activities.csv`):
    - `Distance` is kilometers; `Distance.1` is meters (not used for distance_km).
    - `Elapsed Time` / `Moving Time` are seconds.
    - `Max Speed` / `Average Speed` are meters per second.
    - `Grade Adjusted Distance` is meters.
    """
    df = pd.read_csv(input_path)
    gad = _series(df, "Grade Adjusted Distance") if "Grade Adjusted Distance" in df.columns else pd.Series(pd.NA, index=df.index)

    clean = pd.DataFrame(
        {
            "activity_id": _series(df, "Activity ID"),
            "activity_date": pd.to_datetime(
                _series(df, "Activity Date"), format="%b %d, %Y, %I:%M:%S %p"
            ),
            "activity_name": _series(df, "Activity Name"),
            "activity_type": _series(df, "Activity Type"),
            "distance_km": _series(df, "Distance").round(3),
            "elapsed_time_min": seconds_to_minutes(_series(df, "Elapsed Time")),
            "moving_time_sec": _series(df, "Moving Time"),
            "max_speed_kmh": meters_per_second_to_kmh(_series(df, "Max Speed")),
            "avg_speed_kmh": meters_per_second_to_kmh(_series(df, "Average Speed")),
            "elevation_gain_m": _series(df, "Elevation Gain"),
            "elevation_loss_m": _series(df, "Elevation Loss"),
            "elevation_low_m": _series(df, "Elevation Low"),
            "elevation_high_m": _series(df, "Elevation High"),
            "max_grade_pct": _series(df, "Max Grade"),
            "avg_grade_pct": _series(df, "Average Grade"),
            "is_commute": _series(df, "Commute").astype(str).str.lower().isin(["true", "1", "yes"]),
            "grade_adjusted_distance_km": meters_to_km(gad),
        }
    )
    clean = clean.dropna(subset=["activity_id", "activity_date", "activity_type"])
    clean["activity_id"] = clean["activity_id"].astype("int64")

    clean = clean[clean["elapsed_time_min"] < MAX_ELAPSED_MIN]
    clean = clean[clean["distance_km"].fillna(0) >= 0]

    caps = clean["activity_type"].map(max_avg_speed_kmh_for)
    keep_speed = caps.isna() | (clean["avg_speed_kmh"].fillna(0) < caps)
    clean = clean[keep_speed]

    return clean.sort_values("activity_date").reset_index(drop=True)


def ensure_schema(engine: Engine) -> None:
    """Create dim/fact tables. Postgres uses SERIAL; SQLite uses AUTOINCREMENT."""
    if engine.dialect.name == "postgresql":
        schema_path = Path(__file__).resolve().parent / "schema.sql"
        lines = [
            line
            for line in schema_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        return

    dim_id = "activity_type_id INTEGER PRIMARY KEY AUTOINCREMENT"
    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS dim_activity_type (
                    {dim_id},
                    activity_type_name TEXT UNIQUE NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fact_activities (
                    activity_id BIGINT PRIMARY KEY,
                    activity_date TIMESTAMP NOT NULL,
                    activity_name TEXT,
                    activity_type_id INT NOT NULL REFERENCES dim_activity_type (activity_type_id),
                    distance_km FLOAT,
                    elapsed_time_min FLOAT,
                    moving_time_sec INT,
                    max_speed_kmh FLOAT,
                    avg_speed_kmh FLOAT,
                    elevation_gain_m FLOAT,
                    elevation_loss_m FLOAT,
                    elevation_low_m FLOAT,
                    elevation_high_m FLOAT,
                    max_grade_pct FLOAT,
                    avg_grade_pct FLOAT,
                    is_commute BOOLEAN,
                    grade_adjusted_distance_km FLOAT
                )
                """
            )
        )


def _upsert_activity_types(engine: Engine, types: list[str]) -> dict[str, int]:
    insert_sql = (
        "INSERT INTO dim_activity_type (activity_type_name) VALUES (:n) "
        "ON CONFLICT (activity_type_name) DO NOTHING"
        if engine.dialect.name == "postgresql"
        else "INSERT OR IGNORE INTO dim_activity_type (activity_type_name) VALUES (:n)"
    )
    with engine.begin() as conn:
        for name in types:
            conn.execute(text(insert_sql), {"n": name})
        rows = conn.execute(
            text("SELECT activity_type_id, activity_type_name FROM dim_activity_type")
        ).fetchall()
    return {name: type_id for type_id, name in rows}


def load_to_db(df: pd.DataFrame, engine: Engine) -> int:
    """Idempotent load: re-running the same export updates existing activity_ids."""
    if df.empty:
        return 0

    ensure_schema(engine)
    type_ids = _upsert_activity_types(engine, sorted(df["activity_type"].dropna().unique()))

    fact = df.copy()
    fact["activity_type_id"] = fact["activity_type"].map(type_ids)
    if fact["activity_type_id"].isna().any():
        missing = fact.loc[fact["activity_type_id"].isna(), "activity_type"].unique()
        raise ValueError(f"Unmapped activity types: {missing}")
    fact = fact[FACT_COLUMNS]

    ids = fact["activity_id"].tolist()
    delete_sql = text("DELETE FROM fact_activities WHERE activity_id IN :ids").bindparams(
        bindparam("ids", expanding=True)
    )
    with engine.begin() as conn:
        conn.execute(delete_sql, {"ids": ids})
        fact.to_sql("fact_activities", conn, if_exists="append", index=False)
    return len(fact)


def get_engine(url: str | None = None) -> Engine:
    return create_engine(
        url
        or os.environ.get(
            "DATABASE_URL", "postgresql://tonywang@localhost:5432/strava_analysis"
        )
    )


def default_csv_path() -> Path:
    env = os.environ.get("STRAVA_CSV")
    if env:
        return Path(env)
    root = Path(__file__).resolve().parent
    sample = root / "sample_data" / "activities.csv"
    return sample
