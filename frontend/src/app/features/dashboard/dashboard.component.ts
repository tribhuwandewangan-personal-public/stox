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

        <!-- Quick Picks Table -->
        <app-quick-picks-table></app-quick-picks-table>

        <!-- Top 10 Fundamental Picks Table -->
        <app-fundamental-picks-table></app-fundamental-picks-table>

        <!-- Grid Header Bar -->
        <div class="grid-header">
          <div class="grid-title">
            Equities Decision Dashboard
            <span class="universe-tag" [class.midcap]="activeUniverse() === 'midcap250'">
              {{ universeLabel() }}
            </span>
          </div>
          <div class="grid-actions">
            <button class="btn-universe-toggle" (click)="toggleUniverse()">
              {{ nextUniverseButtonLabel() }}
            </button>
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
      height: 100%;
      overflow: hidden;
    }

    .dashboard-container {
      display: flex;
      flex: 1;
      gap: 0;
      overflow: hidden;
      height: 100%;
      min-height: 0;
    }

    .dashboard-main-flow {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow-y: auto;
      min-height: 0;
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
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.18);
      color: #cbd5e1;
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
      background: rgba(255, 255, 255, 0.15);
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
  activeUniverse = stocksStore.activeUniverse;
  showAddSymbolModal = signal<boolean>(false);

  onStockSelect(stock: Stock): void {
    stocksStore.selectSymbol(stock.symbol);
  }

  universeLabel(): string {
    const u = this.activeUniverse();
    if (u === 'all_nse') return 'Nifty 100 (symbols_nse_all.json)';
    if (u === 'midcap250') return 'Midcap 100 (symbols_midcap_250.json)';
    return 'Curated Watchlist (symbols.json)';
  }

  nextUniverseButtonLabel(): string {
    const u = this.activeUniverse();
    if (u === 'curated') return '🏛️ Switch to Nifty 100';
    if (u === 'all_nse') return '🏢 Switch to Midcap 100';
    return '📋 Switch to Curated Watchlist';
  }

  toggleUniverse(): void {
    const u = this.activeUniverse();
    const next = u === 'curated' ? 'all_nse' : (u === 'all_nse' ? 'midcap250' : 'curated');
    stocksStore.loadUniverse(next);
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
