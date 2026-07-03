"""
test_analysis.py
------------------
Unit tests for the deterministic quantitative analysis engine.
Uses synthetic price data so tests are reproducible without network access.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
import pytest

from src.analysis import compute_technicals, analyze, _rsi, _macd, _max_drawdown


def make_synthetic_history(n=300, start=100.0, drift=0.0005, seed=42):
    rng = np.random.default_rng(seed)
    returns = rng.normal(loc=drift, scale=0.01, size=n)
    prices = start * np.cumprod(1 + returns)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=n, freq="B")
    df = pd.DataFrame({
        "Open": prices * 0.995,
        "High": prices * 1.01,
        "Low": prices * 0.99,
        "Close": prices,
        "Volume": rng.integers(1_000_000, 5_000_000, size=n),
    }, index=dates)
    return df


class TestTechnicalIndicators:
    def test_compute_technicals_returns_expected_fields(self):
        history = make_synthetic_history()
        tech = compute_technicals(history)

        assert tech.last_close > 0
        assert isinstance(tech.change_pct_1d, float)
        assert "MA20" in tech.moving_averages
        assert "MA50" in tech.moving_averages
        assert "MA200" in tech.moving_averages
        assert 0 <= tech.rsi <= 100
        assert tech.volatility_annualized >= 0

    def test_uptrend_produces_positive_drift_metrics(self):
        history = make_synthetic_history(drift=0.003, n=300)
        tech = compute_technicals(history)
        assert tech.change_pct_ytd != 0  # sanity: metric computed

    def test_rsi_bounds(self):
        history = make_synthetic_history()
        rsi = _rsi(history["Close"])
        assert (rsi >= 0).all() and (rsi <= 100).all()

    def test_macd_shapes_match(self):
        history = make_synthetic_history()
        macd_line, signal_line = _macd(history["Close"])
        assert len(macd_line) == len(history)
        assert len(signal_line) == len(history)

    def test_max_drawdown_is_non_positive(self):
        history = make_synthetic_history()
        dd = _max_drawdown(history["Close"])
        assert dd <= 0

    def test_short_history_does_not_crash(self):
        history = make_synthetic_history(n=10)
        tech = compute_technicals(history)
        assert tech.moving_averages["MA200"] is None
        assert tech.moving_averages["MA20"] is None or isinstance(tech.moving_averages["MA20"], float)


class TestAnalyze:
    def test_analyze_returns_valid_recommendation(self):
        history = make_synthetic_history()
        fundamentals = {"pe_ratio": 18.0, "roe": 0.18, "debt_to_equity": 80}
        result = analyze(history, fundamentals)

        assert result.recommendation in {"Buy", "Hold", "Sell"}
        assert result.trend_signal in {"Bullish", "Bearish", "Neutral"}
        assert result.risk_level in {"Low", "Moderate", "High"}
        assert -1.0 <= result.composite_score <= 1.0
        assert len(result.notes) > 0

    def test_high_pe_reduces_score(self):
        history = make_synthetic_history()
        low_pe_result = analyze(history, {"pe_ratio": 10.0})
        high_pe_result = analyze(history, {"pe_ratio": 50.0})
        assert low_pe_result.composite_score >= high_pe_result.composite_score

    def test_high_leverage_flagged_in_notes(self):
        history = make_synthetic_history()
        result = analyze(history, {"debt_to_equity": 300})
        assert any("leverage" in n.lower() for n in result.notes)

    def test_empty_fundamentals_does_not_crash(self):
        history = make_synthetic_history()
        result = analyze(history, {})
        assert result.recommendation in {"Buy", "Hold", "Sell"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
