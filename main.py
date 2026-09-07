from __future__ import annotations

import argparse

from pipeline import clean_activities, default_csv_path, get_engine, load_to_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Load a Strava activities.csv into Postgres.")
    parser.add_argument(
        "--csv",
        default=str(default_csv_path()),
        help="Path to activities.csv (default: sample_data/activities.csv or $STRAVA_CSV)",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="SQLAlchemy URL (default: $DATABASE_URL or local strava_analysis)",
    )
    args = parser.parse_args()

    clean_df = clean_activities(args.csv)
    engine = get_engine(args.database_url)
    loaded = load_to_db(clean_df, engine)
    print(f"Loaded {loaded} rows into fact_activities ({len(clean_df)} after cleaning)")


if __name__ == "__main__":
    main()
