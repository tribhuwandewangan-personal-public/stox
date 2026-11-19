/**
 * Stock card: single item in grid. Shows symbol, name, sector, price, verdict, patterns, events.
 */

import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../core/models/stock.model';
import { fmtPrice, bestPrice } from '../../core/utils/price';
import { getStockBucket, verdictInfo } from '../../core/utils/verdict';
import { SparklineComponent } from './sparkline.component';
import { AppStore } from '../../core/stores/app.store';

@Component({
  selector: 'app-stock-card',
  standalone: true,
  imports: [CommonModule, SparklineComponent],
  template: `
    <div class="stock-card" [class.stale]="stock.is_stale">
      <!-- Header: Symbol & Name -->
      <div class="card-header">
        <div class="symbol-info">
          <span class="symbol">{{ stock.symbol }}</span>
          <span class="sector">{{ stock.sector }}</span>
        </div>
        <div class="verdict-badge" [style]="{ color: verdictColor, backgroundColor: verdictBg }">
          {{ verdictLabel }}
        </div>
      </div>

      <!-- Name -->
      <div class="card-name">{{ stock.name }}</div>

      <!-- Price & Change -->
      <div class="price-section">
        <div class="price">{{ formattedPrice }}</div>
        <div class="change" [ngClass]="changeClass">{{ formattedChange }}</div>
      </div>

      <!-- Pattern badges (if any) -->
      <div class="patterns" *ngIf="stock.patterns && stock.patterns.length">
        <span class="pattern-badge" *ngFor="let p of stock.patterns | slice:0:2"
              [class.bearish]="p.bearish" [title]="p.name">
          {{ p.name.slice(0, 4) }}
        </span>
      </div>

      <!-- Event badge (if any) -->
      <div class="event-badge" *ngIf="hasEvents">
        📌 Event
      </div>

      <!-- Sparkline -->
      <div class="sparkline-container">
        <app-sparkline [data]="stock.sparkline"></app-sparkline>
      </div>
    </div>
  `,
  styles: [`
    .stock-card {
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.8), rgba(18, 26, 43, 0.9));
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
      cursor: pointer;
      transition: all 0.2s ease;
      position: relative;
      overflow: hidden;
    }

    .stock-card:hover {
      border-color: rgba(56, 189, 248, 0.5);
      box-shadow: 0 8px 24px rgba(56, 189, 248, 0.1);
      transform: translateY(-2px);
    }

    .stock-card.stale {
      opacity: 0.6;
      border-color: rgba(239, 68, 68, 0.2);
    }

    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
    }

    .symbol-info {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .symbol {
      font-weight: 700;
      font-size: 14px;
      color: #fff;
      letter-spacing: 0.5px;
    }

    .sector {
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .verdict-badge {
      font-size: 10px;
      font-weight: 700;
      padding: 4px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .card-name {
      font-size: 12px;
      color: var(--text-secondary);
      line-height: 1.3;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
    }

    .price-section {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
    }

    .price {
      font-size: 16px;
      font-weight: 700;
      color: #fff;
    }

    .change {
      font-size: 14px;
      font-weight: 600;
    }

    .change.positive {
      color: var(--accent-green);
    }

    .change.negative {
      color: var(--accent-red);
    }

    .change.neutral {
      color: var(--text-muted);
    }

    .patterns {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .pattern-badge {
      font-size: 10px;
      padding: 3px 6px;
      border-radius: 3px;
      background: rgba(56, 189, 248, 0.15);
      color: var(--accent-blue);
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .pattern-badge.bearish {
      background: rgba(239, 68, 68, 0.15);
      color: var(--accent-red);
      border-color: rgba(239, 68, 68, 0.3);
    }

    .event-badge {
      font-size: 11px;
      padding: 4px 8px;
      border-radius: 4px;
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-amber);
      border: 1px solid rgba(245, 158, 11, 0.3);
      text-align: center;
    }

    .sparkline-container {
      height: 40px;
      margin-top: 4px;
    }
  `]
})
export class StockCardComponent {
  @Input({ required: true }) stock!: Stock;
  @Output() cardClick = new EventEmitter<Stock>();

  constructor(public appStore: AppStore) {}

  /** Find the latest quote for this stock from the AppStore */
  private get liveQuote() {
    const q = this.appStore.quotes().find(quote => quote.symbol === this.stock.symbol);
    return q ?? null;
  }

  get formattedPrice(): string {
    const quote = this.liveQuote;
    if (quote) {
      return fmtPrice(quote.ltp);
    }
    const p = bestPrice(this.stock);
    return fmtPrice(p.price);
  }

  get formattedChange(): string {
    const quote = this.liveQuote;
    if (quote && quote.change_pct !== undefined && quote.change_pct !== null) {
      const sign = quote.change_pct > 0 ? '+' : '';
      return `${sign}${quote.change_pct.toFixed(2)}%`;
    }
    const p = bestPrice(this.stock);
    if (p.change_pct === null || p.change_pct === undefined) return '–';
    const sign = p.change_pct > 0 ? '+' : '';
    return `${sign}${p.change_pct.toFixed(2)}%`;
  }

  get changeClass(): string {
    const quote = this.liveQuote;
    const pct = quote?.change_pct;
    if (pct === null || pct === undefined) return 'neutral';
    if (pct > 0) return 'positive';
    if (pct < 0) return 'negative';
    return 'neutral';
  }

  get verdictLabel(): string {
    const bucket = getStockBucket(this.stock);
    return verdictInfo(bucket).label;
  }

  get verdictColor(): string {
    const bucket = getStockBucket(this.stock);
    return verdictInfo(bucket).color;
  }

  get verdictBg(): string {
    const bucket = getStockBucket(this.stock);
    return verdictInfo(bucket).bgColor;
  }

  get hasEvents(): boolean {
    const events = this.stock.events;
    return !!(
      (events?.upcoming_macro_catalysts && events.upcoming_macro_catalysts.length > 0) ||
      (events?.upcoming_events && Object.keys(events.upcoming_events || {}).length > 0)
    );
  }

  onClick(): void {
    this.cardClick.emit(this.stock);
  }
}
