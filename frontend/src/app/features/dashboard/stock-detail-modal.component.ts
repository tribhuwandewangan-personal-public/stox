/**
 * Stock detail modal: Full analysis view with chart, patterns, events, long-term.
 * Opened when user clicks a stock card.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { apiService } from '../../core/services/api.service';
import { CandleChartComponent } from './candle-chart.component';
import { PatternDetailsComponent } from './pattern-details.component';
import { EventsPanelComponent } from './events-panel.component';
import { LongTermPanelComponent } from './long-term-panel.component';
import { Stock, ChartData, Candle } from '../../core/models/stock.model';
import { verdictInfo, getStockBucket } from '../../core/utils/verdict';
import { bestPrice, fmtPrice } from '../../core/utils/price';

@Component({
  selector: 'app-stock-detail-modal',
  standalone: true,
  imports: [
    CommonModule,
    CandleChartComponent,
    PatternDetailsComponent,
    EventsPanelComponent,
    LongTermPanelComponent
  ],
  template: `
    <div class="modal-overlay" *ngIf="selectedStock" (click)="closeModal()">
      <div class="modal-content" (click)="$event.stopPropagation()">
        <!-- Header -->
        <div class="modal-header">
          <div class="header-left">
            <h2 class="stock-symbol">{{ selectedStock.symbol }}</h2>
            <p class="stock-name">{{ selectedStock.name }}</p>
          </div>
          <div class="header-right">
            <div class="verdict-large" [style.color]="verdictColor" [style.backgroundColor]="verdictBg">
              {{ verdictLabel }}
            </div>
            <button class="close-btn" (click)="closeModal()">✕</button>
          </div>
        </div>

        <!-- Quick Stats -->
        <div class="quick-stats">
          <div class="stat">
            <span class="label">Price</span>
            <span class="value">{{ formattedPrice }}</span>
          </div>
          <div class="stat">
            <span class="label">Change</span>
            <span class="value" [ngClass]="changeClass">{{ formattedChange }}</span>
          </div>
          <div class="stat">
            <span class="label">Sector</span>
            <span class="value">{{ selectedStock.sector }}</span>
          </div>
          <div class="stat">
            <span class="label">Status</span>
            <span class="value" [ngClass]="'status-' + selectedStock.queue_status">
              {{ selectedStock.queue_status }}
            </span>
          </div>
        </div>

        <!-- Chart -->
        <div class="chart-section">
          @if (chartData.length > 0) {
            <app-candle-chart [candles]="chartData"></app-candle-chart>
          } @else {
            <div class="chart-placeholder">
              <p>Loading chart data...</p>
            </div>
          }
        </div>

        <!-- Analysis Panels -->
        <div class="analysis-grid">
          <app-pattern-details [patterns]="selectedStock.patterns"></app-pattern-details>
          <app-events-panel [events]="selectedStock.events"></app-events-panel>
          <app-long-term-panel [signal]="selectedStock.long_term_signal"></app-long-term-panel>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <button class="btn btn-secondary" (click)="closeModal()">Close</button>
          <button class="btn btn-primary" (click)="reAnalyze()">
            {{ isAnalyzing ? 'Re-analyzing...' : 'Re-analyze' }}
          </button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.7);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      padding: 20px;
      animation: fadeIn 0.2s ease;
    }

    @keyframes fadeIn {
      from { opacity: 0; }
      to { opacity: 1; }
    }

    .modal-content {
      background: linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(18, 26, 43, 0.95));
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 12px;
      max-width: 1000px;
      max-height: 90vh;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      animation: slideUp 0.3s ease;
    }

    @keyframes slideUp {
      from { transform: translateY(20px); opacity: 0; }
      to { transform: translateY(0); opacity: 1; }
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding: 20px;
      border-bottom: 1px solid rgba(56, 189, 248, 0.2);
      gap: 20px;
    }

    .header-left {
      flex: 1;
    }

    .stock-symbol {
      font-size: 28px;
      font-weight: 700;
      color: #fff;
      margin: 0;
      letter-spacing: 1px;
    }

    .stock-name {
      font-size: 13px;
      color: var(--text-muted);
      margin: 4px 0 0 0;
    }

    .header-right {
      display: flex;
      align-items: flex-start;
      gap: 12px;
    }

    .verdict-large {
      font-size: 12px;
      font-weight: 700;
      padding: 8px 12px;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      white-space: nowrap;
    }

    .close-btn {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: var(--accent-red);
      font-size: 18px;
      width: 32px;
      height: 32px;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .close-btn:hover {
      background: rgba(239, 68, 68, 0.2);
      border-color: var(--accent-red);
    }

    .quick-stats {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      padding: 16px 20px;
      background: rgba(15, 23, 42, 0.3);
      border-bottom: 1px solid rgba(56, 189, 248, 0.1);
    }

    .stat {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }

    .stat .label {
      font-size: 11px;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.3px;
      font-weight: 700;
    }

    .stat .value {
      font-size: 14px;
      font-weight: 600;
      color: #fff;
    }

    .stat .value.positive {
      color: var(--accent-green);
    }

    .stat .value.negative {
      color: var(--accent-red);
    }

    .stat .value.status-pending {
      color: var(--text-muted);
    }

    .stat .value.status-queued,
    .stat .value.status-in_progress {
      color: var(--accent-blue);
    }

    .stat .value.status-completed {
      color: var(--accent-green);
    }

    .chart-section {
      padding: 20px;
      border-bottom: 1px solid rgba(56, 189, 248, 0.1);
    }

    .chart-placeholder {
      height: 300px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--text-muted);
      background: rgba(15, 23, 42, 0.4);
      border-radius: 8px;
      border: 1px dashed rgba(56, 189, 248, 0.2);
    }

    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
      padding: 20px;
      flex: 1;
    }

    .modal-footer {
      display: flex;
      gap: 12px;
      justify-content: flex-end;
      padding: 16px 20px;
      border-top: 1px solid rgba(56, 189, 248, 0.1);
      background: rgba(15, 23, 42, 0.2);
    }

    .btn {
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: all 0.2s;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .btn-secondary {
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent-blue);
    }

    .btn-secondary:hover {
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--accent-blue);
    }

    .btn-primary {
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: var(--accent-green);
    }

    .btn-primary:hover:not(:disabled) {
      background: rgba(16, 185, 129, 0.3);
      border-color: var(--accent-green);
    }

    .btn:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }

    @media (max-width: 768px) {
      .modal-content {
        max-width: 95vw;
        max-height: 95vh;
      }

      .modal-header {
        flex-direction: column;
      }

      .analysis-grid {
        grid-template-columns: 1fr;
      }

      .quick-stats {
        grid-template-columns: repeat(2, 1fr);
      }
    }
  `]
})
export class StockDetailModalComponent implements OnInit, OnDestroy {
  stocksStore = stocksStore;
  chartData: Candle[] = [];
  isAnalyzing = false;

  get selectedStock(): Stock | null {
    return this.stocksStore.selectedStock();
  }

  get verdictLabel(): string {
    if (!this.selectedStock) return 'N/A';
    const bucket = getStockBucket(this.selectedStock);
    return verdictInfo(bucket).label;
  }

  get verdictColor(): string {
    if (!this.selectedStock) return 'var(--text-muted)';
    const bucket = getStockBucket(this.selectedStock);
    return verdictInfo(bucket).color;
  }

  get verdictBg(): string {
    if (!this.selectedStock) return 'transparent';
    const bucket = getStockBucket(this.selectedStock);
    return verdictInfo(bucket).bgColor;
  }

  get formattedPrice(): string {
    if (!this.selectedStock) return 'N/A';
    const p = bestPrice(this.selectedStock);
    return fmtPrice(p.price);
  }

  get formattedChange(): string {
    if (!this.selectedStock) return '–';
    const p = bestPrice(this.selectedStock);
    if (p.change_pct === null) return '–';
    const sign = p.change_pct > 0 ? '+' : '';
    return `${sign}${p.change_pct.toFixed(2)}%`;
  }

  get changeClass(): string {
    if (!this.selectedStock) return 'neutral';
    const p = bestPrice(this.selectedStock);
    if (p.change_pct === null) return 'neutral';
    if (p.change_pct > 0) return 'positive';
    if (p.change_pct < 0) return 'negative';
    return 'neutral';
  }

  ngOnInit(): void {
    this.loadChartData();
  }

  ngOnDestroy(): void {
    // Cleanup if needed
  }

  private loadChartData(): void {
    if (!this.selectedStock) return;

    // Fetch chart data from API
    apiService.getChartData(this.selectedStock.symbol)
      .then(data => {
        this.chartData = data.candles || [];
      })
      .catch(() => {
        this.chartData = [];
      });
  }

  closeModal(): void {
    this.stocksStore.selectSymbol(null);
  }

  async reAnalyze(): Promise<void> {
    if (!this.selectedStock || this.isAnalyzing) return;

    this.isAnalyzing = true;
    try {
      await apiService.reAnalyzeStock(this.selectedStock.symbol);
      // Wait a moment for backend to process, then refresh
      setTimeout(() => {
        apiService.getStocks()
          .then(stocks => this.stocksStore.setStocks(stocks))
          .finally(() => {
            this.isAnalyzing = false;
            this.loadChartData();
          });
      }, 1000);
    } catch (error) {
      this.isAnalyzing = false;
    }
  }
}
