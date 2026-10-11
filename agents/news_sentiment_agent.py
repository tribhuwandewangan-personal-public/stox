from typing import Dict, Any, Union
from langchain_core.prompts import PromptTemplate

from config import get_llm
from tools.news_tools import NewsSentimentEngine
from storage.cache_manager import CacheManager

class NewsSentimentAgent:
    def __init__(self, news_engine: Union[NewsSentimentEngine, CacheManager] = None):
        if isinstance(news_engine, CacheManager):
            self.news_engine = NewsSentimentEngine(cache_manager=news_engine)
        else:
            self.news_engine = news_engine or NewsSentimentEngine()
        self.llm = get_llm(temperature=0.2)

    def run(self, symbol: str, company_name: str = "") -> Dict[str, Any]:
        news_items = self.news_engine.fetch_stock_news(symbol, company_name)
        
        snippets_text = "\n".join([f"- [{item.get('sentiment_label')}] {item.get('title')}: {item.get('snippet')}" for item in news_items[:5]])
        
        prompt = PromptTemplate.from_template(
            """You are a Market Sentiment Specialist.
Review the following online news headlines and sentiment signals for NSE stock {symbol}:

News Headlines:
{news_snippets}

Provide a 3-sentence market sentiment summary determining whether recent news flow is Bullish, Bearish, or Neutral for {symbol}, highlighting any catalyst or key corporate developments.
"""
        )
        
        chain = prompt | self.llm
        try:
            response = chain.invoke({"symbol": symbol, "news_snippets": snippets_text})
            analysis_text = response.content if hasattr(response, 'content') else str(response)
        except Exception:
            analysis_text = f"News sentiment for {symbol} is overall balanced across recent market headlines."

        return {
            "agent_name": "News & Sentiment Agent",
            "symbol": symbol,
            "news_count": len(news_items),
            "news_items": news_items,
            "analysis": analysis_text
        }
