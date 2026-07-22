from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd


STATISTICS_VERSION = 3
DEFAULT_BOOTSTRAP_SEED = 20260722
DEFAULT_BOOTSTRAP_ITERATIONS = 4000
FIXED_ROUND_TRIP_COST_BPS = (0, 20, 40, 80)


def bootstrap_ci(
    values: Sequence[float],
    *,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence_level: float = 0.95,
    block_length: int = 1,
    statistic: str = "mean",
) -> Dict[str, Any]:
    clean = np.asarray([float(value) for value in values if value is not None and np.isfinite(value)], dtype=float)
    if clean.size == 0:
        return {"available": False, "observations": 0}
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if statistic not in {"mean", "win_rate"}:
        raise ValueError(f"unsupported statistic: {statistic}")
    rng = np.random.default_rng(seed)
    n = clean.size
    block = max(1, min(int(block_length), n))
    estimates = np.empty(iterations, dtype=float)
    for iteration in range(iterations):
        sampled: List[float] = []
        while len(sampled) < n:
            start = int(rng.integers(0, n))
            sampled.extend(clean[(start + offset) % n] for offset in range(block))
        sample = np.asarray(sampled[:n])
        estimates[iteration] = float(np.mean(sample > 0) * 100) if statistic == "win_rate" else float(np.mean(sample))
    estimate = float(np.mean(clean > 0) * 100) if statistic == "win_rate" else float(np.mean(clean))
    alpha = (1 - confidence_level) / 2
    return {
        "available": True,
        "estimate": round(estimate, 3),
        "lower": round(float(np.quantile(estimates, alpha)), 3),
        "upper": round(float(np.quantile(estimates, 1 - alpha)), 3),
        "confidence_level": confidence_level,
        "method": "moving_block_percentile",
        "iterations": iterations,
        "seed": seed,
        "block_length": block,
        "observations": n,
        "statistic": statistic,
    }


def effective_sample_size(samples: Iterable[Dict[str, Any]], value_key: str = "excess_return_pct") -> Dict[str, Any]:
    ordered = sorted(
        [sample for sample in samples if sample.get("entry_date") and sample.get("exit_date") and sample.get(value_key) is not None],
        key=lambda sample: (sample["entry_date"], sample["exit_date"], sample.get("sample_id", "")),
    )
    n = len(ordered)
    if n == 0:
        return {"raw": 0, "non_overlapping": 0, "acf_adjusted": 0.0, "effective": 0.0}
    non_overlapping = 0
    last_exit = None
    # Earliest-finish interval scheduling gives the largest independent subset.
    for sample in sorted(ordered, key=lambda item: (item["exit_date"], item["entry_date"])):
        entry = pd.Timestamp(sample["entry_date"])
        exit_date = pd.Timestamp(sample["exit_date"])
        if last_exit is None or entry > last_exit:
            non_overlapping += 1
            last_exit = exit_date
    values = pd.Series([float(sample[value_key]) for sample in ordered])
    max_lag = min(max(1, int(np.sqrt(n))), n - 1)
    positive_acf = 0.0
    if values.nunique() > 1:
        for lag in range(1, max_lag + 1):
            correlation = values.autocorr(lag=lag)
            if correlation is not None and np.isfinite(correlation) and correlation > 0:
                positive_acf += float(correlation)
    acf_adjusted = n / (1 + 2 * positive_acf)
    effective = max(1.0, min(float(n), float(non_overlapping), acf_adjusted))
    return {
        "raw": n,
        "non_overlapping": non_overlapping,
        "acf_adjusted": round(acf_adjusted, 2),
        "effective": round(effective, 2),
        "method": "min_interval_and_positive_acf",
        "acf_lags": max_lag,
    }


def validation_confidence_intervals(
    samples: Iterable[Dict[str, Any]],
    *,
    seed: int = DEFAULT_BOOTSTRAP_SEED,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    block_length: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """Return deterministic moving-block intervals for the v3 headline metrics."""
    entered = [sample for sample in samples if sample.get("entered")]
    net_returns = _finite_values(entered, "net_return_pct")
    directional_alpha = _finite_values(entered, "directional_alpha_pct", fallback="excess_return_pct")
    block = block_length or _default_block_length(len(entered))
    return {
        "net_return_pct": bootstrap_ci(
            net_returns, seed=seed, iterations=iterations, block_length=block
        ),
        "directional_alpha_pct": bootstrap_ci(
            directional_alpha, seed=seed, iterations=iterations, block_length=block
        ),
        "win_rate_pct": bootstrap_ci(
            net_returns, seed=seed, iterations=iterations, block_length=block, statistic="win_rate"
        ),
    }


def cost_sensitivity(
    samples: Iterable[Dict[str, Any]],
    round_trip_cost_bps: Sequence[int] = FIXED_ROUND_TRIP_COST_BPS,
) -> List[Dict[str, Any]]:
    """Reprice gross trade returns under fixed, comparable round-trip costs."""
    gross_returns = _finite_values(
        [sample for sample in samples if sample.get("entered")], "gross_return_pct"
    )
    scenarios = []
    for cost_bps in round_trip_cost_bps:
        adjusted = [value - float(cost_bps) / 100 for value in gross_returns]
        scenarios.append({
            "round_trip_cost_bps": int(cost_bps),
            "trade_count": len(adjusted),
            "average_net_return_pct": round(float(np.mean(adjusted)), 3) if adjusted else None,
            "win_rate_pct": round(float(np.mean(np.asarray(adjusted) > 0) * 100), 1) if adjusted else None,
        })
    return scenarios


def historical_evidence_grade(
    samples: Iterable[Dict[str, Any]],
    confidence_intervals: Dict[str, Dict[str, Any]],
    effective_n: Dict[str, Any],
) -> Dict[str, Any]:
    """Grade ticker-specific evidence, with an explicit selection-bias cap."""
    entered = [sample for sample in samples if sample.get("entered")]
    n_eff = float(effective_n.get("effective", 0))
    net_ci = confidence_intervals.get("net_return_pct", {})
    alpha_ci = confidence_intervals.get("directional_alpha_pct", {})
    win_ci = confidence_intervals.get("win_rate_pct", {})
    positive_net = net_ci.get("lower") is not None and net_ci["lower"] > 0
    positive_alpha = alpha_ci.get("lower") is not None and alpha_ci["lower"] > 0
    positive_wins = win_ci.get("lower") is not None and win_ci["lower"] > 50

    if len(entered) < 12 or n_eff < 8:
        level, score, reason = "insufficient", 0, "effective_sample_too_small"
    else:
        score = min(49, int(min(n_eff, 40) / 40 * 25) + 8 * sum((positive_net, positive_alpha, positive_wins)))
        level = "low"
        reason = "ticker_specific_evidence_bias_capped"
    return {
        "level": level,
        "score": score,
        "reason": reason,
        "effective_sample_size": round(n_eff, 2),
        "cap": "low",
        "cap_reason": "current_universe_and_ticker_selection_bias",
    }


def _finite_values(
    samples: Iterable[Dict[str, Any]], value_key: str, fallback: Optional[str] = None
) -> List[float]:
    values = []
    for sample in samples:
        value = sample.get(value_key)
        if value is None and fallback:
            value = sample.get(fallback)
        if value is not None and np.isfinite(value):
            values.append(float(value))
    return values


def _default_block_length(observations: int) -> int:
    return max(1, min(observations, int(round(observations ** (1 / 3)))))
