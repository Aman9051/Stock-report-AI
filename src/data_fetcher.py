"""
data_fetcher.py
----------------
Handles retrieval of market price history and fundamental data for a given
stock ticker. Wraps yfinance and normalizes the output into simple,
serializable Python structures used downstream by the analysis engine.
"""
from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

try:
    import yfinance as yf
except ImportError:  # pragma: no cover
    yf = None

import config


@dataclass
class StockData:
    ticker: str
    company_name: str
    sector: str
    industry: str
    currency: str
    history: pd.DataFrame
    fundamentals: dict = field(default_factory=dict)


class DataFetchError(Exception):
    """Raised when market data cannot be retrieved for a ticker."""


def fetch_stock_data(ticker: str, period: str = None) -> StockData:
    """
    Fetch price history and fundamental info for `ticker`.

    Parameters
    ----------
    ticker : str
        Stock ticker symbol (e.g. "AAPL", "HDFCBANK.NS").
    period : str, optional
        yfinance period string (e.g. "6mo", "1y", "5y"). Defaults to
        config.PRICE_HISTORY_PERIOD.

    Returns
    -------
    StockData
    """
    if yf is None:
        raise DataFetchError(
            "yfinance is not installed. Run `pip install -r requirements.txt`."
        )

    period = period or config.PRICE_HISTORY_PERIOD
    t = yf.Ticker(ticker)

    history = t.history(period=period, auto_adjust=True)
    if history is None or history.empty:
        raise DataFetchError(f"No price history found for ticker '{ticker}'.")

    info = {}
    try:
        info = t.info or {}
    except Exception:
        # Some tickers / network conditions return partial/empty info; we
        # degrade gracefully rather than failing the whole report.
        info = {}

    fundamentals = {
        "market_cap": info.get("marketCap"),
        "pe_ratio": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb_ratio": info.get("priceToBook"),
        "dividend_yield": info.get("dividendYield"),
        "eps": info.get("trailingEps"),
        "roe": info.get("returnOnEquity"),
        "debt_to_equity": info.get("debtToEquity"),
        "profit_margin": info.get("profitMargins"),
        "revenue_growth": info.get("revenueGrowth"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "analyst_target_price": info.get("targetMeanPrice"),
        "recommendation_key": info.get("recommendationKey"),
    }

    return StockData(
        ticker=ticker.upper(),
        company_name=info.get("longName") or info.get("shortName") or ticker.upper(),
        sector=info.get("sector", "N/A"),
        industry=info.get("industry", "N/A"),
        currency=info.get("currency", "USD"),
        history=history,
        fundamentals=fundamentals,
    )


def fetch_multiple(tickers: list[str], period: Optional[str] = None) -> dict[str, StockData]:
    """Fetch data for multiple tickers, skipping (with a warning) any that fail."""
    results = {}
    for tk in tickers:
        try:
            results[tk] = fetch_stock_data(tk, period=period)
        except DataFetchError as e:
            print(f"[WARN] Skipping {tk}: {e}")
    return results
