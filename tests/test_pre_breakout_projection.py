"""
Deterministic unit tests for pre-breakout bullish pattern detection,
anti-chasing classification, 4-week price projection math, and API service integration.
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.synthesizer_agent import MasterPredictionSynthesizerAgent as Synth, _pattern_signal
from api.services import get_pre_breakout_projections, get_top_pattern_picks, safe_json_dumps
from storage.cache_manager import CacheManager
from tools.pattern_engine import QuantitativePatternEngine, compute_pattern_projection
from tools.tech_tools import TechnicalAnalysisEngine


def _make_df(closes, highs=None, lows=None, vols=None, start="2026-06-01"):
    n = len(closes)
    dates = pd.bdate_range(start, periods=n)
    c = np.array(closes, dtype=float)
    h = np.array(highs, dtype=float) if highs is not None else c * 1.01
    l = np.array(lows, dtype=float) if lows is not None else c * 0.99
    v = np.array(vols, dtype=float) if vols is not None else np.full(n, 100000.0)
    return pd.DataFrame({
        "DATE": dates.strftime("%Y-%m-%d"),
        "OPEN_PRICE": c,
        "HIGH_PRICE": h,
        "LOW_PRICE": l,
        "CLOSE_PRICE": c,
        "VOLUME": v,
    })


class PreBreakoutProjectionTests(unittest.TestCase):
    def test_forming_inverse_head_and_shoulders_detected_pre_breakout(self):
        # Left shoulder ~95, Head ~86, Neckline ~104, Right shoulder curling at 95 -> close 101.5 (< 104)
        closes = (
            [106, 104, 101, 98, 95, 97, 100, 103, 104]  # left shoulder down to 95, peak 104
            + [100, 95, 90, 86, 90, 95, 100, 103, 104]   # head down to 86, peak 104
            + [101, 98, 95.5, 96.5, 98.5, 100.5, 101.5]  # forming right shoulder curling up below neckline
        )
        # Pad initial bars so len >= 35
        pad = [108.0] * 12
        all_c = pad + closes
        df = QuantitativePatternEngine.compute_atr_and_keltner(_make_df(all_c))
        swings = QuantitativePatternEngine.extract_zigzag_swings(df)
        pats = QuantitativePatternEngine.detect_head_and_shoulders(df, swings)
        self.assertTrue(any("Inverse Head and Shoulders" in p["name"] for p in pats), f"Got patterns: {pats}")

        ihs = [p for p in pats if "Inverse Head and Shoulders" in p["name"]][0]
        proj = compute_pattern_projection(ihs, curr_close=float(all_c[-1]), atr_14=2.2, rsi_14=56.0, symbol="TESTIHS")
        self.assertIn(proj["setup_stage"], ("IMMINENT_BREAKOUT", "FORMING_PRE_BREAKOUT"))
        self.assertTrue(proj["is_pre_breakout"])
        self.assertFalse(proj["is_late_entry"])
        self.assertGreater(proj["breakout_trigger"], all_c[-1])
        self.assertGreater(proj["week4_target"], proj["breakout_trigger"])
        self.assertLess(proj["projected_stop_loss"], all_c[-1])
        self.assertIn("TESTIHS is forming", proj["projection_summary"])
        self.assertIn("4W projected target", proj["projection_summary"])

    def test_forming_saucer_right_wall_and_extended_saucer_rejection(self):
        # 55-bar saucer: left rim 100 -> trough 82 -> right wall recovering to 96.5 (not yet extended)
        x = np.linspace(0, 1, 55)
        bowl = 82.0 + 18.0 * ((2.0 * x - 1.0) ** 2)
        # Right wall curling slightly below left rim 100 (at 96.5)
        bowl[-1] = 96.5
        vols = np.where((x > 0.30) & (x < 0.70), 50000.0, 140000.0)
        df = QuantitativePatternEngine.compute_atr_and_keltner(_make_df(bowl, vols=vols))
        pats = QuantitativePatternEngine.detect_saucer_pattern(df)
        self.assertEqual(len(pats), 1)
        proj = compute_pattern_projection(pats[0], curr_close=96.5, atr_14=2.0, rsi_14=58.0, symbol="SAUCERX")
        self.assertIn(proj["setup_stage"], ("IMMINENT_BREAKOUT", "FORMING_PRE_BREAKOUT"))
        self.assertTrue(proj["is_pre_breakout"])
        self.assertFalse(proj["is_late_entry"])
        self.assertGreater(proj["breakout_trigger"], 96.5)
        self.assertGreater(proj["week4_target"], proj["breakout_trigger"])

        # Extended saucer: price surged > 12% above left rim -> rejected or flagged EXTENDED_LATE
        ext_bowl = bowl.copy()
        ext_bowl[-1] = 115.0
        df_ext = QuantitativePatternEngine.compute_atr_and_keltner(_make_df(ext_bowl, vols=vols))
        pats_ext = QuantitativePatternEngine.detect_saucer_pattern(df_ext)
        if pats_ext:
            proj_ext = compute_pattern_projection(pats_ext[0], curr_close=115.0, atr_14=2.0, rsi_14=75.0)
            self.assertEqual(proj_ext["setup_stage"], "EXTENDED_LATE")
            self.assertTrue(proj_ext["is_late_entry"])
            self.assertFalse(proj_ext["is_pre_breakout"])

    def test_vcp_coil_detection_and_today_tomorrow_timing(self):
        # 55-bar uptrend followed by wide swings then tight 10-bar coil below 120 pivot on dry volume
        closes = [95 + i * 0.6 for i in range(25)]  # 95 -> 109.4
        highs = [c + 1.5 for c in closes]
        lows = [c - 1.5 for c in closes]
        vols = [200000.0] * 25

        # Prior 20 bars: wider pullback/consolidation 108..120
        wide_c = [115, 119.5, 114, 110, 113, 118, 116, 111, 109, 112, 116, 119.0, 115, 112, 114, 117, 119.8, 116, 114, 116]
        wide_h = [c + 2.2 if c < 118 else 120.0 for c in wide_c]
        wide_l = [c - 2.2 for c in wide_c]
        wide_v = [160000.0] * 20

        # Final 10 bars: tight coil between 116.5 and 118.8 just below 120.0 pivot, drying volume
        coil_c = [117.0, 117.6, 117.2, 117.8, 117.5, 118.0, 117.9, 118.2, 118.1, 118.4]
        coil_h = [c + 0.6 for c in coil_c]
        coil_l = [c - 0.6 for c in coil_c]
        coil_v = [70000.0] * 10

        df = QuantitativePatternEngine.compute_atr_and_keltner(
            _make_df(closes + wide_c + coil_c, highs=highs + wide_h + coil_h, lows=lows + wide_l + coil_l, vols=vols + wide_v + coil_v)
        )
        vcp = QuantitativePatternEngine.detect_vcp_coil(df)
        self.assertEqual(len(vcp), 1)
        self.assertEqual(vcp[0]["name"], "Volatility Contraction Coil (VCP)")
        proj = compute_pattern_projection(
            vcp[0],
            curr_close=118.4,
            atr_14=float(df["ATR_14"].iloc[-1]),
            rsi_14=float(df["RSI_14"].iloc[-1]),
            symbol="VCPCO",
        )
        self.assertEqual(proj["setup_stage"], "IMMINENT_BREAKOUT")
        self.assertEqual(proj["entry_window"], "Near Pivot (Watch Close)")
        self.assertTrue(proj["is_pre_breakout"])
        self.assertGreaterEqual(proj["breakout_trigger"], 119.5)
        self.assertGreater(proj["week4_target"], proj["breakout_trigger"])
        self.assertLess(proj["projected_stop_loss"], 118.4)
        self.assertIn("daily close above", proj["projection_summary"].lower())
        self.assertIn("4w projected target", proj["projection_summary"].lower())

    def test_darvas_flat_base_and_falling_wedge_detection(self):
        # 1. Darvas Flat Base: +22% uptrend then 20-bar tight box (114..121) on dry volume, close 118.8
        up = [95.0 + i * 0.70 for i in range(36)]  # 95 -> 119.5
        up_h = [c + 1.0 for c in up]
        up_l = [c - 1.0 for c in up]
        up_v = [200000.0] * 36

        box_c = [119.5, 117.0, 115.5, 116.5, 118.0, 120.0, 118.5, 116.0, 115.0, 117.0,
                 118.5, 119.8, 117.5, 116.0, 116.8, 118.0, 119.0, 118.2, 118.5, 118.8]
        box_h = [121.0 if i in (0, 5, 11) else c + 0.8 for i, c in enumerate(box_c)]
        box_l = [114.0 if i in (2, 8) else c - 0.8 for i, c in enumerate(box_c)]
        box_v = [140000.0] * 15 + [80000.0] * 5

        df_darvas = QuantitativePatternEngine.compute_atr_and_keltner(
            _make_df(up + box_c, highs=up_h + box_h, lows=up_l + box_l, vols=up_v + box_v)
        )
        darvas = QuantitativePatternEngine.detect_flat_base_darvas(df_darvas)
        self.assertEqual(len(darvas), 1)
        self.assertEqual(darvas[0]["name"], "Darvas Box / Flat Base")
        self.assertEqual(darvas[0]["entry_trigger"], 121.0)

        # 2. Falling Wedge: converging lower highs (130 -> 118) & lower lows (116 -> 110)
        df_w = _make_df([120.0] * 40)
        swings_w = [
            {"type": "high", "idx": 15, "price": 130.0},
            {"type": "low", "idx": 20, "price": 116.0},
            {"type": "high", "idx": 28, "price": 118.0},
            {"type": "low", "idx": 34, "price": 110.0},
        ]
        df_w.loc[df_w.index[-1], "CLOSE_PRICE"] = 115.5
        wedge = QuantitativePatternEngine.detect_falling_wedge(df_w, swings_w)
        self.assertEqual(len(wedge), 1)
        self.assertEqual(wedge[0]["name"], "Falling Wedge (Bullish)")
        self.assertEqual(wedge[0]["entry_trigger"], 118.0)

    def test_4week_target_bounds_and_synthesizer_anti_chasing(self):
        # Huge raw pattern target (+60%) gets capped to realistic 4-week ATR move
        pat = {
            "name": "Cup and Handle",
            "direction": "Bullish",
            "quality_score": 88,
            "entry_trigger": 500.0,
            "target_price": 800.0,
            "stop_loss": 475.0,
        }
        proj = compute_pattern_projection(pat, curr_close=492.0, atr_14=10.0, rsi_14=57.0, symbol="CAPTEST")
        self.assertEqual(proj["setup_stage"], "IMMINENT_BREAKOUT")
        self.assertLessEqual(proj["week4_target"], 500.0 + 3.4 * 10.0 + 0.05)
        self.assertGreater(proj["week4_target"], proj["week4_target_low"])
        self.assertGreater(proj["week4_target_low"], proj["breakout_trigger"])
        self.assertLess(proj["projected_stop_loss"], 492.0)

        # Late / extended pattern dampens pattern signal in synthesizer
        fresh_pat = {"name": "Cup and Handle", "direction": "Bullish", "quality_score": 88, "is_late_entry": False}
        late_pat = {"name": "Cup and Handle", "direction": "Bullish", "quality_score": 88, "is_late_entry": True}
        q_fresh, _ = _pattern_signal(fresh_pat)
        q_late, note_late = _pattern_signal(late_pat)
        self.assertLess(q_late, q_fresh)
        self.assertIn("Extended / Late", note_late)

        # Compute verdict keeps pre_breakout_projection when forming
        tech = {"last_price": 492.0, "sma_50": 470.0, "sma_200": 440.0, "rsi_14": 57.0}
        sig = Synth.compute_quantitative_verdict(
            "CAPTEST", "Cap Test Ltd", 492.0, tech, {}, [{**pat, **proj}], {}, None
        )
        self.assertIsNotNone(sig.get("pre_breakout_projection"))
        self.assertEqual(sig["pre_breakout_projection"]["setup_stage"], "IMMINENT_BREAKOUT")

    def test_api_services_pre_breakout_and_top_patterns_exclude_consolidation(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "test_pb.db")
            cm = CacheManager(db_path=db_path)
            te = TechnicalAnalysisEngine(cache_manager=cm)

            # Seed candles for a forming VCP stock (RELIANCE is in curated symbols.json)
            closes = [95 + i * 0.6 for i in range(25)]
            highs = [c + 1.5 for c in closes]
            lows = [c - 1.5 for c in closes]
            vols = [200000.0] * 25
            wide_c = [115, 119.5, 114, 110, 113, 118, 116, 111, 109, 112, 116, 119.0, 115, 112, 114, 117, 119.8, 116, 114, 116]
            wide_h = [c + 2.2 if c < 118 else 120.0 for c in wide_c]
            wide_l = [c - 2.2 for c in wide_c]
            wide_v = [160000.0] * 20
            coil_c = [117.0, 117.6, 117.2, 117.8, 117.5, 118.0, 117.9, 118.2, 118.1, 118.4]
            coil_h = [c + 0.6 for c in coil_c]
            coil_l = [c - 0.6 for c in coil_c]
            coil_v = [70000.0] * 10

            df_in = _make_df(closes + wide_c + coil_c, highs=highs + wide_h + coil_h, lows=lows + wide_l + coil_l, vols=vols + wide_v + coil_v)
            records = []
            for _, row in df_in.iterrows():
                records.append({
                    "symbol": "RELIANCE",
                    "date": row["DATE"],
                    "open": float(row["OPEN_PRICE"]),
                    "high": float(row["HIGH_PRICE"]),
                    "low": float(row["LOW_PRICE"]),
                    "close": float(row["CLOSE_PRICE"]),
                    "adj_close": float(row["CLOSE_PRICE"]),
                    "volume": int(row["VOLUME"]),
                })
            cm.save_historical_candles(records)

            # Seed one "Consolidation Range" stock (should be filtered out of /api/patterns/top)
            cm.save_agent_output("TCS", "Master Prediction Synthesizer Agent", {
                "last_price": 3500.0,
                "structured_signal": {
                    "action_verdict": "HOLD",
                    "confidence_score": 50,
                    "chart_patterns": "Consolidation Range",
                    "when_to_sell_target": "Rs. 3650.00",
                    "stop_loss": "Rs. 3350.00",
                },
            })

            res = get_pre_breakout_projections(cm, te, universe="curated", limit=20)
            self.assertGreaterEqual(res["count"], 1)
            rel = [p for p in res["picks"] if p["symbol"] == "RELIANCE"]
            self.assertEqual(len(rel), 1)
            self.assertIn(rel[0]["setup_stage"], ("IMMINENT_BREAKOUT", "FORMING_PRE_BREAKOUT"))
            self.assertGreater(rel[0]["week4_target"], rel[0]["breakout_trigger"])
            self.assertGreater(rel[0]["breakout_trigger"], rel[0]["last_price"])

            # Verify JSON safety (no NaN/Inf)
            encoded = safe_json_dumps(res).decode("utf-8")
            parsed = json.loads(encoded)
            self.assertEqual(parsed["count"], res["count"])

            top = get_top_pattern_picks(cm, te)
            self.assertFalse(any(p["pattern_name"] == "Consolidation Range" for p in top))

            bulk_ohlcv = cm.get_candles_bulk_ohlcv(["RELIANCE"], limit_days=30)
            self.assertIn("RELIANCE", bulk_ohlcv)
            self.assertEqual(len(bulk_ohlcv["RELIANCE"]), 30)
            self.assertLessEqual(bulk_ohlcv["RELIANCE"][0]["DATE"], bulk_ohlcv["RELIANCE"][-1]["DATE"])

    def test_no_forbidden_order_methods_in_modified_files(self):
        forbidden = ("place_order", "modify_order", "cancel_order", "order_margins")
        for rel_path in (
            "tools/pattern_engine.py",
            "agents/synthesizer_agent.py",
            "api/services.py",
            "api/routes.py",
            "dashboard_server.py",
            "main.py",
        ):
            txt = Path(os.path.join(ROOT, rel_path)).read_text(encoding="utf-8")
            for bad in forbidden:
                self.assertNotIn(bad, txt, f"Forbidden token {bad} found in {rel_path}")


if __name__ == "__main__":
    unittest.main()
