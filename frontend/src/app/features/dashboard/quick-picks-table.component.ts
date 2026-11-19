/**
 * Today's Quick Picks Table: Ranked by Reward:Risk.
 * Direct parity with Jinja quickPicksBanner (Image 1 & 2).
 */

import { Component, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { Stock } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';

interface QuickPickRow {
  symbol: string;
  last_price: number;
  entry_range: string;
  target: number;
  stop_loss: number;
  upside: string;
  rr: number;
  pattern: string;
}

@Component({
  selector: 'app-quick-picks-table',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="qp-wrapper" *ngIf="picks().length">
      <div class="qp-card">
        <div class="qp-header">
          <div class="qp-title-block">
            <span class="qp-icon">⚡</span>
            <div>
              <div class="qp-heading">Today's Quick Picks</div>
              <div class="qp-sub">HIGH-confidence BUY signals &bull; Ranked by Reward:Risk &bull; Scan in under 30 seconds</div>
            </div>
          </div>
          <button class="qp-toggle-btn" (click)="collapsed.update(v => !v)">
            {{ collapsed() ? '▼ Show' : '▲ Hide' }}
          </button>
        </div>

        <div class="qp-body" *ngIf="!collapsed()">
          <div class="table-wrap">
            <table class="qp-table">
              <thead>
                <tr>
                  <th class="col-num">#</th>
                  <th>SYMBOL</th>
                  <th>LAST PRICE</th>
                  <th>ENTRY RANGE</th>
                  <th>TARGET</th>
                  <th>STOP LOSS</th>
                  <th>UPSIDE</th>
                  <th>R:R</th>
                  <th>PATTERN</th>
                </tr>
              </thead>
              <tbody>
                @for (p of picks(); track p.symbol; let i = $index) {
                  <tr (click)="onSelect(p.symbol)">
                    <td class="col-num">{{ i + 1 }}</td>
                    <td class="col-sym">
                      <button class="sym-pill">{{ p.symbol }} ↗</button>
                    </td>
                    <td class="col-mono">Rs. {{ p.last_price | number:'1.2-2' }}</td>
                    <td class="col-mono">{{ p.entry_range }}</td>
                    <td class="col-mono accent-green">Rs. {{ p.target | number:'1.2-2' }}</td>
                    <td class="col-mono accent-red">Rs. {{ p.stop_loss | number:'1.2-2' }}</td>
                    <td class="col-mono accent-green bold">{{ p.upside }}</td>
                    <td class="col-rr">
                      <span class="rr-pill">{{ p.rr }}x</span>
                    </td>
                    <td class="col-pattern">{{ p.pattern }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="qp-tip">
            💡 <strong>How to use:</strong> Place limit buy at the <em>lower end</em> of Entry Range. Stop loss is non-negotiable. Best R:R stocks listed first — on busy days, start from row #1.
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .qp-wrapper {
      padding: 12px 20px 0 20px;
    }

    .qp-card {
      background: rgba(18, 26, 43, 0.7);
      border: 1px solid rgba(56, 189, 248, 0.25);
      border-radius: 12px;
      padding: 14px 18px;
      backdrop-filter: blur(12px);
    }

    .qp-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }

    .qp-title-block {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .qp-icon {
      font-size: 1.4rem;
      color: #38bdf8;
    }

    .qp-heading {
      font-family: 'Outfit', sans-serif;
      font-size: 0.95rem;
      font-weight: 700;
      color: #fff;
    }

    .qp-sub {
      font-size: 0.72rem;
      color: #94a3b8;
    }

    .qp-toggle-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #38bdf8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
    }

    .qp-body {
      margin-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .table-wrap {
      overflow-x: auto;
    }

    .qp-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78rem;
    }

    .qp-table th {
      text-align: left;
      padding: 8px 10px;
      color: #64748b;
      font-size: 0.68rem;
      font-weight: 700;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      white-space: nowrap;
    }

    .qp-table td {
      padding: 9px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
      color: #e2e8f0;
    }
    .qp-table tr:hover td {
      background: rgba(56, 189, 248, 0.05);
      cursor: pointer;
    }

    .col-num {
      color: #64748b;
      font-size: 0.7rem;
      width: 30px;
    }

    .col-mono {
      font-family: 'JetBrains Mono', monospace;
      white-space: nowrap;
    }

    .accent-green { color: #10b981; }
    .accent-red   { color: #ef4444; }
    .bold { font-weight: 700; }

    .sym-pill {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #38bdf8;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      cursor: pointer;
    }

    .rr-pill {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
    }

    .col-pattern {
      color: #cbd5e1;
      font-size: 0.75rem;
    }

    .qp-tip {
      font-size: 0.72rem;
      color: #94a3b8;
      background: rgba(245, 158, 11, 0.05);
      border-left: 2px solid #f59e0b;
      padding: 6px 10px;
      border-radius: 4px;
      line-height: 1.4;
    }

    @media (max-width: 768px) {
      .qp-wrapper { padding: 8px 12px 0 12px; }
    }
  `]
})
export class QuickPicksTableComponent {
  stocksStore = stocksStore;
  collapsed = signal(false);

  picks = computed<QuickPickRow[]>(() => {
    const list: QuickPickRow[] = [];
    const stocks = this.stocksStore.stocks();

    for (const s of stocks) {
      const synth = (s.synth_output?.structured_signal || {}) as any;
      const tech = (s.tech_output?.raw_indicators || {}) as any;
      const verdict = (synth.action_verdict || '').toUpperCase();
      const confRaw = (synth.confidence_rating || '').toUpperCase();

      if (!verdict.includes('BUY') && !verdict.includes('ACCUMULATE')) continue;

      const lp = Number(tech.last_price || s.price_info?.price || 0);
      const tgtRaw = (synth.when_to_sell_target || '').replace(/Rs\.?\s*/i, '').replace(/,/g, '').split('-')[0].trim();
      const slRaw = (synth.stop_loss || '').replace(/Rs\.?\s*/i, '').replace(/,/g, '').trim();
      const tgt = parseFloat(tgtRaw) || Number(synth.target_num || 0);
      const sl = parseFloat(slRaw) || Number(synth.stop_num || 0);

      if (lp > 0 && sl > 0 && sl < lp && tgt > lp) {
        const risk = lp - sl;
        const reward = tgt - lp;
        const rr = Math.round((reward / risk) * 10) / 10;
        const upside = '+' + ((tgt - lp) / lp * 100).toFixed(1) + '%';
        const pattern = s.patterns?.[0]?.name || synth.chart_patterns || 'High Conviction Trend';

        list.push({
          symbol: s.symbol,
          last_price: lp,
          entry_range: synth.when_to_buy_entry || `Rs. ${fmtPrice(lp * 0.98)} - ${fmtPrice(lp * 1.01)}`,
          target: tgt,
          stop_loss: sl,
          upside,
          rr,
          pattern
        });
      }
    }

    list.sort((a, b) => b.rr - a.rr);
    return list.slice(0, 8);
  });

  onSelect(symbol: string): void {
    stocksStore.selectSymbol(symbol);
  }
}
