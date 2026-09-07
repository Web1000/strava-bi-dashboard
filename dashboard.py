"""Build a static dashboard PNG from a cleaned activities table (no personal export required)."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from pipeline import clean_activities, default_csv_path


def build_dashboard(df: pd.DataFrame, output_path: Path) -> None:
    monthly = (
        df.assign(month=df["activity_date"].dt.to_period("M").dt.to_timestamp())
        .groupby("month", as_index=False)
        .agg(total_km=("distance_km", "sum"), n=("activity_id", "count"))
    )
    by_type = (
        df.groupby("activity_type", as_index=False)
        .agg(total_km=("distance_km", "sum"), n=("activity_id", "count"))
        .sort_values("total_km", ascending=False)
    )

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    fig.suptitle("Strava activity dashboard (synthetic sample)", fontsize=14)

    axes[0, 0].bar(by_type["activity_type"], by_type["total_km"], color="#fc4c02")
    axes[0, 0].set_title("Distance by activity type")
    axes[0, 0].set_ylabel("km")

    axes[0, 1].bar(monthly["month"].dt.strftime("%Y-%m"), monthly["total_km"], color="#2d2d2d")
    axes[0, 1].set_title("Monthly distance")
    axes[0, 1].set_ylabel("km")
    axes[0, 1].tick_params(axis="x", rotation=30)

    for activity_type, group in df.groupby("activity_type"):
        axes[1, 0].scatter(
            group["distance_km"],
            group["avg_speed_kmh"],
            label=activity_type,
            alpha=0.8,
        )
    axes[1, 0].set_title("Average speed vs distance")
    axes[1, 0].set_xlabel("km")
    axes[1, 0].set_ylabel("km/h")
    axes[1, 0].legend(fontsize=8)

    axes[1, 1].axis("off")
    summary = [
        f"Activities kept: {len(df)}",
        f"Total distance: {df['distance_km'].sum():.1f} km",
        f"Date range: {df['activity_date'].min():%Y-%m-%d} to {df['activity_date'].max():%Y-%m-%d}",
        "Speed filters are activity-specific (see README).",
    ]
    axes[1, 1].set_title("Summary")
    axes[1, 1].text(0.0, 0.7, "\n".join(summary), va="top", fontsize=11, family="sans-serif")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=140)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=str(default_csv_path()))
    parser.add_argument("--out", default="assets/dashboard.png")
    args = parser.parse_args()
    df = clean_activities(args.csv)
    out = Path(args.out)
    build_dashboard(df, out)
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
