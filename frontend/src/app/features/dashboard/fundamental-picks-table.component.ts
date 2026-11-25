/**
 * Top 10 Fundamental Picks Banner: Long-term compounders at the right valuation & entry.
 * Direct parity with Jinja fundPicksBanner (Image 2).
 */

import { Component, TemplateRef, ViewChild, computed, effect, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { ApiService } from '../../core/services/api.service';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

interface FundPickRow {
  symbol: string;
  score: number;
  sector: string;
  ltp: number | null;
  peg: string;
  peg_num: number;
  intrinsic_value: string;
  margin_of_safety: number | null;
  valuation: string;
  pct_52w: string;
  pct_52w_num: number;
  inst_flow: string;
  inst_flow_num: number;
  lt_rating: string;
}

@Component({
  selector: 'app-fundamental-picks-table',
  standalone: true,
  imports: [CommonModule, StoxGridComponent],
  template: `
    <div class="stox-banner-wrap" *ngIf="picks().length">
      <div class="stox-banner-card stox-banner-card--emerald">
        <div class="stox-banner-header">
          <div class="stox-banner-title-block">
            <span class="stox-banner-icon accent-green">🏛️</span>
            <div>
              <div class="stox-banner-heading">Top 10 Fundamental Picks — Right Time to Buy</div>
              <div class="stox-banner-sub">Long-term compounders at the right valuation &amp; technical entry &bull; Scored on 8 dimensions &bull; Accumulate in tranches</div>
            </div>
          </div>
          <button class="stox-banner-toggle stox-banner-toggle--emerald" (click)="collapsed.update(v => !v)">
            {{ collapsed() ? '▼ Show' : '▲ Hide' }}
          </button>
        </div>

        <div class="stox-banner-body" *ngIf="!collapsed()">
          <app-stox-grid
            [data]="picks()"
            [columns]="gridColumns()"
            (rowClick)="onSelect($event.symbol)"
          ></app-stox-grid>
        </div>
      </div>
    </div>

    <ng-template #fpIdxTpl let-i="index"><span class="col-num">{{ i + 1 }}</span></ng-template>
    <ng-template #fpSymTpl let-p><button class="sym-pill sym-pill--green">{{ p.symbol }} ↗</button></ng-template>
    <ng-template #fpScoreTpl let-p><span class="score-pill" [class.high-score]="p.score >= 75">{{ p.score }}</span></ng-template>
    <ng-template #fpLtpTpl let-p><span class="col-mono">{{ p.ltp != null ? ('Rs. ' + (p.ltp | number:'1.2-2')) : 'N/A' }}</span></ng-template>
    <ng-template #fpIvTpl let-p>
      <span class="col-mono">{{ p.intrinsic_value }}</span>
      <small *ngIf="p.margin_of_safety !== null" [class]="p.margin_of_safety >= 0 ? 'accent-green bold' : 'accent-red bold'" style="margin-left: 4px;">
        ({{ p.margin_of_safety > 0 ? '+' : '' }}{{ p.margin_of_safety.toFixed(0) }}%)
      </small>
    </ng-template>
    <ng-template #fpValTpl let-p><span class="val-pill" [class.undervalued]="p.valuation.includes('Undervalued')">{{ p.valuation }}</span></ng-template>
    <ng-template #fp52Tpl let-p><span class="col-mono accent-blue">{{ p.pct_52w }}</span></ng-template>
    <ng-template #fpFlowTpl let-p><span class="accent-green bold">{{ p.inst_flow }}</span></ng-template>
    <ng-template #fpRatTpl let-p><span class="accent-green font-medium">{{ p.lt_rating }}</span></ng-template>
  `,
})
export class FundamentalPicksTableComponent {
  stocksStore = stocksStore;
  collapsed = signal(false);
  picks = signal<FundPickRow[]>([]);
  private fetchSeq = 0;

  @ViewChild('fpIdxTpl', { static: true }) fpIdxTpl!: TemplateRef<any>;
  @ViewChild('fpSymTpl', { static: true }) fpSymTpl!: TemplateRef<any>;
  @ViewChild('fpScoreTpl', { static: true }) fpScoreTpl!: TemplateRef<any>;
  @ViewChild('fpLtpTpl', { static: true }) fpLtpTpl!: TemplateRef<any>;
  @ViewChild('fpIvTpl', { static: true }) fpIvTpl!: TemplateRef<any>;
  @ViewChild('fpValTpl', { static: true }) fpValTpl!: TemplateRef<any>;
  @ViewChild('fp52Tpl', { static: true }) fp52Tpl!: TemplateRef<any>;
  @ViewChild('fpFlowTpl', { static: true }) fpFlowTpl!: TemplateRef<any>;
  @ViewChild('fpRatTpl', { static: true }) fpRatTpl!: TemplateRef<any>;

  gridColumns = computed<StoxGridColumn<FundPickRow>[]>(() => [
    { id: 'idx', header: '#', sortable: false, cellTemplate: this.fpIdxTpl, cellClass: 'col-num' },
    { id: 'symbol', header: 'Symbol', accessorFn: r => r.symbol, cellTemplate: this.fpSymTpl },
    { id: 'score', header: 'Score', accessorFn: r => r.score, cellTemplate: this.fpScoreTpl },
    { id: 'sector', header: 'Sector', accessorFn: r => r.sector, cellClass: 'col-muted' },
    { id: 'ltp', header: 'LTP', accessorFn: r => r.ltp ?? 0, cellTemplate: this.fpLtpTpl, cellClass: 'col-mono' },
    { id: 'peg', header: 'PEG', accessorFn: r => r.peg_num, cellClass: 'col-mono' },
    { id: 'intrinsic_value', header: 'Intrinsic Value', accessorFn: r => r.margin_of_safety ?? -999, cellTemplate: this.fpIvTpl, cellClass: 'col-mono' },
    { id: 'valuation', header: 'Valuation', accessorFn: r => r.valuation, cellTemplate: this.fpValTpl },
    { id: 'pct_52w', header: '% From 52W High', accessorFn: r => r.pct_52w_num, cellTemplate: this.fp52Tpl, cellClass: 'col-mono' },
    { id: 'inst_flow', header: 'Inst. Flow', accessorFn: r => r.inst_flow_num, cellTemplate: this.fpFlowTpl },
    { id: 'lt_rating', header: 'LT Rating', accessorFn: r => r.lt_rating, cellTemplate: this.fpRatTpl },
  ]);

  constructor() {
    effect(() => {
      const universe = this.stocksStore.activeUniverse();
      // Re-fetch backend-scored picks whenever universe switches or stock list refreshes
      this.stocksStore.stocks();
      void this.loadPicks(universe);
    });
  }

  private async loadPicks(universe: string): Promise<void> {
    const seq = ++this.fetchSeq;
    try {
      const resp = await ApiService.getFundamentalPicks(universe);
      if (seq !== this.fetchSeq) return;
      const rawPicks = Array.isArray(resp?.picks) ? resp.picks : [];
      this.picks.set(rawPicks.map((p: any): FundPickRow => {
        const ltp = typeof p.last_price === 'number' && Number.isFinite(p.last_price) && p.last_price > 0
          ? p.last_price
          : null;
        const pegNum = typeof p.peg === 'number' && Number.isFinite(p.peg) ? p.peg : 999;
        const pegVal = typeof p.peg === 'number' && Number.isFinite(p.peg)
          ? `${p.peg.toFixed(2)}x`
          : 'N/A';
        const ivVal = typeof p.intrinsic_value === 'number' && Number.isFinite(p.intrinsic_value) && p.intrinsic_value > 0
          ? `Rs. ${p.intrinsic_value.toFixed(2)}`
          : 'N/A';
        const mosVal = typeof p.margin_of_safety_pct === 'number' && Number.isFinite(p.margin_of_safety_pct)
          ? p.margin_of_safety_pct
          : null;
        const pct52Num = typeof p.pct52w === 'number' && Number.isFinite(p.pct52w) ? p.pct52w : -999;
        const pct52 = typeof p.pct52w === 'number' && Number.isFinite(p.pct52w)
          ? `${p.pct52w > 0 ? '+' : ''}${p.pct52w.toFixed(1)}%`
          : '—';
        const flowNum = typeof p.ud_ratio === 'number' && Number.isFinite(p.ud_ratio) ? p.ud_ratio : -999;
        const flow = typeof p.ud_ratio === 'number' && Number.isFinite(p.ud_ratio)
          ? `${p.ud_ratio.toFixed(2)}x`
          : '—';
        return {
          symbol: String(p.sym || ''),
          score: Number(p.score ?? 0),
          sector: String(p.sector || '—'),
          ltp,
          peg: pegVal,
          peg_num: pegNum,
          intrinsic_value: ivVal,
          margin_of_safety: mosVal,
          valuation: String(p.valuation || 'N/A'),
          pct_52w: pct52,
          pct_52w_num: pct52Num,
          inst_flow: flow,
          inst_flow_num: flowNum,
          lt_rating: String(p.lt_verdict || '—'),
        };
      }));
    } catch (err) {
      if (seq !== this.fetchSeq) return;
      console.error('[FundamentalPicks] Failed to load picks:', err);
      this.picks.set([]);
    }
  }

  onSelect(symbol: string): void {
    stocksStore.selectSymbol(symbol);
  }
}
