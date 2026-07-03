"""
stock_search.py
----------------
Smart stock search using the Yahoo Finance autocomplete API.
Users type a company name (e.g. "Reliance", "HDFC Bank", "Apple") and
this module resolves the correct full ticker symbol including any exchange
suffix (.NS, .BO, .L, .T, .HK, etc.) automatically.
"""
from dataclasses import dataclass

import requests

# ── Yahoo Finance search endpoint ────────────────────────────────────────────
_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
_HEADERS     = {"User-Agent": "Mozilla/5.0 (compatible; StockReportBot/1.0)"}

# ── Human-readable exchange labels ────────────────────────────────────────────
_EXCHANGE_LABELS: dict[str, str] = {
    # USA
    "NMS": "NASDAQ", "NGM": "NASDAQ", "NCM": "NASDAQ",
    "NYQ": "NYSE",   "PCX": "NYSE Arca", "ASE": "NYSE American",
    # India
    "NSI": "NSE India", "BSE": "BSE India",
    # UK
    "LSE": "London SE",
    # Europe
    "FRA": "Frankfurt", "GER": "XETRA", "XETRA": "XETRA",
    "PAR": "Euronext Paris", "AMS": "Euronext Amsterdam",
    "MIL": "Milan", "MCE": "Madrid", "VIE": "Vienna",
    # Asia-Pacific
    "TYO": "Tokyo SE",   "OSA": "Osaka SE",
    "HKG": "Hong Kong",  "SES": "Singapore",
    "KSC": "Korea SE",   "KOE": "KOSDAQ",
    "SHH": "Shanghai",   "SHZ": "Shenzhen",
    "ASX": "ASX Australia",
    # Americas
    "TOR": "TSX Canada", "VAN": "TSX Venture",
    "SAO": "B3 Brazil",  "MXX": "BMV Mexico",
    # Middle East / Africa
    "TAE": "Tel Aviv SE", "JNB": "JSE South Africa",
    "DFM": "Dubai Financial Market",
}


@dataclass
class StockMatch:
    ticker:           str
    name:             str
    exchange_code:    str
    exchange_display: str
    instrument_type:  str   # "EQUITY" | "ETF" | …

    def label(self) -> str:
        """Dropdown display label shown to the user."""
        return f"{self.name}  ·  {self.ticker}  [{self.exchange_display}]"


def search_stocks(query: str, limit: int = 10) -> list[StockMatch]:
    """
    Search Yahoo Finance for stocks matching `query`.

    Parameters
    ----------
    query : str
        Company name or partial ticker — no suffix needed.
    limit : int
        Max number of results to return (default 10).

    Returns
    -------
    list[StockMatch]
        Ordered by Yahoo's relevance score; equities first.
    """
    query = query.strip()
    if not query:
        return []

    try:
        resp = requests.get(
            _SEARCH_URL,
            params={
                "q":           query,
                "lang":        "en-US",
                "region":      "US",
                "quotesCount": limit * 3,   # over-fetch so we can filter
                "newsCount":   0,
                "enableFuzzyQuery": False,
                "enableNavLinks":   False,
            },
            headers=_HEADERS,
            timeout=6,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []
    except Exception:
        return []

    results: list[StockMatch] = []
    seen:    set[str]         = set()

    for quote in data.get("quotes", []):
        qtype  = quote.get("quoteType", "")
        ticker = (quote.get("symbol") or "").strip()

        # Only equities and ETFs; skip crypto, indices, currencies, futures
        if qtype not in ("EQUITY", "ETF"):
            continue
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)

        exchange_code = quote.get("exchange") or ""
        exchange_disp = _EXCHANGE_LABELS.get(exchange_code, exchange_code or "N/A")
        name          = (
            quote.get("longname")
            or quote.get("shortname")
            or ticker
        )

        results.append(StockMatch(
            ticker=ticker,
            name=name,
            exchange_code=exchange_code,
            exchange_display=exchange_disp,
            instrument_type=qtype,
        ))

        if len(results) >= limit:
            break

    return results


def resolve_ticker(raw_input: str) -> str | None:
    """
    If `raw_input` looks like a direct ticker (short, all-caps, no spaces),
    return it as-is.  Otherwise search and return the top equity match's ticker.
    Returns None if nothing could be resolved.
    """
    raw = raw_input.strip()
    # Looks like a direct ticker (e.g. "AAPL", "RELIANCE.NS")
    if raw.isupper() and " " not in raw and len(raw) <= 15:
        return raw
    # Name search
    matches = search_stocks(raw, limit=1)
    return matches[0].ticker if matches else None
