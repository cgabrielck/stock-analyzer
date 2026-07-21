import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backtesting.calibration import (
    ExpandingScoreCalibrator,
    load_calibration_snapshot,
    probability_from_snapshot,
    save_calibration_snapshot,
)


def test_calibrator_waits_for_completed_minimum_sample() -> None:
    calibrator = ExpandingScoreCalibrator(min_observations=3)
    calibrator.add_many([(70, True), (70, False)])

    assert calibrator.probability(70) is None

    calibrator.add(80, True)
    assert calibrator.probability(70) is not None
    assert calibrator.snapshot()["ready"] is True


def test_calibrator_uses_shrinkage_for_empty_bin() -> None:
    calibrator = ExpandingScoreCalibrator(min_observations=2, prior_strength=10)
    calibrator.add_many([(50, True), (50, False)])

    assert calibrator.probability(90) == 0.5


def test_calibration_snapshot_round_trip_and_expiry(tmp_path) -> None:
    calibrator = ExpandingScoreCalibrator(min_observations=2)
    calibrator.add_many([(70, True), (70, False)])
    path = tmp_path / "calibration.json"

    assert save_calibration_snapshot(calibrator.snapshot(), as_of="2026-07-01", path=path)
    loaded = load_calibration_snapshot(path, now=datetime.now(timezone.utc))
    assert loaded is not None
    assert probability_from_snapshot(70, loaded) == 0.5

    future = datetime.now(timezone.utc) + timedelta(days=181)
    assert load_calibration_snapshot(path, now=future) is None


def test_unready_calibration_is_not_saved(tmp_path) -> None:
    calibrator = ExpandingScoreCalibrator(min_observations=2)
    calibrator.add(70, True)
    path = tmp_path / "calibration.json"

    assert save_calibration_snapshot(calibrator.snapshot(), as_of="2026-07-01", path=path) is False
    assert path.exists() is False
