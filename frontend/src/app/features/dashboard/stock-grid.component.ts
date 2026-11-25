/**
 * Stock grid: supports toggling purely on the client between Cards View (4-column layout)
 * and compact Table View across all 3 symbol universes (Curated Watchlist, Nifty 100, Midcap 100).
 */

import { Component, Output, EventEmitter, TemplateRef, ViewChild, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../core/models/stock.model';
import { stocksStore, HorizonStrategy } from '../../core/stores/stocks.store';
import { StockCardComponent } from './stock-card.component';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

export type GridViewMode = 'cards' | 'table';

interface StockTableRow {
  stock: Stock;
  ltp: number | null;
  pattern: string;
  patternCategory: string;
  catClass: string;
  verdict: string;
  target: number | null;
  stopLoss: number | null;
  upsidePct: number | null;
  riskReward: number | null;
  direction: 'Bullish' | 'Bearish' | 'Neutral';
  sparkPoints: string;
}

const VIEW_STORAGE_KEY = 'stox_grid_view_mode';

function readStoredViewMode(): GridViewMode {
  try {
    return localStorage.getItem(VIEW_STORAGE_KEY) === 'table' ? 'table' : 'cards';
  } catch {
    return 'cards';
  }
}

function parsePriceNum(val: unknown): number | null {
  if (typeof val === 'number' && Number.isFinite(val)) return val;
  if (val == null) return null;
  const m = String(val).replace(/,/g, '').match(/([0-9]+(?:\.[0-9]+)?)/);
  return m ? parseFloat(m[1]) : null;
}

function parseRiskReward(raw: unknown, ltp: number | null, target: number | null, sl: number | null): number | null {
  if (typeof raw === 'string' && raw.includes(':')) {
    const rhs = parseFloat(raw.split(':')[1]);
    if (Number.isFinite(rhs) && rhs > 0) return rhs;
  }
  if (ltp && target && sl && ltp > sl && target > ltp) {
    return (target - ltp) / (ltp - sl);
  }
  return null;
}

function categorizePattern(p: string): { label: string; css: string } {
  const s = p.toLowerCase();
  if (s.includes('cross') || s.includes('moving average')) return { label: 'Moving Average', css: 'ma' };
  if (s.includes('saucer') || s.includes('cup') || s.includes('rounding')) return { label: 'Accumulation', css: 'accumulation' };
  if (s.includes('head') || s.includes('shoulder') || s.includes('wyckoff') || s.includes('double')) return { label: 'Reversal', css: 'reversal' };
  if (s.includes('flag') || s.includes('pennant') || s.includes('triangle') || s.includes('squeeze')) return { label: 'Breakout', css: 'breakout' };
  if (s.includes('star') || s.includes('engulf') || s.includes('candle')) return { label: 'Candlestick', css: 'candlestick' };
  return { label: 'Classical Chart', css: 'other' };
}

function buildSparkPoints(prices: number[] | undefined): string {
  if (!prices || prices.length < 2) return '';
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const W = 60, H = 22;
  return prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * W;
    const y = H - ((p - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
}

@Component({
  selector: 'app-stock-grid',
  standalone: true,
  imports: [CommonModule, StockCardComponent, StoxGridComponent],
  template: `
    <!-- Horizon Strategy Filter Bar + Pure-UI Cards/Table View Switcher -->
    <div class="horizon-filter-bar">
      <div class="filter-tabs-left">
        <button
          class="filter-tab"
          [class.active]="stocksStore.horizonStrategy() === 'ALL'"
          (click)="setStrategy('ALL')">
          🌐 {{ allLabel() }}
          <span class="count-pill">{{ stocksStore.horizonCounts().all }}</span>
        </button>

        <button
          class="filter-tab"
          [class.active]="stocksStore.horizonStrategy() === 'SHORT'"
          (click)="setStrategy('SHORT')">
          ⚡ Short-Term Swing
          <span class="count-pill">{{ stocksStore.horizonCounts().short }}</span>
        </button>

        <button
          class="filter-tab"
          [class.active]="stocksStore.horizonStrategy() === 'LONG'"
          (click)="setStrategy('LONG')">
          🏛 Long-Term Wealth
          <span class="count-pill count-wealth">{{ stocksStore.horizonCounts().long }}</span>
        </button>
      </div>

      <div class="view-mode-toggle" role="group" aria-label="View Mode">
        <button
          class="view-btn"
          [class.active]="viewMode() === 'cards'"
          (click)="setViewMode('cards')"
          title="Detailed Card View">
          🃏 Cards
        </button>
        <button
          class="view-btn"
          [class.active]="viewMode() === 'table'"
          (click)="setViewMode('table')"
          title="Compact Screener Table View">
          📋 Table
        </button>
      </div>
    </div>

    <div class="grid-loading-banner" *ngIf="stocksStore.loading()">
      <span class="spinner">⏳</span>
      <span>Loading {{ loadingLabel() }}...</span>
    </div>

    <div class="grid-error-banner" *ngIf="stocksStore.error() as err">
      <span>⚠️ {{ err }}</span>
      <button class="retry-btn" (click)="stocksStore.loadUniverse(stocksStore.activeUniverse())">Retry</button>
    </div>

    <!-- CARDS VIEW -->
    @if (viewMode() === 'cards') {
      <div class="stock-grid">
        @for (stock of stocksStore.filteredStocks(); track stock.symbol) {
          <app-stock-card
            [stock]="stock"
            (cardClick)="onStockSelect($event)">
          </app-stock-card>
        }
        @empty {
          <div class="no-stocks">No stocks found matching the selected filter criteria</div>
        }
      </div>
    } @else {
      <!-- TABLE VIEW (Compact Screener Layout) -->
      <div class="grid-table-pad">
        <app-stox-grid
          [data]="tableRows()"
          [columns]="gridColumns()"
          [defaultSort]="[{ id: 'upsidePct', desc: true }]"
          [rowClass]="rowClassFn"
          [rowSymbolFn]="rowSymbolFn"
          emptyText="No stocks found matching the selected filter criteria"
          (rowClick)="onStockSelect($event.stock)"
        ></app-stox-grid>
      </div>
    }

    <ng-template #sgIdxTpl let-i="index"><span class="rank-num">{{ i + 1 }}</span></ng-template>
    <ng-template #sgSymTpl let-row>
      <div class="symbol-block">
        <span class="symbol-ticker">{{ row.stock.symbol }}</span>
        <span class="dir-dot" [class.bull]="row.direction === 'Bullish'" [class.bear]="row.direction === 'Bearish'">
          {{ row.direction === 'Bullish' ? '▲' : (row.direction === 'Bearish' ? '▼' : '•') }}
        </span>
      </div>
    </ng-template>
    <ng-template #sgNameTpl let-row>
      <div class="name-block">
        <span class="stock-name">{{ row.stock.name }}</span>
        <span class="stock-sector">{{ row.stock.sector }}</span>
      </div>
    </ng-template>
    <ng-template #sgLtpTpl let-row>
      <span class="ltp-val" *ngIf="row.ltp !== null">₹{{ row.ltp | number:'1.2-2' }}</span>
      <span class="na-val" *ngIf="row.ltp === null">—</span>
    </ng-template>
    <ng-template #sgPatTpl let-row>
      <div class="pattern-block" style="align-items: flex-start;">
        <span class="pattern-name">{{ row.pattern }}</span>
        <span class="category-badge" [class]="'cat-' + row.catClass">{{ row.patternCategory }}</span>
      </div>
    </ng-template>
    <ng-template #sgVerdTpl let-row>
      <span class="verdict-badge" [class]="'verdict-' + row.verdict">{{ row.verdict }}</span>
    </ng-template>
    <ng-template #sgTgtTpl let-row>
      <span class="target-val" *ngIf="row.target !== null">₹{{ row.target | number:'1.2-2' }}</span>
      <span class="na-val" *ngIf="row.target === null">—</span>
    </ng-template>
    <ng-template #sgSlTpl let-row>
      <span class="sl-val" *ngIf="row.stopLoss !== null">₹{{ row.stopLoss | number:'1.2-2' }}</span>
      <span class="na-val" *ngIf="row.stopLoss === null">—</span>
    </ng-template>
    <ng-template #sgUpTpl let-row>
      <span
        class="upside-val"
        *ngIf="row.upsidePct !== null"
        [class.positive]="row.upsidePct > 0"
        [class.negative]="row.upsidePct < 0">
        {{ row.upsidePct > 0 ? '+' : '' }}{{ row.upsidePct | number:'1.1-1' }}%
      </span>
      <span class="na-val" *ngIf="row.upsidePct === null">—</span>
    </ng-template>
    <ng-template #sgRrTpl let-row>
      <span class="rr-val" *ngIf="row.riskReward !== null" [class.good-rr]="row.riskReward >= 2">
        {{ row.riskReward | number:'1.1-1' }}x
      </span>
      <span class="na-val" *ngIf="row.riskReward === null">—</span>
    </ng-template>
    <ng-template #sgSparkTpl let-row>
      <svg class="mini-spark" viewBox="0 0 60 24" preserveAspectRatio="none" *ngIf="row.sparkPoints">
        <polyline
          [attr.points]="row.sparkPoints"
          fill="none"
          [attr.stroke]="row.direction === 'Bearish' ? '#ef4444' : '#10b981'"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round" />
      </svg>
    </ng-template>
  `,
  styles: [`
    .horizon-filter-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding: 16px 16px 0 16px;
      flex-wrap: wrap;
    }

    .filter-tabs-left {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    .filter-tab {
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94a3b8;
      padding: 8px 16px;
      border-radius: 10px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      transition: all 0.2s ease;
    }

    .filter-tab:hover {
      background: rgba(56, 189, 248, 0.1);
      color: #38bdf8;
      border-color: rgba(56, 189, 248, 0.3);
    }

    .filter-tab.active {
      background: rgba(56, 189, 248, 0.18);
      color: #38bdf8;
      border-color: #38bdf8;
      box-shadow: 0 0 14px rgba(56, 189, 248, 0.25);
    }

    .count-pill {
      background: rgba(255, 255, 255, 0.08);
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 700;
    }

    .count-wealth {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
    }

    .view-mode-toggle {
      display: inline-flex;
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      padding: 3px;
      gap: 3px;
    }

    .view-btn {
      background: transparent;
      border: none;
      color: #94a3b8;
      padding: 6px 12px;
      border-radius: 7px;
      font-size: 12.5px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s ease;
    }

    .view-btn:hover {
      color: #e2e8f0;
    }

    .view-btn.active {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.35);
    }

    .stock-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
      width: 100%;
      padding: 16px;
      box-sizing: border-box;
      align-content: start;
    }

    .grid-table-pad {
      padding: 16px;
    }

    .grid-loading-banner {
      margin: 14px 16px 0 16px;
      padding: 12px 16px;
      border-radius: 10px;
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: #38bdf8;
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .grid-error-banner {
      margin: 14px 16px 0 16px;
      padding: 12px 16px;
      border-radius: 10px;
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.35);
      color: #f87171;
      font-size: 13px;
      font-weight: 600;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }

    .retry-btn {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid rgba(239, 68, 68, 0.45);
      color: #fecaca;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
    }

    .retry-btn:hover {
      background: rgba(239, 68, 68, 0.35);
    }

    @media (max-width: 1024px) {
      .stock-grid {
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 12px;
      }
      .col-name, .col-sparkline { display: none; }
    }

    @media (max-width: 768px) {
      .stock-grid {
        grid-template-columns: 1fr;
        gap: 12px;
      }
      .col-rr, .col-target, .col-sl { display: none; }
    }

    .no-stocks {
      grid-column: 1 / -1;
      text-align: center;
      color: var(--text-muted);
      padding: 40px 20px;
      font-size: 14px;
    }
  `]
})
export class StockGridComponent {
  @Output() selectStock = new EventEmitter<Stock>();

  stocksStore = stocksStore;
  viewMode = signal<GridViewMode>(readStoredViewMode());

  @ViewChild('sgIdxTpl', { static: true }) sgIdxTpl!: TemplateRef<any>;
  @ViewChild('sgSymTpl', { static: true }) sgSymTpl!: TemplateRef<any>;
  @ViewChild('sgNameTpl', { static: true }) sgNameTpl!: TemplateRef<any>;
  @ViewChild('sgLtpTpl', { static: true }) sgLtpTpl!: TemplateRef<any>;
  @ViewChild('sgPatTpl', { static: true }) sgPatTpl!: TemplateRef<any>;
  @ViewChild('sgVerdTpl', { static: true }) sgVerdTpl!: TemplateRef<any>;
  @ViewChild('sgTgtTpl', { static: true }) sgTgtTpl!: TemplateRef<any>;
  @ViewChild('sgSlTpl', { static: true }) sgSlTpl!: TemplateRef<any>;
  @ViewChild('sgUpTpl', { static: true }) sgUpTpl!: TemplateRef<any>;
  @ViewChild('sgRrTpl', { static: true }) sgRrTpl!: TemplateRef<any>;
  @ViewChild('sgSparkTpl', { static: true }) sgSparkTpl!: TemplateRef<any>;

  rowClassFn = (r: StockTableRow) =>
    r.direction === 'Bullish' ? 'row-bullish' : (r.direction === 'Bearish' ? 'row-bearish' : '');

  rowSymbolFn = (r: StockTableRow) => r.stock.symbol;

  gridColumns = computed<StoxGridColumn<StockTableRow>[]>(() => [
    { id: 'idx', header: '#', sortable: false, cellTemplate: this.sgIdxTpl, headerClass: 'col-num', cellClass: 'col-num' },
    { id: 'symbol', header: 'Symbol', accessorFn: r => r.stock.symbol, cellTemplate: this.sgSymTpl },
    { id: 'name', header: 'Name / Sector', accessorFn: r => r.stock.name, cellTemplate: this.sgNameTpl, headerClass: 'col-name', cellClass: 'col-name' },
    { id: 'ltp', header: 'LTP', accessorFn: r => r.ltp ?? -Infinity, cellTemplate: this.sgLtpTpl, cellClass: 'col-mono' },
    { id: 'pattern', header: 'Pattern', accessorFn: r => r.pattern, cellTemplate: this.sgPatTpl },
    { id: 'verdict', header: 'Verdict', accessorFn: r => r.verdict, cellTemplate: this.sgVerdTpl },
    { id: 'target', header: 'Target', accessorFn: r => r.target ?? -Infinity, cellTemplate: this.sgTgtTpl, headerClass: 'col-target', cellClass: 'col-target col-mono' },
    { id: 'stopLoss', header: 'Stop Loss', accessorFn: r => r.stopLoss ?? -Infinity, cellTemplate: this.sgSlTpl, headerClass: 'col-sl', cellClass: 'col-sl col-mono' },
    { id: 'upsidePct', header: 'Upside%', accessorFn: r => r.upsidePct ?? -Infinity, cellTemplate: this.sgUpTpl, cellClass: 'col-mono' },
    { id: 'riskReward', header: 'R:R', accessorFn: r => r.riskReward ?? -Infinity, cellTemplate: this.sgRrTpl, headerClass: 'col-rr', cellClass: 'col-rr col-mono' },
    { id: 'sparkline', header: 'Trend', sortable: false, cellTemplate: this.sgSparkTpl, headerClass: 'col-sparkline', cellClass: 'col-sparkline' },
  ]);

  tableRows = computed<StockTableRow[]>(() => {
    return this.stocksStore.filteredStocks().map(stock => {
      const sig = stock.synth_output?.structured_signal;
      const ltp = stock.price_info?.price ?? null;
      const verdict = sig?.action_verdict ?? (stock.queue_status === 'in_progress' ? 'RUNNING' : 'PENDING');
      const pattern = sig?.chart_patterns || stock.patterns?.[0]?.name || 'Consolidation Range';
      const cat = categorizePattern(pattern);
      const target = parsePriceNum(sig?.when_to_sell_target ?? sig?.target_num);
      const stopLoss = parsePriceNum(sig?.stop_loss ?? sig?.stop_num);
      const upsidePct = (ltp && target && ltp > 0) ? ((target - ltp) / ltp) * 100 : null;
      const riskReward = parseRiskReward(sig?.risk_reward_ratio, ltp, target, stopLoss);
      const direction: 'Bullish' | 'Bearish' | 'Neutral' =
        verdict === 'BUY' || verdict === 'ACCUMULATE' || (upsidePct !== null && upsidePct > 0)
          ? 'Bullish'
          : (verdict === 'SELL' || (upsidePct !== null && upsidePct < 0) ? 'Bearish' : 'Neutral');

      return {
        stock,
        ltp,
        pattern,
        patternCategory: cat.label,
        catClass: cat.css,
        verdict,
        target,
        stopLoss,
        upsidePct,
        riskReward,
        direction,
        sparkPoints: buildSparkPoints(stock.sparkline),
      };
    });
  });

  allLabel(): string {
    const u = this.stocksStore.activeUniverse();
    if (u === 'all_nse') return 'All Nifty 100';
    if (u === 'midcap250') return 'All Midcap 100';
    return 'All Watchlist';
  }

  loadingLabel(): string {
    const u = this.stocksStore.activeUniverse();
    if (u === 'all_nse') return 'Nifty 100 (100 stocks)';
    if (u === 'midcap250') return 'Midcap 100 (100 stocks)';
    return 'Curated Watchlist';
  }

  setViewMode(mode: GridViewMode): void {
    this.viewMode.set(mode);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, mode);
    } catch {}
  }

  setStrategy(strategy: HorizonStrategy): void {
    stocksStore.setHorizonStrategy(strategy);
  }

  onStockSelect(stock: Stock): void {
    this.selectStock.emit(stock);
    stocksStore.selectSymbol(stock.symbol);
  }
}
