"""
Tests for the LLM-free analysis engine: macro rules, evidence scoring / verdict invariants,
cache layer behaviour and the "no invented data" guarantees.

Run:  python -m unittest discover -s tests -v          (no third-party packages needed)
      uv run --no-project --with pandas --with numpy python -m unittest discover -s tests -v   (adds history tests)
"""

import itertools
import os
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.news_sentiment_agent import NewsSentimentAgent
from agents.synthesizer_agent import (
    MasterPredictionSynthesizerAgent as Synth,
    score_evidence, ACCUMULATE_THRESHOLD, BUY_THRESHOLD, SELL_THRESHOLD,
)
from storage.cache_manager import CacheManager
from tools.macro_tools import compute_macro_sentiment


def ind(name, pct):
    return {"indicator": name, "pct_change": pct}


def rs(text):
    """First number in a 'Rs. 123.45' / 'Rs. 100.00 - 102.00' string."""
    return float(str(text).replace("Rs.", "").split("-")[0].replace(",", "").strip())


class MacroSentimentTests(unittest.TestCase):
    def test_risk_on_is_bullish(self):
        r = compute_macro_sentiment([ind("S&P 500", 1.2), ind("Nasdaq", 1.5), ind("Brent Crude Oil", -1.5),
                                     ind("US Dollar Index (DXY)", -0.4), ind("USD / INR (Rupee)", -0.2)])
        self.assertEqual(r["label"], "Bullish")
        self.assertTrue(r["available"])
        self.assertGreater(r["score"], 0.25)

    def test_oil_dollar_rupee_shock_is_bearish(self):
        r = compute_macro_sentiment([ind("S&P 500", -0.2), ind("Brent Crude Oil", 3.5),
                                     ind("US Dollar Index (DXY)", 0.8), ind("USD / INR (Rupee)", 0.5)])
        self.assertEqual(r["label"], "Bearish")
        self.assertLess(r["score"], -0.25)

    def test_mixed_is_neutral(self):
        r = compute_macro_sentiment([ind("S&P 500", 0.5), ind("Brent Crude Oil", 1.0),
                                     ind("US Dollar Index (DXY)", 0.0), ind("USD / INR (Rupee)", 0.0)])
        self.assertEqual(r["label"], "Neutral")
        self.assertTrue(r["available"])

    def test_unavailable_when_too_little_data(self):
        for data in ([], [ind("S&P 500", 1.0)], [ind("S&P 500", None), ind("Brent Crude Oil", None)],
                     [ind("Gold Futures", 5.0), ind("WTI Crude Oil", 5.0)]):
            r = compute_macro_sentiment(data)
            self.assertFalse(r["available"], data)
            self.assertEqual(r["label"], "Neutral")
            self.assertEqual(r["score"], 0.0)

    def test_score_bounded(self):
        r = compute_macro_sentiment([ind("S&P 500", 50), ind("Nasdaq", 50), ind("Brent Crude Oil", -50),
                                     ind("US Dollar Index (DXY)", -50)])
        self.assertLessEqual(r["score"], 1.0)


def make_tech(lp, sma50, sma200, rsi):
    return {"last_price": lp, "sma_50": sma50, "sma_200": sma200, "rsi_14": rsi}


BULL = {"name": "Cup & Handle", "direction": "Bullish", "quality_score": 88,
        "target_price": 118.0, "stop_loss": 96.0, "entry_trigger": 101.0}
BEAR = {"name": "Head & Shoulders", "direction": "Bearish", "quality_score": 86,
        "target_price": 85.0, "stop_loss": 106.0, "entry_trigger": 99.0}


class VerdictInvariantTests(unittest.TestCase):
    """For every combination of inputs the levels must agree with the verdict direction."""

    def test_levels_consistent_across_input_grid(self):
        lp = 100.0
        patterns = [[], [BULL], [BEAR]]
        smas = [(90.0, 80.0), (110.0, 120.0), (95.0, 105.0), (None, None)]
        rsis = [None, 25.0, 50.0, 80.0]
        macros = [None, {"available": True, "score": 0.6, "label": "Bullish"},
                  {"available": True, "score": -0.6, "label": "Bearish"}]
        news = [None, {"bullish": 5, "bearish": 0, "total": 5}, {"bullish": 0, "bearish": 4, "total": 4}]
        funds = [None, {"available": False}, {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "roe_pct": 20}]
        # Deliberately hostile risk-tool output: stop above price, target below price
        risks = [{}, {"suggested_target_price": 90.0, "suggested_stop_loss": 120.0},
                 {"suggested_target_price": 112.0, "suggested_stop_loss": 93.0}]

        seen = set()
        for pat, (s50, s200), rsi, mac, nw, fu, risk in itertools.product(patterns, smas, rsis, macros, news, funds, risks):
            ctx = {"news": nw, "macro": mac, "fundamental": fu, "historical": {"pct_change_30d": 4.0}}
            sig = Synth.compute_quantitative_verdict("TEST", "Test Co", lp, make_tech(lp, s50, s200, rsi), risk, pat, {}, ctx)
            v = sig["action_verdict"]
            seen.add(v)
            target, stop = rs(sig["when_to_sell_target"]), rs(sig["stop_loss"])
            label = (v, pat and pat[0]["direction"], s50, rsi, mac and mac["label"], risk)
            if v in ("BUY", "ACCUMULATE"):
                self.assertTrue(stop < lp < target, label)
                entry_hi = float(sig["when_to_buy_entry"].split("-")[1])
                entry_lo = rs(sig["when_to_buy_entry"])
                self.assertTrue(entry_lo < entry_hi < target, (label, sig["when_to_buy_entry"]))
            elif v == "SELL":
                self.assertTrue(target < lp < stop, label)
            else:  # HOLD defensive: downside target / upside stop ; HOLD range: upside target / downside stop
                if sig["when_to_buy_entry"].startswith("Hold existing"):
                    self.assertTrue(target < lp < stop, label)
                else:
                    self.assertTrue(stop < lp < target, label)
            self.assertTrue(0 <= sig["confidence_percentage"] <= 92)
            self.assertTrue(sig["confidence_rating"].startswith(("HIGH", "MEDIUM", "LOW")))
        self.assertEqual(seen, {"BUY", "ACCUMULATE", "HOLD", "SELL"}, "grid should reach every verdict")

    def test_clear_bullish_setup_is_buy(self):
        ctx = {"news": {"bullish": 5, "bearish": 0, "total": 5},
               "macro": {"available": True, "score": 0.5, "label": "Bullish"},
               "fundamental": {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "roe_pct": 22},
               "historical": {"pct_change_30d": 6.0}}
        sig = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 92, 85, 55), {}, [BULL], {}, ctx)
        self.assertEqual(sig["action_verdict"], "BUY")
        self.assertTrue(sig["confidence_rating"].startswith("HIGH"))

    def test_clear_bearish_setup_is_sell(self):
        ctx = {"news": {"bullish": 0, "bearish": 5, "total": 5},
               "macro": {"available": True, "score": -0.5, "label": "Bearish"}}
        sig = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 112, 120, 75), {}, [BEAR], {}, ctx)
        self.assertEqual(sig["action_verdict"], "SELL")

    def test_single_signal_is_not_enough_to_sell_or_buy(self):
        # Downtrend only (no pattern, neutral RSI): one bearish signal -> HOLD, not SELL
        down = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 110, 120, 40), {}, [], {}, None)
        self.assertEqual(down["action_verdict"], "HOLD")
        # Same downtrend plus bearish news -> two agreeing signals -> SELL
        ctx = {"news": {"bullish": 0, "bearish": 5, "total": 5}}
        sell = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 110, 120, 40), {}, [], {}, ctx)
        self.assertEqual(sell["action_verdict"], "SELL")
        # Uptrend only, soft RSI -> HOLD ; add healthy RSI -> ACCUMULATE
        up = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 90, 80, 40), {}, [], {}, None)
        self.assertEqual(up["action_verdict"], "HOLD")
        up2 = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 90, 80, 55), {}, [], {}, None)
        self.assertEqual(up2["action_verdict"], "ACCUMULATE")

    def test_more_agreeing_evidence_never_lowers_bullish_score(self):
        base = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {})["score"]
        more = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL,
                              {"news": {"bullish": 4, "bearish": 0, "total": 4}})["score"]
        self.assertGreaterEqual(more, base - 1e-9)

    def test_missing_inputs_are_excluded_not_defaulted(self):
        ev = score_evidence(100.0, {}, None, None)
        names = [b["signal"] for b in ev["breakdown"]]
        self.assertEqual(names, ["pattern"])           # only "no pattern" counts; nothing invented
        self.assertLess(ev["coverage"], 0.5)
        self.assertEqual(Synth.compute_quantitative_verdict("T", "T", 100.0, {}, {}, [], {}, None)["action_verdict"], "HOLD")

    def test_unavailable_fundamentals_do_not_move_score(self):
        a = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {})
        b = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {"fundamental": {"available": False}})
        self.assertEqual(a["score"], b["score"])

    def test_peg_ratio_rewards_garp_and_penalizes_expensive_growth(self):
        from agents.synthesizer_agent import _fundamental_signal
        # High growth with premium P/E alone receives negative penalty (-0.3)
        pure_premium = {"available": True, "valuation_assessment": "High Growth / Premium Valuation"}
        val_pure, _ = _fundamental_signal(pure_premium)
        self.assertLess(val_pure, 0)

        # High growth with PEG < 1.0 (GARP justified) turns positive
        garp = {"available": True, "valuation_assessment": "High Growth / Premium Valuation", "peg_ratio": 0.85}
        val_garp, note_garp = _fundamental_signal(garp)
        self.assertGreater(val_garp, 0)
        self.assertIn("attractive growth at discount", note_garp)

        # Low P/E with poor growth / negative PEG is dampened compared to genuine value
        true_value = {"available": True, "valuation_assessment": "Undervalued / Value Opportunity"}
        val_true, _ = _fundamental_signal(true_value)
        trap_value = {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "peg_ratio": -1.2}
        val_trap, note_trap = _fundamental_signal(trap_value)
        self.assertLess(val_trap, val_true)
        self.assertIn("growth concern", note_trap)

    def test_balance_sheet_and_order_book_signals(self):
        from agents.synthesizer_agent import _fundamental_signal
        # Healthy balance sheet (debt-free) and order book catalyst boost score
        strong_bs = {
            "available": True,
            "valuation_assessment": "Fairly Valued",
            "debt_to_equity": 8.0,
            "net_cash_status": "Net Cash Positive (Debt-Free)",
            "current_ratio": 1.6,
            "order_book_catalyst": "L&T bags mega order worth Rs 12,000 Cr"
        }
        val_strong, note_strong = _fundamental_signal(strong_bs)
        self.assertGreater(val_strong, 0)
        self.assertIn("virtually debt-free", note_strong)
        self.assertIn("order inflow", note_strong)

        # High leverage and weak working capital decrease score
        leveraged = {
            "available": True,
            "valuation_assessment": "Fairly Valued",
            "debt_to_equity": 210.0,
            "current_ratio": 0.72
        }
        val_weak, note_weak = _fundamental_signal(leveraged)
        self.assertLess(val_weak, 0)
        self.assertIn("high leverage", note_weak)
        self.assertIn("tight liquidity", note_weak)

    def test_contrary_pattern_dampens_score_and_flags_caution(self):
        from agents.synthesizer_agent import _pattern_signal
        bull_pat = {"name": "Cup & Handle", "direction": "Bullish", "quality_score": 90}
        bear_pat = {"name": "Bearish RSI Momentum Divergence", "direction": "Bearish", "quality_score": 85}

        # Solo bullish pattern
        q_solo, note_solo = _pattern_signal(bull_pat)
        self.assertEqual(q_solo, 0.90)

        # Bullish pattern countered by bearish divergence
        q_counter, note_counter = _pattern_signal(bull_pat, [bull_pat, bear_pat])
        self.assertLess(q_counter, q_solo)
        self.assertIn("Caution", note_counter)
        self.assertIn("Bearish RSI", note_counter)

    def test_institutional_volume_accumulation_and_distribution(self):
        from agents.synthesizer_agent import _volume_signal
        # Institutional accumulation
        val_acc, note_acc = _volume_signal(rvol=1.3, ud_ratio=1.45)
        self.assertGreater(val_acc, 0.4)
        self.assertIn("institutional accumulation", note_acc)

        # Institutional distribution
        val_dist, note_dist = _volume_signal(rvol=0.7, ud_ratio=0.60)
        self.assertLess(val_dist, 0)
        self.assertIn("institutional distribution", note_dist)

    def test_overhead_resistance_check_in_verdict(self):
        # When price is 99.5 and resistance is 100.0 (within 0.5%)
        tech = make_tech(99.5, 92, 85, 55)
        tech["swing_high_20"] = 100.0
        sig = Synth.compute_quantitative_verdict("T", "T", 99.5, tech, {}, [BULL], {}, None)
        self.assertIn("testing immediate overhead resistance", sig["key_rationale"])
        self.assertIn("breakout above Rs. 100.00", sig["actionable_recommendation"])

    def test_bearish_divergence_warning_in_verdict(self):
        bear_div = {"name": "Bearish RSI Momentum Divergence", "direction": "Bearish", "quality_score": 85}
        sig = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 92, 85, 55), {}, [BULL, bear_div], {}, None)
        self.assertIn("Bearish RSI Divergence detected", sig["key_rationale"])

    def test_technical_agent_text_includes_institutional_volume_and_swing_levels(self):
        from agents.technical_agent import TechnicalAnalysisAgent
        class FakeTechEngine:
            def analyze_symbol(self, sym):
                return {
                    "last_price": 2500.0,
                    "rsi_14": 58.2,
                    "sma_50": 2420.0,
                    "sma_200": 2200.0,
                    "bollinger_upper": 2580.0,
                    "bollinger_lower": 2350.0,
                    "bollinger_pct_b": 0.65,
                    "up_down_vol_ratio": 1.42,
                    "swing_high_20": 2550.0,
                    "swing_low_20": 2380.0,
                    "pct_from_52w_high": -4.5,
                    "technical_signals": ["Bullish Trend", "RSI Momentum"],
                    "detected_patterns": []
                }
        out = TechnicalAnalysisAgent(FakeTechEngine()).run("RELIANCE")
        self.assertIn("Inst. Volume: Accumulation (1.42x U/D)", out["analysis"])
        self.assertIn("20D Swing Range: [Rs.2380.00 - Rs.2550.00]", out["analysis"])
        self.assertIn("52W High Gap: -4.5%", out["analysis"])

    def test_synthesizer_report_includes_fundamentals_and_structural_levels(self):
        agent_outputs = {
            "technical": {
                "raw_indicators": {
                    "last_price": 100.0,
                    "sma_50": 92.0,
                    "sma_200": 85.0,
                    "rsi_14": 55.0,
                    "up_down_vol_ratio": 1.35,
                    "swing_high_20": 105.0,
                    "swing_low_20": 94.0,
                    "pct_from_52w_high": -3.2,
                },
                "detected_patterns": [BULL]
            },
            "fundamental": {
                "raw_fundamentals": {
                    "pe_ratio": 22.5,
                    "peg_ratio": 1.15,
                    "valuation_assessment": "Fairly Valued",
                    "debt_to_equity": 12.0,
                    "current_ratio": 1.8,
                    "net_cash_status": "Net Cash Positive (Debt-Free)",
                    "order_book_catalyst": "Bags Rs 1,200 Cr EPC order"
                },
                "upcoming_events": {}
            },
            "news_sentiment": {
                "analysis": "Business activity is overall Positive with 3 new contract wins."
            }
        }
        res = Synth().run("TEST", "Test Ltd", agent_outputs)
        report = res["final_report"]
        self.assertIn("**Institutional Flow**", report)
        self.assertIn("Institutional Accumulation", report)
        self.assertIn("**20D Swing Levels**", report)
        self.assertIn("**Valuation & Balance Sheet**", report)
        self.assertIn("PEG: 1.15", report)
        self.assertIn("Net Cash Positive", report)
        self.assertIn("Order Pipeline / Backlog", report)
        self.assertIn("Verified Business Activity", report)

    def test_quick_picks_includes_institutional_flow(self):
        from main import build_quick_picks_section
        symbols_list = [{"symbol": "BEL", "name": "Bharat Electronics", "sector": "Defence"}]
        results_dict = {
            "BEL": {
                "name": "Bharat Electronics",
                "sector": "Defence",
                "result": {
                    "last_price": 300.0,
                    "structured_signal": {
                        "action_verdict": "BUY",
                        "confidence_rating": "HIGH (88%)",
                        "when_to_buy_entry": "Rs. 295.00 - 302.00",
                        "when_to_sell_target": "Rs. 330.00",
                        "stop_loss": "Rs. 285.00",
                        "chart_patterns": "Cup & Handle",
                        "holding_horizon": "1-3 Weeks"
                    },
                    "agent_outputs": {
                        "technical": {
                            "raw_indicators": {
                                "up_down_vol_ratio": 1.45
                            }
                        }
                    }
                }
            }
        }
        md = build_quick_picks_section(symbols_list, results_dict, None)
        self.assertIn("Inst. Flow", md)
        self.assertIn("Accumulation (1.4x)", md)

    def test_kite_portfolio_diagnostics_and_actions(self):
        from tools.kite_portfolio import KitePortfolioEngine
        test_holdings = [
            {
                "symbol": "BEL",
                "quantity": 100,
                "average_price": 280.0,
                "last_price": 305.0,
                "invested_value": 28000.0,
                "current_value": 30500.0,
                "pnl": 2500.0,
                "pnl_pct": 8.93
            },
            {
                "symbol": "TCS",
                "quantity": 10,
                "average_price": 3900.0,
                "last_price": 3800.0,
                "invested_value": 39000.0,
                "current_value": 38000.0,
                "pnl": -1000.0,
                "pnl_pct": -2.56
            }
        ]
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "port_test.db"))
            cm.save_agent_output("BEL", "Fundamental Analyst Agent", {
                "raw_fundamentals": {
                    "available": True,
                    "roe_pct": 24.0,
                    "earnings_growth_pct": 22.0,
                    "revenue_growth_pct": 19.0,
                    "peg_ratio": 0.95,
                    "pe_ratio": 22.0,
                    "net_cash_status": "Net Cash Positive",
                    "profit_margin_pct": 18.0,
                }
            })
            engine = KitePortfolioEngine(cache_manager=cm)
            engine.local_holdings_path = os.path.join(d, "my_holdings.json")
            engine.token_path = os.path.join(d, "kite_token.json")

            res = engine.evaluate_portfolio(test_holdings)
            summary = res["summary"]
            self.assertEqual(summary["total_holdings"], 2)
            self.assertEqual(summary["total_invested"], 67000.0)
            self.assertGreater(summary["current_value"], 0)
            self.assertIn("total_pnl", summary)
            self.assertGreater(summary["total_pnl_pct"], 0)
            self.assertEqual(summary["profitable_count"], 1)
            self.assertEqual(summary["losing_count"], 1)

            holdings = res["holdings"]
            bel = next(h for h in holdings if h["symbol"] == "BEL")
            self.assertIn("COMPOUNDER", bel["long_term_action"])
            self.assertTrue(any(w in bel["swing_action"].lower() for w in ["trailing stop", "stop loss", "target", "resistance", "gains", "accumulation", "entry"]))

            rep_path = engine.generate_portfolio_report(
                output_path=os.path.join(d, "Portfolio_Holdings_Test.md"),
                holdings=test_holdings,
            )
            self.assertTrue(os.path.exists(rep_path))
            with open(rep_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("Portfolio Diagnostics & Strategic Action Report", content)
            self.assertIn("BEL", content)
            self.assertIn("Holdings Action Matrix", content)
            self.assertIn("Advisory Mode", content)

    def test_invalid_price_yields_no_levels(self):
        for bad in (None, "N/A", float("nan"), 0, -5):
            sig = Synth.compute_quantitative_verdict("T", "T", bad, {}, {}, [BULL], {}, None)
            self.assertEqual(sig["action_verdict"], "HOLD", bad)
            self.assertEqual(sig["confidence_percentage"], 0)
            for k in ("when_to_buy_entry", "when_to_sell_target", "stop_loss", "long_term_target"):
                self.assertEqual(sig[k], "N/A", (bad, k))

    def test_frontend_price_string_format(self):
        sig = Synth.compute_quantitative_verdict("T", "T", 123.456, make_tech(123.456, 110, 100, 55), {}, [BULL], {}, None)
        import re
        self.assertRegex(sig["when_to_sell_target"], r"^Rs\. \d+(\.\d+)?$")
        self.assertRegex(sig["stop_loss"], r"^Rs\. \d+(\.\d+)?$")
        self.assertRegex(sig["when_to_buy_entry"], r"^Rs\. \d+\.\d{2} - \d+\.\d{2}$")

    def test_thresholds_are_ordered(self):
        self.assertLess(SELL_THRESHOLD, 0)
        self.assertLess(ACCUMULATE_THRESHOLD, BUY_THRESHOLD)


class FakeNewsEngine:
    def __init__(self, items):
        self.items = items

    def fetch_stock_news(self, symbol, company_name=""):
        return self.items


class NewsAgentTests(unittest.TestCase):
    def test_counts_mildly_labels_and_exposes_score(self):
        items = [{"title": "a", "sentiment_label": "Mildly Bullish"}, {"title": "b", "sentiment_label": "Bullish"},
                 {"title": "c", "sentiment_label": "Bearish"}, {"title": "d", "sentiment_label": "Neutral"}]
        out = NewsSentimentAgent(FakeNewsEngine(items)).run("X", "X Ltd")
        self.assertEqual(out["news_score"]["bullish"], 2)
        self.assertEqual(out["news_score"]["bearish"], 1)
        self.assertIn("Positive", out["analysis"])

    def test_no_news_is_reported_as_unavailable(self):
        out = NewsSentimentAgent(FakeNewsEngine([])).run("X", "X Ltd")
        self.assertEqual(out["news_score"]["total"], 0)
        self.assertIn("No recent news", out["analysis"])

    def test_filters_broker_recommendation_and_ticker_spam(self):
        from tools.news_tools import is_recommendation_spam
        # Broker recommendation headlines must be rejected as spam
        self.assertTrue(is_recommendation_spam("Buy Reliance with target price of Rs 3,400: Brokerage Radar"))
        self.assertTrue(is_recommendation_spam("Stocks to watch today: HDFC Bank, ICICI Bank, Swiggy"))
        self.assertTrue(is_recommendation_spam("Share price target for 2026: Experts recommend Accumulate"))
        self.assertTrue(is_recommendation_spam("Bharat Electronics Ltd. Share Price, Stock Price - NSE/BSE Live"))

        # Genuine business activity headlines must NOT be rejected
        self.assertFalse(is_recommendation_spam("L&T Construction bags mega orders worth Rs 12,000 crore from Saudi Aramco"))
        self.assertFalse(is_recommendation_spam("Aether Industries commissions new 2,000 MTPA manufacturing facility in Surat"))
        self.assertFalse(is_recommendation_spam("Bharat Electronics secures Rs 1,150 crore communication contract from MoD"))
        self.assertFalse(is_recommendation_spam("Ambuja Cements acquires 46% stake in Orient Cement"))

    def test_classifies_business_activity_accurately(self):
        from tools.news_tools import classify_business_activity
        cat1, badge1 = classify_business_activity("L&T bags mega EPC order worth Rs 15,000 Cr")
        self.assertEqual(cat1, "Orders & Contracts")
        self.assertIn("Order", badge1)

        cat2, badge2 = classify_business_activity("Tata Motors acquires 51% stake in European EV battery maker")
        self.assertEqual(cat2, "M&A & Partnerships")
        self.assertIn("M&A", badge2)

        cat3, badge3 = classify_business_activity("Dixon Tech commissions new smartphone manufacturing facility in Noida")
        self.assertEqual(cat3, "Capacity & Expansion")
        self.assertIn("Expansion", badge3)

        cat4, badge4 = classify_business_activity("Q2 net profit surges 28% YoY to Rs 450 Cr driven by margin expansion")
        self.assertEqual(cat4, "Financial Results")
        self.assertIn("Earnings", badge4)


class CacheManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "cache.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def candles(self, n, start_close=100.0):
        return [{"symbol": "AAA", "date": f"2026-01-{i + 1:02d}", "open": start_close + i, "high": start_close + i + 1,
                 "low": start_close + i - 1, "close": start_close + i, "volume": 1000 + i} for i in range(n)]

    def test_wal_enabled(self):
        with self.cm._get_connection() as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")

    def test_candle_limit_in_sql_keeps_prev_close(self):
        self.cm.save_historical_candles(self.candles(20))
        full = self.cm.get_cached_candles("AAA", limit_days=500)
        tail = self.cm.get_cached_candles("AAA", limit_days=5)
        self.assertEqual(len(full), 20)
        self.assertEqual(len(tail), 5)
        self.assertEqual([c["DATE"] for c in tail], [c["DATE"] for c in full[-5:]])
        self.assertEqual(tail[0]["PREV_CLOSE"], full[-6]["CLOSE_PRICE"])      # true previous close, not own close
        self.assertEqual(full[0]["PREV_CLOSE"], full[0]["CLOSE_PRICE"])        # legacy behaviour for first row
        self.assertEqual(self.cm.get_cached_candles("AAA", limit_days=1)[0]["DATE"], "2026-01-20")
        self.assertEqual(self.cm.get_cached_candles("NOPE"), [])

    def test_replace_symbol_drops_old_basis(self):
        self.cm.save_historical_candles(self.candles(10))
        self.cm.save_historical_candles(self.candles(3, start_close=50.0), replace_symbol="AAA")
        rows = self.cm.get_cached_candles("AAA")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["CLOSE_PRICE"], 50.0)

    def test_macro_cache_latest_per_indicator_with_pct(self):
        self.cm.save_macro([{"indicator": "S&P 500", "value": 1.0, "unit": "pts", "summary": "a", "pct_change": 0.5}])
        self.cm.save_macro([{"indicator": "S&P 500", "value": 2.0, "unit": "pts", "summary": "b", "pct_change": -0.3},
                            {"indicator": "Nasdaq", "value": 9.0, "unit": "pts", "summary": "c", "pct_change": None}])
        rows = {r["indicator"]: r for r in self.cm.get_cached_macro(12)}
        self.assertEqual(len(rows), 2)                      # no duplicates
        self.assertEqual(rows["S&P 500"]["value"], 2.0)     # latest wins
        self.assertEqual(rows["S&P 500"]["pct_change"], -0.3)
        self.assertIsNone(rows["Nasdaq"]["pct_change"])

    def test_bulk_latest_outputs(self):
        self.cm.save_agent_output("AAA", "Technical Analysis Agent", {"v": 1})
        self.cm.save_agent_output("BBB", "Technical Analysis Agent", {"v": 2})
        self.cm.save_agent_output("AAA", "Risk & Volatility Agent", {"v": 3})
        bulk = self.cm.get_latest_agent_outputs_bulk()
        self.assertEqual(bulk["AAA"]["Technical Analysis Agent"]["output"], {"v": 1})
        self.assertEqual(bulk["BBB"]["Technical Analysis Agent"]["output"], {"v": 2})
        self.assertEqual(bulk["AAA"]["Risk & Volatility Agent"]["output"], {"v": 3})
        self.assertTrue(self.cm.get_agent_runs_marker())

    def test_fundamentals_roundtrip(self):
        self.assertIsNone(self.cm.get_cached_fundamentals("AAA"))
        self.cm.save_fundamentals("aaa", {"available": True, "pe_ratio": 12.5})
        hit = self.cm.get_cached_fundamentals("AAA")
        self.assertEqual(hit["data"]["pe_ratio"], 12.5)

    def test_reinit_is_idempotent_and_migrates_legacy_macro_table(self):
        path = os.path.join(self.tmp.name, "legacy.db")
        import sqlite3
        legacy = sqlite3.connect(path)
        try:
            legacy.execute("CREATE TABLE macro_cache (indicator_name TEXT, fetch_date TEXT, value REAL, unit TEXT, summary TEXT, PRIMARY KEY (indicator_name, fetch_date))")
            legacy.execute("CREATE TABLE bhavcopy_cache (x INTEGER)")
            legacy.commit()
        finally:
            legacy.close()
        cm = CacheManager(db_path=path)
        CacheManager(db_path=path)
        cm.save_macro([{"indicator": "S&P 500", "value": 1.0, "unit": "pts", "summary": "s", "pct_change": 1.1}])
        self.assertEqual(cm.get_cached_macro(12)[0]["pct_change"], 1.1)
        with cm._get_connection() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='bhavcopy_cache'").fetchone())


class LongTermTests(unittest.TestCase):
    def test_no_price_means_no_target(self):
        from tools.long_term_strategy import long_term_engine
        for sym in ("LT", "ZZZUNKNOWN"):
            r = long_term_engine.evaluate_long_term_stock(sym, last_price=None, short_verdict="BUY")
            self.assertEqual(r["long_term_target"], "N/A")
            self.assertIsNone(r["long_term_target_num"])
            self.assertEqual(r["target_basis"], "indicative_scenario")

    def test_target_is_scenario_multiple_of_price(self):
        from tools.long_term_strategy import long_term_engine
        r_buy = long_term_engine.evaluate_long_term_stock("ZZZUNKNOWN", last_price=200.0, short_verdict="BUY")
        r_sell = long_term_engine.evaluate_long_term_stock("ZZZUNKNOWN", last_price=200.0, short_verdict="SELL")
        # 8.0% baseline indicative CAGR over 3 years -> 200 * (1.08^3) = 251.94, decoupled from short_verdict
        self.assertEqual(r_buy["long_term_target_num"], 251.94)
        self.assertEqual(r_buy["long_term_verdict"], r_sell["long_term_verdict"])
        self.assertEqual(r_buy["long_term_target_num"], r_sell["long_term_target_num"])
        self.assertIn("indicative", r_buy["long_term_thesis"])


try:
    import pandas as pd
    from tools.historical_data_tools import HistoricalDataEngine
    HAVE_PANDAS = True
except ImportError:  # pandas not installed: history tests are skipped
    HAVE_PANDAS = False


@unittest.skipUnless(HAVE_PANDAS, "pandas not installed")
class IncrementalHistoryTests(unittest.TestCase):
    """Price history refresh: only missing days are downloaded unless the series was re-adjusted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cm = CacheManager(db_path=os.path.join(self.tmp.name, "cache.db"))
        outer = self

        class FakeEngine(HistoricalDataEngine):
            def __init__(self):
                super().__init__(cache_manager=cm)
                self.calls = []          # (start, period)
                self.source = None       # callable(start) -> DataFrame
                self.fail = False

            def fetch_from_source(self, symbol, period="5y", start=None):
                self.calls.append((start, period))
                if self.fail:
                    return pd.DataFrame()
                return outer.make_df(outer.source_rows(start))

        self.engine = FakeEngine()
        self.cm = cm
        # Fixed clock: 18:00 IST (after the close + vendor buffer) on the latest business day, so the tests do not
        # depend on the time of day they run. Series ends on that day; cached history ends 8 business days earlier.
        from datetime import datetime as _dt, time as _t
        from tools import market_calendar as _mc
        self.today = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=1)[0]
        self._clock = unittest.mock.patch.object(
            _mc, "now_ist", return_value=_dt.combine(self.today.date(), _t(18, 0), tzinfo=_mc.IST))
        self._clock.start()
        self.all_days = pd.bdate_range(end=self.today, periods=60)
        self.rows = {d: 100.0 + i for i, d in enumerate(self.all_days)}
        self.cutoff_old = self.all_days[-8]    # cached history ends here
        self.shift = 1.0
        self.splits = {}

    def tearDown(self):
        self._clock.stop()
        self.tmp.cleanup()

    def source_rows(self, start):
        days = [d for d in self.all_days if (start is None or d >= pd.Timestamp(start))]
        return [(d, self.rows[d] * self.shift, self.splits.get(d, 0.0)) for d in days]

    @staticmethod
    def make_df(rows):
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame({
            "DATE": [r[0] for r in rows],
            "OPEN_PRICE": [r[1] for r in rows], "HIGH_PRICE": [r[1] + 1 for r in rows],
            "LOW_PRICE": [r[1] - 1 for r in rows], "CLOSE_PRICE": [r[1] for r in rows],
            "ADJ_CLOSE": [r[1] for r in rows], "VOLUME": [1000] * len(rows),
            "DIVIDENDS": [0.0] * len(rows), "SPLITS": [r[2] for r in rows],
        })
        return df

    def seed_cache(self):
        """Store history up to cutoff_old (as a previous run would have)."""
        seed = [(d, self.rows[d], 0.0) for d in self.all_days if d <= self.cutoff_old]
        self.cm.save_historical_candles(HistoricalDataEngine._df_to_records("AAA", self.make_df(seed)))

    def test_cold_start_does_one_full_download(self):
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(df), len(self.all_days))
        self.assertEqual(self.engine.calls, [(None, "5y")])

    def test_fresh_cache_needs_no_network(self):
        self.engine.sync_symbol_data("AAA")
        self.engine.calls.clear()
        self.engine.sync_symbol_data("AAA")
        self.assertEqual(self.engine.calls, [])

    def test_stale_cache_downloads_only_missing_days(self):
        self.seed_cache()
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(self.engine.calls), 1)
        start, period = self.engine.calls[0]
        self.assertIsNotNone(start, "must use a start date, not a 5y period")
        self.assertLess(pd.Timestamp(start), self.cutoff_old + pd.Timedelta(days=1))
        self.assertEqual(len(df), len(self.all_days))
        self.assertEqual(df["CLOSE_PRICE"].iloc[-1], self.rows[self.all_days[-1]])

    def test_readjusted_history_triggers_full_replace(self):
        self.seed_cache()
        self.shift = 0.95                       # dividend re-adjustment: every historical close moved 5%
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(self.engine.calls), 2)
        self.assertIsNotNone(self.engine.calls[0][0])                  # incremental attempt first
        self.assertEqual(self.engine.calls[1], (None, "5y"))           # then full refresh
        # one consistent basis: every stored close equals the new adjusted value
        for d, close in zip(df["DATE"], df["CLOSE_PRICE"]):
            self.assertAlmostEqual(close, self.rows[d] * 0.95, places=6)

    def test_split_in_window_triggers_full_replace(self):
        self.seed_cache()
        self.splits[self.all_days[-3]] = 2.0
        self.engine.sync_symbol_data("AAA")
        self.assertEqual(self.engine.calls[-1], (None, "5y"))

    def test_source_down_serves_cached_history(self):
        self.seed_cache()
        self.engine.fail = True
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(df), len([d for d in self.all_days if d <= self.cutoff_old]))

    def test_small_limit_does_not_truncate_later_larger_request(self):
        self.engine.sync_symbol_data("AAA")
        self.engine.df_cache.clear()
        self.assertEqual(len(self.engine.load_symbol_history("AAA", limit_days=10)), 10)
        self.assertEqual(len(self.engine.load_symbol_history("AAA", limit_days=50)), 50)   # used to return 10

    def test_sync_all_symbols_parallel(self):
        res = self.engine.sync_all_symbols([{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}])
        self.assertEqual(res, {"AAA": True, "BBB": True, "CCC": True})


# =============================================================================
# Fundamental Picks Engine Tests
# =============================================================================

class TestFundamentalPicksEngine(unittest.TestCase):
    """Unit tests for tools/fundamental_picks.py scoring engine."""

    def _make_synth(self, **overrides):
        """Build a minimal synth_res dict suitable for scoring."""
        base = {
            "last_price": 500.0,
            "peg_ratio": 1.2,
            "pe_ratio": 20.0,
            "debt_to_equity": 0.4,
            "current_ratio": 1.8,
            "net_cash_status": "low debt",
            "valuation_assessment": "Fairly Valued",
            "structured_signal": {
                "action_verdict": "BUY",
                "confidence_rating": "HIGH (82%)",
                "long_term_verdict": "BUY",
                "long_term_target": "Rs. 750",
                "when_to_sell_target": "Rs. 650",
                "stop_loss": "Rs. 450",
                "upcoming_events_note": "Q2 results expected next week",
            },
            "agent_outputs": {},
        }
        base.update(overrides)
        return base

    def _make_tech(self, pct52w=-15.0, ud=1.3, swing_low=480.0):
        """Build a minimal tech raw_indicators dict."""
        return {
            "raw_indicators": {
                "pct_from_52w_high": pct52w,
                "up_down_vol_ratio": ud,
                "swing_low_20": swing_low,
                "last_price": 500.0,
            }
        }

    def test_garp_stock_scores_above_expensive_growth(self):
        """A GARP stock (PEG 1.2, Fairly Valued, net cash) must outscore an expensive one (PEG 3.5)."""
        from tools.fundamental_picks import score_fundamental_pick

        garp = self._make_synth(peg_ratio=1.2, valuation_assessment="Fairly Valued", net_cash_status="net cash positive")
        tech = self._make_tech(pct52w=-12.0, ud=1.4)

        expensive = self._make_synth(peg_ratio=3.5, valuation_assessment="High growth priced in", net_cash_status="moderate debt")
        # Put expensive stock 2% from 52W high — should be ineligible
        tech_expensive = self._make_tech(pct52w=-1.5)

        garp_pick = score_fundamental_pick("GARP", garp, tech)
        exp_pick  = score_fundamental_pick("EXP", expensive, tech_expensive)

        self.assertIsNotNone(garp_pick, "GARP stock should be eligible")
        self.assertIsNone(exp_pick, "Stock within 3% of 52W high is ineligible")
        self.assertGreater(garp_pick["score"], 30, "GARP stock should have strong positive score")

    def test_overvalued_stock_at_52w_high_excluded(self):
        """Overvalued stock near 52W high must be ineligible (fails two gates)."""
        from tools.fundamental_picks import score_fundamental_pick

        synth = self._make_synth(peg_ratio=4.0, valuation_assessment="Overvalued")
        tech  = self._make_tech(pct52w=-1.0)   # near 52W high

        pick = score_fundamental_pick("OVERVAL", synth, tech)
        self.assertIsNone(pick, "Overvalued stock near 52W high must be excluded")

    def test_overvalued_with_exceptional_peg_allowed(self):
        """An 'overvalued' label stock with PEG < 1.0 (genuine GARP) may still qualify."""
        from tools.fundamental_picks import score_fundamental_pick

        # PEG 0.7 overrides the valuation label gate
        synth = self._make_synth(peg_ratio=0.7, valuation_assessment="Overvalued")
        tech  = self._make_tech(pct52w=-18.0)

        pick = score_fundamental_pick("GARPVAL", synth, tech)
        self.assertIsNotNone(pick, "Exceptional PEG < 1.0 should override overvalued gate")
        # Must have received PEG bonus AND valuation penalty
        self.assertGreater(pick["score"], 10)

    def test_sell_verdict_excluded(self):
        """SELL-rated stock must always be excluded regardless of valuation."""
        from tools.fundamental_picks import score_fundamental_pick

        synth = self._make_synth(peg_ratio=0.5, valuation_assessment="Undervalued")
        synth["structured_signal"]["action_verdict"] = "SELL"
        tech  = self._make_tech(pct52w=-20.0)

        pick = score_fundamental_pick("SELLME", synth, tech)
        self.assertIsNone(pick, "SELL verdict must be a hard gate regardless of fundamentals")

    def test_top10_cap_enforced(self):
        """build_fundamental_picks_section must return at most 10 stocks."""
        from tools.fundamental_picks import build_fundamental_picks_section

        # Build 15 eligible symbols
        symbols_list = [{"symbol": f"ST{i:02d}", "name": f"Stock {i}", "sector": "Test"} for i in range(15)]

        # results_dict: each stock is a good GARP stock
        results_dict = {}
        for i, item in enumerate(symbols_list):
            sym = item["symbol"]
            results_dict[sym] = {
                "name": item["name"],
                "sector": item["sector"],
                "result": {
                    "last_price": 500.0,
                    "peg_ratio": 1.1,
                    "valuation_assessment": "Fairly Valued",
                    "net_cash_status": "net cash positive",
                    "structured_signal": {
                        "action_verdict": "BUY",
                        "long_term_verdict": "BUY",
                        "long_term_target": "Rs. 700",
                        "when_to_sell_target": "Rs. 650",
                        "stop_loss": "Rs. 450",
                        "upcoming_events_note": "",
                    },
                    "agent_outputs": {
                        "technical": {
                            "raw_indicators": {
                                "pct_from_52w_high": -15.0,
                                "up_down_vol_ratio": 1.3,
                                "swing_low_20": 475.0,
                                "last_price": 500.0,
                            }
                        }
                    },
                },
            }

        md = build_fundamental_picks_section(symbols_list, results_dict, None)
        # Count rows in the markdown table (each data row starts with "| {number}")
        import re
        rows = re.findall(r"^\| \d+ \|", md, re.MULTILINE)
        self.assertLessEqual(len(rows), 10, f"Must return at most 10 picks, got {len(rows)}")
        self.assertGreater(len(rows), 0, "Should have at least 1 pick from 15 eligible stocks")

    def test_near_support_timing_tag(self):
        """Stock within 4% of swing_low_20 should get 'Near Support Floor' timing tag."""
        from tools.fundamental_picks import score_fundamental_pick

        synth = self._make_synth(peg_ratio=1.3, valuation_assessment="Fairly Valued")
        # last_price = 500, swing_low = 485 → 3.1% above low = near support
        tech  = self._make_tech(pct52w=-14.0, ud=1.2, swing_low=485.0)
        # Override last_price in tech to match
        tech["raw_indicators"]["last_price"] = 500.0

        pick = score_fundamental_pick("NEARSUPP", synth, tech)
        self.assertIsNotNone(pick)
        # Timing tag should reference support
        self.assertIn("Support", pick["timing_tag"], f"Expected 'Support' in timing_tag, got: {pick['timing_tag']}")

    def test_net_cash_gives_balance_sheet_bonus(self):
        """Net cash / debt-free status must add significant balance sheet score."""
        from tools.fundamental_picks import score_fundamental_pick

        net_cash = self._make_synth(net_cash_status="net cash positive", debt_to_equity=None)
        high_debt = self._make_synth(net_cash_status="high leverage", debt_to_equity=2.5)

        tech = self._make_tech(pct52w=-12.0)

        nc_pick = score_fundamental_pick("NETCASH", net_cash, tech)
        hd_pick = score_fundamental_pick("HDEBT",  high_debt, tech)

        self.assertIsNotNone(nc_pick)
        # High debt may still qualify but must score lower
        if hd_pick is not None:
            self.assertGreater(nc_pick["score"], hd_pick["score"],
                               "Net cash stock should outscore high-debt stock")

    def test_markdown_table_has_expected_columns(self):
        """The generated markdown must include all required column headers."""
        from tools.fundamental_picks import build_fundamental_picks_section

        symbols_list = [{"symbol": "TESTCO", "name": "Test Company", "sector": "Technology"}]
        results_dict = {
            "TESTCO": {
                "name": "Test Company",
                "sector": "Technology",
                "result": {
                    "last_price": 1200.0,
                    "peg_ratio": 1.4,
                    "valuation_assessment": "Fairly Valued",
                    "net_cash_status": "net cash positive",
                    "structured_signal": {
                        "action_verdict": "ACCUMULATE",
                        "long_term_verdict": "ACCUMULATE",
                        "long_term_target": "Rs. 1600",
                        "when_to_sell_target": "Rs. 1550",
                        "stop_loss": "Rs. 1100",
                        "upcoming_events_note": "Q3 results next month",
                    },
                    "agent_outputs": {
                        "technical": {
                            "raw_indicators": {
                                "pct_from_52w_high": -18.5,
                                "up_down_vol_ratio": 1.35,
                                "swing_low_20": 1160.0,
                                "last_price": 1200.0,
                            }
                        }
                    },
                },
            }
        }

        md = build_fundamental_picks_section(symbols_list, results_dict, None)
        for col in ("Symbol", "PEG", "Intrinsic Value", "Valuation", "52W", "Inst. Flow", "LT Rating", "Why Now", "Action"):
            self.assertIn(col, md, f"Column '{col}' missing from fundamental picks table")
        self.assertIn("TESTCO", md)
        self.assertIn("🏛️", md, "Section header emoji must be present")

    def test_intrinsic_value_boosts_fundamental_score(self):
        """Stocks with deep intrinsic value margin of safety score higher than fairly valued or overvalued stocks."""
        from tools.fundamental_picks import score_fundamental_pick

        synth = self._make_synth(peg_ratio=1.0, valuation_assessment="Fairly Valued")
        tech = self._make_tech(pct52w=-10.0, ud=1.2)

        fund_deep_value = {
            "forensic_analysis": {
                "verdict": "STRONG_BUY",
                "verdict_badge": "🟢 SOUND VALUE",
                "fair_value": 700.0,
                "margin_of_safety_pct": 40.0,  # 40% margin of safety
            }
        }

        fund_expensive = {
            "forensic_analysis": {
                "verdict": "HOLD",
                "fair_value": 400.0,
                "margin_of_safety_pct": -20.0,  # 20% overvalued vs intrinsic
            }
        }

        pick_deep = score_fundamental_pick("DEEP", synth, tech, fund_res=fund_deep_value)
        pick_exp = score_fundamental_pick("EXP", synth, tech, fund_res=fund_expensive)

        self.assertIsNotNone(pick_deep)
        self.assertIsNotNone(pick_exp)
        self.assertGreater(pick_deep["score"], pick_exp["score"])
        self.assertEqual(pick_deep["intrinsic_value"], 700.0)
        self.assertEqual(pick_deep["margin_of_safety_pct"], 40.0)


# =============================================================================
# Macro Risk Shield Engine Tests
# =============================================================================

class TestMacroRiskShieldEngine(unittest.TestCase):
    """Unit tests for tools/macro_risk_shield.py."""

    def test_risk_level_thresholds(self):
        from tools.macro_risk_shield import compute_risk_level

        low = compute_risk_level(0.40)
        self.assertEqual(low["risk_key"], "LOW")
        self.assertIn("🟢", low["risk_label"])

        elevated = compute_risk_level(0.05)
        self.assertEqual(elevated["risk_key"], "ELEVATED")
        self.assertIn("🟡", elevated["risk_label"])

        high = compute_risk_level(-0.35)
        self.assertEqual(high["risk_key"], "HIGH")
        self.assertIn("🟠", high["risk_label"])

        danger = compute_risk_level(-0.75)
        self.assertEqual(danger["risk_key"], "DANGER")
        self.assertIn("🔴", danger["risk_label"])

    def test_holding_shield_evaluates_sensitivity_and_pnl(self):
        from tools.macro_risk_shield import evaluate_holding_shield

        # High sensitivity cyclical holding (Banking) in HIGH risk
        bank_holding = {
            "symbol": "HDFCBANK",
            "sector": "Banking & Finance",
            "pnl_pct": 2.5,
            "current_value": 50000,
        }
        res_bank = evaluate_holding_shield(bank_holding, "HIGH")
        self.assertIn("REDUCE", res_bank["shield_action"])
        self.assertEqual(res_bank["urgency"], "high")

        # Defensive holding (Pharma) in HIGH risk
        pharma_holding = {
            "symbol": "SUNPHARMA",
            "sector": "Pharma / Healthcare",
            "pnl_pct": 5.0,
            "current_value": 30000,
        }
        res_pharma = evaluate_holding_shield(pharma_holding, "HIGH")
        self.assertIn("HOLD", res_pharma["shield_action"])
        self.assertEqual(res_pharma["urgency"], "none")

        # Losing holding in DANGER risk
        losing_holding = {
            "symbol": "TATASTEEL",
            "sector": "Metals & Mining",
            "pnl_pct": -6.5,
            "current_value": 20000,
        }
        res_losing = evaluate_holding_shield(losing_holding, "DANGER")
        self.assertIn("EXIT", res_losing["shield_action"])
        self.assertEqual(res_losing["urgency"], "critical")

    def test_macro_risk_shield_markdown_generation(self):
        from tools.macro_risk_shield import build_macro_risk_shield, build_macro_risk_shield_markdown

        macro_result = {
            "label": "Bearish",
            "score": -0.42,
            "available": True,
            "drivers": ["Brent Crude Oil +3.20% (headwind)", "US 10Y Yield +4.10% (headwind)"]
        }
        holdings = [
            {"symbol": "ICICIBANK", "sector": "Banking", "pnl_pct": 3.0, "current_value": 40000},
            {"symbol": "ITC", "sector": "FMCG", "pnl_pct": 8.0, "current_value": 30000}
        ]

        shield_data = build_macro_risk_shield(macro_result, holdings)
        self.assertEqual(shield_data["risk_key"], "HIGH")

        md = build_macro_risk_shield_markdown(shield_data)
        self.assertIn("Macro Risk Shield", md)
        self.assertIn("Protection Playbook", md)
        self.assertIn("Safe-Haven Sectors", md)
        self.assertIn("High-Risk Scheduled Events", md)
        self.assertIn("Portfolio Shield Actions", md)
        self.assertIn("ICICIBANK", md)
        self.assertIn("ITC", md)

    def test_defensive_sectors_and_scheduled_events(self):
        from tools.macro_risk_shield import DEFENSIVE_SECTORS, SCHEDULED_RISK_EVENTS

        self.assertIn("FMCG", DEFENSIVE_SECTORS)
        self.assertIn("Pharma / Healthcare", DEFENSIVE_SECTORS)
        self.assertTrue(any("FOMC" in e["event"] for e in SCHEDULED_RISK_EVENTS))
        self.assertTrue(any("Budget" in e["event"] for e in SCHEDULED_RISK_EVENTS))

    def test_no_order_placement_methods_exist_in_codebase(self):
        """Enforce strict read-only invariant: no order placement or modification methods permitted."""
        import glob
        forbidden_patterns = [
            ".place_order(",
            ".modify_order(",
            ".cancel_order(",
            ".order_margins(",
            ".place_gtt(",
            ".modify_gtt(",
            ".delete_gtt(",
            ".place_mf_order(",
            ".place_mf_sip(",
            ".basket_order_margins(",
            ".convert_position(",
            "kite.place_order",
            "kite.modify_order",
            "kite.cancel_order",
            "api.kite.trade/orders",
        ]
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        source_files = (
            glob.glob(os.path.join(repo_root, "tools", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(repo_root, "agents", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(repo_root, "api", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(repo_root, "storage", "**", "*.py"), recursive=True) +
            glob.glob(os.path.join(repo_root, "frontend", "src", "**", "*.ts"), recursive=True) +
            [
                os.path.join(repo_root, "main.py"),
                os.path.join(repo_root, "dashboard_server.py"),
                os.path.join(repo_root, "graph.py"),
                os.path.join(repo_root, "config.py"),
                os.path.join(repo_root, "generate_news_report.py"),
            ]
        )

        for filepath in source_files:
            if not os.path.exists(filepath):
                continue
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for pattern in forbidden_patterns:
                self.assertNotIn(
                    pattern,
                    content,
                    f"CRITICAL SAFETY VIOLATION: Forbidden order method '{pattern}' detected in {filepath}!"
                )


    def test_52w_high_metrics_computed_from_candles(self):
        """Verifies that 52-week high, low, and gap are computed accurately from candle series."""
        # Mock 250 daily candles with peak at 500.0 and last close at 420.0 (-16.0%)
        mock_candles = [
            {"HIGH_PRICE": 400.0, "LOW_PRICE": 350.0, "CLOSE_PRICE": 380.0}
            for _ in range(200)
        ]
        mock_candles.append({"HIGH_PRICE": 500.0, "LOW_PRICE": 480.0, "CLOSE_PRICE": 490.0}) # 52W High
        mock_candles.append({"HIGH_PRICE": 430.0, "LOW_PRICE": 410.0, "CLOSE_PRICE": 420.0}) # Latest close

        high_52w = max(float(c.get("HIGH_PRICE") or 0.0) for c in mock_candles)
        low_52w = min(float(c.get("LOW_PRICE") or 1e9) for c in mock_candles)
        last_p = float(mock_candles[-1]["CLOSE_PRICE"])
        pct_52w = round((last_p - high_52w) / high_52w * 100, 2)

        self.assertEqual(high_52w, 500.0)
        self.assertEqual(low_52w, 350.0)
        self.assertEqual(pct_52w, -16.0)

    def test_hardened_peg_ratio_handling_and_fallbacks(self):
        """Verifies PEG calculation guards against negative multiples and normalizes base effects."""
        from tools.fundamental_picks import score_fundamental_pick

        # 1. Normal valid PEG <= 0.8 receives maximum score
        synth_good = {"structured_signal": {"action_verdict": "BUY"}}
        fund_good = {"raw_fundamentals": {"peg_ratio": 0.75, "pe_ratio": 18.0, "net_cash_status": "Net Cash Positive"}}
        tech_good = {"raw_indicators": {"pct_from_52w_high": -12.0, "up_down_vol_ratio": 1.35}}
        pick_good = score_fundamental_pick("TEST1", synth_good, tech_good, fund_res=fund_good)
        self.assertIsNotNone(pick_good)
        self.assertIn("Exceptional PEG ≤0.8", pick_good["reasons"])

        # 2. Negative PEG is NOT scored as low PEG; receives penalty
        synth_neg = {"structured_signal": {"action_verdict": "BUY"}}
        fund_neg = {"raw_fundamentals": {"peg_ratio": -1.5, "pe_ratio": 15.0}}
        tech_neg = {"raw_indicators": {"pct_from_52w_high": -12.0}}
        pick_neg = score_fundamental_pick("TEST2", synth_neg, tech_neg, fund_res=fund_neg)
        self.assertIsNotNone(pick_neg)
        self.assertNotIn("Exceptional PEG ≤0.8", pick_neg["reasons"])
        self.assertIn("Earnings Contraction (Negative PEG)", pick_neg["reasons"])

    def test_market_scanner_candidate_exclusion_and_scoring(self):
        """Verifies market scanner excludes tracked symbols and correctly computes composite scores."""
        from tools.market_scanner import get_scan_candidates, load_existing_symbols, _cache_scan_results, get_latest_cached_scan

        existing = load_existing_symbols()
        candidates = get_scan_candidates()

        # All candidates must be outside symbols.json
        candidate_syms = {c["symbol"].upper() for c in candidates}
        overlap = existing.intersection(candidate_syms)
        self.assertEqual(len(overlap), 0, f"Market scanner candidates contain tracked symbols: {overlap}")

        # Cache & retrieval round-trip
        mock_results = [{
            "symbol": "TESTSCAN",
            "name": "Test Scanning Ltd",
            "sector": "Technology",
            "strength_score": 85,
            "tier": "⭐ TOP LEADER",
            "last_price": 1250.0,
            "high_52w": 1300.0,
            "low_52w": 850.0,
            "pct_from_52w_high": -3.8,
            "rsi_14": 62.5,
            "up_down_vol_ratio": 1.45,
            "rvol": 1.3,
            "pe_ratio": 22.5,
            "peg_ratio": 0.95,
            "roe_pct": 18.5,
            "signals": ["Stage 2 Bullish Trend", "Prime Leader High Proximity"],
            "evaluated_at": "2026-11-16 00:00:00"
        }]
        with tempfile.TemporaryDirectory() as d:
            scanner_db = os.path.join(d, "scanner_test.db")
            with unittest.mock.patch("tools.market_scanner.CACHE_DB_PATH", scanner_db):
                _cache_scan_results(mock_results)
                cached = get_latest_cached_scan()
        self.assertGreaterEqual(len(cached.get("stocks", [])), 1)
        self.assertEqual(cached["stocks"][0]["symbol"], "TESTSCAN")
        self.assertEqual(cached["stocks"][0]["strength_score"], 85)


class Phase1RegressionTests(unittest.TestCase):
    """Deterministic unit regression tests verifying Phase 1 (1.1–1.8) fixes with zero network calls."""

    def test_synthesizer_bfsi_exemptions_directional_rvol_and_pattern_match(self):
        from agents.synthesizer_agent import (
            _is_bfsi_sector,
            _pattern_signal,
            _volume_signal,
            _fundamental_signal,
        )

        self.assertTrue(_is_bfsi_sector("Financial Services"))
        self.assertTrue(_is_bfsi_sector("Private Sector Bank"))
        self.assertFalse(_is_bfsi_sector("Information Technology"))

        # "Bullish Reversal Watch" must score positive (not be dropped as non-exact "Bullish")
        pat_val, _ = _pattern_signal({"name": "Hammer", "direction": "Bullish Reversal Watch", "quality_score": 80})
        self.assertGreater(pat_val, 0.0)

        # High volume on a down day must score bearish distribution, not bullish surge
        vol_val, _ = _volume_signal(2.0, ud_ratio=0.7, day_change_pct=-3.2)
        self.assertLess(vol_val, 0.0)

        # BFSI sectors are exempt from non-bank D/E > 150, CR < 0.9, and CFO/PAT < 0.50 penalties
        bfsi_res = _fundamental_signal({
            "available": True,
            "sector": "Financial Services",
            "valuation_assessment": "Undervalued",
            "peg_ratio": 1.1,
            "roe_pct": 16.0,
            "debt_to_equity": 800.0,
            "current_ratio": 0.4,
            "forensic_verdict": "HOLD",
            "forensic_analysis": {"cash_conversion": {"cfo_to_pat_ratio": 0.2}},
        })
        self.assertIsNotNone(bfsi_res)
        self.assertNotIn("high leverage", bfsi_res[1].lower())
        self.assertNotIn("tight liquidity", bfsi_res[1].lower())
        self.assertNotIn("weak cash conversion", bfsi_res[1].lower())

        # Forensic red flag must still penalize even when yfinance fundamentals are unavailable
        trap_res = _fundamental_signal({
            "available": False,
            "forensic_verdict": "AVOID_OR_VALUE_TRAP",
            "forensic_analysis": {"verdict": "AVOID_OR_VALUE_TRAP"},
        })
        self.assertIsNotNone(trap_res)
        self.assertLess(trap_res[0], 0.0)

    def test_fundamental_picks_de_unit_normalization_and_bfsi(self):
        from tools.fundamental_picks import score_fundamental_pick

        synth = {"structured_signal": {"action_verdict": "BUY"}}
        tech = {"raw_indicators": {"pct_from_52w_high": -12.0, "up_down_vol_ratio": 1.3}}

        # yfinance reports 25.0% D/E meaning 0.25x debt/equity -> Strong B/S, not 25x High D/E
        low_de = score_fundamental_pick(
            "TESTDE1",
            synth,
            tech,
            fund_res={"raw_fundamentals": {"debt_to_equity": 25.0, "pe_ratio": 18.0, "net_cash_status": "Net Debt"}},
            sector="IT Services",
        )
        self.assertIsNotNone(low_de)
        self.assertTrue(any("Strong B/S" in r for r in low_de["reasons"]), low_de["reasons"])
        self.assertFalse(any("High D/E" in r for r in low_de["reasons"]))

        # BFSI stocks are exempt from D/E penalty even at 600%
        bank_pick = score_fundamental_pick(
            "TESTBNK",
            synth,
            tech,
            fund_res={"raw_fundamentals": {"debt_to_equity": 600.0, "current_ratio": 0.5, "pe_ratio": 15.0}},
            sector="Financial Services",
        )
        self.assertIsNotNone(bank_pick)
        self.assertFalse(any("High D/E" in r for r in bank_pick["reasons"]))

    def test_macro_shield_regex_defensive_protection_and_unavailable(self):
        from tools.macro_risk_shield import (
            _sector_sensitivity,
            evaluate_holding_shield,
            build_macro_risk_shield,
        )

        self.assertEqual(_sector_sensitivity("Financial Services & Banking"), 0.90)
        self.assertEqual(_sector_sensitivity("Fast Moving Consumer Goods"), 0.20)
        self.assertEqual(_sector_sensitivity("Healthcare & Pharmaceuticals"), 0.20)

        # Defensive sector must stay protected ("low" urgency) in DANGER even when pnl_pct < 0
        defensive_shield = evaluate_holding_shield(
            {"symbol": "SUNPHARMA", "sector": "Healthcare & Pharmaceuticals", "pnl_pct": -5.0},
            "DANGER",
        )
        self.assertEqual(defensive_shield["urgency"], "low")
        self.assertIn("HOLD (Defensive)", defensive_shield["shield_action"])

        # Unavailable macro feed must report UNAVAILABLE tier cleanly
        offline = build_macro_risk_shield({"available": False, "label": "Unavailable", "score": 0.0})
        self.assertEqual(offline["risk_key"], "UNAVAILABLE")

    def test_peer_benchmark_word_boundary_and_ticker_updates(self):
        from tools.peer_benchmark_engine import _resolve_sector, SECTOR_PEER_MAP

        self.assertEqual(_resolve_sector("Capital Goods & Engineering"), "CAPITAL_GOODS")
        self.assertEqual(_resolve_sector("Defence & Aerospace"), "DEFENCE")
        self.assertIn("TMPV", SECTOR_PEER_MAP["AUTO"])
        self.assertIn("LTM", SECTOR_PEER_MAP["IT"])

    def test_news_sentiment_word_boundaries_negation_and_spam(self):
        from tools.news_tools import NewsSentimentEngine, is_recommendation_spam

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "news_test.db"))
            eng = NewsSentimentEngine(cache_manager=cm)
            # "ban" must never match inside "bank"
            self.assertEqual(eng._quick_sentiment_score("HDFC Bank posts steady quarter"), ("Neutral", 0.0))
            # Negation / cut phrases must score negative
            lbl, score = eng._quick_sentiment_score("Company cuts dividend amid weak demand")
            self.assertEqual(lbl, "Bearish")
            self.assertLess(score, 0.0)
            self.assertTrue(is_recommendation_spam("Multibagger stock to buy: target price Rs 500"))

    def test_kite_portfolio_token_expiry_collateral_and_bearish_swing(self):
        from datetime import datetime, timedelta
        import json
        from tools.kite_portfolio import KitePortfolioEngine

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "kp_test.db"))
            engine = KitePortfolioEngine(cache_manager=cm)
            engine.api_key = "dummy_key"
            engine.token_path = os.path.join(d, "kite_token.json")
            engine.local_holdings_path = os.path.join(d, "my_holdings.json")

            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            with open(engine.token_path, "w", encoding="utf-8") as f:
                json.dump({"api_key": "dummy_key", "access_token": "old_tok", "created_at": yesterday}, f)

            with unittest.mock.patch.dict(os.environ, {"KITE_ACCESS_TOKEN": ""}, clear=False):
                status = engine.get_connection_status()
            self.assertFalse(status["connected"])
            self.assertIn("Expired", status["status"])

            # Verify collateral_quantity - used_quantity is included in holdings
            import types
            fake_kite_instance = types.SimpleNamespace(
                set_access_token=lambda tok: None,
                holdings=lambda: [{
                    "tradingsymbol": "COLTEST",
                    "quantity": 0,
                    "t1_quantity": 0,
                    "collateral_quantity": 10,
                    "used_quantity": 2,
                    "average_price": 100.0,
                    "last_price": 110.0,
                }],
            )
            fake_kc_mod = types.ModuleType("kiteconnect")
            fake_kc_mod.KiteConnect = lambda api_key=None: fake_kite_instance
            with unittest.mock.patch.dict(os.environ, {"KITE_ACCESS_TOKEN": "live_tok"}, clear=False), \
                 unittest.mock.patch.dict(sys.modules, {"kiteconnect": fake_kc_mod}):
                fetched = engine.fetch_holdings()
            self.assertEqual(len(fetched), 1)
            self.assertEqual(fetched[0]["quantity"], 8)

            # Bearish SELL verdict below target price must NOT report "TARGET ACHIEVED"
            cm.save_agent_output("SELLTEST", "Master Prediction Synthesizer Agent", {
                "structured_signal": {
                    "action_verdict": "SELL",
                    "confidence_rating": "HIGH",
                    "when_to_sell_target": "Rs. 250.00",
                    "stop_loss": "Rs. 320.00",
                }
            })
            res = engine.evaluate_portfolio([{
                "symbol": "SELLTEST",
                "quantity": 10,
                "average_price": 300.0,
                "last_price": 240.0,
                "invested_value": 3000.0,
                "current_value": 2400.0,
                "pnl": -600.0,
                "pnl_pct": -20.0,
            }])
            holding = res["holdings"][0]
            self.assertNotIn("TARGET ACHIEVED", holding["swing_action"].upper())

    def test_events_tools_and_ticker_hygiene(self):
        from datetime import datetime
        from tools.events_tools import EventsEngine
        from tools.ticker_validator import KNOWN_UNAVAILABLE, KNOWN_YF_OVERRIDES

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "ev_test.db"))
            ev = EventsEngine(cache_manager=cm)
            self.assertIsNone(ev._get_curated_corporate_calendar("INFY"))
            today = datetime.now().strftime("%Y-%m-%d")
            for item in ev.get_upcoming_macro_events():
                dt = datetime.strptime(item["date"], "%Y-%m-%d")
                self.assertGreaterEqual(item["date"], today)
                self.assertLess(dt.weekday(), 5, item)

        self.assertNotIn("YESBANK", KNOWN_UNAVAILABLE)
        self.assertIn("TMPV.NS", KNOWN_YF_OVERRIDES["TATAMOTORS"])
        self.assertIn("LTM.NS", KNOWN_YF_OVERRIDES["LTIM"])

    def test_forensic_engine_unaudited_no_fabricated_metrics(self):
        from tools.forensic_financial_engine import ForensicFinancialEngine
        from tools.peer_benchmark_engine import PeerBenchmarkEngine

        class EmptyTicker:
            major_holders = None
            insider_transactions = None
            info = {}

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "for_test.db"))
            eng = ForensicFinancialEngine(cache_manager=cm)
            with unittest.mock.patch.object(eng.fund_engine, "get_fundamental_metrics", return_value={"available": False}), \
                 unittest.mock.patch.object(eng, "_extract_statement_data", return_value={"statements_available": False}), \
                 unittest.mock.patch.object(eng, "_get_current_price", return_value=100.0), \
                 unittest.mock.patch.object(PeerBenchmarkEngine, "compute_peer_benchmarks", return_value=None), \
                 unittest.mock.patch("yfinance.Ticker", return_value=EmptyTicker()):
                res = eng.analyze_company("FAKEUNAUDITED", price_override=100.0)

        self.assertEqual(res["verdict"], "UNAUDITED")
        self.assertEqual(res["governance_telemetry"]["governance_grade"], "UNAUDITED")
        self.assertIsNone(res["governance_telemetry"]["promoter_pledge_pct"])
        self.assertIsNone(res["earnings_quality"]["reported_pat"])
        self.assertIsNone(res["solvency_health"]["total_debt"])
        self.assertIsNone(res["cash_conversion"]["cfo"])


class Phase2WaveATests(unittest.TestCase):
    """Deterministic tests for Phase 2 Wave 2A (Tasks 2.1 & 2.2)."""

    def _make_ohlcv_df(self, n: int = 80, start_price: float = 100.0, step: float = 1.0, spread: float = 2.0):
        import pandas as pd
        dates = pd.bdate_range("2026-01-01", periods=n)
        rows = []
        for i in range(n):
            c = start_price + i * step
            rows.append({
                "DATE": dates[i],
                "OPEN_PRICE": round(c - step * 0.3, 2),
                "HIGH_PRICE": round(c + spread, 2),
                "LOW_PRICE": round(max(1.0, c - spread), 2),
                "CLOSE_PRICE": round(c, 2),
                "VOLUME": 100000 + (i % 5) * 10000,
            })
        return pd.DataFrame(rows)

    def test_wilder_indicators_and_engine_parity(self):
        import pandas as pd
        from tools.indicators import wilder_atr, wilder_adx
        from tools.pattern_engine import QuantitativePatternEngine
        from tools.tech_tools import TechnicalAnalysisEngine

        # Constant TR = 10.0 across 25 bars
        df_const = pd.DataFrame({
            "HIGH_PRICE": [105.0] * 25,
            "LOW_PRICE": [95.0] * 25,
            "CLOSE_PRICE": [100.0] * 25,
        })
        atr = wilder_atr(df_const["HIGH_PRICE"], df_const["LOW_PRICE"], df_const["CLOSE_PRICE"], 14)
        self.assertTrue(atr.iloc[:13].isna().all())
        self.assertAlmostEqual(float(atr.iloc[-1]), 10.0, places=4)

        # Monotonic uptrend -> high ADX and +DI > -DI
        df_up = self._make_ohlcv_df(n=60, start_price=100.0, step=1.5, spread=1.0)
        adx_df = wilder_adx(df_up["HIGH_PRICE"], df_up["LOW_PRICE"], df_up["CLOSE_PRICE"], 14)
        self.assertGreater(float(adx_df["ADX_14"].iloc[-1]), 25.0)
        self.assertGreater(float(adx_df["PLUS_DI_14"].iloc[-1]), float(adx_df["MINUS_DI_14"].iloc[-1]))

        # Parity between tech_tools and pattern_engine
        tech_calc = TechnicalAnalysisEngine()._compute_indicators(df_up)
        pat_calc = QuantitativePatternEngine.compute_atr_and_keltner(df_up)
        self.assertAlmostEqual(float(tech_calc["RSI_14"].iloc[-1]), float(pat_calc["RSI_14"].iloc[-1]), places=4)
        self.assertAlmostEqual(float(tech_calc["ATR_14"].iloc[-1]), float(pat_calc["ATR_14"].iloc[-1]), places=4)
        self.assertAlmostEqual(float(tech_calc["ADX_14"].iloc[-1]), float(pat_calc["ADX_14"].iloc[-1]), places=4)

    def test_pattern_hardening_recency_invalidation_and_wyckoff_adx(self):
        import pandas as pd
        import numpy as np
        from tools.pattern_engine import QuantitativePatternEngine

        # 1. Double Bottom picks max mid-peak neckline (125.0), Double Top picks min mid-trough (84.0)
        df_dummy = self._make_ohlcv_df(n=80, start_price=110.0, step=0.0, spread=2.0)
        df_dummy.loc[df_dummy.index[-1], "CLOSE_PRICE"] = 122.0
        swings_db = [
            {"type": "low", "idx": 50, "price": 100.0},
            {"type": "high", "idx": 55, "price": 115.0},
            {"type": "high", "idx": 58, "price": 125.0},
            {"type": "low", "idx": 65, "price": 101.0},
        ]
        res_db = QuantitativePatternEngine.detect_double_patterns(df_dummy, swings_db)
        self.assertEqual(len(res_db), 1)
        self.assertEqual(res_db[0]["key_levels"]["neckline"], 125.0)

        df_dummy.loc[df_dummy.index[-1], "CLOSE_PRICE"] = 86.0
        swings_dt = [
            {"type": "high", "idx": 50, "price": 120.0},
            {"type": "low", "idx": 55, "price": 92.0},
            {"type": "low", "idx": 58, "price": 84.0},
            {"type": "high", "idx": 65, "price": 119.0},
        ]
        res_dt = QuantitativePatternEngine.detect_double_patterns(df_dummy, swings_dt)
        self.assertEqual(len(res_dt), 1)
        self.assertEqual(res_dt[0]["key_levels"]["neckline"], 84.0)

        # 2. Stale Triangle & Stale/Invalidated Harmonic & Stale RSI Divergence are rejected
        stale_tri_swings = [
            {"type": "low", "idx": 5, "price": 90.0},
            {"type": "high", "idx": 10, "price": 100.0},
            {"type": "low", "idx": 15, "price": 95.0},
            {"type": "high", "idx": 20, "price": 100.5},
        ]
        self.assertEqual(QuantitativePatternEngine.detect_triangles(df_dummy, stale_tri_swings), [])

        stale_harm_swings = [
            {"type": "low", "idx": 10, "price": 100.0},
            {"type": "high", "idx": 15, "price": 150.0},
            {"type": "low", "idx": 20, "price": 119.0},
            {"type": "high", "idx": 25, "price": 140.0},
            {"type": "low", "idx": 30, "price": 110.7},  # D was 49 bars ago -> stale!
        ]
        self.assertEqual(QuantitativePatternEngine.detect_harmonic_patterns(df_dummy, stale_harm_swings), [])

        # Recent harmonic whose post-D bar violated stop_loss X*0.99 must be rejected
        df_viol = self._make_ohlcv_df(n=60, start_price=112.0, step=0.0, spread=1.0)
        df_viol.loc[56, "LOW_PRICE"] = 95.0  # breaches X * 0.99 = 99.0
        inv_harm = [
            {"type": "low", "idx": 35, "price": 100.0},
            {"type": "high", "idx": 40, "price": 150.0},
            {"type": "low", "idx": 45, "price": 119.0},
            {"type": "high", "idx": 50, "price": 140.0},
            {"type": "low", "idx": 54, "price": 110.7},
        ]
        self.assertEqual(QuantitativePatternEngine.detect_harmonic_patterns(df_viol, inv_harm), [])

        df_dummy["RSI_14"] = 40.0
        stale_div = [
            {"type": "low", "idx": 10, "price": 105.0, "rsi": 30.0},
            {"type": "high", "idx": 20, "price": 120.0, "rsi": 55.0},
            {"type": "low", "idx": 30, "price": 100.0, "rsi": 38.0},
            {"type": "high", "idx": 40, "price": 118.0, "rsi": 50.0},
        ]
        self.assertEqual(QuantitativePatternEngine.detect_rsi_divergence(df_dummy, stale_div), [])

        # 3. Wyckoff Spring blocked in strong trend (ADX > 28) vs detected in sideways range
        n_w = 50
        dates_w = pd.bdate_range("2026-01-01", periods=n_w)
        base_closes = [100.0 + (2.0 if i % 4 < 2 else -2.0) for i in range(n_w)]
        base_lows = [c - 1.5 for c in base_closes]
        base_highs = [c + 1.5 for c in base_closes]
        base_vols = [100000] * n_w
        # Last 3 bars: sweep below tr_support (~97) to 95.5, close back inside at 101.0
        base_lows[-2] = 95.5
        base_closes[-1] = 101.0
        base_vols[-3:] = [60000, 65000, 70000]
        df_wyck_side = pd.DataFrame({
            "DATE": dates_w, "OPEN_PRICE": base_closes, "HIGH_PRICE": base_highs,
            "LOW_PRICE": base_lows, "CLOSE_PRICE": base_closes, "VOLUME": base_vols,
            "ADX_14": [18.0] * n_w,
        })
        springs_ok = QuantitativePatternEngine.detect_wyckoff_spring(df_wyck_side)
        self.assertTrue(any("Wyckoff Accumulation Spring" in p["name"] for p in springs_ok))

        df_wyck_trend = df_wyck_side.copy()
        df_wyck_trend["ADX_14"] = 36.0
        self.assertEqual(QuantitativePatternEngine.detect_wyckoff_spring(df_wyck_trend), [])

    def test_nse_delivery_parsing_sqlite_roundtrip_and_volume_signal(self):
        from tools.historical_data_tools import parse_nse_delivery_csv
        from agents.synthesizer_agent import _volume_signal

        sample_csv = (
            "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
            "BEL, EQ, 20-Nov-2026, 300.0, 301.0, 310.0, 299.0, 308.0, 308.0, 305.0, 1000000, 3050.0, 20000, 625000, 62.50\n"
            "INFY, BE, 20-Nov-2026, 1800, 1810, 1820, 1790, 1815, 1815, 1810, 500000, 9000.0, 15000, 200000, 40.00\n"
            "NIFTYBEES, EQ, 20-Nov-2026, 250, 251, 252, 249, 250, 250, 250, 100000, 250.0, 1000, -, -\n"
        )
        parsed = parse_nse_delivery_csv(sample_csv)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0], {
            "symbol": "BEL",
            "date": "2026-11-20",
            "delivery_qty": 625000,
            "delivery_pct": 62.5,
        })

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "deliv.db"))
            cm.save_historical_candles([{
                "symbol": "BEL", "date": "2026-11-20",
                "open": 301.0, "high": 310.0, "low": 299.0, "close": 308.0, "adj_close": 308.0, "volume": 1000000,
            }])
            updated = cm.update_delivery_data(parsed)
            self.assertEqual(updated, 1)
            # Re-saving price candles on overlapping date must preserve delivery fields
            cm.save_historical_candles([{
                "symbol": "BEL", "date": "2026-11-20",
                "open": 301.0, "high": 310.0, "low": 299.0, "close": 308.5, "adj_close": 308.5, "volume": 1000000,
            }])
            rows = cm.get_cached_candles("BEL", limit_days=5)
            self.assertEqual(rows[0]["DELIVERY_QTY"], 625000)
            self.assertAlmostEqual(rows[0]["DELIVERY_PCT"], 62.5, places=2)

        strong_deliv, _ = _volume_signal(1.6, ud_ratio=1.3, day_change_pct=1.8, delivery_pct=65.0, delivery_avg=45.0)
        weak_churn, _ = _volume_signal(1.6, ud_ratio=1.3, day_change_pct=1.8, delivery_pct=18.0, delivery_avg=45.0)
        self.assertGreater(strong_deliv, weak_churn)

    def test_mansfield_rs_weekly_mtf_and_regime_aware_rsi(self):
        import pandas as pd
        from tools.indicators import mansfield_relative_strength, compute_weekly_trend
        from agents.synthesizer_agent import _momentum_signal

        n = 150
        dates = pd.bdate_range("2026-01-01", periods=n)
        bench_df = pd.DataFrame({
            "DATE": dates,
            "CLOSE_PRICE": [22000.0 + i * 5.0 for i in range(n)],
        })
        stock_df = pd.DataFrame({
            "DATE": dates,
            "CLOSE_PRICE": [100.0 * (1.003 ** i) for i in range(n)],
        })
        rs = mansfield_relative_strength(stock_df, bench_df)
        self.assertIsNotNone(rs["mansfield_rs"])
        self.assertGreater(rs["mansfield_rs"], 2.0)
        self.assertGreater(rs["rs_63d_alpha_pct"], 0.0)
        self.assertIn(rs["rs_rating"], ("Outperforming", "Market Leader"))

        wt = compute_weekly_trend(stock_df)
        self.assertEqual(wt["weekly_trend"], "Bullish")
        self.assertGreater(wt["weekly_ema_10"], wt["weekly_ema_30"])

        # Regime-aware RSI: strong bull trend at RSI 73 stays positive; strong bear at RSI 28 stays cautious
        bull_v, _ = _momentum_signal(73.0, trend_regime="strong_bull", adx_14=32.0)
        bear_v, _ = _momentum_signal(28.0, trend_regime="strong_bear", adx_14=32.0)
        self.assertGreater(bull_v, 0.0)
        self.assertLessEqual(bear_v, 0.0)

    def test_nse_tick_snapping_atr_stops_and_surveillance_caution(self):
        import json
        import pandas as pd
        from tools.indicators import snap_nse_tick
        from tools.risk_tools import RiskManagementEngine, check_circuit_and_surveillance
        from tools.historical_data_tools import HistoricalDataEngine

        self.assertEqual(snap_nse_tick(123.456, "down"), 123.45)
        self.assertEqual(snap_nse_tick(123.456, "up"), 123.46)
        self.assertEqual(snap_nse_tick(512.37, "down"), 512.35)
        self.assertEqual(snap_nse_tick(512.37, "up"), 512.40)

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "risk_test.db"))
            rag = HistoricalDataEngine(cache_manager=cm)
            # Low-volatility stock vs High-volatility stock around Rs. 500
            dates = pd.bdate_range("2026-01-01", periods=60)
            low_vol_recs = [{
                "symbol": "CALM", "date": d_i.strftime("%Y-%m-%d"),
                "open": 500.0, "high": 502.5, "low": 497.5, "close": 500.0, "adj_close": 500.0, "volume": 500000,
            } for d_i in dates]
            high_vol_recs = [{
                "symbol": "WILD", "date": d_i.strftime("%Y-%m-%d"),
                "open": 500.0, "high": 522.0, "low": 478.0, "close": 500.0, "adj_close": 500.0, "volume": 500000,
            } for d_i in dates]
            cm.save_historical_candles(low_vol_recs + high_vol_recs)

            risk_eng = RiskManagementEngine(rag_engine=rag, cache_manager=cm)
            r_calm = risk_eng.evaluate_risk("CALM")
            r_wild = risk_eng.evaluate_risk("WILD")

            # Calm blue-chip gets tighter ATR-adaptive stop than volatile stock
            self.assertEqual(r_calm["stop_method"], "ATR-Adaptive")
            self.assertGreater(r_calm["suggested_stop_loss"], r_wild["suggested_stop_loss"])
            # Stops >= Rs 250 snap cleanly to Rs 0.05 ticks
            self.assertAlmostEqual((r_calm["suggested_stop_loss"] * 100) % 5, 0.0, places=4)
            self.assertAlmostEqual((r_wild["suggested_stop_loss"] * 100) % 5, 0.0, places=4)

            # 3 circuit-lock sessions (+5% with H == L) -> surveillance_flag=True and HIGH circuit_risk
            circ_rows = [{"HIGH_PRICE": 100.0, "LOW_PRICE": 98.0, "CLOSE_PRICE": 100.0, "VOLUME": 10000}]
            p = 100.0
            for _ in range(3):
                p = round(p * 1.05, 2)
                circ_rows.append({"HIGH_PRICE": p, "LOW_PRICE": p, "CLOSE_PRICE": p, "VOLUME": 10000})
            circ_info = check_circuit_and_surveillance(pd.DataFrame(circ_rows), symbol="CIRCSTOCK")
            self.assertTrue(circ_info["surveillance_flag"])
            self.assertEqual(circ_info["circuit_risk"], "HIGH")

            # ASM list file flag also triggers surveillance_flag and caps synthesizer confidence <= 60
            surv_file = os.path.join(d, "surv.json")
            with open(surv_file, "w", encoding="utf-8") as f:
                json.dump({"asm": ["ASMSTOCK"], "gsm": []}, f)
            asm_info = check_circuit_and_surveillance(pd.DataFrame(circ_rows[:1]), symbol="ASMSTOCK", surveillance_path=surv_file)
            self.assertTrue(asm_info["surveillance_flag"])

            ctx = {
                "news": {"bullish": 5, "bearish": 0, "total": 5},
                "macro": {"available": True, "score": 0.6, "label": "Bullish"},
                "fundamental": {"available": True, "valuation_assessment": "Undervalued", "roe_pct": 20},
            }
            sig = Synth.compute_quantitative_verdict(
                "CIRCSTOCK", "Circuit Corp", 100.0, make_tech(100, 92, 85, 55),
                {"surveillance_flag": True, "surveillance_warning": "NSE ASM surveillance list"},
                [BULL], {}, ctx,
            )
            self.assertLessEqual(sig["confidence_percentage"], 60)
            self.assertIn("Caution:", sig["key_rationale"])


class Phase2WaveBTests(unittest.TestCase):
    """Deterministic unit tests for Phase 2 Wave 2B (Tasks 2.3, 2.4 & 2.5)."""

    def test_non_bfsi_multi_method_valuation_is_price_independent(self):
        from tools.forensic_financial_engine import ForensicFinancialEngine
        from tools.peer_benchmark_engine import PeerBenchmarkEngine

        class EmptyTicker:
            major_holders = None
            insider_transactions = None
            info = {}

        stmts = {
            "statements_available": True,
            "company_name": "Clean Industrial Ltd",
            "sector": "Information Technology",
            "revenue": 1000.0,
            "revenue_prior": 850.0,
            "reported_pat": 100.0,
            "reported_pat_prior": 82.0,
            "other_income": 5.0,
            "exceptional_items": 0.0,
            "minority_interest": 0.0,
            "cfo": 120.0,
            "capex": 20.0,
            "free_cashflow": 100.0,
            "ebitda": 160.0,
            "total_debt": 0.0,
            "total_cash": 100.0,
            "shares_outstanding_cr": 10.0,
            "shares_prior_cr": 10.0,
            "roe_pct": 22.0,
        }

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "val_test.db"))
            eng = ForensicFinancialEngine(cache_manager=cm)
            with unittest.mock.patch.object(eng.fund_engine, "get_fundamental_metrics", return_value={"available": True, "roe_pct": 22.0, "revenue_growth_pct": 17.6}), \
                 unittest.mock.patch.object(PeerBenchmarkEngine, "compute_peer_benchmarks", return_value=None), \
                 unittest.mock.patch("yfinance.Ticker", return_value=EmptyTicker()):
                r_low = eng.analyze_company("CLEANM", price_override=100.0, financial_statement_override=stmts)
                r_high = eng.analyze_company("CLEANM", price_override=200.0, financial_statement_override=stmts)

        self.assertEqual(r_low["valuation_metrics"]["valuation_method"], "MULTI_METHOD_INTRINSIC")
        self.assertGreater(r_low["fair_value"], 0.0)
        # Intrinsic fair value must NOT scale linearly with market price
        self.assertEqual(r_low["fair_value"], r_high["fair_value"])
        self.assertGreater(r_low["margin_of_safety_pct"], r_high["margin_of_safety_pct"])

    def test_bfsi_justified_pb_and_health_scoring(self):
        from tools.forensic_financial_engine import ForensicFinancialEngine
        from tools.peer_benchmark_engine import PeerBenchmarkEngine

        class EmptyTicker:
            major_holders = None
            insider_transactions = None
            info = {}

        fortress_bank = {
            "statements_available": True,
            "company_name": "Fortress Bank Ltd",
            "sector": "Banking",
            "revenue": 25000.0,
            "revenue_prior": 21000.0,
            "reported_pat": 5500.0,
            "reported_pat_prior": 4700.0,
            "cfo": 600.0,  # Banks routinely have fluctuating operating cash flows
            "capex": 100.0,
            "total_debt": 280000.0,
            "total_cash": 150000.0,
            "book_value_per_share": 500.0,
            "roe_pct": 17.0,
            "roa_pct": 1.9,
            "nim_pct": 3.8,
            "gnpa_pct": 1.2,
            "nnpa_pct": 0.35,
            "casa_pct": 46.0,
            "crar_pct": 19.5,
        }
        stressed_bank = {
            **fortress_bank,
            "company_name": "Stressed Lender Ltd",
            "gnpa_pct": 7.5,
            "nnpa_pct": 3.1,
            "crar_pct": 11.0,
            "roa_pct": 0.4,
            "roe_pct": 5.0,
        }

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "bfsi_test.db"))
            eng = ForensicFinancialEngine(cache_manager=cm)
            with unittest.mock.patch.object(eng.fund_engine, "get_fundamental_metrics", return_value={"available": True, "debt_to_equity": 800.0}), \
                 unittest.mock.patch.object(PeerBenchmarkEngine, "compute_peer_benchmarks", return_value=None), \
                 unittest.mock.patch("yfinance.Ticker", return_value=EmptyTicker()):
                r_ok = eng.analyze_company("FORTBNK", price_override=700.0, financial_statement_override=fortress_bank)
                r_bad = eng.analyze_company("STRSBNK", price_override=700.0, financial_statement_override=stressed_bank)

        self.assertEqual(r_ok["valuation_metrics"]["valuation_method"], "BFSI_JUSTIFIED_PB")
        self.assertEqual(r_ok["solvency_health"]["solvency_rating"], "BFSI_REGULATED")
        self.assertEqual(r_ok["bfsi_health"]["bfsi_grade"], "FORTRESS_BANK")
        self.assertEqual(r_ok["beneish_m_score"]["status"], "NOT_APPLICABLE_BFSI")
        self.assertFalse(any("leverage" in f.lower() for f in r_ok["red_flags"]))
        self.assertEqual(r_bad["bfsi_health"]["bfsi_grade"], "STRESSED_BFSI")
        self.assertEqual(r_bad["verdict"], "HIGH_RISK_DISTRESSED")

    def test_authentic_piotroski_and_beneish_m_score(self):
        from tools.forensic_financial_engine import ForensicFinancialEngine
        from tools.peer_benchmark_engine import PeerBenchmarkEngine

        class EmptyTicker:
            major_holders = None
            insider_transactions = None
            info = {}

        # Incomplete 1-year data: missing prior-year balance sheet/shares -> INSUFFICIENT_HISTORY, zero free points
        partial_stmts = {
            "statements_available": True,
            "sector": "Industrial",
            "revenue": 500.0,
            "reported_pat": 60.0,
            "cfo": 65.0,
            "total_debt": 0.0,
            "total_cash": 50.0,
        }
        # Manipulator profile: inflating receivables (DSRI), high accruals (TATA), dropping gross margin (GMI), rising leverage
        manip_stmts = {
            "statements_available": True,
            "sector": "Industrial",
            "revenue": 1100.0,
            "revenue_prior": 1000.0,
            "reported_pat": 120.0,
            "reported_pat_prior": 80.0,
            "cfo": 5.0,
            "capex": 10.0,
            "trade_receivables": 420.0,
            "receivables_prior": 120.0,
            "total_assets": 400.0,
            "total_assets_prior": 350.0,
            "current_assets": 220.0,
            "current_assets_prior": 240.0,
            "current_liabilities": 180.0,
            "current_liabilities_prior": 120.0,
            "total_debt": 150.0,
            "total_debt_prior": 80.0,
            "total_cash": 10.0,
            "gross_profit": 280.0,
            "gross_profit_prior": 360.0,
            "ppe": 80.0,
            "ppe_prior": 80.0,
            "depreciation": 12.0,
            "depreciation_prior": 14.0,
            "sga_expense": 110.0,
            "sga_expense_prior": 90.0,
        }

        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "piot_test.db"))
            eng = ForensicFinancialEngine(cache_manager=cm)
            with unittest.mock.patch.object(eng.fund_engine, "get_fundamental_metrics", return_value={"available": False}), \
                 unittest.mock.patch.object(PeerBenchmarkEngine, "compute_peer_benchmarks", return_value=None), \
                 unittest.mock.patch("yfinance.Ticker", return_value=EmptyTicker()):
                r_part = eng.analyze_company("PARTCO", price_override=100.0, financial_statement_override=partial_stmts)
                r_manip = eng.analyze_company("MANIPCO", price_override=100.0, financial_statement_override=manip_stmts)

        p_det = r_part["piotroski_f_score_details"]
        self.assertEqual(p_det["rating"], "INSUFFICIENT_HISTORY")
        self.assertLess(p_det["evaluable_criteria"], 5)
        self.assertIn("F_DELTA_LIQUID", p_det["missing_criteria"])

        b_res = r_manip["beneish_m_score"]
        self.assertIsNotNone(b_res["m_score"])
        self.assertGreater(b_res["m_score"], -1.78)
        self.assertEqual(b_res["status"], "HIGH_MANIPULATION_RISK")
        self.assertEqual(r_manip["verdict"], "AVOID_OR_VALUE_TRAP")

    def test_filing_freshness_and_shareholding_parser(self):
        from datetime import date
        from tools.local_financials_parser import compute_filing_freshness, parse_nse_shareholding_payload

        fresh = compute_filing_freshness({"fiscal_year": "FY2025"}, as_of_date=date(2025, 6, 15))
        self.assertEqual(fresh["status"], "FRESH")
        self.assertFalse(fresh["is_stale"])

        stale = compute_filing_freshness({"fiscal_year": "FY2025"}, as_of_date=date(2026, 11, 22))
        self.assertEqual(stale["status"], "STALE")
        self.assertTrue(stale["is_stale"])
        self.assertGreater(stale["filing_age_days"], 420)

        parsed = parse_nse_shareholding_payload({
            "promoterAndPromoterGroup": {"totalPct": "52.40"},
            "pledgedOrEncumbered": {"pct": "12.5"},
            "publicShareholding": {"fiiPct": "19.8", "diiPct": "14.2"},
            "periodEndDate": "2026-09-30",
        })
        self.assertEqual(parsed["promoter_holding_pct"], 52.4)
        self.assertEqual(parsed["promoter_pledge_pct"], 12.5)
        self.assertEqual(parsed["fii_holding_pct"], 19.8)
        self.assertEqual(parsed["dii_holding_pct"], 14.2)
        self.assertEqual(parsed["quarter_end_date"], "2026-09-30")

    def test_dynamic_long_term_compounder_decoupling(self):
        from tools.long_term_strategy import long_term_engine

        self.assertFalse(hasattr(long_term_engine, "curated_profiles"))

        strong_fund = {
            "available": True,
            "roe_pct": 26.0,
            "earnings_growth_pct": 24.0,
            "revenue_growth_pct": 19.0,
            "peg_ratio": 0.95,
            "net_cash_status": "Net Cash Positive",
            "profit_margin_pct": 18.0,
        }
        strong_forensic = {
            "verdict": "STRONG_BUY",
            "fair_value": 140.0,
            "margin_of_safety_pct": 40.0,
            "piotroski_f_score": 8,
            "cash_conversion": {"cfo_to_pat_ratio": 1.05, "revenue_growth_pct": 19.0},
            "earnings_quality": {"distortion_pct": 4.0},
            "governance_telemetry": {"governance_grade": "SOUND"},
            "valuation_metrics": {"valuation_method": "MULTI_METHOD_INTRINSIC"},
        }
        lt_buy = long_term_engine.evaluate_long_term_stock(
            "DYNCO", "Dynamic Compounder", "Information Technology",
            last_price=100.0, short_verdict="BUY", fund_data=strong_fund, forensic_data=strong_forensic,
        )
        lt_sell = long_term_engine.evaluate_long_term_stock(
            "DYNCO", "Dynamic Compounder", "Information Technology",
            last_price=100.0, short_verdict="SELL", fund_data=strong_fund, forensic_data=strong_forensic,
        )
        # Completely decoupled from short-term verdict
        self.assertEqual(lt_buy["compounder_score"], lt_sell["compounder_score"])
        self.assertEqual(lt_buy["long_term_verdict"], lt_sell["long_term_verdict"])
        self.assertTrue(lt_buy["is_top_wealth_pick"])
        self.assertEqual(lt_buy["target_basis"], "quantitative_fundamental_model")

        weak_lt = long_term_engine.evaluate_long_term_stock(
            "WEAKCO", "Weak Corp", "Metals",
            last_price=100.0, short_verdict="BUY",
            fund_data={"available": True, "roe_pct": 4.0, "earnings_growth_pct": -10.0, "peg_ratio": -1.2, "debt_to_equity": 240.0},
        )
        self.assertGreater(lt_buy["compounder_score"], weak_lt["compounder_score"])
        self.assertFalse(weak_lt["is_top_wealth_pick"])

    def test_fundamental_picks_52w_breakout_leader_gate(self):
        from tools.fundamental_picks import score_fundamental_pick

        synth = {"structured_signal": {"action_verdict": "BUY"}}
        tech_52w = {"raw_indicators": {"pct_from_52w_high": -1.5, "up_down_vol_ratio": 1.4, "last_price": 500.0}}

        garp_breakout = score_fundamental_pick(
            "LEAD52", synth, tech_52w,
            fund_res={"raw_fundamentals": {"peg_ratio": 1.1, "pe_ratio": 22.0, "net_cash_status": "Net Cash Positive"}},
        )
        self.assertIsNotNone(garp_breakout)
        self.assertTrue(any("52W Breakout Leader" in r for r in garp_breakout["reasons"]))

        expensive_chaser = score_fundamental_pick(
            "CHASE52", synth, tech_52w,
            fund_res={"raw_fundamentals": {"peg_ratio": 3.5, "pe_ratio": 60.0}},
        )
        self.assertIsNone(expensive_chaser)


class Phase2WaveCTests(unittest.TestCase):
    """Deterministic unit tests for Phase 2 Wave 2C (Tasks 2.6, 2.7 & 2.8) — zero network calls."""

    def test_macro_domestic_regime_ewma_unified_thresholds_and_sector_betas(self):
        import pandas as pd
        from tools import macro_tools, macro_risk_shield
        from agents.synthesizer_agent import _macro_signal

        # 1. Unified thresholds between macro_tools and macro_risk_shield
        self.assertEqual(
            macro_risk_shield.RISK_LEVELS["LOW"]["threshold_lo"],
            macro_tools.BULLISH_THRESHOLD,
        )
        self.assertEqual(
            macro_risk_shield.RISK_LEVELS["ELEVATED"]["threshold_lo"],
            macro_tools.BEARISH_THRESHOLD,
        )
        self.assertEqual(
            macro_risk_shield.RISK_LEVELS["HIGH"]["threshold_lo"],
            macro_tools.DANGER_THRESHOLD,
        )

        # 2. EWMA + Z-score smoothing & Brent-in-INR derivation
        closes = [100.0 * (1.005 ** i) for i in range(25)]
        ew = macro_tools.compute_ewma_and_zscore(closes)
        self.assertGreater(ew["ewma_5_pct"], 0.0)
        self.assertGreater(ew["ewma_20_pct"], 0.0)
        self.assertGreater(ew["z_score_20d"], 1.0)

        brent_inr = macro_tools.derive_brent_in_inr([
            {"indicator": "Brent Crude Oil", "value": 80.0, "pct_change": 2.0},
            {"indicator": "USD / INR (Rupee)", "value": 85.0, "pct_change": 0.5},
        ])
        self.assertIsNotNone(brent_inr)
        self.assertEqual(brent_inr["value"], 6800.0)
        self.assertAlmostEqual(brent_inr["pct_change"], 2.51, places=2)

        # 3. FII/DII NSE payload parser
        flows = macro_tools.parse_fii_dii_payload(
            [
                {"category": "FII/FPI *", "date": "20-Nov-2026", "buyValue": "12,000.0", "sellValue": "14,200.0", "netValue": "-2,200.00"},
                {"category": "DII **", "date": "20-Nov-2026", "buyValue": "11,500.0", "sellValue": "9,100.0", "netValue": "2,400.00"},
            ],
            fno_payload={"fii_fno_net_cr": -800.0},
        )
        self.assertIsNotNone(flows)
        self.assertEqual(flows["fii_net_cr"], -2200.0)
        self.assertEqual(flows["dii_net_cr"], 2400.0)
        self.assertEqual(flows["combined_net_cr"], 200.0)
        self.assertEqual(flows["flow_regime"], "DII_CUSHIONED")

        # 4. Local SQLite market breadth & domestic India VIX macro scoring
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "breadth_test.db"))
            dates = pd.bdate_range("2026-01-01", periods=60)
            recs = []
            # 4 uptrending stocks above 50 DMA + 1 downtrending stock + 1 ^NSEI index (excluded)
            for idx, sym in enumerate(["AAA", "BBB", "CCC", "DDD", "EEE", "^NSEI"]):
                for i, dt_i in enumerate(dates):
                    px = (120.0 - i * 0.5) if sym == "EEE" else (100.0 + i * 0.5)
                    recs.append({
                        "symbol": sym,
                        "date": dt_i.strftime("%Y-%m-%d"),
                        "open": px, "high": px + 1, "low": px - 1, "close": px, "adj_close": px, "volume": 100000,
                    })
            cm.save_historical_candles(recs)
            breadth = macro_tools.compute_market_breadth(cm)
            self.assertIsNotNone(breadth)
            self.assertEqual(breadth["stocks_evaluated_50"], 5)
            self.assertEqual(breadth["pct_above_50dma"], 80.0)
            self.assertEqual(breadth["breadth_regime"], "BULLISH_BREADTH")

        # High India VIX + FII outflow + Brent/INR shock drives Bearish score, cushioned for IT, amplified for Banking & Paints
        shock_inds = [
            {"indicator": "S&P 500", "value": 5800.0, "pct_change": -1.0},
            {"indicator": "Brent Crude Oil", "value": 90.0, "pct_change": 3.0},
            {"indicator": "USD / INR (Rupee)", "value": 86.0, "pct_change": 0.45},
            {"indicator": "India VIX", "value": 26.5, "pct_change": 8.0},
            {"indicator": "FII Net Flow (Rs Cr)", "value": -2800.0, "pct_change": None},
            {"indicator": "Market Breadth (% > 50 DMA)", "value": 28.0, "pct_change": None},
        ]
        macro_res = macro_tools.compute_macro_sentiment(shock_inds)
        self.assertTrue(macro_res["available"])
        self.assertEqual(macro_res["label"], "Bearish")

        macro_payload = {**macro_res, "indicators": shock_inds}
        it_sig, _ = _macro_signal(macro_payload, sector="Information Technology")
        bank_sig, _ = _macro_signal(macro_payload, sector="Banking & Finance")
        paints_sig, _ = _macro_signal(macro_payload, sector="Paints & Coatings")
        fmcg_sig, _ = _macro_signal(macro_payload, sector="FMCG")
        self.assertGreater(it_sig, bank_sig)
        self.assertGreater(fmcg_sig, bank_sig)
        self.assertLess(paints_sig, fmcg_sig)

        # 5. GlobalMacroAgent blends local cache + breadth + Brent-INR with zero network calls
        from agents.macro_agent import GlobalMacroAgent
        with tempfile.TemporaryDirectory() as d:
            cm_ag = CacheManager(db_path=os.path.join(d, "mag.db"))
            cm_ag.save_macro([
                {"indicator": "S&P 500", "value": 5900.0, "unit": "pts", "pct_change": 0.8, "summary": "up"},
                {"indicator": "Nasdaq", "value": 19000.0, "unit": "pts", "pct_change": 1.1, "summary": "up"},
                {"indicator": "Brent Crude Oil", "value": 76.0, "unit": "USD", "pct_change": -1.0, "summary": "dn"},
                {"indicator": "US Dollar Index (DXY)", "value": 103.0, "unit": "pts", "pct_change": -0.3, "summary": "dn"},
                {"indicator": "USD / INR (Rupee)", "value": 84.5, "unit": "INR", "pct_change": -0.1, "summary": "dn"},
                {"indicator": "US 10Y Treasury Yield", "value": 4.2, "unit": "%", "pct_change": -1.2, "summary": "dn"},
            ])
            ag_out = GlobalMacroAgent(cm_ag).run("INFY")
            self.assertEqual(ag_out["macro_sentiment"]["label"], "Bullish")
            self.assertIsNotNone(ag_out["macro_sentiment"]["brent_inr"])
            self.assertEqual(ag_out["macro_sentiment"]["brent_inr"]["value"], 6422.0)

    def test_nse_corporate_actions_fo_expiry_and_pre_event_guardrails(self):
        from datetime import date
        from tools.events_tools import (
            parse_nse_corporate_actions,
            parse_nse_board_meetings,
            compute_nse_fo_expiry_dates,
            evaluate_pre_event_guardrail,
        )

        ca = parse_nse_corporate_actions(
            [
                {"symbol": "INFY", "exDate": "18-Dec-2026", "recDate": "18-Dec-2026", "subject": "Interim Dividend - Rs 21.50 Per Share"},
                {"symbol": "INFY", "exDate": "02-Jan-2027", "recDate": "03-Jan-2027", "subject": "Bonus Issue 1:1"},
            ],
            symbol="INFY",
            as_of_date=date(2026, 12, 16),
        )
        self.assertEqual(ca["dividend_ex_date"], "2026-12-18")
        self.assertEqual(ca["dividend_per_share"], 21.5)
        self.assertEqual(ca["bonus_ex_date"], "2027-01-02")
        self.assertEqual(ca["bonus_ratio"], "1:1")

        bm = parse_nse_board_meetings(
            [
                {"symbol": "INFY", "meetingDate": "17-Jan-2027", "purpose": "To approve unaudited quarterly financial results for Q3FY27"},
            ],
            symbol="INFY",
            as_of_date=date(2026, 12, 16),
        )
        self.assertIsNotNone(bm)
        self.assertEqual(bm["earnings_date"], "2027-01-17")

        expiries = compute_nse_fo_expiry_dates(start_date=date(2026, 11, 20), months_ahead=2)
        self.assertGreaterEqual(len(expiries), 2)
        for ex in expiries:
            ex_d = date.fromisoformat(ex["date"])
            self.assertLess(ex_d.weekday(), 5)

        # Synthesizer pre-event guardrails:
        # 1) T-2 Earnings suppresses fresh BUY -> HOLD and caps confidence <= 65
        ctx_bull = {
            "news": {"bullish": 5, "bearish": 0, "total": 5},
            "macro": {"available": True, "score": 0.6, "label": "Bullish"},
            "fundamental": {"available": True, "valuation_assessment": "Undervalued", "roe_pct": 22},
        }
        sig_earn = Synth.compute_quantitative_verdict(
            "INFY", "Infosys", 1500.0,
            make_tech(1500.0, 1420.0, 1350.0, 58.0),
            {"atr_14": 25.0, "suggested_target_price": 1650.0, "suggested_stop_loss": 1450.0},
            [{"name": "Cup & Handle", "direction": "Bullish", "quality_score": 90, "target_price": 1680.0, "stop_loss": 1445.0}],
            {"earnings_date": "2026-11-24", "_as_of_date": "2026-11-22"},
            ctx_bull,
        )
        self.assertEqual(sig_earn["action_verdict"], "HOLD")
        self.assertLessEqual(sig_earn["confidence_percentage"], 65)
        self.assertIn("Earnings Guardrail", sig_earn["key_rationale"])

        # 2) T-2 Ex-Dividend shifts protective stop-loss down by exact dividend_per_share while keeping stop < price < target
        sig_no_div = Synth.compute_quantitative_verdict(
            "INFY", "Infosys", 1500.0,
            make_tech(1500.0, 1420.0, 1350.0, 58.0),
            {"atr_14": 25.0, "suggested_target_price": 1650.0, "suggested_stop_loss": 1450.0},
            [{"name": "Cup & Handle", "direction": "Bullish", "quality_score": 90, "target_price": 1680.0, "stop_loss": 1450.0}],
            {},
            ctx_bull,
        )
        sig_ex_div = Synth.compute_quantitative_verdict(
            "INFY", "Infosys", 1500.0,
            make_tech(1500.0, 1420.0, 1350.0, 58.0),
            {"atr_14": 25.0, "suggested_target_price": 1650.0, "suggested_stop_loss": 1450.0},
            [{"name": "Cup & Handle", "direction": "Bullish", "quality_score": 90, "target_price": 1680.0, "stop_loss": 1450.0}],
            {"dividend_ex_date": "2026-11-24", "dividend_per_share": 30.0, "_as_of_date": "2026-11-22"},
            ctx_bull,
        )
        sl_plain = rs(sig_no_div["stop_loss"])
        sl_div = rs(sig_ex_div["stop_loss"])
        self.assertLess(sl_div, sl_plain)
        self.assertTrue(sl_div < 1500.0 < rs(sig_ex_div["when_to_sell_target"]))

    def test_institutional_news_clustering_credibility_decay_and_severity(self):
        from datetime import datetime, timedelta, timezone
        from tools.news_tools import (
            cluster_duplicate_headlines,
            compute_time_decay_weight,
            compute_event_severity,
            score_news_items_institutional,
        )
        from agents.news_sentiment_agent import NewsSentimentAgent
        from agents.synthesizer_agent import _news_signal

        now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
        fresh_ts = now.isoformat()
        old_ts = (now - timedelta(days=9)).isoformat()

        # 3 syndicated copies of the same headline collapse into 1 cluster, keeping Reuters over RandomBlog
        items = [
            {"title": "Larsen & Toubro bags Rs 5000 crore solar EPC order in Gujarat", "source": "RandomBlog", "sentiment_label": "Bullish", "sentiment_score": 0.6, "pub_date": fresh_ts},
            {"title": "L&T bags Rs 5000 crore solar EPC order in Gujarat state", "source": "Reuters", "sentiment_label": "Bullish", "sentiment_score": 0.6, "pub_date": fresh_ts},
            {"title": "Larsen Toubro bags solar EPC order in Gujarat worth Rs 5000 Cr", "source": "Economic Times", "sentiment_label": "Bullish", "sentiment_score": 0.6, "pub_date": fresh_ts},
            {"title": "Company faces SEBI probe over accounting irregularity and debt default", "source": "NSE", "sentiment_label": "Bearish", "sentiment_score": -0.8, "pub_date": fresh_ts},
        ]
        clustered = cluster_duplicate_headlines(items)
        self.assertEqual(len(clustered), 2)
        order_rep = [c for c in clustered if "solar" in c["title"].lower()][0]
        self.assertEqual(order_rep["source"], "Reuters")
        self.assertEqual(order_rep["cluster_size"], 3)

        self.assertAlmostEqual(compute_time_decay_weight(fresh_ts, half_life_days=3.0, now=now), 1.0, places=3)
        self.assertLess(compute_time_decay_weight(old_ts, half_life_days=3.0, now=now), 0.20)
        sev_wt, sev_tier = compute_event_severity("SEBI probe and debt default notice")
        self.assertEqual(sev_tier, "CRITICAL")
        self.assertEqual(sev_wt, 1.50)

        # Fresh critical NSE negative item outweighs an old blog positive item
        asym_items = [
            {"title": "Small supply contract signed last week", "source": "RandomBlog", "sentiment_label": "Bullish", "sentiment_score": 0.6, "pub_date": old_ts},
            {"title": "SEBI probe launched over accounting fraud and debt default", "source": "NSE", "sentiment_label": "Bearish", "sentiment_score": -0.8, "pub_date": fresh_ts},
        ]
        sc = score_news_items_institutional(asym_items, now=now)
        self.assertLess(sc["weighted_score"], -0.5)
        self.assertEqual(len(sc["critical_alerts"]), 1)

        out = NewsSentimentAgent(FakeNewsEngine(items)).run("LT", "Larsen & Toubro")
        self.assertEqual(out["news_score"]["clustered_count"], 2)
        self.assertEqual(out["news_score"]["raw_count"], 4)
        sig_val, sig_note = _news_signal(out["news_score"])
        self.assertIn("CRITICAL corporate alert", sig_note)
        self.assertLess(sig_val, 0.0)

    def test_portfolio_analytics_beta_corr_var_sizing_and_indian_tax(self):
        import pandas as pd
        from tools.portfolio_analytics import (
            compute_stock_beta,
            compute_correlation_matrix,
            compute_portfolio_var_cvar,
            compute_hhi_concentration,
            classify_sebi_cap_tier,
            compute_atr_position_sizing,
            estimate_indian_tax_and_cost_impact,
        )
        from tools.kite_portfolio import KitePortfolioEngine

        # 1. Beta, correlation, VaR/CVaR, HHI, SEBI cap tier
        b_rets = {f"2026-01-{i+1:02d}": (0.01 if i % 2 == 0 else -0.012) for i in range(25)}
        s1_rets = {d: r * 1.5 for d, r in b_rets.items()}   # exact 1.5x beta & +1.0 corr with b
        s2_rets = {d: r * 1.2 for d, r in b_rets.items()}   # +1.0 corr with s1

        self.assertAlmostEqual(compute_stock_beta(s1_rets, b_rets), 1.5, places=2)
        corr = compute_correlation_matrix({"S1": s1_rets, "S2": s2_rets})
        self.assertEqual(len(corr["high_correlation_pairs"]), 1)
        self.assertAlmostEqual(corr["high_correlation_pairs"][0]["correlation"], 1.0, places=2)

        var_res = compute_portfolio_var_cvar({"S1": s1_rets, "S2": s2_rets}, {"S1": 0.6, "S2": 0.4}, 100000.0)
        self.assertTrue(var_res["available"])
        self.assertGreaterEqual(var_res["cvar_95_pct"], var_res["var_95_pct"])
        self.assertGreaterEqual(var_res["var_99_pct"], var_res["var_95_pct"])

        hhi_conc = compute_hhi_concentration({"A": 0.8, "B": 0.2})
        self.assertGreater(hhi_conc["hhi"], 2500.0)
        self.assertEqual(hhi_conc["regime"], "Highly Concentrated")
        self.assertEqual(classify_sebi_cap_tier("TCS"), "Large Cap")
        self.assertEqual(classify_sebi_cap_tier("MIDTEST", market_cap_cr=45000.0), "Mid Cap")

        # 2. ATR Position Sizing & 20D ADV Liquidity Flag
        sz_hi = compute_atr_position_sizing(1000000.0, entry_price=500.0, stop_loss=475.0, risk_per_trade_pct=1.0, avg_daily_volume=10000.0)
        # risk = 10000 / (500-475) = 400 shares -> 4% of 10k ADV -> HIGH_IMPACT
        self.assertEqual(sz_hi["recommended_shares"], 400)
        self.assertEqual(sz_hi["liquidity_flag"], "HIGH_IMPACT")

        # 3. Indian Finance Act 2024 STCG (20%) / LTCG (12.5% above 1.25L) + NSE CNC costs
        stcg = estimate_indian_tax_and_cost_impact(100, avg_price=1000.0, sell_price=1500.0, holding_days=180)
        self.assertEqual(stcg["tax_regime"], "STCG_20_PCT")
        self.assertEqual(stcg["gross_pnl"], 50000.0)
        self.assertEqual(stcg["estimated_tax"], 10000.0)
        self.assertGreater(stcg["statutory_costs"], 150.0)

        ltcg_exempt = estimate_indian_tax_and_cost_impact(100, avg_price=1000.0, sell_price=1500.0, holding_days=400)
        self.assertEqual(ltcg_exempt["tax_regime"], "LTCG_12_5_PCT")
        self.assertEqual(ltcg_exempt["estimated_tax"], 0.0)  # under Rs. 1.25L exemption

        ltcg_taxable = estimate_indian_tax_and_cost_impact(1000, avg_price=1000.0, sell_price=1225.0, holding_days=400)
        # gross gain 2,25,000 - 1,25,000 exemption = 1,00,000 * 12.5% = 12,500
        self.assertEqual(ltcg_taxable["estimated_tax"], 12500.0)

        # 4. End-to-end KitePortfolioEngine integration with ^NSEI + local candles (zero network)
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "kp_quant.db"))
            dates = pd.bdate_range("2026-01-01", periods=30)
            candles = []
            for i, dt_i in enumerate(dates):
                d_str = dt_i.strftime("%Y-%m-%d")
                b_px = 24000.0 + ((-1) ** i) * 150.0 + i * 10.0
                candles.append({"symbol": "^NSEI", "date": d_str, "open": b_px, "high": b_px + 50, "low": b_px - 50, "close": b_px, "adj_close": b_px, "volume": 1000000})
                for sym, beta_m in (("TCS", 1.1), ("INFY", 1.2)):
                    s_px = 1500.0 + ((-1) ** i) * 10.0 * beta_m + i * 2.0
                    candles.append({"symbol": sym, "date": d_str, "open": s_px, "high": s_px + 10, "low": s_px - 10, "close": s_px, "adj_close": s_px, "volume": 500000})
            cm.save_historical_candles(candles)

            kp = KitePortfolioEngine(cache_manager=cm)
            res = kp.evaluate_portfolio([
                {"symbol": "TCS", "quantity": 20, "average_price": 1400.0, "last_price": 1560.0, "holding_days": 500},
                {"symbol": "INFY", "quantity": 25, "average_price": 1450.0, "last_price": 1560.0, "holding_days": 120},
            ])
            pa = res["portfolio_analytics"]
            self.assertIsNotNone(pa["portfolio_beta_vs_nifty"])
            self.assertTrue(pa["var_cvar"]["available"])
            self.assertGreaterEqual(len(pa["correlation"]["high_correlation_pairs"]), 1)
            self.assertGreaterEqual(len(pa["stress_tests"]), 4)
            rep_path = kp.generate_portfolio_report(
                output_path=os.path.join(d, "port_rep.md"),
                holdings=[
                    {"symbol": "TCS", "quantity": 20, "average_price": 1400.0, "last_price": 1560.0, "holding_days": 500},
                    {"symbol": "INFY", "quantity": 25, "average_price": 1450.0, "last_price": 1560.0, "holding_days": 120},
                ],
            )
            with open(rep_path, "r", encoding="utf-8") as rf:
                rep_md = rf.read()
            self.assertIn("Portfolio Quantitative Risk, Stress Tests & Tax Impact", rep_md)


if __name__ == "__main__":
    unittest.main()
