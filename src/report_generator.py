"""
report_generator.py
---------------------
Renders the final stock report in Markdown, HTML (with interactive Chart.js
charts), and PDF (with embedded matplotlib charts) formats.
"""
import base64
import io
import json
import os
from datetime import datetime

import config
from src.analysis import AnalysisResult
from src.data_fetcher import StockData


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(value, suffix=""):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}{suffix}"
    return f"{value}{suffix}"


def _history_to_json(stock: StockData, analysis: AnalysisResult) -> dict:
    """Serialize price history + computed MAs into JSON for Chart.js."""
    import pandas as pd

    h = stock.history.copy()
    h.index = h.index.strftime("%Y-%m-%d")
    labels = h.index.tolist()
    close  = [round(float(v), 2) for v in h["Close"]]
    volume = [int(v) for v in h["Volume"]]

    # Pre-compute MAs from the close series (already available via technicals
    # but we need the full rolling series for the chart)
    close_s = h["Close"]
    mas = {}
    for w in config.MOVING_AVERAGE_WINDOWS:
        if len(close_s) >= w:
            rolled = close_s.rolling(w).mean()
            mas[f"MA{w}"] = [
                None if pd.isna(v) else round(float(v), 2) for v in rolled
            ]

    # RSI
    delta = close_s.diff()
    gain  = delta.clip(lower=0).rolling(config.RSI_WINDOW).mean()
    loss  = (-delta.clip(upper=0)).rolling(config.RSI_WINDOW).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi_s = (100 - 100 / (1 + rs)).fillna(50)
    rsi   = [round(float(v), 2) for v in rsi_s]

    # MACD
    ema12    = close_s.ewm(span=12, adjust=False).mean()
    ema26    = close_s.ewm(span=26, adjust=False).mean()
    macd_s   = ema12 - ema26
    signal_s = macd_s.ewm(span=9, adjust=False).mean()
    macd_hist = macd_s - signal_s
    macd     = [round(float(v), 2) for v in macd_s]
    signal   = [round(float(v), 2) for v in signal_s]
    hist     = [round(float(v), 2) for v in macd_hist]

    return dict(
        labels=labels, close=close, volume=volume,
        mas=mas, rsi=rsi, macd=macd, signal=signal, hist=hist
    )


# ---------------------------------------------------------------------------
# Markdown (plain)
# ---------------------------------------------------------------------------

def build_markdown(stock: StockData, analysis: AnalysisResult, narrative: str) -> str:
    tech = analysis.technicals
    f    = stock.fundamentals
    now  = datetime.now().strftime("%Y-%m-%d %H:%M")
    ma_lines = "\n".join(f"| {k} | {_fmt(v)} |" for k, v in tech.moving_averages.items())

    return f"""# Stock Analysis Report — {stock.company_name} ({stock.ticker})

**Prepared by:** {config.REPORT_PREPARED_BY}  
**Generated on:** {now}  
**Sector / Industry:** {stock.sector} / {stock.industry}

---

## 1. Executive Summary

| Metric | Value |
|---|---|
| Last Close | {_fmt(tech.last_close)} {stock.currency} |
| 1-Day Change | {_fmt(tech.change_pct_1d, '%')} |
| 1-Month Change | {_fmt(tech.change_pct_1m, '%')} |
| YTD Change | {_fmt(tech.change_pct_ytd, '%')} |
| Trend Signal | **{analysis.trend_signal}** |
| Risk Level | **{analysis.risk_level}** |
| Composite Score | {analysis.composite_score} |
| **Recommendation** | **{analysis.recommendation}** |

---

## 2. Technical Analysis

| Indicator | Value |
|---|---|
{ma_lines}
| RSI (14) | {_fmt(tech.rsi)} |
| MACD | {_fmt(tech.macd)} |
| MACD Signal | {_fmt(tech.macd_signal)} |
| Annualized Volatility | {_fmt(tech.volatility_annualized, '%')} |
| Sharpe Ratio | {_fmt(tech.sharpe_ratio)} |
| Max Drawdown | {_fmt(tech.max_drawdown_pct, '%')} |

---

## 3. Fundamental Snapshot

| Metric | Value |
|---|---|
| Market Cap | {_fmt(f.get('market_cap'))} |
| P/E Ratio (TTM) | {_fmt(f.get('pe_ratio'))} |
| Forward P/E | {_fmt(f.get('forward_pe'))} |
| P/B Ratio | {_fmt(f.get('pb_ratio'))} |
| EPS (TTM) | {_fmt(f.get('eps'))} |
| Return on Equity | {_fmt(f.get('roe'))} |
| Debt to Equity | {_fmt(f.get('debt_to_equity'))} |
| Profit Margin | {_fmt(f.get('profit_margin'))} |
| Dividend Yield | {_fmt(f.get('dividend_yield'))} |
| Beta | {_fmt(f.get('beta'))} |
| 52-Week High / Low | {_fmt(f.get('fifty_two_week_high'))} / {_fmt(f.get('fifty_two_week_low'))} |
| Analyst Target Price | {_fmt(f.get('analyst_target_price'))} |

---

## 4. AI-Generated Analyst Commentary

{narrative}

---

## 5. Rule-Based Signal Notes

{chr(10).join(f"- {n}" for n in analysis.notes)}

---

## 6. Disclaimer

> {config.DISCLAIMER}
"""


# ---------------------------------------------------------------------------
# HTML  (interactive Chart.js charts)
# ---------------------------------------------------------------------------

_CHART_JS_SCRIPT = """
<script>
const D = {chartData};

// ── helpers ──────────────────────────────────────────────────────────────
function makeGrad(ctx, c1, c2) {
  const g = ctx.createLinearGradient(0, 0, 0, 300);
  g.addColorStop(0, c1); g.addColorStop(1, c2); return g;
}
Chart.defaults.font.family = "Inter, Arial, sans-serif";
Chart.defaults.font.size   = 11;

// ── 1. Price + Volume + MAs ───────────────────────────────────────────────
(function() {
  const ctx = document.getElementById("priceChart").getContext("2d");
  const maCols = { MA20:"#f39c12", MA50:"#8e44ad", MA200:"#27ae60" };
  const maSets = Object.entries(D.mas).map(([k,v]) => ({
    label: k, data: v, borderColor: maCols[k] || "#999",
    borderWidth: 1.5, pointRadius: 0, tension: 0.3, yAxisID: "yPrice"
  }));
  new Chart(ctx, {
    data: {
      labels: D.labels,
      datasets: [
        { type:"bar",  label:"Volume", data: D.volume,
          backgroundColor:"rgba(108,92,231,0.18)", yAxisID:"yVol",
          order: 2 },
        { type:"line", label:"Close",  data: D.close,
          borderColor:"#6c5ce7", borderWidth: 2, pointRadius: 0,
          tension: 0.2, yAxisID:"yPrice", order: 1,
          fill: true,
          backgroundColor: (ctx2) => makeGrad(ctx2.chart.ctx,
            "rgba(108,92,231,0.25)", "rgba(108,92,231,0)") },
        ...maSets.map(s => ({...s, type:"line", order:1}))
      ]
    },
    options: {
      responsive: true, interaction:{ mode:"index", intersect:false },
      plugins:{ legend:{ position:"top" },
        tooltip:{ callbacks:{ label: ctx3 =>
          ` ${ctx3.dataset.label}: ${Number(ctx3.raw).toLocaleString()}` }}},
      scales:{
        yPrice:{ position:"left",  grid:{ color:"#f0f0f0" } },
        yVol:  { position:"right", grid:{ display:false },
                 ticks:{ callback: v => (v/1e6).toFixed(1)+"M" } },
        x:{ ticks:{ maxTicksLimit:12, maxRotation:0 },
            grid:{ display:false } }
      }
    }
  });
})();

// ── 2. RSI ────────────────────────────────────────────────────────────────
(function() {
  const ctx = document.getElementById("rsiChart").getContext("2d");
  new Chart(ctx, {
    type:"line",
    data:{ labels: D.labels, datasets:[{
      label:"RSI (14)", data: D.rsi,
      borderColor:"#e17055", borderWidth:1.8, pointRadius:0, tension:0.3,
      fill:false
    }]},
    options:{
      responsive:true,
      plugins:{ legend:{ position:"top" },
        annotation:{
          annotations:{
            ob:{ type:"line", yMin:70, yMax:70, borderColor:"red",
                 borderWidth:1, borderDash:[4,4],
                 label:{ content:"Overbought (70)", enabled:true, position:"end",
                         font:{size:9} } },
            os:{ type:"line", yMin:30, yMax:30, borderColor:"green",
                 borderWidth:1, borderDash:[4,4],
                 label:{ content:"Oversold (30)", enabled:true, position:"end",
                         font:{size:9} } }
          }
        }
      },
      scales:{
        y:{ min:0, max:100, grid:{ color:"#f0f0f0" },
            ticks:{ stepSize:10 } },
        x:{ ticks:{ maxTicksLimit:12, maxRotation:0 },
            grid:{ display:false } }
      }
    }
  });
})();

// ── 3. MACD ───────────────────────────────────────────────────────────────
(function() {
  const ctx = document.getElementById("macdChart").getContext("2d");
  new Chart(ctx, {
    data:{
      labels: D.labels,
      datasets:[
        { type:"bar",  label:"Histogram", data: D.hist,
          backgroundColor: D.hist.map(v => v >= 0 ? "rgba(39,174,96,0.5)"
                                                   : "rgba(231,76,60,0.5)"),
          order:2 },
        { type:"line", label:"MACD",   data: D.macd,
          borderColor:"#2980b9", borderWidth:1.8, pointRadius:0,
          tension:0.3, fill:false, order:1 },
        { type:"line", label:"Signal", data: D.signal,
          borderColor:"#e67e22", borderWidth:1.8, pointRadius:0,
          tension:0.3, fill:false, order:1 }
      ]
    },
    options:{
      responsive:true, interaction:{ mode:"index", intersect:false },
      plugins:{ legend:{ position:"top" } },
      scales:{
        y:{ grid:{ color:"#f0f0f0" } },
        x:{ ticks:{ maxTicksLimit:12, maxRotation:0 },
            grid:{ display:false } }
      }
    }
  });
})();

// ── 4. Fundamentals radar ─────────────────────────────────────────────────
(function() {
  const el = document.getElementById("radarChart");
  if (!el) return;
  const raw = JSON.parse(el.dataset.values);
  const ctx = el.getContext("2d");
  new Chart(ctx, {
    type:"radar",
    data:{
      labels: raw.labels,
      datasets:[{
        label:"Score (0–10)", data: raw.scores,
        backgroundColor:"rgba(108,92,231,0.2)",
        borderColor:"#6c5ce7", borderWidth:2, pointRadius:4,
        pointBackgroundColor:"#6c5ce7"
      }]
    },
    options:{
      responsive:true,
      plugins:{ legend:{ position:"top" } },
      scales:{ r:{ min:0, max:10, ticks:{ stepSize:2 } } }
    }
  });
})();
</script>
"""


def _fundamentals_radar(fundamentals: dict) -> dict:
    """
    Normalise a handful of fundamental metrics to a 0–10 scale for the radar.
    Returns {labels, scores} dict.
    """
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))

    items = [
        ("P/E Ratio",     fundamentals.get("pe_ratio"),     lambda v: 10 - clamp((v - 5) / 5, 0, 10)),
        ("ROE",           fundamentals.get("roe"),           lambda v: clamp(v * 50, 0, 10)),
        ("Profit Margin", fundamentals.get("profit_margin"), lambda v: clamp(v * 40, 0, 10)),
        ("Div Yield",     fundamentals.get("dividend_yield"),lambda v: clamp(v * 200, 0, 10)),
        ("Beta (inv)",    fundamentals.get("beta"),          lambda v: clamp(10 - v * 3, 0, 10)),
        ("D/E (inv)",     fundamentals.get("debt_to_equity"),lambda v: clamp(10 - v / 30, 0, 10)),
    ]

    labels, scores = [], []
    for label, val, fn in items:
        labels.append(label)
        scores.append(round(fn(val), 1) if val is not None else 5.0)

    return {"labels": labels, "scores": scores}


def build_html(stock: StockData, analysis: AnalysisResult,
               markdown_text: str, narrative: str) -> str:
    import markdown2

    body   = markdown2.markdown(markdown_text, extras=["tables", "fenced-code-blocks"])
    cdata  = json.dumps(_history_to_json(stock, analysis))
    radar  = json.dumps(_fundamentals_radar(stock.fundamentals))
    script = _CHART_JS_SCRIPT.replace("{chartData}", cdata)
    rec_color = {"Buy": "#27ae60", "Hold": "#f39c12", "Sell": "#e74c3c"}.get(
        analysis.recommendation, "#6c5ce7"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{stock.company_name} ({stock.ticker}) — Stock Report</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3.0.1/dist/chartjs-plugin-annotation.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: Inter, "Segoe UI", Arial, sans-serif;
    background: #f4f6fb;
    color: #1a1a2e;
    line-height: 1.65;
  }}
  .header {{
    background: linear-gradient(135deg, #2d1b69 0%, #6c5ce7 100%);
    color: #fff;
    padding: 32px 40px 28px;
  }}
  .header h1 {{ font-size: 1.6rem; font-weight: 700; }}
  .header .sub {{ opacity: .8; font-size: .9rem; margin-top: 4px; }}
  .badge {{
    display: inline-block;
    background: {rec_color};
    color: #fff;
    font-size: 1rem;
    font-weight: 700;
    padding: 6px 20px;
    border-radius: 20px;
    margin-top: 12px;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 30px 24px 60px; }}
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    gap: 14px;
    margin-bottom: 32px;
  }}
  .kpi {{
    background: #fff;
    border-radius: 12px;
    padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(0,0,0,.07);
  }}
  .kpi .label {{ font-size: .75rem; color: #888; text-transform: uppercase; letter-spacing: .04em; }}
  .kpi .value {{ font-size: 1.25rem; font-weight: 700; margin-top: 4px; }}
  .kpi .value.up   {{ color: #27ae60; }}
  .kpi .value.down {{ color: #e74c3c; }}
  .card {{
    background: #fff;
    border-radius: 14px;
    padding: 24px 28px;
    box-shadow: 0 2px 10px rgba(0,0,0,.07);
    margin-bottom: 28px;
  }}
  .card h2 {{
    font-size: 1.05rem;
    font-weight: 700;
    color: #2d1b69;
    border-left: 4px solid #6c5ce7;
    padding-left: 10px;
    margin-bottom: 18px;
  }}
  .chart-wrap {{ position: relative; height: 240px; }}
  .chart-wrap.tall {{ height: 160px; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  @media(max-width:700px) {{ .chart-grid {{ grid-template-columns: 1fr; }} }}
  table {{ width: 100%; border-collapse: collapse; font-size: .9rem; }}
  th, td {{ padding: 9px 14px; text-align: left; border-bottom: 1px solid #eee; }}
  th {{ background: #f5f3ff; color: #2d1b69; font-weight: 600; }}
  tr:hover td {{ background: #faf9ff; }}
  .narrative {{ font-size: .95rem; line-height: 1.8; color: #333; }}
  .narrative p {{ margin-bottom: 1em; }}
  .notes li {{ margin: 6px 0; font-size: .9rem; color: #444; }}
  .disclaimer {{
    font-size: .78rem;
    color: #888;
    background: #fff8e1;
    border-left: 4px solid #ffc107;
    padding: 12px 16px;
    border-radius: 6px;
    margin-top: 8px;
  }}
  .pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: .8rem;
    font-weight: 600;
  }}
  .pill.bull {{ background:#d4efdf; color:#1e8449; }}
  .pill.bear {{ background:#fadbd8; color:#922b21; }}
  .pill.neut {{ background:#fdebd0; color:#935116; }}
</style>
</head>
<body>

<div class="header">
  <h1>📊 {stock.company_name} <span style="opacity:.7">({stock.ticker})</span></h1>
  <div class="sub">{stock.sector} &nbsp;·&nbsp; {stock.industry} &nbsp;·&nbsp; Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
  <div class="badge">{'⬆' if analysis.recommendation=='Buy' else '⬇' if analysis.recommendation=='Sell' else '➡'} &nbsp;{analysis.recommendation}</div>
</div>

<div class="container">

  <!-- KPI strip -->
  <div class="kpi-grid">
    <div class="kpi">
      <div class="label">Last Close</div>
      <div class="value">{_fmt(analysis.technicals.last_close)} {stock.currency}</div>
    </div>
    <div class="kpi">
      <div class="label">1-Day Change</div>
      <div class="value {'up' if analysis.technicals.change_pct_1d>=0 else 'down'}">{analysis.technicals.change_pct_1d:+.2f}%</div>
    </div>
    <div class="kpi">
      <div class="label">1-Month Change</div>
      <div class="value {'up' if analysis.technicals.change_pct_1m>=0 else 'down'}">{analysis.technicals.change_pct_1m:+.2f}%</div>
    </div>
    <div class="kpi">
      <div class="label">YTD Return</div>
      <div class="value {'up' if analysis.technicals.change_pct_ytd>=0 else 'down'}">{analysis.technicals.change_pct_ytd:+.2f}%</div>
    </div>
    <div class="kpi">
      <div class="label">RSI (14)</div>
      <div class="value">{analysis.technicals.rsi}</div>
    </div>
    <div class="kpi">
      <div class="label">Volatility (ann.)</div>
      <div class="value">{analysis.technicals.volatility_annualized}%</div>
    </div>
    <div class="kpi">
      <div class="label">Sharpe Ratio</div>
      <div class="value">{analysis.technicals.sharpe_ratio}</div>
    </div>
    <div class="kpi">
      <div class="label">Max Drawdown</div>
      <div class="value down">{analysis.technicals.max_drawdown_pct}%</div>
    </div>
    <div class="kpi">
      <div class="label">Trend Signal</div>
      <div class="value">
        <span class="pill {'bull' if analysis.trend_signal=='Bullish' else 'bear' if analysis.trend_signal=='Bearish' else 'neut'}">{analysis.trend_signal}</span>
      </div>
    </div>
    <div class="kpi">
      <div class="label">Risk Level</div>
      <div class="value">{analysis.risk_level}</div>
    </div>
  </div>

  <!-- Price + Volume chart -->
  <div class="card">
    <h2>Price History &amp; Moving Averages</h2>
    <div class="chart-wrap"><canvas id="priceChart"></canvas></div>
  </div>

  <!-- RSI + MACD -->
  <div class="chart-grid">
    <div class="card">
      <h2>RSI (14)</h2>
      <div class="chart-wrap tall"><canvas id="rsiChart"></canvas></div>
    </div>
    <div class="card">
      <h2>MACD (12/26/9)</h2>
      <div class="chart-wrap tall"><canvas id="macdChart"></canvas></div>
    </div>
  </div>

  <!-- Fundamentals table + radar -->
  <div class="chart-grid">
    <div class="card">
      <h2>Fundamental Snapshot</h2>
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Market Cap</td><td>{_fmt(stock.fundamentals.get('market_cap'))}</td></tr>
        <tr><td>P/E (TTM)</td><td>{_fmt(stock.fundamentals.get('pe_ratio'))}</td></tr>
        <tr><td>Forward P/E</td><td>{_fmt(stock.fundamentals.get('forward_pe'))}</td></tr>
        <tr><td>P/B Ratio</td><td>{_fmt(stock.fundamentals.get('pb_ratio'))}</td></tr>
        <tr><td>EPS (TTM)</td><td>{_fmt(stock.fundamentals.get('eps'))}</td></tr>
        <tr><td>ROE</td><td>{_fmt(stock.fundamentals.get('roe'))}</td></tr>
        <tr><td>Debt / Equity</td><td>{_fmt(stock.fundamentals.get('debt_to_equity'))}</td></tr>
        <tr><td>Profit Margin</td><td>{_fmt(stock.fundamentals.get('profit_margin'))}</td></tr>
        <tr><td>Dividend Yield</td><td>{_fmt(stock.fundamentals.get('dividend_yield'))}</td></tr>
        <tr><td>Beta</td><td>{_fmt(stock.fundamentals.get('beta'))}</td></tr>
        <tr><td>52-Wk High</td><td>{_fmt(stock.fundamentals.get('fifty_two_week_high'))}</td></tr>
        <tr><td>52-Wk Low</td><td>{_fmt(stock.fundamentals.get('fifty_two_week_low'))}</td></tr>
        <tr><td>Analyst Target</td><td>{_fmt(stock.fundamentals.get('analyst_target_price'))}</td></tr>
      </table>
    </div>
    <div class="card">
      <h2>Fundamentals Scorecard</h2>
      <div class="chart-wrap" style="height:280px">
        <canvas id="radarChart" data-values='{radar}'></canvas>
      </div>
    </div>
  </div>

  <!-- AI narrative -->
  <div class="card">
    <h2>AI-Generated Analyst Commentary</h2>
    <div class="narrative">
      {''.join(f"<p>{p.strip()}</p>" for p in narrative.split(chr(10)+chr(10)) if p.strip())}
    </div>
  </div>

  <!-- Signal notes -->
  <div class="card">
    <h2>Rule-Based Signal Notes</h2>
    <ul class="notes">
      {''.join(f"<li>{n}</li>" for n in analysis.notes)}
    </ul>
  </div>

  <!-- Disclaimer -->
  <div class="disclaimer">{config.DISCLAIMER}</div>

</div>

{script}
</body>
</html>"""


# ---------------------------------------------------------------------------
# PDF  (matplotlib charts embedded as base64 PNGs → xhtml2pdf)
# ---------------------------------------------------------------------------

def _matplotlib_charts_b64(stock: StockData, analysis: AnalysisResult) -> str:
    """
    Render a 4-panel matplotlib figure and return an <img> tag with the
    chart embedded as a base64 PNG — no temp files, no system dependencies.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    import pandas as pd
    import numpy as np

    h      = stock.history.copy()
    close  = h["Close"]
    volume = h["Volume"]
    dates  = h.index

    # Moving averages
    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    # RSI
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(config.RSI_WINDOW).mean()
    loss  = (-delta.clip(upper=0)).rolling(config.RSI_WINDOW).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = (100 - 100 / (1 + rs)).fillna(50)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist   = macd_line - signal_line

    fig = plt.figure(figsize=(14, 10), facecolor="#ffffff")
    fig.suptitle(
        f"{stock.company_name} ({stock.ticker}) — Technical Analysis",
        fontsize=14, fontweight="bold", color="#2d1b69", y=0.98
    )
    gs = gridspec.GridSpec(4, 1, figure=fig, height_ratios=[3, 1, 1.2, 1.2],
                           hspace=0.06)

    purple = "#6c5ce7"
    green  = "#27ae60"
    red    = "#e74c3c"

    # Panel 1: Price + MAs
    ax1 = fig.add_subplot(gs[0])
    ax1.plot(dates, close,  color=purple, linewidth=1.8, label="Close", zorder=3)
    ax1.plot(dates, ma20,   color="#f39c12", linewidth=1.2, linestyle="--", label="MA20")
    ax1.plot(dates, ma50,   color="#8e44ad", linewidth=1.2, linestyle="--", label="MA50")
    ax1.plot(dates, ma200,  color=green,     linewidth=1.2, linestyle="--", label="MA200")
    ax1.fill_between(dates, close, close.min(), alpha=0.08, color=purple)
    ax1.set_ylabel("Price", fontsize=9, color="#555")
    ax1.legend(loc="upper left", fontsize=8, framealpha=0.7)
    ax1.set_facecolor("#fafafa")
    ax1.grid(axis="y", color="#eeeeee", linewidth=0.8)
    ax1.tick_params(labelbottom=False, labelsize=8)
    ax1.set_title(f"Recommendation: {analysis.recommendation}  |  "
                  f"Signal: {analysis.trend_signal}  |  "
                  f"Risk: {analysis.risk_level}",
                  fontsize=9, loc="right", color="#555")

    # Panel 2: Volume
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    colors = [green if c >= o else red
              for c, o in zip(h["Close"], h["Open"])]
    ax2.bar(dates, volume, color=colors, width=0.8, alpha=0.7)
    ax2.set_ylabel("Volume", fontsize=9, color="#555")
    ax2.yaxis.set_major_formatter(
        matplotlib.ticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M"))
    ax2.set_facecolor("#fafafa")
    ax2.grid(axis="y", color="#eeeeee", linewidth=0.8)
    ax2.tick_params(labelbottom=False, labelsize=8)

    # Panel 3: RSI
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    ax3.plot(dates, rsi, color="#e17055", linewidth=1.5, label="RSI(14)")
    ax3.axhline(70, color=red,   linewidth=0.9, linestyle="--", alpha=0.7)
    ax3.axhline(30, color=green, linewidth=0.9, linestyle="--", alpha=0.7)
    ax3.fill_between(dates, rsi, 70, where=(rsi >= 70), alpha=0.15, color=red)
    ax3.fill_between(dates, rsi, 30, where=(rsi <= 30), alpha=0.15, color=green)
    ax3.set_ylim(0, 100)
    ax3.set_ylabel("RSI", fontsize=9, color="#555")
    ax3.text(dates[-1], 72, "OB", fontsize=7, color=red,   ha="right")
    ax3.text(dates[-1], 22, "OS", fontsize=7, color=green, ha="right")
    ax3.set_facecolor("#fafafa")
    ax3.grid(axis="y", color="#eeeeee", linewidth=0.8)
    ax3.tick_params(labelbottom=False, labelsize=8)

    # Panel 4: MACD
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    ax4.bar(dates, macd_hist,
            color=[green if v >= 0 else red for v in macd_hist],
            width=0.8, alpha=0.6, label="Histogram")
    ax4.plot(dates, macd_line,   color="#2980b9", linewidth=1.5, label="MACD")
    ax4.plot(dates, signal_line, color="#e67e22", linewidth=1.5, label="Signal")
    ax4.axhline(0, color="#aaa", linewidth=0.7)
    ax4.set_ylabel("MACD", fontsize=9, color="#555")
    ax4.legend(loc="upper left", fontsize=8, framealpha=0.7)
    ax4.set_facecolor("#fafafa")
    ax4.grid(axis="y", color="#eeeeee", linewidth=0.8)
    ax4.tick_params(labelsize=8)

    plt.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def build_pdf_html(stock: StockData, analysis: AnalysisResult,
                   markdown_text: str, narrative: str) -> str:
    """
    Lightweight HTML variant for xhtml2pdf (no JS, charts as embedded PNGs).
    """
    import markdown2

    body   = markdown2.markdown(markdown_text, extras=["tables", "fenced-code-blocks"])
    chart  = _matplotlib_charts_b64(stock, analysis)
    rec_color = {"Buy": "#27ae60", "Hold": "#f39c12", "Sell": "#e74c3c"}.get(
        analysis.recommendation, "#6c5ce7"
    )

    return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8">
<style>
  body {{ font-family: Arial, sans-serif; color: #1a1a2e; font-size: 11pt; line-height: 1.5; }}
  h1 {{ color: #2d1b69; font-size: 16pt; border-bottom: 2pt solid #6c5ce7; padding-bottom: 6pt; }}
  h2 {{ color: #2d1b69; font-size: 12pt; margin-top: 18pt; }}
  table {{ width: 100%; border-collapse: collapse; margin: 10pt 0; font-size: 9.5pt; }}
  th, td {{ border: 1pt solid #ddd; padding: 5pt 8pt; text-align: left; }}
  th {{ background: #6c5ce7; color: #fff; }}
  tr:nth-child(even) td {{ background: #f5f3ff; }}
  .badge {{
    display: inline-block; padding: 4pt 16pt;
    background: {rec_color}; color: #fff;
    border-radius: 12pt; font-weight: bold; font-size: 12pt;
  }}
  .chart-img {{ width: 100%; margin: 12pt 0; }}
  blockquote {{ background: #fff8e1; border-left: 4pt solid #ffc107;
               padding: 8pt 12pt; font-size: 9pt; color: #666; }}
</style>
</head><body>
<h1>{stock.company_name} ({stock.ticker}) — Stock Report</h1>
<p><strong>Prepared by:</strong> {config.REPORT_PREPARED_BY}<br>
   <strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
   <strong>Sector / Industry:</strong> {stock.sector} / {stock.industry}<br>
   <strong>Recommendation:</strong> <span class="badge">{analysis.recommendation}</span>
</p>

<img class="chart-img" src="data:image/png;base64,{chart}" />

{body}
</body></html>"""


# ---------------------------------------------------------------------------
# save_report  (public API)
# ---------------------------------------------------------------------------

def save_report(stock: StockData, analysis: AnalysisResult,
                narrative: str, fmt: str = "markdown") -> str:

    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    base      = f"{stock.ticker}_report_{ts}"
    md_text   = build_markdown(stock, analysis, narrative)

    if fmt == "markdown":
        path = os.path.join(config.OUTPUT_DIR, f"{base}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(md_text)
        return path

    if fmt == "html":
        path = os.path.join(config.OUTPUT_DIR, f"{base}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(build_html(stock, analysis, md_text, narrative))
        return path

    if fmt == "pdf":
        from xhtml2pdf import pisa

        path     = os.path.join(config.OUTPUT_DIR, f"{base}.pdf")
        html_src = build_pdf_html(stock, analysis, md_text, narrative)
        with open(path, "wb") as fh:
            result = pisa.CreatePDF(html_src, dest=fh)
        if result.err:
            raise RuntimeError(f"PDF generation failed with {result.err} error(s).")
        return path

    raise ValueError(f"Unsupported format '{fmt}'. Choose from {config.SUPPORTED_FORMATS}.")
