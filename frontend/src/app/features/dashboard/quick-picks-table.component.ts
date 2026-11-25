/**
 * Today's Quick Picks Table: Ranked by Reward:Risk.
 * Direct parity with Jinja quickPicksBanner (Image 1 & 2).
 */

import { Component, TemplateRef, ViewChild, computed, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { Stock } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

interface QuickPickRow {
  symbol: string;
  last_price: number;
  entry_range: string;
  target: number;
  stop_loss: number;
  upside: string;
  upside_num: number;
  rr: number;
  pattern: string;
}

@Component({
  selector: 'app-quick-picks-table',
  standalone: true,
  imports: [CommonModule, StoxGridComponent],
  template: `
    <div class="stox-banner-wrap" *ngIf="picks().length">
      <div class="stox-banner-card">
        <div class="stox-banner-header">
          <div class="stox-banner-title-block">
            <span class="stox-banner-icon accent-sky">⚡</span>
            <div>
              <div class="stox-banner-heading">Today's Quick Picks</div>
              <div class="stox-banner-sub">HIGH-confidence BUY signals &bull; Ranked by Reward:Risk &bull; Scan in under 30 seconds</div>
            </div>
          </div>
          <button class="stox-banner-toggle" (click)="collapsed.update(v => !v)">
            {{ collapsed() ? '▼ Show' : '▲ Hide' }}
          </button>
        </div>

        <div class="stox-banner-body" *ngIf="!collapsed()">
          <app-stox-grid
            [data]="picks()"
            [columns]="gridColumns()"
            (rowClick)="onSelect($event.symbol)"
          ></app-stox-grid>

          <div class="stox-banner-tip">
            💡 <strong>Advisory Notice:</strong> Rule-based R:R shortlist for educational analysis only (not financial advice). Verify entry range and invalidation stop loss before making any independent decision; list is ordered by R:R ratio.
          </div>
        </div>
      </div>
    </div>
    <ng-template #qpIdxTpl let-i="index"><span class="col-num">{{ i + 1 }}</span></ng-template>
    <ng-template #qpSymTpl let-p><button class="sym-pill">{{ p.symbol }} ↗</button></ng-template>
    <ng-template #qpLtpTpl let-p><span class="col-mono price-bold">Rs. {{ p.last_price | number:'1.2-2' }}</span></ng-template>
    <ng-template #qpEntryTpl let-p><span class="col-mono entry-chip">{{ p.entry_range }}</span></ng-template>
    <ng-template #qpTgtTpl let-p><span class="col-mono accent-green bold">Rs. {{ p.target | number:'1.2-2' }}</span></ng-template>
    <ng-template #qpSlTpl let-p><span class="col-mono sl-chip">Rs. {{ p.stop_loss | number:'1.2-2' }}</span></ng-template>
    <ng-template #qpUpTpl let-p><span class="upside-pill">{{ p.upside }}</span></ng-template>
    <ng-template #qpRrTpl let-p><span class="rr-pill">{{ p.rr }}x</span></ng-template>
    <ng-template #qpPatTpl let-p><span class="pat-chip" [title]="p.pattern">{{ p.pattern }}</span></ng-template>
  `,
})
export class QuickPicksTableComponent {
  stocksStore = stocksStore;
  collapsed = signal(false);

  @ViewChild('qpIdxTpl', { static: true }) qpIdxTpl!: TemplateRef<any>;
  @ViewChild('qpSymTpl', { static: true }) qpSymTpl!: TemplateRef<any>;
  @ViewChild('qpLtpTpl', { static: true }) qpLtpTpl!: TemplateRef<any>;
  @ViewChild('qpEntryTpl', { static: true }) qpEntryTpl!: TemplateRef<any>;
  @ViewChild('qpTgtTpl', { static: true }) qpTgtTpl!: TemplateRef<any>;
  @ViewChild('qpSlTpl', { static: true }) qpSlTpl!: TemplateRef<any>;
  @ViewChild('qpUpTpl', { static: true }) qpUpTpl!: TemplateRef<any>;
  @ViewChild('qpRrTpl', { static: true }) qpRrTpl!: TemplateRef<any>;
  @ViewChild('qpPatTpl', { static: true }) qpPatTpl!: TemplateRef<any>;

  gridColumns = computed<StoxGridColumn<QuickPickRow>[]>(() => [
    { id: 'idx', header: '#', sortable: false, cellTemplate: this.qpIdxTpl, cellClass: 'col-num' },
    { id: 'symbol', header: 'Symbol', accessorFn: r => r.symbol, cellTemplate: this.qpSymTpl },
    { id: 'last_price', header: 'Last Price', accessorFn: r => r.last_price, cellTemplate: this.qpLtpTpl },
    { id: 'entry_range', header: 'Entry Range', accessorFn: r => r.entry_range, cellTemplate: this.qpEntryTpl },
    { id: 'target', header: 'Target', accessorFn: r => r.target, cellTemplate: this.qpTgtTpl },
    { id: 'stop_loss', header: 'Stop Loss', accessorFn: r => r.stop_loss, cellTemplate: this.qpSlTpl },
    { id: 'upside_num', header: 'Upside', accessorFn: r => r.upside_num, cellTemplate: this.qpUpTpl },
    { id: 'rr', header: 'R:R', accessorFn: r => r.rr, cellTemplate: this.qpRrTpl },
    { id: 'pattern', header: 'Pattern', accessorFn: r => r.pattern, cellTemplate: this.qpPatTpl },
  ]);

  picks = computed<QuickPickRow[]>(() => {
    const list: QuickPickRow[] = [];
    const stocks = this.stocksStore.stocks();

    for (const s of stocks) {
      const synth = (s.synth_output?.structured_signal || {}) as any;
      const tech = (s.tech_output?.raw_indicators || {}) as any;
      const verdict = (synth.action_verdict || '').toUpperCase();
      const confRaw = (synth.confidence_rating || '').toUpperCase();

      if ((!verdict.includes('BUY') && !verdict.includes('ACCUMULATE')) || !confRaw.includes('HIGH')) continue;

      const lp = Number(s.price_info?.price || tech.last_price || 0);
      const tgtRaw = (synth.when_to_sell_target || '').replace(/Rs\.?\s*/i, '').replace(/,/g, '').split('-')[0].trim();
      const slRaw = (synth.stop_loss || '').replace(/Rs\.?\s*/i, '').replace(/,/g, '').trim();
      const tgt = parseFloat(tgtRaw) || Number(synth.target_num || 0);
      const sl = parseFloat(slRaw) || Number(synth.stop_num || 0);

      if (lp > 0 && sl > 0 && sl < lp && tgt > lp) {
        const risk = lp - sl;
        const reward = tgt - lp;
        const riskPct = risk / lp;
        const rewardPct = reward / lp;
        const rr = Math.round((reward / risk) * 10) / 10;
        if (riskPct < 0.014 || riskPct > 0.125 || rewardPct < 0.035 || rr < 1.8 || rr > 10.0) continue;
        const upside = '+' + (rewardPct * 100).toFixed(1) + '%';
        const rawPattern = (synth.chart_patterns || '').trim();
        const pattern = s.patterns?.[0]?.name || (rawPattern && rawPattern !== 'N/A' ? rawPattern : '—');

        list.push({
          symbol: s.symbol,
          last_price: lp,
          entry_range: synth.when_to_buy_entry || `${fmtPrice(lp * 0.98)} - ${fmtPrice(lp * 1.01).replace(/^Rs\.\s*/, '')}`,
          target: tgt,
          stop_loss: sl,
          upside,
          upside_num: rewardPct * 100,
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
