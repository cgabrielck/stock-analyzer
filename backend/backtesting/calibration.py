from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


MODEL_VERSION = 2
DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "score_calibration.json"


@dataclass
class CalibrationBin:
    wins: int = 0
    count: int = 0


class ExpandingScoreCalibrator:
    """Calibrate scores using completed observations only."""

    def __init__(self, bin_width: int = 10, min_observations: int = 100, prior_strength: int = 20) -> None:
        self.bin_width = bin_width
        self.min_observations = min_observations
        self.prior_strength = prior_strength
        self._bins: Dict[int, CalibrationBin] = {}
        self.total_wins = 0
        self.total_count = 0

    def add(self, score: float, won: bool) -> None:
        key = self._bin_key(score)
        bucket = self._bins.setdefault(key, CalibrationBin())
        bucket.count += 1
        bucket.wins += int(won)
        self.total_count += 1
        self.total_wins += int(won)

    def add_many(self, observations: List[Tuple[float, bool]]) -> None:
        for score, won in observations:
            self.add(score, won)

    def probability(self, score: float) -> Optional[float]:
        if self.total_count < self.min_observations:
            return None
        global_rate = self.total_wins / self.total_count
        bucket = self._bins.get(self._bin_key(score), CalibrationBin())
        probability = (
            bucket.wins + self.prior_strength * global_rate
        ) / (bucket.count + self.prior_strength)
        return max(0.01, min(0.99, probability))

    def snapshot(self) -> Dict[str, object]:
        global_rate = self.total_wins / self.total_count if self.total_count else None
        return {
            "observations": self.total_count,
            "global_win_rate": round(global_rate, 4) if global_rate is not None else None,
            "ready": self.total_count >= self.min_observations,
            "model_version": MODEL_VERSION,
            "bin_width": self.bin_width,
            "min_observations": self.min_observations,
            "prior_strength": self.prior_strength,
            "bins": {
                f"{key}-{key + self.bin_width}": {"wins": value.wins, "count": value.count}
                for key, value in sorted(self._bins.items())
            },
        }

    def _bin_key(self, score: float) -> int:
        bounded = max(0.0, min(100.0, float(score)))
        return min(int(bounded // self.bin_width) * self.bin_width, 100 - self.bin_width)


def probability_from_snapshot(score: float, snapshot: Dict[str, Any]) -> Optional[float]:
    if not snapshot.get("ready") or snapshot.get("model_version") != MODEL_VERSION:
        return None
    observations = int(snapshot.get("observations", 0) or 0)
    minimum = int(snapshot.get("min_observations", 100) or 100)
    global_rate = snapshot.get("global_win_rate")
    if observations < minimum or global_rate is None:
        return None

    bin_width = int(snapshot.get("bin_width", 10) or 10)
    prior_strength = int(snapshot.get("prior_strength", 20) or 20)
    bounded = max(0.0, min(100.0, float(score)))
    key = min(int(bounded // bin_width) * bin_width, 100 - bin_width)
    bucket = snapshot.get("bins", {}).get(f"{key}-{key + bin_width}", {})
    count = int(bucket.get("count", 0) or 0)
    wins = int(bucket.get("wins", 0) or 0)
    probability = (wins + prior_strength * float(global_rate)) / (count + prior_strength)
    return max(0.01, min(0.99, probability))


def save_calibration_snapshot(
    snapshot: Dict[str, Any],
    *,
    as_of: str,
    path: Path = DEFAULT_MODEL_PATH,
) -> bool:
    if probability_from_snapshot(50.0, snapshot) is None:
        return False
    payload = dict(snapshot)
    payload.update({
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "walk_forward_backtest",
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(path)
    return True


def load_calibration_snapshot(
    path: Path = DEFAULT_MODEL_PATH,
    *,
    max_age_days: int = 180,
    now: Optional[datetime] = None,
) -> Optional[Dict[str, Any]]:
    try:
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        generated = datetime.fromisoformat(str(snapshot["generated_at"]).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if (current - generated).days > max_age_days:
            return None
        if probability_from_snapshot(50.0, snapshot) is None:
            return None
        return snapshot
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None
