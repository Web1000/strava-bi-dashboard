from pipeline import clean_activities, default_csv_path


def test_sample_csv_is_the_default_input():
    assert default_csv_path().name == "activities.csv"
    df = clean_activities(default_csv_path())
    assert not df.empty
    assert {"Run", "Ride"}.issubset(set(df["activity_type"]))
