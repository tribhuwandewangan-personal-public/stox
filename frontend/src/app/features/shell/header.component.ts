/**
 * Header component: Top navigation bar with action buttons, market badge, queue status, engine label.
 * Includes nav tabs to switch between Watchlist and Pattern Screener views.
 */

import { Component, OnInit, Output, EventEmitter, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppStore } from '../../core/stores/app.store';
import { stocksStore, StockUniverse } from '../../core/stores/stocks.store';

export type AppView = 'watchlist' | 'screener';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule],
  template: `
    <header class="top-bar">
      <div class="bar-left">
        <div class="brand-logo">N</div>
        <div class="title-group">
          <h1 class="title">NSE Multi-Agent Stock Predictor</h1>
          <div class="subtitle">Technical Indicators, Pattern Recognition (H&amp;S, Bollinger, Saucer) &amp; Catalysts Calendar</div>
        </div>

        <!-- Nav Tabs -->
        <nav class="nav-tabs">
          <button class="nav-tab" [class.active]="activeView === 'watchlist' && currentUniverse() === 'curated'" (click)="selectUniverse('curated')">
            📋 Watchlist
          </button>
          <button class="nav-tab" [class.active]="activeView === 'watchlist' && currentUniverse() === 'midcap250'" (click)="selectUniverse('midcap250')">
            🏢 Midcap 250
            <span class="nav-badge midcap-badge">250 STOCKS</span>
          </button>
          <button class="nav-tab" [class.active]="activeView === 'screener'" (click)="switchView('screener')">
            🔍 Pattern Screener
            <span class="nav-badge">ALL NSE</span>
          </button>
        </nav>
      </div>

      <div class="bar-right">
        <!-- Action Buttons matching legacy UI -->
        <button class="header-btn btn-risk" title="View Global Shock Safeguards & Risk Shield Playbook">
          <span>🛡️</span> Risk: <strong class="risk-val">LOW</strong>
        </button>

        <button class="header-btn btn-portfolio" (click)="openPortfolio.emit()" title="View Zerodha Kite Portfolio Holdings, Diagnostics & Actions">
          <span>💼</span> My Portfolio
        </button>

        <button class="header-btn btn-scanner" (click)="switchView('screener')" title="Discover High-Strength Leaders Outside Active Watchlist">
          <span>🔍</span> Market Scanner
        </button>

        <a href="/news_reports/latest_market_news.md" target="_blank" rel="noopener noreferrer" class="header-btn btn-link" title="Open Latest Market News Markdown report">
          <span>📰</span> Market News (.md) ↗
        </a>

        <a href="/news_reports/latest_stocks_news.md" target="_blank" rel="noopener noreferrer" class="header-btn btn-link" title="Open Latest Stocks News Markdown report">
          <span>📊</span> Stocks News (.md) ↗
        </a>

        <button class="header-btn btn-graph" title="View Multi-Agent Architecture & Pipeline">
          <span>🕸️</span> Multi-Agent Graph
        </button>

        <div class="status-badge engine-badge">
          <div class="pulse-dot"></div>
          <span>{{ engineLabel || 'Rule-based engine (no LLM)' }}</span>
        </div>

        <button class="header-btn btn-accuracy" title="Past verdict performance tracking">
          <span>🎯</span> Accuracy
        </button>

        <!-- Market status badge -->
        <div class="status-badge market-badge" [ngClass]="'market-' + marketState()">
          <span class="pulse-dot-market"></span>
          <span>Market {{ marketState() }} &bull; live</span>
        </div>

        <!-- Valkey / Queue status -->
        <div class="status-badge queue-badge" *ngIf="status as s">
          <span>Valkey / Redis: {{ s.queue_status.pending_count }} Pending | {{ s.queue_status.completed_count }} Done</span>
        </div>
      </div>
    </header>
  `,
  styles: [`
    .top-bar {
      position: sticky;
      top: 31px; /* Just below ticker ribbon */
      z-index: 100;
      background: rgba(10, 15, 26, 0.95);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 10px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
    }

    .bar-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-shrink: 0;
    }

    .brand-logo {
      width: 36px;
      height: 36px;
      border-radius: 9px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.15rem;
      color: #0f172a;
      flex-shrink: 0;
    }

    .title-group {
      display: flex;
      flex-direction: column;
    }

    .title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.05rem;
      font-weight: 700;
      color: #fff;
      margin: 0;
      line-height: 1.2;
    }

    .subtitle {
      font-size: 0.68rem;
      color: #64748b;
      font-weight: 500;
    }

    /* ---- Nav Tabs ---- */
    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 4px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 2px 4px;
      margin-left: 8px;
    }

    .nav-tab {
      display: flex;
      align-items: center;
      gap: 5px;
      background: transparent;
      border: none;
      color: #64748b;
      padding: 5px 11px;
      border-radius: 6px;
      font-size: 0.74rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s;
      white-space: nowrap;
    }

    .nav-tab:hover {
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.05);
    }

    .nav-tab.active {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }

    .nav-badge {
      background: rgba(16, 185, 129, 0.15);
      color: #10b981;
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 1px 5px;
      border-radius: 999px;
      font-size: 0.58rem;
      font-weight: 700;
    }

    .midcap-badge {
      background: rgba(245, 158, 11, 0.15);
      color: #f59e0b;
      border-color: rgba(245, 158, 11, 0.35);
    }

    /* ---- Right Action Group ---- */
    .bar-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .header-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      padding: 5px 11px;
      border-radius: 8px;
      font-size: 0.72rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      text-decoration: none;
      transition: all 0.18s ease;
      white-space: nowrap;
    }

    .header-btn:hover {
      background: rgba(255, 255, 255, 0.1);
      border-color: rgba(255, 255, 255, 0.25);
    }

    .btn-risk {
      background: rgba(56, 189, 248, 0.1);
      border-color: rgba(56, 189, 248, 0.3);
      color: #38bdf8;
    }
    .btn-risk .risk-val {
      color: #10b981;
    }

    .btn-portfolio {
      background: linear-gradient(135deg, rgba(16, 185, 129, 0.15), rgba(56, 189, 248, 0.15));
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
    }

    .btn-scanner {
      background: linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(56, 189, 248, 0.15));
      border: 1px solid rgba(168, 85, 247, 0.4);
      color: #c084fc;
    }

    .btn-graph {
      background: rgba(99, 102, 241, 0.15);
      border-color: rgba(99, 102, 241, 0.35);
      color: #818cf8;
    }

    .status-badge {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      color: #94a3b8;
      padding: 5px 10px;
      border-radius: 8px;
      font-size: 0.7rem;
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }

    .pulse-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #10b981;
      animation: pulse 2s infinite;
    }

    .pulse-dot-market {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #38bdf8;
    }

    .market-open .pulse-dot-market {
      background: #10b981;
    }

    .market-closed .pulse-dot-market {
      background: #f97316;
    }

    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
      100% { opacity: 1; transform: scale(1); }
    }

    .queue-badge {
      color: #64748b;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.68rem;
    }

    @media (max-width: 1200px) {
      .subtitle { display: none; }
      .btn-graph { display: none; }
    }

    @media (max-width: 900px) {
      .top-bar { padding: 8px 12px; }
      .queue-badge { display: none; }
    }
  `]
})
export class HeaderComponent implements OnInit {
  @Input()  activeView: AppView = 'watchlist';
  @Output() viewChange = new EventEmitter<AppView>();
  @Output() openPortfolio = new EventEmitter<void>();

  constructor(public appStore: AppStore) {}

  currentUniverse = stocksStore.activeUniverse;

  get status() { return this.appStore.status(); }
  get engineLabel() { return this.appStore.status()?.model ?? ''; }

  switchView(view: AppView): void {
    this.viewChange.emit(view);
  }

  selectUniverse(universe: StockUniverse): void {
    if (this.activeView !== 'watchlist') {
      this.switchView('watchlist');
    }
    if (
      stocksStore.activeUniverse() !== universe ||
      stocksStore.error() !== null ||
      stocksStore.stocks().length === 0
    ) {
      stocksStore.loadUniverse(universe);
    }
  }

  marketState(): string {
    const hour = new Date().getHours();
    if (hour >= 9 && hour < 15) return 'open';
    if (hour >= 8 && hour < 9)  return 'premarket';
    return 'closed';
  }

  ngOnInit(): void {}
}
