/**
 * Ticker Bar component: Horizontal ribbon at the very top of the page.
 * Displays real-time global macro indicators (Crude, Gold, Nasdaq, S&P 500, US 10Y, DXY, USD/INR).
 */

import { Component, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppStore } from '../../core/stores/app.store';

export interface MacroTickerItem {
  indicator: string;
  value: number | string;
  unit: string;
  pct_change: number;
  category?: string;
}

@Component({
  selector: 'app-ticker-bar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="ticker-bar">
      <div class="ticker-track">
        @for (item of tickerItems(); track item.indicator) {
          <div class="ticker-item">
            <span class="ticker-name">{{ item.indicator }}:</span>
            <span class="ticker-val">{{ item.value }} {{ item.unit }}</span>
            <span [class.ticker-up]="item.pct_change >= 0" [class.ticker-down]="item.pct_change < 0">
              {{ item.pct_change >= 0 ? '+' : '' }}{{ item.pct_change | number:'1.2-2' }}%
            </span>
          </div>
        }
        @empty {
          <div class="ticker-item loading">
            <span class="ticker-name">Loading Global Macro Tickers...</span>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .ticker-bar {
      background: rgba(10, 15, 26, 0.98);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 6px 16px;
      display: flex;
      overflow-x: auto;
      white-space: nowrap;
      font-size: 0.76rem;
      scrollbar-width: none;
      z-index: 101;
      position: sticky;
      top: 0;
    }
    .ticker-bar::-webkit-scrollbar { display: none; }

    .ticker-track {
      display: inline-flex;
      align-items: center;
      gap: 24px;
    }

    .ticker-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .ticker-name {
      color: #94a3b8;
      font-weight: 500;
    }

    .ticker-val {
      font-weight: 600;
      color: #f1f5f9;
      font-family: 'JetBrains Mono', monospace;
    }

    .ticker-up {
      color: #10b981;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }

    .ticker-down {
      color: #ef4444;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }

    .loading {
      color: #64748b;
      font-style: italic;
    }
  `]
})
export class TickerBarComponent {
  constructor(private appStore: AppStore) {}

  tickerItems = computed<MacroTickerItem[]>(() => {
    const status = this.appStore.status();
    if (status && (status as any).macro_items && Array.isArray((status as any).macro_items)) {
      return (status as any).macro_items;
    }
    const raw = (status as any)?.bulletin?.raw_indicators?.indicators;
    if (Array.isArray(raw)) {
      return raw;
    }
    return [];
  });
}
