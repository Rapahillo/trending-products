import yaml

from config.settings import settings

_weights_cache: dict | None = None


def _load_weights() -> dict:
    global _weights_cache
    if _weights_cache is None:
        with open(settings.scoring_weights_path) as f:
            _weights_cache = yaml.safe_load(f)
    return _weights_cache


def _percentile_rank(value: float, all_values: list[float]) -> float:
    """Return percentile rank (0-1) of value within all_values."""
    if len(all_values) <= 1:
        return 1.0
    sorted_values = sorted(all_values)
    rank = sorted_values.index(value)
    return rank / (len(sorted_values) - 1)


def calculate_trend_score(signals: dict, all_signals: list[dict]) -> int:
    """Calculate trend score (0-100) using weighted percentile ranking."""
    config = _load_weights()
    weights = config["weights"]
    calibration = config["calibration_factor"]

    signal_keys = [
        "advertiser_count",
        "ad_duration",
        "creative_volume",
        "engagement_velocity",
        "order_volume_growth",
        "supplier_availability",
    ]

    raw_score = 0.0
    for key in signal_keys:
        value = signals.get(key, 0)
        all_values = [s.get(key, 0) for s in all_signals]
        percentile = _percentile_rank(value, all_values)
        raw_score += percentile * weights[key]

    score = min(100, int(raw_score * 100 * calibration))
    return score


def calculate_velocity(scores: list[int]) -> str:
    """Calculate velocity from score history (oldest to newest)."""
    config = _load_weights()
    threshold = config["velocity_stable_threshold"]

    if len(scores) < 3:
        return "stable"

    velocity = (scores[-1] - scores[-3]) / 2

    if abs(velocity) < threshold:
        return "stable"
    elif velocity > 0:
        return "accelerating"
    else:
        return "decelerating"


def determine_status(score: int, velocity: str, declining_runs: int) -> str:
    """Determine product status based on score, velocity, and history."""
    config = _load_weights()
    min_score = config["trending_min_score"]
    consecutive_needed = config["velocity_consecutive_runs_for_status"]

    if score < min_score and declining_runs >= consecutive_needed:
        return "expired"

    if score >= min_score and velocity == "decelerating" and declining_runs >= consecutive_needed:
        return "declining"

    return "trending"


def calculate_competition(advertiser_count: int, supplier_count: int) -> str:
    """Classify competition level based on advertiser and supplier counts."""
    config = _load_weights()
    comp = config["competition"]

    if (
        advertiser_count <= comp["low_max_advertisers"]
        and supplier_count <= comp["low_max_suppliers"]
    ):
        return "low"
    elif (
        advertiser_count <= comp["medium_max_advertisers"]
        and supplier_count <= comp["medium_max_suppliers"]
    ):
        return "medium"
    else:
        return "high"
