/**
 * Shell component: Top-level layout — header, bulletin, and switchable content views.
 * Views: 'watchlist' (existing dashboard) | 'screener' (Pattern Screener).
 */

import { Component, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TickerBarComponent } from './ticker-bar.component';
import { HeaderComponent, AppView } from './header.component';
import { BulletinComponent } from './bulletin.component';
import { DashboardComponent } from '../dashboard/dashboard.component';
import { PatternScreenerComponent } from '../screener/pattern-screener.component';
import { SectorResearchComponent } from '../sector-research/sector-research.component';
import { CatalystRadarComponent } from '../catalyst-radar/catalyst-radar.component';
import { TagManagerComponent } from '../tags/tag-manager.component';
import { PortfolioModalComponent } from '../dashboard/portfolio-modal.component';
import { StockDetailModalComponent } from '../dashboard/stock-detail-modal.component';
import { ActivityChatComponent } from './activity-chat.component';
import { stocksStore } from '../../core/stores/stocks.store';
import { AppStore } from '../../core/stores/app.store';

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
    TagManagerComponent,
    PortfolioModalComponent,
    StockDetailModalComponent,
    ActivityChatComponent,
  ],
  template: `
    <div class="app-container">
      <!-- Sticky Top Macro Ticker & Header -->
      <div class="top-chrome-sticky">
        <app-ticker-bar></app-ticker-bar>

        <app-header
          [activeView]="activeView()"
          (viewChange)="onViewChange($event)"
          (openPortfolio)="showPortfolioModal.set(true)">
        </app-header>
      </div>

      <app-bulletin></app-bulletin>

      <!-- Live Background Stock Analysis Progress Strip -->
      <div class="analysis-progress-bar" *ngIf="isAnalyzing()">
        <div class="apb-left">
          <span class="apb-spinner"></span>
          <span class="apb-label">{{ analysisLabel() }}</span>
          <div class="apb-chips" *ngIf="activeSymbols().length > 0">
            <span class="apb-chip" *ngFor="let sym of activeSymbols().slice(0, 4)">{{ sym }}</span>
            <span class="apb-more" *ngIf="activeSymbols().length > 4">+{{ activeSymbols().length - 4 }} more</span>
          </div>
        </div>
        <div class="apb-right" *ngIf="progressPct() !== null">
          <div class="apb-track">
            <div class="apb-fill" [style.width.%]="progressPct()"></div>
          </div>
          <span class="apb-pct">{{ progressPct() }}%</span>
        </div>
      </div>

      <main class="main-content">
        <!-- Watchlist / Dashboard view -->
        <app-dashboard *ngIf="activeView() === 'watchlist'"></app-dashboard>

        <!-- Pattern Screener view -->
        <app-pattern-screener *ngIf="activeView() === 'screener'"></app-pattern-screener>

        <!-- Dynamic LLM Sector Research view -->
        <app-sector-research *ngIf="activeView() === 'sector'"></app-sector-research>

        <!-- Stock Catalyst Early-Warning Radar -->
        <app-catalyst-radar *ngIf="activeView() === 'catalysts'"></app-catalyst-radar>

        <!-- Stock Tag Manager -->
        <app-tag-manager *ngIf="activeView() === 'tags'"></app-tag-manager>
      </main>

      <!-- Portfolio Diagnostics Modal -->
      <app-portfolio-modal
        *ngIf="showPortfolioModal()"
        (close)="showPortfolioModal.set(false)">
      </app-portfolio-modal>

      <!-- Stock Detail Modal (shared across Watchlist & Pattern Screener) -->
      <app-stock-detail-modal></app-stock-detail-modal>

      <!-- Floating Live Tool Change Chat-Box -->
      <app-activity-chat></app-activity-chat>

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
      min-height: 100vh;
    }

    .app-container {
      display: flex;
      flex-direction: column;
      min-height: 100vh;
      background-color: var(--bg-dark, #0a0f1a);
      background-image:
        radial-gradient(at 10% 10%, rgba(56, 189, 248, 0.05) 0px, transparent 50%),
        radial-gradient(at 90% 90%, rgba(139, 92, 246, 0.05) 0px, transparent 50%);
    }

    .top-chrome-sticky {
      position: sticky;
      top: 0;
      z-index: 120;
    }

    .main-content {
      flex: 1;
      display: flex;
      flex-direction: column;
    }

    .main-content > app-dashboard {
      display: flex;
      flex: 1;
      min-height: 0;
    }

    .main-content > app-pattern-screener,
    .main-content > app-sector-research,
    .main-content > app-catalyst-radar,
    .main-content > app-tag-manager {
      display: block;
      flex: 1;
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

    .analysis-progress-bar {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 7px 20px;
      background: linear-gradient(90deg, rgba(14, 165, 233, 0.14), rgba(56, 189, 248, 0.06));
      border-bottom: 1px solid rgba(56, 189, 248, 0.25);
      color: #e0f2fe;
      font-size: 0.78rem;
      font-weight: 600;
      flex-shrink: 0;
    }

    :host-context([data-theme='light']) .analysis-progress-bar {
      background: linear-gradient(90deg, rgba(14, 165, 233, 0.12), rgba(56, 189, 248, 0.05));
      color: #0369a1;
      border-bottom-color: rgba(14, 165, 233, 0.25);
    }

    .apb-left {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      min-width: 0;
    }

    .apb-spinner {
      width: 12px;
      height: 12px;
      border-radius: 50%;
      border: 2px solid rgba(56, 189, 248, 0.3);
      border-top-color: #38bdf8;
      animation: apb-spin 0.8s linear infinite;
      flex-shrink: 0;
    }

    @keyframes apb-spin {
      to { transform: rotate(360deg); }
    }

    .apb-chips {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      flex-wrap: wrap;
    }

    .apb-chip {
      background: rgba(56, 189, 248, 0.16);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: #7dd3fc;
      padding: 1px 7px;
      border-radius: 999px;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
      font-weight: 700;
    }

    :host-context([data-theme='light']) .apb-chip {
      color: #0284c7;
      background: rgba(14, 165, 233, 0.12);
    }

    .apb-more {
      font-size: 0.7rem;
      opacity: 0.8;
    }

    .apb-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }

    .apb-track {
      width: 120px;
      height: 6px;
      background: rgba(148, 163, 184, 0.2);
      border-radius: 999px;
      overflow: hidden;
    }

    .apb-fill {
      height: 100%;
      background: linear-gradient(90deg, #38bdf8, #10b981);
      border-radius: 999px;
      transition: width 0.4s ease;
    }

    .apb-pct {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.72rem;
      min-width: 34px;
      text-align: right;
    }
  `]
})
export class ShellComponent {
  stocksStore = stocksStore;
  activeView = signal<AppView>('watchlist');
  showPortfolioModal = signal<boolean>(false);

  constructor(public appStore: AppStore) {}

  readonly isAnalyzing = computed(() => {
    const s = this.appStore.status();
    return Boolean(s?.scheduler?.active || (s?.running_symbols?.length ?? 0) > 0);
  });

  readonly activeSymbols = computed(() => {
    const s = this.appStore.status();
    const schedSyms = s?.scheduler?.in_progress ?? [];
    const manualSyms = s?.running_symbols ?? [];
    return Array.from(new Set([...schedSyms, ...manualSyms]));
  });

  readonly progressPct = computed<number | null>(() => {
    const sched = this.appStore.status()?.scheduler;
    if (!sched?.active || !sched.total) return null;
    const done = (sched.completed ?? 0) + (sched.failed ?? 0);
    return Math.min(100, Math.round((done / sched.total) * 100));
  });

  readonly analysisLabel = computed(() => {
    const s = this.appStore.status();
    const sched = s?.scheduler;
    if (sched?.active) {
      const done = (sched.completed ?? 0) + (sched.failed ?? 0);
      const total = sched.total ?? 0;
      if (sched.phase === 'syncing_candles') {
        return `Syncing historical candles for ${total} stocks...`;
      }
      if (sched.phase === 'analyzing_stocks') {
        return `Analyzing stocks: ${done} / ${total} completed`;
      }
      if (sched.phase === 'scoring_predictions') {
        return `Scoring predictions & finalizing ${total} stocks...`;
      }
      if (sched.job === 'premarket') {
        return `Pre-market macro & news refresh: ${done} / ${total}`;
      }
      return `Processing stocks: ${done} / ${total}`;
    }
    const manual = s?.running_symbols ?? [];
    if (manual.length > 0) {
      return `Analyzing ${manual.length} stock${manual.length > 1 ? 's' : ''}...`;
    }
    return '';
  });

  onViewChange(view: AppView): void {
    this.activeView.set(view);
  }
}
