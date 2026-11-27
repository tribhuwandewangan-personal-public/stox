/**
 * Dashboard component: Main content area with sidebar, macro catalysts, quick picks, fundamental picks, and stock grid.
 */

import { Component, AfterViewInit, ViewChild, ElementRef, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StockGridComponent } from './stock-grid.component';
import { SidebarComponent } from './sidebar.component';
import { AddSymbolModalComponent } from './add-symbol-modal.component';
import { MacroCatalystsBannerComponent } from './macro-catalysts-banner.component';
import { QuickPicksTableComponent } from './quick-picks-table.component';
import { PreBreakoutRadarComponent } from './pre-breakout-radar.component';
import { FundamentalPicksTableComponent } from './fundamental-picks-table.component';
import { Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    SidebarComponent,
    MacroCatalystsBannerComponent,
    PreBreakoutRadarComponent,
    QuickPicksTableComponent,
    FundamentalPicksTableComponent,
    StockGridComponent,
    AddSymbolModalComponent
  ],
  template: `
    <div class="dashboard-container">
      <!-- Left Watchlist Sidebar -->
      <app-sidebar
        (stockSelect)="onSidebarSelect($event)"
        (addSymbol)="showAddSymbolModal.set(true)">
      </app-sidebar>

      <!-- Main Dashboard Stream -->
      <div class="dashboard-main-flow">
        <!-- Upcoming Macro Catalysts Banner -->
        <app-macro-catalysts-banner></app-macro-catalysts-banner>

        <!-- Pre-Breakout Bullish Radar (4-Week Projections) -->
        <app-pre-breakout-radar></app-pre-breakout-radar>

        <!-- Quick Picks Table -->
        <app-quick-picks-table></app-quick-picks-table>

        <!-- Top 10 Fundamental Picks Table -->
        <app-fundamental-picks-table></app-fundamental-picks-table>

        <!-- Grid Header Bar -->
        <div class="grid-header">
          <div class="grid-title">
            Equities Decision Dashboard
            <span class="universe-tag">
              {{ universeLabel() }}
            </span>
          </div>
          <div class="grid-actions">
            <div class="tag-filter-pills" *ngIf="stocksStore.availableTags().length > 0">
              <button
                type="button"
                class="btn-universe-toggle"
                [class.active-tag-pill]="stocksStore.filter().tag === null"
                (click)="stocksStore.setTagFilter(null)"
              >All ({{ stocksStore.stocks().length }})</button>
              <button
                type="button"
                class="btn-universe-toggle"
                *ngFor="let t of stocksStore.availableTags()"
                [class.active-tag-pill]="stocksStore.filter().tag === t.tag"
                (click)="stocksStore.setTagFilter(t.tag)"
              >{{ t.tag }} ({{ t.count }})</button>
            </div>
            <a href="/news_reports/latest_market_news.md" target="_blank" rel="noopener noreferrer" class="btn-grid-link">
              <span>📰</span> Market News (.md) ↗
            </a>
            <button class="btn-grid-refresh" (click)="refreshData()">🔄 Refresh Data</button>
            <button class="btn-grid-add" (click)="showAddSymbolModal.set(true)">🌐 ➕ Add Symbol</button>
          </div>
        </div>

        <!-- Stock Cards Grid -->
        <app-stock-grid (selectStock)="onStockSelect($event)"></app-stock-grid>
      </div>
    </div>

    <!-- Add Symbol Modal (Partial Search & Watchlist Manager) -->
    <app-add-symbol-modal
      *ngIf="showAddSymbolModal()"
      (close)="showAddSymbolModal.set(false)">
    </app-add-symbol-modal>
  `,
  styles: [`
    :host {
      display: flex;
      flex: 1;
      min-height: 0;
    }

    .dashboard-container {
      display: flex;
      flex: 1;
      gap: 0;
      min-height: 0;
      align-items: flex-start;
    }

    .dashboard-main-flow {
      flex: 1;
      min-width: 0;
      display: flex;
      flex-direction: column;
      padding: 16px 20px 40px 20px;
      gap: 16px;
    }

    .grid-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 16px;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      flex-wrap: wrap;
      gap: 12px;
    }

    .grid-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.15rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .universe-tag {
      font-size: 0.72rem;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .universe-tag.midcap {
      background: rgba(245, 158, 11, 0.15);
      color: #f59e0b;
      border-color: rgba(245, 158, 11, 0.35);
    }

    .btn-universe-toggle {
      background: rgba(15, 23, 42, 0.75);
      border: 1px solid rgba(148, 163, 184, 0.35);
      color: #e2e8f0;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }

    .btn-universe-toggle:hover {
      background: rgba(56, 189, 248, 0.16);
      border-color: rgba(56, 189, 248, 0.5);
      color: #ffffff;
    }

    :host-context([data-theme='light']) .btn-universe-toggle {
      background: #f1f5f9;
      border-color: #cbd5e1;
      color: #1e293b;
    }

    :host-context([data-theme='light']) .btn-universe-toggle:hover {
      background: #e2e8f0;
      color: #0f172a;
    }

    :host-context([data-theme='light']) .active-tag-pill {
      background: #e0f2fe !important;
      border-color: #0284c7 !important;
      color: #0369a1 !important;
    }

    .grid-actions {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
    }

    .btn-grid-link {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      padding: 6px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }

    .btn-grid-link:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.25);
    }

    .btn-grid-refresh {
      background: linear-flex;
      background: linear-gradient(135deg, #0284c7, #6366f1);
      border: none;
      color: #fff;
      padding: 6px 16px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      box-shadow: 0 2px 10px rgba(2, 132, 199, 0.3);
      transition: all 0.2s;
    }

    .btn-grid-refresh:hover {
      opacity: 0.9;
      transform: translateY(-1px);
    }

    .btn-grid-add {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: #38bdf8;
      padding: 6px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }

    .btn-grid-add:hover {
      background: #38bdf8;
      color: #0f172a;
    }

    .tag-filter-pills {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .active-tag-pill {
      background: rgba(56, 189, 248, 0.22) !important;
      border-color: rgba(56, 189, 248, 0.55) !important;
      color: #7dd3fc !important;
    }

    @media (max-width: 900px) {
      .dashboard-container {
        flex-direction: column;
      }
      .dashboard-main-flow {
        padding: 12px 10px;
      }
    }
  `]
})
export class DashboardComponent {
  stocksStore = stocksStore;
  activeUniverse = stocksStore.activeUniverse;
  showAddSymbolModal = signal<boolean>(false);

  onStockSelect(stock: Stock): void {
    stocksStore.selectSymbol(stock.symbol);
  }

  universeLabel(): string {
    const activeTag = stocksStore.filter().tag;
    return activeTag
      ? `Tag: ${activeTag} (symbols.json)`
      : `Unified Universe (${stocksStore.stocks().length} stocks in symbols.json)`;
  }

  refreshData(): void {
    stocksStore.loadUniverse(this.activeUniverse());
  }

  onSidebarSelect(symbol: string): void {
    // Close any open detail modal
    stocksStore.selectSymbol('');
    const card = document.querySelector(`[data-symbol="${symbol}"]`);
    if (card) {
      (card as HTMLElement).scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
      console.warn('Card for symbol', symbol, 'not found');
    }
  }
}
