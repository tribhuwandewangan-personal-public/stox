"""
One-shot script: reads cached synthesizer outputs and injects the
Quick Picks section at the top of NSE_Stock_Predictions_latest.md.
Run once to update the existing report without a full re-analysis.
"""

import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage.cache_manager import CacheManager

REPORT_PATH = os.path.join(PROJECT_ROOT, "reports", "NSE_Stock_Predictions_latest.md")
SYMBOLS_PATH = os.path.join(PROJECT_ROOT, "symbols.json")


def compute_rr(lp, sl_raw, tgt_raw):
    try:
        _lp  = float(lp)
        _sl  = float(str(sl_raw).replace("Rs.", "").replace(",", "").strip())
        _tgt = float(str(tgt_raw).split("-")[0].replace("Rs.", "").replace(",", "").strip())
        risk   = max(0.01, _lp - _sl)
        reward = max(0.0,  _tgt - _lp)
        rr     = round(reward / risk, 2)
        upside = f"+{round((_tgt - _lp) / _lp * 100, 1)}%"
        return rr, upside
    except Exception:
        return 0.0, "N/A"


def build_quick_picks(symbols_list, cache_mgr):
    picks = []
    for item in symbols_list:
        sym   = item.get("symbol", "").upper()
        cname = item.get("name", "")
        sec   = item.get("sector", "")

        synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=168)
        if not synth_res:
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=None)
        if not synth_res:
            continue

        sig      = synth_res.get("structured_signal", {})
        verdict  = str(sig.get("action_verdict", "HOLD")).upper()
        conf_raw = str(sig.get("confidence_rating", "")).upper()
        entry    = sig.get("when_to_buy_entry", "N/A")
        target   = sig.get("when_to_sell_target", "N/A")
        sl       = sig.get("stop_loss", "N/A")
        pattern  = sig.get("chart_patterns", "")
        lp       = synth_res.get("last_price", "N/A")

        if verdict not in ("BUY", "ACCUMULATE", "STRONG BUY"):
            continue
        if "HIGH" not in conf_raw:
            continue

        rr, upside = compute_rr(lp, sl, target)

        picks.append({
            "sym": sym, "cname": cname, "sec": sec,
            "verdict": verdict, "entry": entry, "target": target,
            "sl": sl, "lp": lp, "upside": upside, "rr": rr, "pattern": pattern,
        })

    picks.sort(key=lambda x: x["rr"], reverse=True)
    top = picks[:7]

    if not top:
        return "\n## ⚡ Today's Quick Picks\n> No HIGH-confidence BUY signals found.\n\n---\n"

    lines = []
    lines.append("## ⚡ Today's Quick Picks")
    lines.append("> **For busy days** — HIGH-confidence BUY signals only, ranked by Reward\\:Risk ratio.")
    lines.append("> Entry, target and stop-loss are all you need. No need to read individual stock sections.\n")
    lines.append("| # | Symbol | Last Price | Entry Range | Target | Stop Loss | Upside | R:R | Pattern | Sector |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for i, p in enumerate(top, 1):
        rr_disp = f"{p['rr']:.1f}x" if p["rr"] else "N/A"
        lines.append(
            f"| {i} | **[{p['sym']}](#{p['sym'].lower()}---{p['cname'].lower().replace(' ', '-').replace('(', '').replace(')', '')})** "
            f"| Rs. {p['lp']} | {p['entry']} | {p['target']} "
            f"| {p['sl']} | {p['upside']} | {rr_disp} | {p['pattern']} | {p['sec']} |"
        )

    lines.append("")
    lines.append("> [!TIP]")
    lines.append("> **How to use**: Place limit buy orders at the **lower end** of the Entry Range.")
    lines.append("> Stop loss is non-negotiable. Stocks are sorted best Reward\\:Risk first —")
    lines.append("> if you can only act on 1–2 today, start from the top of this table.\n")
    lines.append("---\n")

    return "\n".join(lines)


def main():
    with open(SYMBOLS_PATH, "r", encoding="utf-8") as f:
        symbols_list = json.load(f).get("symbols", [])

    cache_mgr = CacheManager()
    quick_picks_md = build_quick_picks(symbols_list, cache_mgr)

    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Check if section already injected
    if "## ⚡ Today's Quick Picks" in content:
        # Remove old section so we can refresh it
        start = content.find("## ⚡ Today's Quick Picks")
        # Find the next '## ' heading or '---' that ends this section
        end = content.find("\n## ", start + 10)
        if end == -1:
            end = len(content)
        content = content[:start] + content[end:].lstrip("\n")

    # Inject after the header block (after the first '---')
    insert_after = content.find("\n---\n")
    if insert_after == -1:
        insert_after = content.find("\n---")
    if insert_after == -1:
        insert_after = 0

    inject_pos = insert_after + len("\n---\n")
    new_content = content[:inject_pos] + "\n" + quick_picks_md + "\n" + content[inject_pos:]

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✅ Quick Picks section injected into {REPORT_PATH}")
    print(f"   Showing top picks from cached analysis.")


if __name__ == "__main__":
    main()

