"""
ai_summary.py
--------------
Generates banker-appropriate narrative commentary using the Google Gemini API.
Falls back to a deterministic rule-based generator when GOOGLE_API_KEY is not
set or a network/API error occurs.
"""
import config
from src.analysis import AnalysisResult
from src.data_fetcher import StockData

_SYSTEM_PROMPT = (
    "You are a senior equity research analyst writing for a banking institution's "
    "internal stock report. Write in a professional, measured, compliance-aware tone. "
    "Avoid hype, avoid definitive predictions, and always frame conclusions as being "
    "derived from the data provided. Structure your response in exactly 3 paragraphs:\n"
    "1. Summary of recent price action and trend.\n"
    "2. Risk assessment.\n"
    "3. Outlook and rationale for the recommendation.\n"
    "Do not repeat raw numbers excessively — interpret them."
)


def generate_narrative(stock: StockData, analysis: AnalysisResult) -> str:
    if config.USE_AI_NARRATIVE:
        try:
            return _generate_with_gemini(stock, analysis)
        except Exception as e:
            print(f"[WARN] Gemini narrative generation failed ({e}); using fallback generator.")
    return _generate_fallback(stock, analysis)


def _build_user_prompt(stock: StockData, analysis: AnalysisResult) -> str:
    tech = analysis.technicals
    return f"""
Company: {stock.company_name} ({stock.ticker})
Sector: {stock.sector} | Industry: {stock.industry}

Latest close: {tech.last_close} {stock.currency}
1-day change: {tech.change_pct_1d:+.2f}%
1-month change: {tech.change_pct_1m:+.2f}%
YTD change: {tech.change_pct_ytd:+.2f}%
Moving averages: {tech.moving_averages}
RSI(14): {tech.rsi}
MACD: {tech.macd} vs signal {tech.macd_signal}
Annualized volatility: {tech.volatility_annualized}%
Sharpe ratio: {tech.sharpe_ratio}
Max drawdown: {tech.max_drawdown_pct}%

Fundamentals: {stock.fundamentals}

Composite trend signal: {analysis.trend_signal}
Risk level: {analysis.risk_level}
Composite score: {analysis.composite_score}
Recommendation: {analysis.recommendation}
Supporting notes: {'; '.join(analysis.notes)}

Write the 3-paragraph analyst narrative now.
""".strip()


def _generate_with_gemini(stock: StockData, analysis: AnalysisResult) -> str:
    """Call Google Gemini API using the new google-genai SDK."""
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GOOGLE_API_KEY)

    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=_build_user_prompt(stock, analysis),
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            max_output_tokens=700,
            temperature=0.4,
        ),
    )
    return response.text.strip()


def _generate_fallback(stock: StockData, analysis: AnalysisResult) -> str:
    """Deterministic, rule-based narrative — no external API required."""
    tech = analysis.technicals

    trend_phrase = {
        "Bullish": "an upward bias",
        "Bearish": "a downward bias",
        "Neutral": "a sideways, range-bound pattern",
    }[analysis.trend_signal]

    momentum_phrase = (
        "overbought territory, which can precede a near-term pullback"
        if tech.rsi >= 70
        else "oversold territory, which may signal a potential rebound opportunity"
        if tech.rsi <= 30
        else "a neutral momentum zone"
    )

    risk_phrase = {
        "Low": "relatively low historical volatility, suggesting a stable risk profile",
        "Moderate": "moderate historical volatility, in line with typical sector behavior",
        "High": "elevated historical volatility, warranting close risk monitoring",
    }[analysis.risk_level]

    p1 = (
        f"{stock.company_name} ({stock.ticker}) closed its most recent session at "
        f"{tech.last_close} {stock.currency}, reflecting a {tech.change_pct_1d:+.2f}% move "
        f"on the day and a {tech.change_pct_1m:+.2f}% change over the trailing month. "
        f"Year-to-date the stock has moved {tech.change_pct_ytd:+.2f}%. The relationship "
        f"between short- and medium-term moving averages currently points to {trend_phrase}, "
        f"while the 14-day RSI of {tech.rsi} places the stock in {momentum_phrase}."
    )

    p2 = (
        f"On a risk basis the stock exhibits {risk_phrase}, with annualized volatility of "
        f"{tech.volatility_annualized}% and a maximum observed drawdown of "
        f"{tech.max_drawdown_pct}% over the lookback period. The risk-adjusted return as "
        f"measured by the Sharpe ratio stands at {tech.sharpe_ratio}, which should be "
        f"weighed against the institution's risk tolerance and the broader sector backdrop "
        f"of {stock.sector}."
    )

    notes_str = " ".join(analysis.notes[:4])
    p3 = (
        f"Taking the technical and fundamental signals together, the composite analysis "
        f"yields a '{analysis.trend_signal}' signal with a score of {analysis.composite_score} "
        f"(on a −1 to +1 scale), supporting a '{analysis.recommendation}' stance at this time. "
        f"Key factors: {notes_str} As with any automated output, this recommendation should "
        f"be corroborated with qualitative due diligence before any portfolio action is taken."
    )

    return f"{p1}\n\n{p2}\n\n{p3}"
