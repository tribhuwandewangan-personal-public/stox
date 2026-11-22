"""
News & Sentiment Agent.
Deterministic: applies deduplicating headline clustering, publisher credibility weights,
exponential time-decay, and event severity scaling via tools/news_tools.py. No LLM involved.
"""

from typing import Dict, Any, Union

from tools.news_tools import NewsSentimentEngine, score_news_items_institutional
from storage.cache_manager import CacheManager


class NewsSentimentAgent:
    def __init__(self, news_engine: Union[NewsSentimentEngine, CacheManager] = None):
        if isinstance(news_engine, CacheManager):
            self.news_engine = NewsSentimentEngine(cache_manager=news_engine)
        else:
            self.news_engine = news_engine or NewsSentimentEngine()

    def run(self, symbol: str, company_name: str = "") -> Dict[str, Any]:
        raw_items = self.news_engine.fetch_stock_news(symbol, company_name)
        scored = score_news_items_institutional(raw_items)
        news_items = scored["clustered_items"]

        bull_count = scored["bullish"]
        bear_count = scored["bearish"]
        total = scored["clustered_count"]
        w_score = scored["weighted_score"]

        if total == 0:
            overall_sentiment = "Unavailable"
        elif w_score >= 0.15 or bull_count > bear_count:
            overall_sentiment = "Positive / Bullish"
        elif w_score <= -0.15 or bear_count > bull_count:
            overall_sentiment = "Negative / Bearish"
        else:
            overall_sentiment = "Balanced / Neutral"

        if total == 0:
            analysis_text = (
                f"No recent news on verified business activity (orders, deals, expansion) found for "
                f"{symbol} ({company_name}); broker recommendation noise filtered out."
            )
        else:
            category_groups = {}
            for item in news_items:
                cat = item.get("category", "Corporate Activity")
                badge = item.get("category_badge", "🏢 [Corporate]")
                title = item.get("title", "")
                if cat not in category_groups:
                    category_groups[cat] = {"badge": badge, "items": []}
                category_groups[cat]["items"].append(title)

            summary_lines = [
                f"{data['badge']} {data['items'][0]}"
                for _, data in list(category_groups.items())[:3]
            ]
            cat_str = " | ".join(summary_lines) if summary_lines else "Standard market operations."
            dedup_note = (
                f" ({scored['raw_count']} raw deduplicated to {total} unique stories)"
                if scored["raw_count"] > total
                else ""
            )
            analysis_text = (
                f"Business activity for {symbol} ({company_name}) is overall {overall_sentiment} "
                f"({bull_count} positive vs {bear_count} negative across {total} unique business news items{dedup_note}; "
                f"weighted score {w_score:+.2f}). Key Business Events: {cat_str}."
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
                "weighted_score": w_score,
                "raw_count": scored["raw_count"],
                "clustered_count": total,
                "critical_alerts": scored["critical_alerts"],
            },
            "analysis": analysis_text,
        }
