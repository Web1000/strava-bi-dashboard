from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from pipeline import (
    MS_TO_KMH,
    clean_activities,
    load_to_db,
    max_avg_speed_kmh_for,
    meters_per_second_to_kmh,
    meters_to_km,
    seconds_to_minutes,
)

SAMPLE = Path(__file__).resolve().parents[1] / "sample_data" / "activities.csv"


def test_speed_and_distance_units():
    speed = meters_per_second_to_kmh(pd.Series([10.0, 0.0]))
    assert speed.tolist() == [36.0, 0.0]
    assert pytest.approx(10 * MS_TO_KMH) == 36.0
    assert meters_to_km(pd.Series([5000.0])).tolist() == [5.0]
    assert seconds_to_minutes(pd.Series([120.0])).tolist() == [2.0]


def test_clean_maps_strava_export_units():
    df = clean_activities(SAMPLE)
    riverside = df.loc[df["activity_id"] == 1001].iloc[0]
    assert riverside["distance_km"] == pytest.approx(5.0)
    assert riverside["elapsed_time_min"] == pytest.approx(25.0)
    assert riverside["avg_speed_kmh"] == pytest.approx(12.0)
    assert riverside["grade_adjusted_distance_km"] == pytest.approx(5.12)


def test_outliers_use_activity_specific_speed_caps():
    assert max_avg_speed_kmh_for("Ride") == 80.0
    assert max_avg_speed_kmh_for("Run") == 24.0
    df = clean_activities(SAMPLE)
    ids = set(df["activity_id"])
    assert 1002 not in ids  # ~80 km/h average run — GPS glitch
    assert 1003 in ids  # ~50 km/h average ride — would fail a global 45 km/h cutoff
    assert 1009 in ids  # cycling time trial at 50 km/h
    assert 1010 not in ids  # elapsed time far beyond 72 hours


def test_repeat_loading_does_not_duplicate_rows():
    engine = create_engine("sqlite:///:memory:")
    df = clean_activities(SAMPLE)
    first = load_to_db(df, engine)
    renamed = df.copy()
    renamed.loc[renamed["activity_id"] == 1001, "activity_name"] = "Riverside tempo (edited)"
    second = load_to_db(renamed, engine)
    assert first == second == len(df)
    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM fact_activities")).scalar()
        name = conn.execute(
            text("SELECT activity_name FROM fact_activities WHERE activity_id = 1001")
        ).scalar()
        types = conn.execute(text("SELECT COUNT(*) FROM dim_activity_type")).scalar()
    assert count == len(df)
    assert name == "Riverside tempo (edited)"
    assert types == df["activity_type"].nunique()
