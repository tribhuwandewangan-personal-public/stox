/**
 * Sidebar: "Stocks Watchlist" navigation panel with compact stocks list.
 * Fixes layout & styling to match Jinja reference (Image 1).
 */

import { Component, signal, computed, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { stocksStore } from '../../core/stores/stocks.store';
import { Stock } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';

type SidebarViewMode = 'flat' | 'sector';
type SidebarFilter = 'ALL' | 'BUY' | 'HOLD' | 'SELL' | 'ACTIVE';

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <aside class="sidebar-watchlist-panel">
      <!-- Header -->
      <div class="sidebar-header">
        <div class="sidebar-title-row">
          <div class="sidebar-title">
            <span>📋</span> {{ stocksStore.activeUniverse() === 'midcap250' ? 'Midcap 250' : 'Stocks Watchlist' }}
            <span class="sidebar-badge">{{ stocksStore.availableCount() }}/{{ stocksStore.stocks().length }}</span>
          </div>
        </div>

        <!-- Search Box -->
        <div class="sidebar-search-box">
          <input
            type="text"
            placeholder="🔍 Search symbol, sector..."
            [ngModel]="searchQuery()"
            (ngModelChange)="searchQuery.set($event)"
            class="sidebar-search-input">
          <button *ngIf="searchQuery()" class="sidebar-search-clear" (click)="searchQuery.set('')">✕</button>
        </div>

        <!-- Filter Count Chips -->
        <div class="sidebar-filters">
          <button class="sidebar-filter-chip" [class.active]="filterMode() === 'ALL'" (click)="setFilter('ALL')">
            All <span>{{ counts().all }}</span>
          </button>
          <button class="sidebar-filter-chip" [class.active]="filterMode() === 'BUY'" (click)="setFilter('BUY')">
            Buy <span>{{ counts().buy }}</span>
          </button>
          <button class="sidebar-filter-chip" [class.active]="filterMode() === 'HOLD'" (click)="setFilter('HOLD')">
            Hold <span>{{ counts().hold }}</span>
          </button>
          <button class="sidebar-filter-chip" [class.active]="filterMode() === 'SELL'" (click)="setFilter('SELL')">
            Sell <span>{{ counts().sell }}</span>
          </button>
          <button class="sidebar-filter-chip" [class.active]="filterMode() === 'ACTIVE'" (click)="setFilter('ACTIVE')">
            Active <span>{{ counts().active }}</span>
          </button>
        </div>
      </div>

      <!-- View Toggle -->
      <div class="sidebar-view-toggle">
        <button class="sidebar-view-btn" [class.active]="viewMode() === 'flat'" (click)="viewMode.set('flat')">
          📋 Flat
        </button>
        <button class="sidebar-view-btn" [class.active]="viewMode() === 'sector'" (click)="viewMode.set('sector')">
          🏭 By Sector
        </button>
      </div>

      <!-- Add Symbol Button -->
      <button class="sidebar-add-btn" (click)="onAddSymbolClick()">
        🌐 ➕ Add Symbol
      </button>

      <!-- Scrollable Stocks List -->
      <div class="sidebar-list">
        <!-- Flat View -->
        <ng-container *ngIf="viewMode() === 'flat'">
          @for (stock of displayedStocks(); track stock.symbol) {
            <div class="sidebar-stock-item" [class.selected]="stock.symbol === selectedSymbol()" (click)="onSelect(stock.symbol)">
              <div class="stock-item-top">
                <div class="stock-names-wrap">
                  <span class="stock-sym">{{ stock.symbol }}</span>
                  <span class="stock-full-name" [title]="stock.name || stock.symbol">{{ stock.name || stock.symbol }}</span>
                </div>
                <span class="verdict-mini" [ngClass]="verdictClass(stock)">
                  {{ getVerdict(stock) }}
                </span>
              </div>
              <div class="stock-item-bottom">
                <span class="stock-price">{{ getPrice(stock) }}</span>
                <span class="stock-chg" *ngIf="stock.price_info.change_pct != null" [class.up]="(stock.price_info.change_pct || 0) >= 0" [class.down]="(stock.price_info.change_pct || 0) < 0">
                  {{ (stock.price_info.change_pct || 0) >= 0 ? '+' : '' }}{{ stock.price_info.change_pct | number:'1.2-2' }}%
                </span>
                <span class="stock-sec" [title]="stock.sector">{{ stock.sector }}</span>
              </div>
            </div>
          }
          @empty {
            <div class="sidebar-empty">No stocks match search</div>
          }
        </ng-container>

        <!-- Sector Grouped View -->
        <ng-container *ngIf="viewMode() === 'sector'">
          @for (grp of sectorGroups(); track grp.sector) {
            <div class="sector-group-header">
              <span>{{ grp.sector }}</span>
              <span class="sector-count-pill">{{ grp.stocks.length }}</span>
            </div>
            @for (stock of grp.stocks; track stock.symbol) {
              <div class="sidebar-stock-item" [class.selected]="stock.symbol === selectedSymbol()" (click)="onSelect(stock.symbol)">
                <div class="stock-item-top">
                  <div class="stock-names-wrap">
                    <span class="stock-sym">{{ stock.symbol }}</span>
                    <span class="stock-full-name" [title]="stock.name || stock.symbol">{{ stock.name || stock.symbol }}</span>
                  </div>
                  <span class="verdict-mini" [ngClass]="verdictClass(stock)">
                    {{ getVerdict(stock) }}
                  </span>
                </div>
                <div class="stock-item-bottom">
                  <span class="stock-price">{{ getPrice(stock) }}</span>
                  <span class="stock-chg" *ngIf="stock.price_info.change_pct != null" [class.up]="(stock.price_info.change_pct || 0) >= 0" [class.down]="(stock.price_info.change_pct || 0) < 0">
                    {{ (stock.price_info.change_pct || 0) >= 0 ? '+' : '' }}{{ stock.price_info.change_pct | number:'1.2-2' }}%
                  </span>
                  <span class="stock-sec" [title]="stock.name">{{ stock.name }}</span>
                </div>
              </div>
            }
          }
          @empty {
            <div class="sidebar-empty">No stocks match search</div>
          }
        </ng-container>
      </div>
    </aside>
  `,
  styles: [`
    :host {
      display: flex;
      height: 100%;
      min-height: 0;
    }

    .sidebar-watchlist-panel {
      width: 250px;
      flex-shrink: 0;
      background: rgba(10, 15, 26, 0.85);
      border-right: 1px solid rgba(255, 255, 255, 0.08);
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 0;
      overflow: hidden;
    }

    .sidebar-header {
      padding: 14px 14px 10px 14px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .sidebar-title-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .sidebar-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .sidebar-badge {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
      font-size: 0.68rem;
      padding: 1px 7px;
      border-radius: 12px;
      font-weight: 700;
    }

    .sidebar-search-box {
      position: relative;
    }

    .sidebar-search-input {
      width: 100%;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      padding: 6px 26px 6px 10px;
      color: #f1f5f9;
      font-size: 0.78rem;
      box-sizing: border-box;
      outline: none;
    }
    .sidebar-search-input:focus {
      border-color: #38bdf8;
    }

    .sidebar-search-clear {
      position: absolute;
      right: 8px;
      top: 50%;
      transform: translateY(-50%);
      background: none;
      border: none;
      color: #64748b;
      cursor: pointer;
      font-size: 0.75rem;
    }

    .sidebar-filters {
      display: flex;
      gap: 4px;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .sidebar-filters::-webkit-scrollbar { display: none; }

    .sidebar-filter-chip {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94a3b8;
      padding: 3px 8px;
      border-radius: 12px;
      font-size: 0.68rem;
      font-weight: 600;
      cursor: pointer;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .sidebar-filter-chip.active {
      background: rgba(56, 189, 248, 0.18);
      border-color: #38bdf8;
      color: #38bdf8;
    }
    .sidebar-filter-chip span {
      font-size: 0.62rem;
      opacity: 0.8;
    }

    .sidebar-view-toggle {
      display: flex;
      padding: 6px 14px;
      gap: 6px;
    }

    .sidebar-view-btn {
      flex: 1;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94a3b8;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 600;
      cursor: pointer;
    }
    .sidebar-view-btn.active {
      background: rgba(56, 189, 248, 0.15);
      border-color: #38bdf8;
      color: #38bdf8;
    }

    .sidebar-add-btn {
      margin: 0 14px 8px 14px;
      background: rgba(56, 189, 248, 0.12);
      border: 1px dashed rgba(56, 189, 248, 0.4);
      color: #38bdf8;
      padding: 6px;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.2s;
    }
    .sidebar-add-btn:hover {
      background: rgba(56, 189, 248, 0.22);
    }

    .sidebar-list {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 0 8px 14px 8px;
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .sector-group-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 8px 2px 8px;
      margin-top: 6px;
      font-size: 0.7rem;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
    }

    .sector-count-pill {
      background: rgba(255, 255, 255, 0.08);
      color: #38bdf8;
      font-size: 0.62rem;
      padding: 1px 6px;
      border-radius: 10px;
    }

    .sidebar-stock-item {
      padding: 8px 10px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid transparent;
      cursor: pointer;
      display: flex;
      flex-direction: column;
      gap: 3px;
      transition: all 0.15s;
    }
    .sidebar-stock-item:hover {
      background: rgba(255, 255, 255, 0.06);
      border-color: rgba(56, 189, 248, 0.25);
    }
    .sidebar-stock-item.selected {
      background: rgba(56, 189, 248, 0.15);
      border-color: #38bdf8;
    }

    .stock-item-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 6px;
    }

    .stock-names-wrap {
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-width: 0;
      flex: 1;
    }

    .stock-sym {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      font-size: 0.8rem;
      color: #fff;
    }

    .stock-full-name {
      font-size: 0.68rem;
      color: #94a3b8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      line-height: 1.2;
      margin-top: 1px;
    }

    .verdict-mini {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 8px;
      text-transform: uppercase;
    }
    .verdict-mini.buy {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }
    .verdict-mini.hold {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .verdict-mini.sell {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .verdict-mini.active {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
    }

    .stock-item-bottom {
      display: flex;
      align-items: baseline;
      gap: 6px;
      font-size: 0.7rem;
    }

    .stock-price {
      font-family: 'JetBrains Mono', monospace;
      color: #cbd5e1;
      font-weight: 600;
    }

    .stock-chg {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.65rem;
    }
    .stock-chg.up   { color: #10b981; }
    .stock-chg.down { color: #ef4444; }

    .stock-sec {
      color: #64748b;
      font-size: 0.62rem;
      margin-left: auto;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 90px;
    }

    .sidebar-empty {
      padding: 20px;
      text-align: center;
      color: #64748b;
      font-size: 0.75rem;
    }

    @media (max-width: 768px) {
      .sidebar-watchlist-panel {
        width: 100%;
        height: auto;
        max-height: 280px;
      }
    }
  `]
})
export class SidebarComponent {
  stocksStore = stocksStore;
  searchQuery = signal('');
  viewMode = signal<SidebarViewMode>('flat');
  filterMode = signal<SidebarFilter>('ALL');

  selectedSymbol = stocksStore.selectedSymbol;

  counts = computed(() => {
    const stocks = this.stocksStore.stocks();
    let buy = 0, hold = 0, sell = 0, active = 0;
    for (const s of stocks) {
      const v = (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase();
      if (v.includes('BUY') || v.includes('ACCUMULATE')) buy++;
      else if (v.includes('SELL')) sell++;
      else if (v.includes('HOLD')) hold++;
      if (s.queue_status === 'in_progress' || s.queue_status === 'pending') active++;
    }
    return { all: stocks.length, buy, hold, sell, active };
  });

  displayedStocks = computed<Stock[]>(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const mode = this.filterMode();
    let list = this.stocksStore.stocks();

    // Filter by mode
    if (mode === 'BUY') {
      list = list.filter(s => {
        const v = (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase();
        return v.includes('BUY') || v.includes('ACCUMULATE');
      });
    } else if (mode === 'HOLD') {
      list = list.filter(s => (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase().includes('HOLD'));
    } else if (mode === 'SELL') {
      list = list.filter(s => (s.synth_output?.structured_signal?.action_verdict || '').toUpperCase().includes('SELL'));
    } else if (mode === 'ACTIVE') {
      list = list.filter(s => s.queue_status === 'in_progress' || s.queue_status === 'pending');
    }

    // Filter by search query
    if (q) {
      list = list.filter(s => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q) || (s.sector || '').toLowerCase().includes(q));
    }

    // Sort alphabetically by company name (or symbol if name matches)
    return [...list].sort((a, b) => {
      const nameA = (a.name || a.symbol || '').toLowerCase();
      const nameB = (b.name || b.symbol || '').toLowerCase();
      return nameA.localeCompare(nameB);
    });
  });

  sectorGroups = computed<{ sector: string; stocks: Stock[] }[]>(() => {
    const list = this.displayedStocks();
    const map = new Map<string, Stock[]>();
    for (const s of list) {
      const sec = s.sector || 'General / Unclassified';
      if (!map.has(sec)) {
        map.set(sec, []);
      }
      map.get(sec)!.push(s);
    }
    const groups: { sector: string; stocks: Stock[] }[] = [];
    const sortedSectors = Array.from(map.keys()).sort();
    for (const sec of sortedSectors) {
      groups.push({ sector: sec, stocks: map.get(sec)! });
    }
    return groups;
  });

  setFilter(f: SidebarFilter): void {
    this.filterMode.set(f);
  }

  @Output() stockSelect = new EventEmitter<string>();

  onSelect(symbol: string): void {
    this.stockSelect.emit(symbol);
  }

  onAddSymbolClick(): void {
    const sym = prompt('Enter Stock Symbol to add (e.g. TATAPOWER):');
    if (sym && sym.trim()) {
      alert(`Symbol ${sym.toUpperCase()} queued for addition.`);
    }
  }

  getVerdict(s: Stock): string {
    return s.synth_output?.structured_signal?.action_verdict || (s.queue_status === 'in_progress' ? 'RUNNING' : 'PENDING');
  }

  verdictClass(s: Stock): string {
    const v = this.getVerdict(s).toUpperCase();
    if (v.includes('BUY') || v.includes('ACCUMULATE')) return 'buy';
    if (v.includes('HOLD')) return 'hold';
    if (v.includes('SELL')) return 'sell';
    return 'active';
  }

  getPrice(s: Stock): string {
    return s.price_info?.price ? fmtPrice(s.price_info.price) : '--';
  }
}
