"""
main.py
--------
Command-line entry point for the AI-Powered Automated Stock Report
Generation System.

Usage:
    python main.py --ticker AAPL --format pdf
    python main.py --tickers AAPL,MSFT,HDFCBANK.NS --format html
"""
import argparse
import sys

from src.data_fetcher import fetch_stock_data, DataFetchError
from src.analysis import analyze
from src.ai_summary import generate_narrative
from src.report_generator import save_report
import config


def generate_report_for_ticker(ticker: str, fmt: str) -> str:
    print(f"[1/4] Fetching market data for {ticker}...")
    stock = fetch_stock_data(ticker)

    print(f"[2/4] Running quantitative analysis...")
    analysis = analyze(stock.history, stock.fundamentals)

    print(f"[3/4] Generating AI narrative "
          f"({'LLM' if config.USE_AI_NARRATIVE else 'rule-based fallback'})...")
    narrative = generate_narrative(stock, analysis)

    print(f"[4/4] Building {fmt} report...")
    path = save_report(stock, analysis, narrative, fmt=fmt)
    print(f"✅ Report saved: {path}\n")
    return path


def main():
    parser = argparse.ArgumentParser(
        description="AI-Powered Automated Stock Report Generation System for Banking Industry"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", help="Single stock ticker, e.g. AAPL")
    group.add_argument("--tickers", help="Comma-separated tickers, e.g. AAPL,MSFT,HDFCBANK.NS")
    parser.add_argument(
        "--format", choices=config.SUPPORTED_FORMATS, default="markdown",
        help="Output report format (default: markdown)"
    )
    args = parser.parse_args()

    tickers = [args.ticker] if args.ticker else [t.strip() for t in args.tickers.split(",")]

    generated = []
    for ticker in tickers:
        try:
            generated.append(generate_report_for_ticker(ticker, args.format))
        except DataFetchError as e:
            print(f"❌ Failed for {ticker}: {e}")

    if not generated:
        sys.exit(1)


if __name__ == "__main__":
    main()
