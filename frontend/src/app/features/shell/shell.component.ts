/**
 * Shell component: Top-level layout — header, bulletin, and switchable content views.
 * Views: 'watchlist' (existing dashboard) | 'screener' (Pattern Screener).
 */

import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TickerBarComponent } from './ticker-bar.component';
import { HeaderComponent, AppView } from './header.component';
import { BulletinComponent } from './bulletin.component';
import { DashboardComponent } from '../dashboard/dashboard.component';
import { PatternScreenerComponent } from '../screener/pattern-screener.component';
import { SectorResearchComponent } from '../sector-research/sector-research.component';
import { CatalystRadarComponent } from '../catalyst-radar/catalyst-radar.component';
import { PortfolioModalComponent } from '../dashboard/portfolio-modal.component';
import { StockDetailModalComponent } from '../dashboard/stock-detail-modal.component';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    TickerBarComponent,
    HeaderComponent,
    BulletinComponent,
    DashboardComponent,
    PatternScreenerComponent,
    SectorResearchComponent,
    CatalystRadarComponent,
    PortfolioModalComponent,
    StockDetailModalComponent,
  ],
  template: `
    <div class="app-container">
      <!-- Top Macro Ticker Ribbon -->
      <app-ticker-bar></app-ticker-bar>

      <app-header
        [activeView]="activeView()"
        (viewChange)="onViewChange($event)"
        (openPortfolio)="showPortfolioModal.set(true)">
      </app-header>

      <app-bulletin></app-bulletin>

      <main class="main-content">
        <!-- Watchlist / Dashboard view -->
        <app-dashboard *ngIf="activeView() === 'watchlist'"></app-dashboard>

        <!-- Pattern Screener view -->
        <app-pattern-screener *ngIf="activeView() === 'screener'"></app-pattern-screener>

        <!-- Dynamic LLM Sector Research view -->
        <app-sector-research *ngIf="activeView() === 'sector'"></app-sector-research>

        <!-- Stock Catalyst Early-Warning Radar -->
        <app-catalyst-radar *ngIf="activeView() === 'catalysts'"></app-catalyst-radar>
      </main>

      <!-- Portfolio Diagnostics Modal -->
      <app-portfolio-modal
        *ngIf="showPortfolioModal()"
        (close)="showPortfolioModal.set(false)">
      </app-portfolio-modal>

      <!-- Stock Detail Modal (shared across Watchlist & Pattern Screener) -->
      <app-stock-detail-modal></app-stock-detail-modal>

      <footer class="app-footer">
        <div class="footer-content">
          ⚠️ <strong>Educational &amp; Research Project Only</strong> &bull;
          Not SEBI Registered &bull; No Investment Advice or Stock Tips &bull;
          <em>"Investments in securities market are subject to market risks.
          Read all the related documents carefully before investing."</em>
        </div>
      </footer>
    </div>
  `,
  styles: [`
:host {
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }

    .app-container {
      display: flex;
      flex-direction: column;
      height: 100%;
      overflow: hidden;
      background-color: var(--bg-dark, #0a0f1a);
      background-image:
        radial-gradient(at 10% 10%, rgba(56, 189, 248, 0.05) 0px, transparent 50%),
        radial-gradient(at 90% 90%, rgba(139, 92, 246, 0.05) 0px, transparent 50%);
    }

    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      min-height: 0;
    }

    .main-content > app-dashboard {
      display: flex;
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow: hidden;
    }

    .main-content > app-pattern-screener,
    .main-content > app-sector-research,
    .main-content > app-catalyst-radar {
      display: block;
      flex: 1;
      min-height: 0;
      height: 100%;
      overflow-y: auto;
      overflow-x: hidden;
    }

    .app-footer {
      border-top: 1px solid rgba(255, 255, 255, 0.07);
      background: rgba(10, 15, 26, 0.9);
      backdrop-filter: blur(8px);
      padding: 8px 16px;
      font-size: 11px;
      color: #475569;
      text-align: center;
      line-height: 1.4;
    }

    .footer-content {
      max-width: 1200px;
      margin: 0 auto;
    }

    @media (max-width: 768px) {
      .app-footer {
        font-size: 10px;
        padding: 6px 10px;
      }
    }
  `]
})
export class ShellComponent {
  stocksStore = stocksStore;
  activeView = signal<AppView>('watchlist');
  showPortfolioModal = signal<boolean>(false);

  onViewChange(view: AppView): void {
    this.activeView.set(view);
  }
}
