"""
Historical Data RAG Engine (Compatibility Shim).
Redirects to the new corporate-action adjusted HistoricalDataEngine in tools.historical_data_tools.
"""

from storage.cache_manager import CacheManager
from tools.historical_data_tools import HistoricalDataEngine


class BhavcopyRAGEngine(HistoricalDataEngine):
    """
    Backwards compatibility alias for HistoricalDataEngine.
    Retrieves split-adjusted historical data from SQLite and reliable market feeds.
    """
    def __init__(self, data_dir: str = "", cache_manager: CacheManager = None):
        super().__init__(cache_manager=cache_manager)
