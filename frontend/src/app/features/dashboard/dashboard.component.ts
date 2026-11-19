/**
 * Dashboard component: Main content area with sidebar, macro catalysts, quick picks, fundamental picks, and stock grid.
 */

import { Component, AfterViewInit, ViewChild, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StockGridComponent } from './stock-grid.component';
import { SidebarComponent } from './sidebar.component';
import { StockDetailModalComponent } from './stock-detail-modal.component';
import { MacroCatalystsBannerComponent } from './macro-catalysts-banner.component';
import { QuickPicksTableComponent } from './quick-picks-table.component';
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
    QuickPicksTableComponent,
    FundamentalPicksTableComponent,
    StockGridComponent,
    StockDetailModalComponent
  ],
  template: `
    <div class="dashboard-container">
      <!-- Left Watchlist Sidebar -->
      <app-sidebar (stockSelect)="onSidebarSelect($event)"></app-sidebar>

      <!-- Main Dashboard Stream -->
      <div class="dashboard-main-flow">
        <!-- Upcoming Macro Catalysts Banner -->
        <app-macro-catalysts-banner></app-macro-catalysts-banner>

        <!-- Quick Picks Table -->
        <app-quick-picks-table></app-quick-picks-table>

        <!-- Top 10 Fundamental Picks Table -->
        <app-fundamental-picks-table></app-fundamental-picks-table>

        <!-- Grid Header Bar -->
        <div class="grid-header">
          <div class="grid-title">Equities Decision Dashboard (symbols.json)</div>
          <div class="grid-actions">
            <a href="/news_reports/latest_market_news.md" target="_blank" rel="noopener noreferrer" class="btn-grid-link">
              <span>📰</span> Market News (.md) ↗
            </a>
            <button class="btn-grid-refresh" (click)="refreshData()">🔄 Refresh Data</button>
            <button class="btn-grid-add">🌐 ➕ Add Symbol</button>
          </div>
        </div>

        <!-- Stock Cards Grid -->
        <app-stock-grid (selectStock)="onStockSelect($event)"></app-stock-grid>
      </div>
    </div>

    <!-- Stock detail modal (Level 3) -->
    <app-stock-detail-modal></app-stock-detail-modal>
  `,
  styles: [`
    .dashboard-container {
      display: flex;
      flex: 1;
      gap: 0;
      overflow: hidden;
      height: 100%;
    }

    .dashboard-main-flow {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
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
    }

    .grid-actions {
      display: flex;
      align-items: center;
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
  onStockSelect(stock: Stock): void {
    stocksStore.selectSymbol(stock.symbol);
  }

  refreshData(): void {
    window.location.reload();
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
