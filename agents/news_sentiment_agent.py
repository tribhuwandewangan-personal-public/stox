"""
News & Sentiment Agent.
Deterministic: counts the keyword-scored sentiment of recent headlines (tools/news_tools.py) and summarises
them. No LLM involved.
"""

from typing import Dict, Any, Union

from tools.news_tools import NewsSentimentEngine
from storage.cache_manager import CacheManager


def _is_bullish(label: str) -> bool:
    return "Bullish" in (label or "")


def _is_bearish(label: str) -> bool:
    return "Bearish" in (label or "")


class NewsSentimentAgent:
    def __init__(self, news_engine: Union[NewsSentimentEngine, CacheManager] = None):
        if isinstance(news_engine, CacheManager):
            self.news_engine = NewsSentimentEngine(cache_manager=news_engine)
        else:
            self.news_engine = news_engine or NewsSentimentEngine()

    def run(self, symbol: str, company_name: str = "") -> Dict[str, Any]:
        news_items = self.news_engine.fetch_stock_news(symbol, company_name)

        bull_count = sum(1 for item in news_items if _is_bullish(item.get("sentiment_label")))
        bear_count = sum(1 for item in news_items if _is_bearish(item.get("sentiment_label")))
        total = len(news_items)

        if total == 0:
            overall_sentiment = "Unavailable"
        elif bull_count > bear_count:
            overall_sentiment = "Positive / Bullish"
        elif bear_count > bull_count:
            overall_sentiment = "Negative / Bearish"
        else:
            overall_sentiment = "Balanced / Neutral"

        if total == 0:
            analysis_text = f"No recent news could be retrieved for {symbol} ({company_name}); news sentiment is not factored in."
        else:
            top_catalysts = [item.get("title") for item in news_items[:2] if item.get("title")]
            cat_str = " | ".join(top_catalysts) if top_catalysts else "Normal market trade flows."
            analysis_text = (
                f"News sentiment for {symbol} ({company_name}) is overall {overall_sentiment} "
                f"({bull_count} bullish vs {bear_count} bearish headlines out of {total}). "
                f"Recent headlines: {cat_str}."
            )

        return {
            "agent_name": "News & Sentiment Agent",
            "symbol": symbol,
            "news_count": total,
            "news_items": news_items,
            "news_score": {
                "bullish": bull_count,
                "bearish": bear_count,
                "total": total,
                "net": (bull_count - bear_count) / total if total else 0.0,
            },
            "analysis": analysis_text
        }
