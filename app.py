"""
app.py
-------
Streamlit front-end for the AI-Powered Stock Report Generation System.

Run with:
    streamlit run app.py
"""

import io

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

# ── Page config — must be the very first Streamlit call ──────────────────────
st.set_page_config(
    page_title="AI Stock Report Generator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Project imports ───────────────────────────────────────────────────────────
import config
from src.ai_summary import generate_narrative
from src.analysis import analyze
from src.data_fetcher import DataFetchError, fetch_stock_data
from src.report_generator import build_html, build_markdown, build_pdf_html
from src.stock_search import search_stocks

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Sidebar */
[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stSelectbox label,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span { color: #c8c8e8 !important; }
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3   { color: #ffffff !important; }

/* Metric cards */
[data-testid="stMetric"] {
    background: #f8f7ff;
    border: 1px solid #e8e4ff;
    border-radius: 10px;
    padding: 12px 16px !important;
}
[data-testid="stMetricLabel"]  { font-size: 0.78rem !important; color: #888 !important; }
[data-testid="stMetricValue"]  { font-size: 1.15rem !important; color: #1a1a2e !important; }

/* Dataframe */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

/* Hide Streamlit branding */
#MainMenu, footer { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Chart helpers
# ─────────────────────────────────────────────────────────────────────────────

def _compute(history: pd.DataFrame) -> dict:
    """Compute all indicator series needed for Plotly charts."""
    close  = history["Close"]
    volume = history["Volume"]
    opens  = history["Open"]

    ma20  = close.rolling(20).mean()
    ma50  = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    rsi   = (100 - 100 / (1 + rs)).fillna(50)

    ema12     = close.ewm(span=12, adjust=False).mean()
    ema26     = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    sig_line  = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - sig_line

    vol_colors = [
        "#27ae60" if float(c) >= float(o) else "#e74c3c"
        for c, o in zip(close, opens)
    ]

    return dict(
        dates=history.index, close=close, volume=volume,
        ma20=ma20, ma50=ma50, ma200=ma200,
        rsi=rsi, macd=macd_line, signal=sig_line, hist=macd_hist,
        vol_colors=vol_colors,
    )


def _price_chart(s: dict, currency: str) -> go.Figure:
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.70, 0.30], vertical_spacing=0.03,
    )
    # Area + price line
    fig.add_trace(go.Scatter(
        x=s["dates"], y=s["close"], name="Close",
        line=dict(color="#6c5ce7", width=2.2),
        fill="tozeroy", fillcolor="rgba(108,92,231,0.07)",
        hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>Close: %{{y:,.2f}} {currency}<extra></extra>",
    ), row=1, col=1)
    # Moving averages
    for key, color, label in [
        ("ma20",  "#f39c12", "MA 20"),
        ("ma50",  "#8e44ad", "MA 50"),
        ("ma200", "#27ae60", "MA 200"),
    ]:
        if s[key].notna().any():
            fig.add_trace(go.Scatter(
                x=s["dates"], y=s[key], name=label,
                line=dict(color=color, width=1.5, dash="dash"),
                hovertemplate=f"<b>%{{x|%d %b %Y}}</b><br>{label}: %{{y:,.2f}}<extra></extra>",
            ), row=1, col=1)
    # Volume bars
    fig.add_trace(go.Bar(
        x=s["dates"], y=s["volume"], name="Volume",
        marker_color=s["vol_colors"], opacity=0.75,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Volume: %{y:,.0f}<extra></extra>",
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=0, r=0, t=8, b=0), height=430,
        xaxis2=dict(rangeslider=dict(visible=False)),
    )
    fig.update_yaxes(title_text=f"Price ({currency})", row=1, col=1, gridcolor="#f0f0f0", tickformat=",.2f")
    fig.update_yaxes(title_text="Volume", row=2, col=1, gridcolor="#f0f0f0", tickformat=".2s")
    return fig


def _rsi_chart(s: dict) -> go.Figure:
    fig = go.Figure()
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(231,76,60,0.07)",  line_width=0)
    fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(39,174,96,0.07)",  line_width=0)
    fig.add_hline(y=70, line_dash="dash", line_color="rgba(231,76,60,0.7)", line_width=1.2,
                  annotation_text="Overbought 70", annotation_position="top right",
                  annotation_font=dict(size=9, color="#e74c3c"))
    fig.add_hline(y=30, line_dash="dash", line_color="rgba(39,174,96,0.7)",  line_width=1.2,
                  annotation_text="Oversold 30",  annotation_position="bottom right",
                  annotation_font=dict(size=9, color="#27ae60"))
    fig.add_trace(go.Scatter(
        x=s["dates"], y=s["rsi"], name="RSI (14)",
        line=dict(color="#e17055", width=2),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>RSI: %{y:.1f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white", hovermode="x unified", showlegend=False,
        margin=dict(l=0, r=0, t=8, b=0), height=230,
        yaxis=dict(range=[0, 100], gridcolor="#f0f0f0", tickvals=[0,20,30,50,70,80,100]),
        xaxis=dict(gridcolor="#f0f0f0"),
    )
    return fig


def _macd_chart(s: dict) -> go.Figure:
    hist_colors = ["#27ae60" if float(v) >= 0 else "#e74c3c" for v in s["hist"]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=s["dates"], y=s["hist"], name="Histogram",
        marker_color=hist_colors, opacity=0.65,
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Hist: %{y:.4f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=s["dates"], y=s["macd"], name="MACD",
        line=dict(color="#2980b9", width=2),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>MACD: %{y:.4f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=s["dates"], y=s["signal"], name="Signal",
        line=dict(color="#e67e22", width=2),
        hovertemplate="<b>%{x|%d %b %Y}</b><br>Signal: %{y:.4f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white", hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1, font=dict(size=11)),
        margin=dict(l=0, r=0, t=8, b=0), height=230,
        yaxis=dict(gridcolor="#f0f0f0"), xaxis=dict(gridcolor="#f0f0f0"),
    )
    return fig


def _radar_chart(fundamentals: dict) -> go.Figure:
    def _clamp(v, lo, hi): return max(lo, min(hi, v))
    items = [
        ("P/E Ratio",      fundamentals.get("pe_ratio"),      lambda v: 10 - _clamp((v - 5) / 5, 0, 10)),
        ("ROE",            fundamentals.get("roe"),            lambda v: _clamp(v * 50, 0, 10)),
        ("Profit Margin",  fundamentals.get("profit_margin"),  lambda v: _clamp(v * 40, 0, 10)),
        ("Div Yield",      fundamentals.get("dividend_yield"), lambda v: _clamp(v * 200, 0, 10)),
        ("Beta (inv)",     fundamentals.get("beta"),           lambda v: _clamp(10 - v * 3, 0, 10)),
        ("D/E (inv)",      fundamentals.get("debt_to_equity"), lambda v: _clamp(10 - v / 30, 0, 10)),
    ]
    labels = [i[0] for i in items]
    scores = [round(fn(val), 1) if val is not None else 5.0 for _, val, fn in items]

    fig = go.Figure(go.Scatterpolar(
        r=scores + [scores[0]], theta=labels + [labels[0]],
        fill="toself", fillcolor="rgba(108,92,231,0.15)",
        line=dict(color="#6c5ce7", width=2.2),
        marker=dict(color="#6c5ce7", size=7),
        hovertemplate="%{theta}: %{r:.1f} / 10<extra></extra>",
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 10], gridcolor="#eee",
                            tickfont=dict(size=9), tickvals=[0, 2, 4, 6, 8, 10]),
            angularaxis=dict(tickfont=dict(size=10)),
        ),
        showlegend=False, template="plotly_white",
        margin=dict(l=40, r=40, t=20, b=20), height=300,
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Report byte builders (for download buttons)
# ─────────────────────────────────────────────────────────────────────────────

def _build_pdf_bytes(stock, analysis, narrative) -> bytes | None:
    try:
        from xhtml2pdf import pisa
        md_text  = build_markdown(stock, analysis, narrative)
        html_src = build_pdf_html(stock, analysis, md_text, narrative)
        buf      = io.BytesIO()
        result   = pisa.CreatePDF(html_src, dest=buf)
        return buf.getvalue() if not result.err else None
    except Exception:
        return None


def _build_html_bytes(stock, analysis, narrative) -> bytes:
    md_text = build_markdown(stock, analysis, narrative)
    return build_html(stock, analysis, md_text, narrative).encode("utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Session state initialisation
# ─────────────────────────────────────────────────────────────────────────────
_STATE_KEYS = [
    "search_results", "selected_match",
    "stock", "analysis", "narrative",
    "md_bytes", "html_bytes", "pdf_bytes",
    "cache_key",
]
for _k in _STATE_KEYS:
    if _k not in st.session_state:
        st.session_state[_k] = None


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center; padding: 10px 0 18px;'>
      <div style='font-size:2.2rem;'>📊</div>
      <div style='font-size:1.1rem; font-weight:700; color:#fff; margin-top:4px;'>
        AI Stock Report
      </div>
      <div style='font-size:0.75rem; color:#aaa; margin-top:2px;'>
        Search any stock worldwide
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Search section ────────────────────────────────────────────────────
    st.markdown("### 🔍 Search Stock")
    query = st.text_input(
        "search_query",
        placeholder="Company name or ticker  (e.g. Apple, Reliance, HDFC Bank)",
        label_visibility="collapsed",
    )

    col_search, col_clear = st.columns(2)
    search_clicked = col_search.button("Search", use_container_width=True)
    clear_clicked  = col_clear.button("Clear",  use_container_width=True)

    if clear_clicked:
        for k in _STATE_KEYS:
            st.session_state[k] = None
        st.rerun()

    if search_clicked:
        if not query.strip():
            st.warning("Please enter a company name or ticker.")
        else:
            with st.spinner("Searching..."):
                results = search_stocks(query)
            if results:
                st.session_state.search_results = results
                st.session_state.selected_match = None
            else:
                st.warning("No results found. Try a different name or a direct ticker symbol.")

    # Results selectbox
    if st.session_state.search_results:
        results  = st.session_state.search_results
        options  = [m.label() for m in results]
        choice   = st.selectbox(
            "Select from results",
            options,
            label_visibility="collapsed",
        )
        idx = options.index(choice)
        st.session_state.selected_match = results[idx]
        # Show exchange info
        m = results[idx]
        st.caption(f"🏛️ Exchange: **{m.exchange_display}** &nbsp;|&nbsp; Type: {m.instrument_type}")

    st.markdown("---")

    # ── Settings section ──────────────────────────────────────────────────
    st.markdown("### ⚙️ Settings")
    period = st.selectbox(
        "Data period",
        ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
        index=3,
        format_func=lambda x: {
            "1mo":"1 Month","3mo":"3 Months","6mo":"6 Months",
            "1y":"1 Year","2y":"2 Years","5y":"5 Years"
        }.get(x, x),
    )

    ai_enabled = config.USE_AI_NARRATIVE
    if ai_enabled:
        st.success("🤖 Gemini AI active", icon=None)
    else:
        st.warning("📝 Rule-based mode (set GOOGLE_API_KEY for AI)", icon=None)

    st.markdown("---")

    # ── Generate button ───────────────────────────────────────────────────
    generate_clicked = st.button(
        "🚀  Generate Report",
        use_container_width=True,
        type="primary",
        disabled=(st.session_state.selected_match is None),
        help="Select a stock from the search results first" if st.session_state.selected_match is None else "",
    )

    if generate_clicked and st.session_state.selected_match:
        match     = st.session_state.selected_match
        ticker    = match.ticker
        cache_key = f"{ticker}_{period}"

        if st.session_state.cache_key != cache_key:
            progress = st.progress(0, text="Fetching market data…")
            try:
                stock = fetch_stock_data(ticker, period=period)
            except DataFetchError as exc:
                st.error(f"❌ Could not fetch data for **{ticker}**: {exc}")
                st.stop()

            progress.progress(30, text="Running quantitative analysis…")
            analysis = analyze(stock.history, stock.fundamentals)

            progress.progress(60, text="Generating AI narrative…")
            narrative = generate_narrative(stock, analysis)

            progress.progress(80, text="Building report files…")
            md_text    = build_markdown(stock, analysis, narrative)
            md_bytes   = md_text.encode("utf-8")
            html_bytes = _build_html_bytes(stock, analysis, narrative)
            pdf_bytes  = _build_pdf_bytes(stock, analysis, narrative)

            progress.progress(100, text="Done!")
            progress.empty()

            st.session_state.update({
                "cache_key":      cache_key,
                "stock":          stock,
                "analysis":       analysis,
                "narrative":      narrative,
                "md_bytes":       md_bytes,
                "html_bytes":     html_bytes,
                "pdf_bytes":      pdf_bytes,
            })

        st.rerun()

    # ── Download buttons ──────────────────────────────────────────────────
    if st.session_state.stock is not None:
        ticker = st.session_state.stock.ticker
        st.markdown("---")
        st.markdown("### 📥 Download Report")

        if st.session_state.md_bytes:
            st.download_button(
                "📄 Markdown",
                st.session_state.md_bytes,
                file_name=f"{ticker}_report.md",
                mime="text/markdown",
                use_container_width=True,
            )
        if st.session_state.html_bytes:
            st.download_button(
                "🌐 HTML  (interactive charts)",
                st.session_state.html_bytes,
                file_name=f"{ticker}_report.html",
                mime="text/html",
                use_container_width=True,
            )
        if st.session_state.pdf_bytes:
            st.download_button(
                "📑 PDF  (print-ready)",
                st.session_state.pdf_bytes,
                file_name=f"{ticker}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.caption("⚠️ PDF unavailable — check xhtml2pdf install")


# ─────────────────────────────────────────────────────────────────────────────
# Main content area
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.stock is None:
    # ── Welcome / landing screen ──────────────────────────────────────────
    st.markdown("""
    <div style='text-align:center; padding:60px 0 36px;'>
      <div style='font-size:3.5rem;'>📊</div>
      <h1 style='color:#2d1b69; margin:16px 0 10px; font-size:2rem;'>
        AI-Powered Stock Report Generator
      </h1>
      <p style='color:#666; font-size:1.05rem; max-width:540px; margin:0 auto;'>
        Search any stock worldwide — no ticker suffixes needed.<br>
        Get live charts, AI analysis, and downloadable reports instantly.
      </p>
    </div>
    """, unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    features = [
        ("🔍", "Smart Search",
         "Type any company name. We auto-resolve the correct exchange ticker — "
         "RELIANCE → RELIANCE.NS, HSBC → HSBA.L, etc."),
        ("📈", "Live Charts",
         "Interactive Plotly charts: price + MA overlay, volume, RSI with "
         "overbought/oversold bands, MACD histogram, and fundamentals radar."),
        ("🤖", "AI Analysis",
         "Google Gemini generates professional 3-paragraph analyst commentary "
         "with a rule-based fallback when offline."),
        ("⬇️", "Export",
         "Download reports as PDF (embedded matplotlib charts), "
         "HTML (Chart.js interactive), or Markdown."),
    ]
    for col, (icon, title, desc) in zip([c1, c2, c3, c4], features):
        col.markdown(f"""
        <div style='background:#f8f7ff; border:1px solid #e8e4ff; border-radius:14px;
                    padding:22px 18px; text-align:center; min-height:200px;'>
          <div style='font-size:2rem; margin-bottom:10px;'>{icon}</div>
          <strong style='color:#2d1b69; font-size:1rem;'>{title}</strong>
          <p style='font-size:0.83rem; color:#666; margin-top:10px; line-height:1.55;'>{desc}</p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Exchange reference table
    with st.expander("🌍 Supported exchanges & auto-resolved suffixes"):
        ex_data = {
            "Country":  ["USA", "India", "India", "UK", "Germany", "Japan", "Hong Kong",
                         "Canada", "Australia", "France", "Brazil", "South Korea"],
            "Exchange": ["NYSE / NASDAQ", "NSE", "BSE", "London SE", "XETRA", "Tokyo SE",
                         "HKEX", "TSX", "ASX", "Euronext Paris", "B3", "KRX"],
            "Suffix":   ["(none)", ".NS", ".BO", ".L", ".DE", ".T",
                         ".HK", ".TO", ".AX", ".PA", ".SA", ".KS"],
            "Example":  ["AAPL", "RELIANCE.NS", "RELIANCE.BO", "HSBA.L", "VOW.DE",
                         "7203.T", "0700.HK", "RY.TO", "CBA.AX", "MC.PA",
                         "PETR4.SA", "005930.KS"],
        }
        st.dataframe(pd.DataFrame(ex_data), hide_index=True, use_container_width=True)
        st.caption("All suffixes are resolved automatically — just type the company name.")

    st.info("👈  Use the sidebar to search for any stock and generate your report.")

else:
    # ── Report view ───────────────────────────────────────────────────────
    stock     = st.session_state.stock
    analysis  = st.session_state.analysis
    narrative = st.session_state.narrative
    tech      = analysis.technicals
    s         = _compute(stock.history)

    rec_color = {"Buy": "#27ae60", "Hold": "#f39c12", "Sell": "#e74c3c"}.get(
        analysis.recommendation, "#6c5ce7"
    )
    trend_bg = {"Bullish": "rgba(39,174,96,0.85)",
                "Neutral":  "rgba(243,156,18,0.85)",
                "Bearish":  "rgba(231,76,60,0.85)"}.get(analysis.trend_signal, "#888")

    # ── Stock header ──────────────────────────────────────────────────────
    st.markdown(f"""
    <div style='background:linear-gradient(135deg,#2d1b69 0%,#6c5ce7 100%);
                color:#fff; padding:22px 28px; border-radius:14px; margin-bottom:20px;'>
      <div style='font-size:1.55rem; font-weight:700; line-height:1.2;'>
        {stock.company_name}
        <span style='opacity:.65; font-size:1rem; margin-left:10px;'>({stock.ticker})</span>
      </div>
      <div style='opacity:.8; font-size:0.88rem; margin-top:5px;'>
        {stock.sector}&nbsp;&nbsp;·&nbsp;&nbsp;{stock.industry}&nbsp;&nbsp;·&nbsp;&nbsp;{stock.currency}
      </div>
      <div style='margin-top:14px; display:flex; gap:10px; flex-wrap:wrap; align-items:center;'>
        <span style='background:{rec_color}; padding:5px 18px; border-radius:20px; font-weight:700; font-size:0.95rem;'>
          {'⬆' if analysis.recommendation=='Buy' else '⬇' if analysis.recommendation=='Sell' else '➡'}&nbsp;
          {analysis.recommendation}
        </span>
        <span style='background:{trend_bg}; padding:5px 18px; border-radius:20px; font-weight:700; font-size:0.95rem;'>
          {analysis.trend_signal}
        </span>
        <span style='background:rgba(255,255,255,0.18); padding:5px 18px; border-radius:20px; font-size:0.9rem;'>
          Risk: {analysis.risk_level}
        </span>
        <span style='background:rgba(255,255,255,0.18); padding:5px 18px; border-radius:20px; font-size:0.9rem;'>
          Score: {analysis.composite_score:+.2f}
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── KPI metrics (row 1) ───────────────────────────────────────────────
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
    kpi1.metric("Last Close",    f"{tech.last_close:,.2f} {stock.currency}")
    kpi2.metric("1-Day Change",  f"{tech.change_pct_1d:+.2f}%",  delta=f"{tech.change_pct_1d:.2f}")
    kpi3.metric("1-Month",       f"{tech.change_pct_1m:+.2f}%",  delta=f"{tech.change_pct_1m:.2f}")
    kpi4.metric("YTD Return",    f"{tech.change_pct_ytd:+.2f}%", delta=f"{tech.change_pct_ytd:.2f}")
    kpi5.metric("Sharpe Ratio",  f"{tech.sharpe_ratio:.2f}")

    kpi6, kpi7, kpi8, kpi9, kpi10 = st.columns(5)
    kpi6.metric("RSI (14)",          f"{tech.rsi:.1f}")
    kpi7.metric("Volatility (ann.)",  f"{tech.volatility_annualized:.1f}%")
    kpi8.metric("Max Drawdown",       f"{tech.max_drawdown_pct:.1f}%")
    kpi9.metric("MACD",               f"{tech.macd:.4f}")
    kpi10.metric("Signal Line",       f"{tech.macd_signal:.4f}")

    st.markdown("---")

    # ── Price + Volume chart ──────────────────────────────────────────────
    st.markdown("#### 📈 Price History & Moving Averages")
    st.plotly_chart(_price_chart(s, stock.currency), use_container_width=True, config={"displayModeBar": True})

    # ── RSI + MACD ────────────────────────────────────────────────────────
    col_rsi, col_macd = st.columns(2)
    with col_rsi:
        st.markdown("#### ⚡ RSI (14-Day)")
        rsi_val = tech.rsi
        if rsi_val >= 70:
            st.caption(f"⚠️ RSI {rsi_val:.1f} — **Overbought** territory")
        elif rsi_val <= 30:
            st.caption(f"💡 RSI {rsi_val:.1f} — **Oversold** territory (potential entry)")
        else:
            st.caption(f"RSI {rsi_val:.1f} — Neutral range")
        st.plotly_chart(_rsi_chart(s), use_container_width=True, config={"displayModeBar": False})

    with col_macd:
        st.markdown("#### 📉 MACD (12 / 26 / 9)")
        if tech.macd > tech.macd_signal:
            st.caption("🟢 MACD above signal line — **bullish momentum**")
        else:
            st.caption("🔴 MACD below signal line — **bearish momentum**")
        st.plotly_chart(_macd_chart(s), use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")

    # ── Fundamentals table + radar ────────────────────────────────────────
    col_fund, col_radar = st.columns([3, 2])

    with col_fund:
        st.markdown("#### 🏦 Fundamental Snapshot")
        f = stock.fundamentals

        def fv(v, pct=False, millions=False):
            if v is None:
                return "N/A"
            if millions and isinstance(v, (int, float)):
                return f"{v/1e9:.2f}B" if v >= 1e9 else f"{v/1e6:.1f}M"
            if pct and isinstance(v, float):
                return f"{v*100:.2f}%"
            if isinstance(v, float):
                return f"{v:,.2f}"
            return str(v)

        fund_rows = [
            ("Market Cap",       fv(f.get("market_cap"), millions=True)),
            ("P/E Ratio (TTM)",  fv(f.get("pe_ratio"))),
            ("Forward P/E",      fv(f.get("forward_pe"))),
            ("P/B Ratio",        fv(f.get("pb_ratio"))),
            ("EPS (TTM)",        fv(f.get("eps"))),
            ("Return on Equity", fv(f.get("roe"), pct=True)),
            ("Debt / Equity",    fv(f.get("debt_to_equity"))),
            ("Profit Margin",    fv(f.get("profit_margin"), pct=True)),
            ("Dividend Yield",   fv(f.get("dividend_yield"), pct=True)),
            ("Beta",             fv(f.get("beta"))),
            ("52-Week High",     fv(f.get("fifty_two_week_high"))),
            ("52-Week Low",      fv(f.get("fifty_two_week_low"))),
            ("Analyst Target",   fv(f.get("analyst_target_price"))),
        ]
        st.dataframe(
            pd.DataFrame(fund_rows, columns=["Metric", "Value"]),
            hide_index=True,
            use_container_width=True,
        )

    with col_radar:
        st.markdown("#### 🎯 Fundamentals Scorecard")
        st.caption("Normalised 0–10 scale per metric")
        st.plotly_chart(_radar_chart(stock.fundamentals), use_container_width=True,
                        config={"displayModeBar": False})

    st.markdown("---")

    # ── AI Commentary ─────────────────────────────────────────────────────
    st.markdown("#### 🤖 AI-Generated Analyst Commentary")
    mode = "Google Gemini" if config.USE_AI_NARRATIVE else "Rule-Based Fallback"
    st.caption(f"Generated by: {mode}")

    paras = [p.strip() for p in narrative.split("\n\n") if p.strip()]
    para_labels = ["📌 Price Action & Trend", "⚠️ Risk Assessment", "🔭 Outlook & Recommendation"]
    for i, para in enumerate(paras):
        label = para_labels[i] if i < len(para_labels) else f"📄 Paragraph {i+1}"
        with st.expander(label, expanded=True):
            st.markdown(para)

    st.markdown("---")

    # ── Signal notes ──────────────────────────────────────────────────────
    st.markdown("#### 📋 Rule-Based Signal Notes")
    c_bull, c_bear = st.columns(2)
    bull_notes = [n for n in analysis.notes if any(
        w in n.lower() for w in ["bullish", "above", "strong", "positive", "value", "uptrend"])]
    bear_notes = [n for n in analysis.notes if n not in bull_notes]

    with c_bull:
        st.markdown("**🟢 Positive signals**")
        for n in bull_notes:
            st.markdown(f"- {n}")
        if not bull_notes:
            st.caption("No positive signals at this time.")

    with c_bear:
        st.markdown("**🔴 Cautionary signals**")
        for n in bear_notes:
            st.markdown(f"- {n}")
        if not bear_notes:
            st.caption("No cautionary signals at this time.")

    st.markdown("---")
    st.caption(config.DISCLAIMER)
