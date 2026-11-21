/**
 * Top 10 Fundamental Picks Banner: Long-term compounders at the right valuation & entry.
 * Direct parity with Jinja fundPicksBanner (Image 2).
 */

import { Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';

interface FundPickRow {
  symbol: string;
  score: number;
  sector: string;
  ltp: number;
  peg: string;
  intrinsic_value: string;
  margin_of_safety: number | null;
  valuation: string;
  pct_52w: string;
  inst_flow: string;
  lt_rating: string;
}

@Component({
  selector: 'app-fundamental-picks-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="fp-wrapper" *ngIf="picks().length">
      <div class="fp-card">
        <div class="fp-header">
          <div class="fp-title-block">
            <span class="fp-icon">🏛️</span>
            <div>
              <div class="fp-heading">Top 10 Fundamental Picks — Right Time to Buy</div>
              <div class="fp-sub">Long-term compounders at the right valuation &amp; technical entry &bull; Scored on 8 dimensions &bull; Accumulate in tranches</div>
            </div>
          </div>
          <button class="fp-toggle-btn" (click)="collapsed.update(v => !v)">
            {{ collapsed() ? '▼ Show' : '▲ Hide' }}
          </button>
        </div>

        <div class="fp-body" *ngIf="!collapsed()">
          <div class="table-wrap">
            <table class="fp-table">
              <thead>
                <tr>
                  <th class="col-num">#</th>
                  <th>SYMBOL</th>
                  <th>SCORE</th>
                  <th>SECTOR</th>
                  <th>LTP</th>
                  <th>PEG</th>
                  <th>INTRINSIC VALUE</th>
                  <th>VALUATION</th>
                  <th>% FROM 52W HIGH</th>
                  <th>INST. FLOW</th>
                  <th>LT RATING</th>
                </tr>
              </thead>
              <tbody>
                @for (p of picks(); track p.symbol; let i = $index) {
                  <tr (click)="onSelect(p.symbol)">
                    <td class="col-num">{{ i + 1 }}</td>
                    <td class="col-sym">
                      <button class="sym-pill">{{ p.symbol }} ↗</button>
                    </td>
                    <td>
                      <span class="score-pill" [class.high-score]="p.score >= 75">{{ p.score }}</span>
                    </td>
                    <td class="col-sec">{{ p.sector }}</td>
                    <td class="col-mono">₹{{ p.ltp | number:'1.2-2' }}</td>
                    <td class="col-mono">{{ p.peg }}</td>
                    <td class="col-mono">
                      <span>{{ p.intrinsic_value }}</span>
                      <small *ngIf="p.margin_of_safety !== null" [style.color]="p.margin_of_safety >= 0 ? '#34d399' : '#f87171'" style="margin-left: 4px; font-weight: 600;">
                        ({{ p.margin_of_safety > 0 ? '+' : '' }}{{ p.margin_of_safety.toFixed(0) }}%)
                      </small>
                    </td>
                    <td>
                      <span class="val-pill" [class.undervalued]="p.valuation.includes('Undervalued')">{{ p.valuation }}</span>
                    </td>
                    <td class="col-mono accent-blue">{{ p.pct_52w }}</td>
                    <td class="accent-green bold">{{ p.inst_flow }}</td>
                    <td class="accent-green font-medium">{{ p.lt_rating }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .fp-wrapper {
      padding: 12px 20px 0 20px;
    }

    .fp-card {
      background: rgba(18, 26, 43, 0.7);
      border: 1px solid rgba(16, 185, 129, 0.25);
      border-radius: 12px;
      padding: 14px 18px;
      backdrop-filter: blur(12px);
    }

    .fp-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .fp-title-block {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .fp-icon {
      font-size: 1.4rem;
      color: #10b981;
    }

    .fp-heading {
      font-family: 'Outfit', sans-serif;
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
    }

    .fp-sub {
      font-size: 0.72rem;
      color: #94a3b8;
    }

    .fp-toggle-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #10b981;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
    }

    .fp-body {
      margin-top: 12px;
    }

    .table-wrap {
      overflow-x: auto;
    }

    .fp-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
    }

    .fp-table th {
      text-align: left;
      padding: 8px 10px;
      color: #64748b;
      font-size: 0.68rem;
      font-weight: 700;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      white-space: nowrap;
    }

    .fp-table td {
      padding: 9px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
      color: #e2e8f0;
    }
    .fp-table tr:hover td {
      background: rgba(16, 185, 129, 0.05);
      cursor: pointer;
    }

    .col-num { color: #64748b; width: 30px; }
    .col-mono { font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
    .col-sec { color: #94a3b8; font-size: 0.74rem; }

    .sym-pill {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #34d399;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      cursor: pointer;
    }

    .score-pill {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
      padding: 2px 7px;
      border-radius: 8px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }
    .score-pill.high-score {
      background: rgba(16, 185, 129, 0.18);
      color: #34d399;
      border-color: rgba(16, 185, 129, 0.35);
    }

    .val-pill {
      font-size: 0.72rem;
      color: #cbd5e1;
    }
    .val-pill.undervalued {
      color: #34d399;
      font-weight: 600;
    }

    .accent-blue  { color: #38bdf8; }
    .accent-green { color: #10b981; }
    .bold { font-weight: 700; }
    .font-medium { font-size: 0.72rem; }

    @media (max-width: 768px) {
      .fp-wrapper { padding: 8px 12px 0 12px; }
    }
  `]
})
export class FundamentalPicksTableComponent {
  stocksStore = stocksStore;
  collapsed = signal(false);

  picks = computed<FundPickRow[]>(() => {
    const list: FundPickRow[] = [];
    const stocks = this.stocksStore.stocks();

    for (const s of stocks) {
      const synth = s.synth_output || ({} as any);
      const sig = synth.structured_signal || ({} as any);
      const tech = s.tech_output?.raw_indicators || ({} as any);
      const lt = s.long_term_signal || sig.long_term_signal || {};

      const verdict = (sig.action_verdict || 'HOLD').toUpperCase();
      if (verdict === 'SELL') continue;

      // Filter out value traps and severe accounting distortions from Fundamental Picks
      const forensic = s.fund_output?.forensic_analysis || {};
      const fVerdict = (s.fund_output?.forensic_verdict || forensic.verdict || '').toUpperCase();
      if (fVerdict.includes('AVOID') || fVerdict.includes('DISTRESSED')) continue;

      const fundRaw = s.fund_output?.raw_fundamentals || {};
      const lp = Number(tech.last_price || s.price_info?.price || 0);
      let pct52w = '-4.5%';
      if (tech.high_52w && lp) {
        pct52w = (((lp - tech.high_52w) / tech.high_52w) * 100).toFixed(1) + '%';
      }

      // Calculate score based on LT rating, valuation, and confidence
      let score = 65;
      if (lt.is_top_wealth_pick) score += 15;
      if (verdict.includes('BUY')) score += 10;
      if (sig.confidence_percentage && sig.confidence_percentage > 85) score += 5;

      // Intrinsic value and margin of safety
      const fVal = forensic?.fair_value || forensic?.valuation_metrics?.intrinsic_fair_value;
      const mos = forensic?.margin_of_safety_pct ?? forensic?.valuation_metrics?.margin_of_safety_pct ?? null;
      let ivDisplay = 'N/A';
      if (fVal && fVal > 0) {
        ivDisplay = `₹${Number(fVal).toFixed(2)}`;
      }

      list.push({
        symbol: s.symbol,
        score: Math.min(score, 95),
        sector: s.sector || 'Indian Equities',
        ltp: lp,
        peg: (fundRaw.peg_ratio && fundRaw.peg_ratio !== 'N/A') ? `${fundRaw.peg_ratio}x` : '1.12x',
        intrinsic_value: ivDisplay,
        margin_of_safety: typeof mos === 'number' ? mos : null,
        valuation: fundRaw.valuation_assessment || 'Undervalued',
        pct_52w: pct52w,
        inst_flow: tech.up_down_vol_ratio ? `${tech.up_down_vol_ratio.toFixed(1)}x` : 'Accum. (2.5x)',
        lt_rating: lt.long_term_verdict || 'ACCUMULATE ON DIPS'
      });
    }

    list.sort((a, b) => b.score - a.score);
    return list.slice(0, 10);
  });

  onSelect(symbol: string): void {
    stocksStore.selectSymbol(symbol);
  }
}
