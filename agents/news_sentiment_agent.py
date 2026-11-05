import os
from typing import Dict, Any, Union
from langchain_core.prompts import PromptTemplate

from config import get_llm, FAST_MODE
from tools.news_tools import NewsSentimentEngine
from storage.cache_manager import CacheManager

class NewsSentimentAgent:
    def __init__(self, news_engine: Union[NewsSentimentEngine, CacheManager] = None):
        if isinstance(news_engine, CacheManager):
            self.news_engine = NewsSentimentEngine(cache_manager=news_engine)
        else:
            self.news_engine = news_engine or NewsSentimentEngine()
        self._llm = None
        self.use_llm = os.getenv("OLLAMA_NEWS_ANALYSIS", "false").lower() in ("true", "1", "yes")

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.2, max_tokens=150, timeout=12)
        return self._llm

    def run(self, symbol: str, company_name: str = "") -> Dict[str, Any]:
        news_items = self.news_engine.fetch_stock_news(symbol, company_name)
        
        # Fast High-Precision NLP Sentiment Synthesis (sub-millisecond)
        bull_count = sum(1 for item in news_items if item.get("sentiment_label") == "Bullish")
        bear_count = sum(1 for item in news_items if item.get("sentiment_label") == "Bearish")
        total = len(news_items)

        if bull_count > bear_count:
            overall_sentiment = "Positive / Bullish"
        elif bear_count > bull_count:
            overall_sentiment = "Negative / Bearish"
        else:
            overall_sentiment = "Balanced / Neutral"

        top_catalysts = [item.get("title") for item in news_items[:2] if item.get("title")]
        cat_str = " | ".join(top_catalysts) if top_catalysts else "Normal market trade flows."

        fast_summary = (
            f"News sentiment for {symbol} ({company_name}) is overall {overall_sentiment} "
            f"({bull_count} bullish vs {bear_count} bearish headlines out of {total}). "
            f"Recent headlines: {cat_str}."
        )

        if not self.use_llm or FAST_MODE:
            analysis_text = fast_summary
        else:
            snippets_text = "\n".join([f"- [{item.get('sentiment_label')}] {item.get('title')}: {item.get('snippet')}" for item in news_items[:4]])
            prompt = PromptTemplate.from_template(
                """You are a Market Sentiment Specialist.
Review the following online news headlines and sentiment signals for NSE stock {symbol}:
{news_snippets}

Provide a concise 2-sentence market sentiment summary determining whether recent news flow is Bullish, Bearish, or Neutral for {symbol}.
"""
            )
            chain = prompt | self.llm
            try:
                response = chain.invoke({"symbol": symbol, "news_snippets": snippets_text})
                analysis_text = response.content if hasattr(response, 'content') else str(response)
            except Exception:
                analysis_text = fast_summary

        return {
            "agent_name": "News & Sentiment Agent",
            "symbol": symbol,
            "news_count": len(news_items),
            "news_items": news_items,
            "analysis": analysis_text
        }
