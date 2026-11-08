"""Patch index.html to add Quick Picks banner + CSS + JS."""
import re, os

HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "index.html")

with open(HTML_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# ── 1. CSS  ──────────────────────────────────────────────────────────────────
CSS = """
    /* ⚡ Quick Picks Banner */
    .quick-picks-banner {
      background: linear-gradient(135deg, rgba(16,24,40,0.97) 0%, rgba(10,30,50,0.97) 100%);
      border: 1px solid rgba(56,189,248,0.35);
      border-radius: 14px;
      margin-bottom: 22px;
      overflow: hidden;
      box-shadow: 0 0 32px rgba(56,189,248,0.08);
    }
    .qp-header {
      display: flex; align-items: center; justify-content: space-between;
      padding: 14px 20px;
      background: linear-gradient(90deg, rgba(56,189,248,0.12) 0%, transparent 100%);
      border-bottom: 1px solid rgba(56,189,248,0.2);
      flex-wrap: wrap; gap: 10px;
    }
    .qp-title { display: flex; align-items: center; gap: 14px; }
    .qp-icon { font-size: 1.8rem; line-height: 1; }
    .qp-heading {
      font-family: 'Outfit', sans-serif; font-size: 1.1rem; font-weight: 700;
      color: #38bdf8; letter-spacing: 0.3px;
    }
    .qp-sub { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
    .qp-collapse-btn {
      background: rgba(56,189,248,0.1); border: 1px solid rgba(56,189,248,0.3);
      color: #38bdf8; padding: 5px 14px; border-radius: 20px;
      font-size: 0.78rem; cursor: pointer; transition: all 0.2s; white-space: nowrap;
    }
    .qp-collapse-btn:hover { background: rgba(56,189,248,0.25); }
    .qp-table-wrap { overflow-x: auto; padding: 16px 20px 8px; }
    .qp-table {
      width: 100%; border-collapse: collapse; font-size: 0.82rem;
    }
    .qp-table th {
      text-align: left; padding: 7px 12px;
      color: var(--text-muted); font-weight: 600; font-size: 0.72rem;
      text-transform: uppercase; letter-spacing: 0.5px;
      border-bottom: 1px solid rgba(255,255,255,0.08); white-space: nowrap;
    }
    .qp-table td {
      padding: 9px 12px; border-bottom: 1px solid rgba(255,255,255,0.05);
      white-space: nowrap; vertical-align: middle;
    }
    .qp-table tr:last-child td { border-bottom: none; }
    .qp-table tr:hover td { background: rgba(56,189,248,0.04); }
    .qp-rank { font-weight: 700; color: var(--text-muted); }
    .qp-sym-btn {
      background: rgba(56,189,248,0.12); border: 1px solid rgba(56,189,248,0.3);
      color: #38bdf8; padding: 4px 10px; border-radius: 6px;
      font-weight: 700; font-size: 0.82rem; cursor: pointer;
      font-family: 'JetBrains Mono', monospace; transition: all 0.15s;
    }
    .qp-sym-btn:hover { background: rgba(56,189,248,0.25); }
    .qp-price { font-family: 'JetBrains Mono', monospace; color: #cbd5e1; }
    .qp-entry { font-family: 'JetBrains Mono', monospace; color: #94a3b8; font-size: 0.78rem; }
    .qp-target { font-family: 'JetBrains Mono', monospace; color: #10b981; font-weight: 600; }
    .qp-sl { font-family: 'JetBrains Mono', monospace; color: #ef4444; }
    .qp-upside { color: #10b981; font-weight: 700; }
    .qp-rr {
      font-weight: 700; padding: 2px 8px; border-radius: 6px;
      font-family: 'JetBrains Mono', monospace;
    }
    .qp-rr-high { background: rgba(16,185,129,0.15); color: #10b981; }
    .qp-rr-mid  { background: rgba(245,158,11,0.15);  color: #f59e0b; }
    .qp-rr-low  { background: rgba(148,163,184,0.1);  color: #94a3b8; }
    .qp-pattern { color: var(--text-muted); font-size: 0.75rem; max-width: 160px;
                  overflow: hidden; text-overflow: ellipsis; }
    .qp-tip {
      padding: 10px 20px 14px;
      font-size: 0.75rem; color: var(--text-muted);
      border-top: 1px solid rgba(255,255,255,0.05);
    }
    .qp-tip strong { color: #38bdf8; }
"""

# Insert CSS before closing </style>
if "/* ⚡ Quick Picks Banner */" not in html:
    html = html.replace("  </style>", CSS + "\n  </style>", 1)

# ── 2. HTML banner (before Grid Header) ─────────────────────────────────────
BANNER_HTML = """
    <!-- ⚡ Quick Picks Banner -->
    <div class="quick-picks-banner" id="quickPicksBanner" style="display:none;">
      <div class="qp-header">
        <div class="qp-title">
          <span class="qp-icon">&#9889;</span>
          <div>
            <div class="qp-heading">Today's Quick Picks</div>
            <div class="qp-sub">HIGH-confidence BUY signals &bull; Ranked by Reward:Risk &bull; Scan in under 30 seconds</div>
          </div>
        </div>
        <button class="qp-collapse-btn" onclick="toggleQuickPicks()" id="qpCollapseBtn">&#9650; Hide</button>
      </div>
      <div id="quickPicksBody">
        <div class="qp-table-wrap">
          <table class="qp-table">
            <thead>
              <tr>
                <th>#</th><th>Symbol</th><th>Last Price</th><th>Entry Range</th>
                <th>Target</th><th>Stop Loss</th><th>Upside</th><th>R:R</th><th>Pattern</th>
              </tr>
            </thead>
            <tbody id="quickPicksRows"></tbody>
          </table>
        </div>
        <div class="qp-tip">
          &#128161; <strong>How to use:</strong> Place limit buy at the <strong>lower end</strong> of Entry Range.
          Stop loss is non-negotiable. Best R:R stocks listed first &mdash; on busy days, start from row&nbsp;#1.
        </div>
      </div>
    </div>

"""

# Find the Grid Header comment and insert before it
GRID_COMMENT = "    <!-- Grid Header -->"
if "quickPicksBanner" not in html:
    html = html.replace(GRID_COMMENT, BANNER_HTML + GRID_COMMENT, 1)

# ── 3. JS functions (before closing </script> tag) ───────────────────────────
JS = """
    // ── Quick Picks ──────────────────────────────────────────────────────────
    let qpVisible = true;

    function toggleQuickPicks() {
      const body = document.getElementById('quickPicksBody');
      const btn  = document.getElementById('qpCollapseBtn');
      if (!body) return;
      qpVisible = !qpVisible;
      body.style.display = qpVisible ? '' : 'none';
      if (btn) btn.innerHTML = qpVisible ? '&#9650; Hide' : '&#9660; Show Picks';
    }

    function renderQuickPicks(stocks) {
      const banner = document.getElementById('quickPicksBanner');
      const tbody  = document.getElementById('quickPicksRows');
      if (!banner || !tbody) return;

      const picks = [];
      stocks.forEach(s => {
        const synth = s.synth_output?.structured_signal || {};
        const tech  = s.tech_output?.raw_indicators    || {};
        const verdict   = (synth.action_verdict || '').toUpperCase();
        const confRaw   = (synth.confidence_rating || '').toUpperCase();

        if (!verdict.includes('BUY') && !verdict.includes('ACCUMULATE')) return;
        if (!confRaw.includes('HIGH')) return;

        const lp      = parseFloat(tech.last_price || 0);
        const tgtRaw  = (synth.when_to_sell_target || '').replace(/Rs\\.?\\s*/i,'').replace(/,/g,'').split('-')[0].trim();
        const slRaw   = (synth.stop_loss           || '').replace(/Rs\\.?\\s*/i,'').replace(/,/g,'').trim();
        const tgt     = parseFloat(tgtRaw) || 0;
        const sl      = parseFloat(slRaw)  || 0;

        let rr = 0, upside = 'N/A';
        if (lp > 0 && sl > 0 && tgt > 0) {
          const risk   = Math.max(0.01, lp - sl);
          const reward = Math.max(0, tgt - lp);
          rr     = reward / risk;
          upside = '+' + ((tgt - lp) / lp * 100).toFixed(1) + '%';
        }

        picks.push({
          sym:     s.symbol,
          lp:      lp ? 'Rs. ' + lp.toLocaleString('en-IN') : 'N/A',
          entry:   synth.when_to_buy_entry   || 'N/A',
          target:  synth.when_to_sell_target || 'N/A',
          sl:      synth.stop_loss           || 'N/A',
          upside,
          rr,
          rrDisp: rr ? rr.toFixed(1) + 'x' : 'N/A',
          pattern: synth.chart_patterns      || '',
        });
      });

      picks.sort((a, b) => b.rr - a.rr);
      const top = picks.slice(0, 7);

      if (top.length === 0) { banner.style.display = 'none'; return; }

      tbody.innerHTML = top.map((p, i) => {
        const rrClass = p.rr >= 2.5 ? 'qp-rr-high' : p.rr >= 1.5 ? 'qp-rr-mid' : 'qp-rr-low';
        return `<tr>
          <td class="qp-rank">${i + 1}</td>
          <td><button class="qp-sym-btn" onclick="openStockModalDirect('${p.sym}', event)">${p.sym} &#8599;</button></td>
          <td class="qp-price">${p.lp}</td>
          <td class="qp-entry">${p.entry}</td>
          <td class="qp-target">${p.target}</td>
          <td class="qp-sl">${p.sl}</td>
          <td class="qp-upside">${p.upside}</td>
          <td><span class="qp-rr ${rrClass}">${p.rrDisp}</span></td>
          <td class="qp-pattern" title="${p.pattern}">${p.pattern}</td>
        </tr>`;
      }).join('');

      banner.style.display = '';
    }
    // ─────────────────────────────────────────────────────────────────────────
"""

# Insert JS before the last </script> that is inside the body (heuristic: last occurrence)
if "renderQuickPicks" not in html:
    last_script_close = html.rfind("</script>")
    if last_script_close != -1:
        html = html[:last_script_close] + JS + "\n    </script>" + html[last_script_close + len("</script>"):]

# ── 4. Call renderQuickPicks after allStocksData is populated ────────────────
# Hook it right after renderStockGrid() call inside fetchStockCards
if "renderQuickPicks(stocks)" not in html:
    html = html.replace(
        "        renderSidebarItems();\n        renderStockGrid();",
        "        renderSidebarItems();\n        renderStockGrid();\n        renderQuickPicks(stocks);"
    )

with open(HTML_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("✅ index.html patched — Quick Picks banner added.")

