import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from backtesting.statistics import (
    bootstrap_ci,
    cost_sensitivity,
    effective_sample_size,
    historical_evidence_grade,
    validation_confidence_intervals,
)


def _sample(number: int, net_return: float = 1.0) -> dict:
    day = number * 3 + 1
    return {
        "sample_id": f"TEST:{number}",
        "entered": True,
        "entry_date": f"2025-01-{day:02d}",
        "exit_date": f"2025-01-{day + 1:02d}",
        "gross_return_pct": net_return + 0.4,
        "net_return_pct": net_return,
        "directional_alpha_pct": net_return - 0.2,
    }


def test_moving_block_bootstrap_is_deterministic() -> None:
    first = bootstrap_ci([1, -2, 3, 4, -1], seed=17, iterations=250, block_length=2)
    second = bootstrap_ci([1, -2, 3, 4, -1], seed=17, iterations=250, block_length=2)

    assert first == second
    assert first["method"] == "moving_block_percentile"


def test_validation_intervals_cover_all_required_statistics() -> None:
    intervals = validation_confidence_intervals([_sample(i) for i in range(6)], iterations=100)

    assert set(intervals) == {"net_return_pct", "directional_alpha_pct", "win_rate_pct"}
    assert all(interval["available"] for interval in intervals.values())


def test_effective_sample_size_uses_non_overlap_and_positive_autocorrelation() -> None:
    samples = [
        {**_sample(0), "entry_date": "2025-01-01", "exit_date": "2025-01-10"},
        {**_sample(1), "entry_date": "2025-01-05", "exit_date": "2025-01-12"},
        {**_sample(2), "entry_date": "2025-01-13", "exit_date": "2025-01-15"},
    ]

    result = effective_sample_size(samples, "net_return_pct")

    assert result["raw"] == 3
    assert result["non_overlapping"] == 2
    assert result["effective"] <= 2


def test_cost_sensitivity_is_monotonic() -> None:
    scenarios = cost_sensitivity([_sample(i) for i in range(5)])
    returns = [scenario["average_net_return_pct"] for scenario in scenarios]

    assert returns == sorted(returns, reverse=True)
    assert [scenario["round_trip_cost_bps"] for scenario in scenarios] == [0, 20, 40, 80]


def test_historical_evidence_grade_is_capped_low() -> None:
    samples = []
    for number in range(20):
        entry = f"2025-{number + 1:02d}-01" if number < 12 else f"2026-{number - 11:02d}-01"
        exit_date = f"2025-{number + 1:02d}-02" if number < 12 else f"2026-{number - 11:02d}-02"
        samples.append({**_sample(0, 5.0), "sample_id": str(number), "entry_date": entry, "exit_date": exit_date})
    intervals = validation_confidence_intervals(samples, iterations=100)
    ess = effective_sample_size(samples, "net_return_pct")

    grade = historical_evidence_grade(samples, intervals, ess)

    assert grade["level"] == "low"
    assert grade["cap"] == "low"
    assert "selection_bias" in grade["cap_reason"]
