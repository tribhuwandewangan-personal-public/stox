/**
 * Stock grid: 4-column responsive layout with horizon filtering and trackBy for performance.
 */

import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../core/models/stock.model';
import { stocksStore, HorizonStrategy } from '../../core/stores/stocks.store';
import { StockCardComponent } from './stock-card.component';

@Component({
  selector: 'app-stock-grid',
  standalone: true,
  imports: [CommonModule, StockCardComponent],
  template: `
    <!-- Horizon Strategy Filter Bar (Matching Jinja UI) -->
    <div class="horizon-filter-bar">
      <button
        class="filter-tab"
        [class.active]="stocksStore.horizonStrategy() === 'ALL'"
        (click)="setStrategy('ALL')">
        🌐 {{ stocksStore.activeUniverse() === 'midcap250' ? 'All Midcap 250' : 'All Watchlist' }}
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

    <div class="grid-loading-banner" *ngIf="stocksStore.loading()">
      <span class="spinner">⏳</span>
      <span>Loading {{ stocksStore.activeUniverse() === 'midcap250' ? 'Midcap 250 (250 stocks)' : 'Curated Watchlist' }}...</span>
    </div>

    <div class="grid-error-banner" *ngIf="stocksStore.error() as err">
      <span>⚠️ {{ err }}</span>
      <button class="retry-btn" (click)="stocksStore.loadUniverse(stocksStore.activeUniverse())">Retry</button>
    </div>

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
  `,
  styles: [`
    .horizon-filter-bar {
      display: flex;
      gap: 10px;
      padding: 16px 16px 0 16px;
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

    .stock-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
      width: 100%;
      padding: 16px;
      box-sizing: border-box;
      align-content: start;
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
    }

    @media (max-width: 768px) {
      .stock-grid {
        grid-template-columns: 1fr;
        gap: 12px;
      }
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

  setStrategy(strategy: HorizonStrategy): void {
    stocksStore.setHorizonStrategy(strategy);
  }

  onStockSelect(stock: Stock): void {
    this.selectStock.emit(stock);
    stocksStore.selectSymbol(stock.symbol);
  }
}
