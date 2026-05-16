import pytest

from src.pipeline.scorer import (
    calculate_competition,
    calculate_trend_score,
    calculate_velocity,
    determine_status,
)


class TestCalculateTrendScore:
    def test_high_signals_produce_high_score(self):
        signals = {
            "advertiser_count": 50,
            "ad_duration": 30,
            "creative_volume": 100,
            "engagement_velocity": 5000000,
            "order_volume_growth": 500,
            "supplier_availability": 30,
        }
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert 0 <= score <= 100

    def test_low_signals_produce_low_score(self):
        low = {
            "advertiser_count": 1,
            "ad_duration": 1,
            "creative_volume": 1,
            "engagement_velocity": 1000,
            "order_volume_growth": 5,
            "supplier_availability": 1,
        }
        high = {
            "advertiser_count": 50,
            "ad_duration": 30,
            "creative_volume": 100,
            "engagement_velocity": 5000000,
            "order_volume_growth": 500,
            "supplier_availability": 30,
        }
        all_signals = [low, high]
        low_score = calculate_trend_score(low, all_signals)
        high_score = calculate_trend_score(high, all_signals)
        assert low_score < high_score

    def test_score_capped_at_100(self):
        signals = {
            "advertiser_count": 1000,
            "ad_duration": 365,
            "creative_volume": 5000,
            "engagement_velocity": 100000000,
            "order_volume_growth": 10000,
            "supplier_availability": 500,
        }
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert score <= 100

    def test_single_product_gets_percentile_of_100(self):
        signals = {
            "advertiser_count": 20,
            "ad_duration": 10,
            "creative_volume": 30,
            "engagement_velocity": 1000000,
            "order_volume_growth": 100,
            "supplier_availability": 10,
        }
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert score == 100


class TestCalculateVelocity:
    def test_accelerating(self):
        scores = [50, 60, 70]
        velocity = calculate_velocity(scores)
        assert velocity == "accelerating"

    def test_stable(self):
        scores = [50, 51, 52]
        velocity = calculate_velocity(scores)
        assert velocity == "stable"

    def test_decelerating(self):
        scores = [70, 60, 50]
        velocity = calculate_velocity(scores)
        assert velocity == "decelerating"

    def test_insufficient_history_returns_stable(self):
        scores = [50]
        velocity = calculate_velocity(scores)
        assert velocity == "stable"


class TestDetermineStatus:
    def test_trending(self):
        status = determine_status(score=50, velocity="stable", declining_runs=0)
        assert status == "trending"

    def test_declining(self):
        status = determine_status(score=50, velocity="decelerating", declining_runs=3)
        assert status == "declining"

    def test_not_declining_until_3_runs(self):
        status = determine_status(score=50, velocity="decelerating", declining_runs=2)
        assert status == "trending"

    def test_expired(self):
        status = determine_status(score=20, velocity="decelerating", declining_runs=3)
        assert status == "expired"

    def test_expired_needs_3_consecutive_runs(self):
        status = determine_status(score=20, velocity="decelerating", declining_runs=2)
        assert status == "trending"


class TestCalculateCompetition:
    def test_low_competition(self):
        result = calculate_competition(advertiser_count=5, supplier_count=10)
        assert result == "low"

    def test_medium_competition(self):
        result = calculate_competition(advertiser_count=25, supplier_count=50)
        assert result == "medium"

    def test_high_competition(self):
        result = calculate_competition(advertiser_count=60, supplier_count=150)
        assert result == "high"
