# 📊 AI-Powered Stock Report Generator

An end-to-end personal project that automatically generates professional stock analysis reports — complete with interactive charts, AI narrative, and one-click downloads — for any stock worldwide.

> **No ticker suffixes needed.** Type "Reliance" and get `RELIANCE.NS`. Type "HSBC" and get `HSBA.L`. The app resolves the correct exchange ticker automatically.

---

## ✨ Features

- **🔍 Smart Stock Search** — powered by Yahoo Finance autocomplete. Type a company name in any language; the app resolves the full ticker + exchange suffix automatically for every market worldwide.
- **📈 Interactive Plotly Charts** — price history + MA20/50/200 overlay with volume bars, RSI (14) with overbought/oversold bands, MACD (12/26/9) with histogram, fundamentals radar scorecard — all with hover tooltips, zoom, and pan.
- **🤖 AI Narrative** — Google Gemini generates a 3-paragraph professional analyst commentary (price action, risk assessment, outlook). Falls back to a deterministic rule-based generator when offline or without an API key.
- **📥 Multi-format Export** — PDF (matplotlib charts embedded, print-ready), HTML (Chart.js interactive, standalone), Markdown (plain text, version-control friendly).
- **🖥️ Streamlit Web UI** — clean, responsive browser app with dark sidebar and live progress indicators.
- **⌨️ CLI mode** — headless `main.py` for batch/scripted report generation.
- **🧪 Unit tested** analytics engine (10 tests, CI via GitHub Actions).

---

## 🏗️ System Architecture

```
User types company name
        │
        ▼
┌─────────────────────┐
│  stock_search.py    │  Yahoo Finance autocomplete API
│  Smart ticker       │  → resolves "Apple" → "AAPL"
│  resolution         │  → resolves "Reliance" → "RELIANCE.NS"
└────────┬────────────┘
         │  full ticker
         ▼
┌─────────────────────┐
│  data_fetcher.py    │  yfinance  →  StockData
│  Market data        │  (OHLCV history + fundamentals)
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  analysis.py        │  MA / RSI / MACD / Sharpe /
│  Quant engine       │  drawdown / composite score
└────────┬────────────┘
         ▼
┌─────────────────────┐
│  ai_summary.py      │  Google Gemini API
│  Narrative gen      │  (rule-based fallback)
└────────┬────────────┘
         ▼
┌─────────────────────┐        ┌──────────────────────────┐
│  report_generator   │        │  app.py  (Streamlit)     │
│  Markdown / HTML /  │◄───────│  Plotly charts live UI   │
│  PDF output         │        │  Download buttons        │
└─────────────────────┘        └──────────────────────────┘
```

---

## 📊 Charts & Visualisations

| Chart | Streamlit UI | HTML download | PDF download |
|---|---|---|---|
| Price history + MA 20/50/200 | ✅ Plotly interactive | ✅ Chart.js | ✅ matplotlib PNG |
| Volume bars (green/red per day) | ✅ Plotly | ✅ Chart.js | ✅ matplotlib PNG |
| RSI (14) with OB/OS bands | ✅ Plotly interactive | ✅ Chart.js | ✅ matplotlib PNG |
| MACD (12/26/9) + histogram | ✅ Plotly interactive | ✅ Chart.js | ✅ matplotlib PNG |
| Fundamentals radar scorecard | ✅ Plotly interactive | ✅ Chart.js | — |

All Streamlit charts support **hover tooltips, zoom, pan, and download as PNG**.

---

## 🌍 Global Stock Support

Type any company name — suffixes are resolved automatically:

| Country | Exchange | Auto-resolved suffix | Example |
|---|---|---|---|
| USA | NYSE / NASDAQ | *(none)* | `AAPL` |
| India | NSE | `.NS` | `RELIANCE.NS` |
| India | BSE | `.BO` | `RELIANCE.BO` |
| UK | London SE | `.L` | `HSBA.L` |
| Germany | XETRA | `.DE` | `VOW.DE` |
| Japan | Tokyo SE | `.T` | `7203.T` |
| Hong Kong | HKEX | `.HK` | `0700.HK` |
| Canada | TSX | `.TO` | `RY.TO` |
| Australia | ASX | `.AX` | `CBA.AX` |
| France | Euronext | `.PA` | `MC.PA` |
| Brazil | B3 | `.SA` | `PETR4.SA` |
| South Korea | KRX | `.KS` | `005930.KS` |

---

## 📁 Project Structure

```
stock-report-ai/
├── app.py                        # Streamlit web app (main entry point)
├── main.py                       # CLI entry point (batch / headless mode)
├── config.py                     # Env-driven configuration
├── requirements.txt
├── .env                          # Local secrets (git-ignored)
├── .env.example                  # Template — commit this
├── .streamlit/
│   └── config.toml               # Streamlit theme
├── src/
│   ├── stock_search.py           # Yahoo Finance autocomplete + ticker resolution
│   ├── data_fetcher.py           # yfinance market data retrieval
│   ├── analysis.py               # Technical + fundamental analysis engine
│   ├── ai_summary.py             # Google Gemini narrative (+ fallback)
│   └── report_generator.py       # Markdown / HTML (Chart.js) / PDF (matplotlib)
├── sample_output/
│   └── sample_report_AAPL.md
├── tests/
│   └── test_analysis.py
```

---

## 🚀 Getting Started

### 1. Clone & install

```bash
git clone https://github.com/<your-username>/stock-report-ai.git
cd stock-report-ai
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
GOOGLE_API_KEY=your_google_api_key_here
GEMINI_MODEL=gemini-3.1-flash-lite
```

Get a free key at [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey).
If the key is not set, the system uses a deterministic rule-based narrative generator automatically.

### 3a. Run the Streamlit web app (recommended)

```bash
streamlit run app.py
```

Opens at `http://localhost:8501` — search any stock, explore live charts, download reports.

### 3b. CLI / headless mode

```bash
# Single ticker
python main.py --ticker AAPL --format pdf

# Batch — auto-resolves all suffixes
python main.py --tickers AAPL,RELIANCE.NS,HDFCBANK.NS,TSLA --format html
```

---

## 🖥️ Streamlit App Walkthrough

```
┌─────────────────────┬───────────────────────────────────────────────┐
│  SIDEBAR (dark)     │  MAIN AREA                                    │
│                     │                                               │
│  📊 Stock Report AI │  [No stock]  Welcome screen + exchange table  │
│                     │                                               │
│  🔍 Search box      │  [Stock selected]                             │
│  [Search] [Clear]   │  ┌─ Header: company name, badges, score ─┐   │
│  ↓ results          │  └────────────────────────────────────────┘   │
│  [Selectbox]        │  KPI metrics (2 rows × 5 cards)               │
│  Exchange: NSE      │  ─────────────────────────────────────────    │
│                     │  Price + MA + Volume chart (full width)       │
│  ⚙️  Settings        │  ─────────────────────────────────────────    │
│  Period: 1y         │  RSI chart  │  MACD chart  (50/50)            │
│  AI: Gemini ✅      │  ─────────────────────────────────────────    │
│                     │  Fundamentals table  │  Radar scorecard       │
│  🚀 Generate Report │  ─────────────────────────────────────────    │
│                     │  AI Commentary (3 expandable sections)        │
│  ─────────────────  │  ─────────────────────────────────────────    │
│  📥 Download        │  Signal Notes (🟢 bullish / 🔴 cautionary)   │
│  📄 Markdown        │  ─────────────────────────────────────────    │
│  🌐 HTML            │  Disclaimer                                   │
│  📑 PDF             │                                               │
└─────────────────────┴───────────────────────────────────────────────┘
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v
```

Tests run against synthetic, seeded price data — no network access or API key required.

---

## 🧱 Tech Stack

| Layer | Technology |
|---|---|
| Web UI | Streamlit |
| Interactive charts (UI) | Plotly |
| Interactive charts (HTML export) | Chart.js 4 (CDN) |
| Embedded charts (PDF export) | matplotlib |
| Market data | yfinance |
| Quantitative analysis | pandas, numpy |
| AI narrative | Google Gemini (`google-genai`) |
| PDF generation | xhtml2pdf |
| Environment config | python-dotenv |
| Testing / CI | pytest, GitHub Actions |

---

## ⚠️ Disclaimer

This is a personal project for research and demonstration purposes. Generated reports are not investment advice and should be reviewed by a qualified professional before any decision-making use.

---

## 📜 License

MIT License — see [LICENSE](LICENSE).
