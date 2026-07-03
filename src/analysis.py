"""
analysis.py
------------
Quantitative analysis engine: computes technical indicators, risk metrics,
and a rule-based composite signal from raw price history + fundamentals.

This module has zero dependency on any LLM/AI service so it can be unit
tested deterministically.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

import config


@dataclass
class TechnicalIndicators:
    last_close: float
    change_pct_1d: float
    change_pct_1m: float
    change_pct_ytd: float
    moving_averages: dict
    rsi: float
    macd: float
    macd_signal: float
    volatility_annualized: float
    sharpe_ratio: float
    max_drawdown_pct: float


@dataclass
class AnalysisResult:
    technicals: TechnicalIndicators
    trend_signal: str          # "Bullish" | "Bearish" | "Neutral"
    risk_level: str            # "Low" | "Moderate" | "High"
    composite_score: float     # -1.0 (strong sell) to +1.0 (strong buy)
    recommendation: str        # "Buy" | "Hold" | "Sell"
    notes: list = field(default_factory=list)


def _rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50)


def _macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line


def _max_drawdown(series: pd.Series) -> float:
    cumulative_max = series.cummax()
    drawdown = (series - cumulative_max) / cumulative_max
    return float(drawdown.min() * 100)


def compute_technicals(history: pd.DataFrame) -> TechnicalIndicators:
    close = history["Close"].dropna()

    last_close = float(close.iloc[-1])
    change_1d = float((close.iloc[-1] / close.iloc[-2] - 1) * 100) if len(close) > 1 else 0.0

    one_month_idx = max(0, len(close) - 21)
    change_1m = float((close.iloc[-1] / close.iloc[one_month_idx] - 1) * 100) if len(close) > one_month_idx else 0.0

    ytd_close = close[close.index.year == close.index[-1].year]
    change_ytd = float((close.iloc[-1] / ytd_close.iloc[0] - 1) * 100) if len(ytd_close) > 0 else 0.0

    moving_averages = {}
    for window in config.MOVING_AVERAGE_WINDOWS:
        if len(close) >= window:
            moving_averages[f"MA{window}"] = float(close.rolling(window).mean().iloc[-1])
        else:
            moving_averages[f"MA{window}"] = None

    rsi_series = _rsi(close, config.RSI_WINDOW)
    macd_line, signal_line = _macd(close)

    daily_returns = close.pct_change().dropna()
    volatility_annualized = float(daily_returns.std() * np.sqrt(252) * 100)

    mean_daily_return = daily_returns.mean() * 252
    sharpe = (
        (mean_daily_return - config.RISK_FREE_RATE) / (daily_returns.std() * np.sqrt(252))
        if daily_returns.std() > 0
        else 0.0
    )

    return TechnicalIndicators(
        last_close=round(last_close, 2),
        change_pct_1d=round(change_1d, 2),
        change_pct_1m=round(change_1m, 2),
        change_pct_ytd=round(change_ytd, 2),
        moving_averages={k: (round(v, 2) if v else None) for k, v in moving_averages.items()},
        rsi=round(float(rsi_series.iloc[-1]), 2),
        macd=round(float(macd_line.iloc[-1]), 4),
        macd_signal=round(float(signal_line.iloc[-1]), 4),
        volatility_annualized=round(volatility_annualized, 2),
        sharpe_ratio=round(float(sharpe), 2),
        max_drawdown_pct=round(_max_drawdown(close), 2),
    )


def analyze(history: pd.DataFrame, fundamentals: dict) -> AnalysisResult:
    """
    Run the full quantitative analysis pipeline and produce a composite
    signal + recommendation. Logic is intentionally transparent / rule-based
    so it is auditable for banking compliance purposes.
    """
    tech = compute_technicals(history)
    notes = []
    score = 0.0

    # --- Trend component (moving average crossover) -------------------
    ma20, ma50, ma200 = (
        tech.moving_averages.get("MA20"),
        tech.moving_averages.get("MA50"),
        tech.moving_averages.get("MA200"),
    )
    if ma20 and ma50:
        if ma20 > ma50:
            score += 0.25
            notes.append("Short-term MA(20) is above MA(50): bullish short-term trend.")
        else:
            score -= 0.25
            notes.append("Short-term MA(20) is below MA(50): bearish short-term trend.")
    if ma50 and ma200:
        if ma50 > ma200:
            score += 0.15
            notes.append("MA(50) above MA(200): broader uptrend (golden-cross territory).")
        else:
            score -= 0.15
            notes.append("MA(50) below MA(200): broader downtrend (death-cross territory).")

    # --- Momentum component (RSI) --------------------------------------
    if tech.rsi >= 70:
        score -= 0.2
        notes.append(f"RSI at {tech.rsi} indicates overbought conditions.")
    elif tech.rsi <= 30:
        score += 0.2
        notes.append(f"RSI at {tech.rsi} indicates oversold conditions (potential value entry).")
    else:
        notes.append(f"RSI at {tech.rsi} is within a neutral range.")

    # --- MACD component ---------------------------------------------------
    if tech.macd > tech.macd_signal:
        score += 0.15
        notes.append("MACD line above signal line: positive momentum.")
    else:
        score -= 0.15
        notes.append("MACD line below signal line: negative momentum.")

    # --- Fundamentals component ----------------------------------------
    pe = fundamentals.get("pe_ratio")
    if pe is not None:
        if pe < 15:
            score += 0.1
            notes.append(f"P/E ratio of {pe:.1f} suggests the stock may be undervalued relative to earnings.")
        elif pe > 35:
            score -= 0.1
            notes.append(f"P/E ratio of {pe:.1f} is elevated, suggesting a premium valuation.")

    roe = fundamentals.get("roe")
    if roe is not None and roe > 0.15:
        score += 0.1
        notes.append(f"Return on equity of {roe*100:.1f}% reflects strong capital efficiency.")

    debt_to_equity = fundamentals.get("debt_to_equity")
    if debt_to_equity is not None and debt_to_equity > 150:
        score -= 0.1
        notes.append(f"Debt-to-equity of {debt_to_equity:.0f}% indicates elevated leverage risk.")

    # --- Risk classification --------------------------------------------
    if tech.volatility_annualized < 20:
        risk_level = "Low"
    elif tech.volatility_annualized < 40:
        risk_level = "Moderate"
    else:
        risk_level = "High"

    score = max(-1.0, min(1.0, score))

    if score >= 0.25:
        trend_signal = "Bullish"
        recommendation = "Buy"
    elif score <= -0.25:
        trend_signal = "Bearish"
        recommendation = "Sell"
    else:
        trend_signal = "Neutral"
        recommendation = "Hold"

    return AnalysisResult(
        technicals=tech,
        trend_signal=trend_signal,
        risk_level=risk_level,
        composite_score=round(score, 2),
        recommendation=recommendation,
        notes=notes,
    )
