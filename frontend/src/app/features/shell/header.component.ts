/**
 * Header component: Top navigation bar with market badge, queue status, engine label.
 * Includes nav tabs to switch between Watchlist and Pattern Screener views.
 */

import { Component, OnInit, Output, EventEmitter, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppStore } from '../../core/stores/app.store';

export type AppView = 'watchlist' | 'screener';

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="top-bar">
      <div class="bar-left">
        <div class="logo-icon">📊</div>
        <div class="title-group">
          <h1 class="title">Stox</h1>
          <div class="subtitle">NSE Analysis Engine</div>
        </div>

        <!-- Nav Tabs -->
        <nav class="nav-tabs">
          <button class="nav-tab" [class.active]="activeView === 'watchlist'" (click)="switchView('watchlist')">
            📋 Watchlist
          </button>
          <button class="nav-tab" [class.active]="activeView === 'screener'" (click)="switchView('screener')">
            🔍 Pattern Screener
            <span class="nav-badge">ALL NSE</span>
          </button>
        </nav>
      </div>

      <div class="bar-center">
        <div class="status-group" *ngIf="status as s">
          <div class="queue-badge">
            <span class="queue-label">Pending:</span>
            <span class="queue-count">{{ s.queue_status.pending_count }}</span>
          </div>
          <div class="queue-badge">
            <span class="queue-label">Running:</span>
            <span class="queue-count">{{ s.queue_status.in_progress_count }}</span>
          </div>
          <div class="queue-badge">
            <span class="queue-label">Done:</span>
            <span class="queue-count">{{ s.queue_status.completed_count }}</span>
          </div>
        </div>
      </div>

      <div class="bar-right">
        <div class="market-badge" [ngClass]="'market-' + marketState()">
          <span class="market-icon">{{ marketIcon() }}</span>
          <span class="market-text">{{ marketState() | uppercase }}</span>
        </div>

        <div class="engine-badge" *ngIf="engineLabel">
          <span class="engine-label">Engine:</span>
          <span class="engine-value">{{ engineLabel }}</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .top-bar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(10, 15, 26, 0.95);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 10px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
    }

    .bar-left {
      display: flex;
      align-items: center;
      gap: 14px;
      flex: 1;
      min-width: 0;
    }

    .logo-icon {
      font-size: 1.6rem;
      line-height: 1;
      flex-shrink: 0;
    }

    .title-group {
      display: flex;
      flex-direction: column;
      flex-shrink: 0;
    }

    .title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      margin: 0;
      line-height: 1.1;
    }

    .subtitle {
      font-size: 0.65rem;
      color: var(--text-muted, #64748b);
      font-weight: 500;
    }

    /* ---- Nav Tabs ---- */
    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 4px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px;
      padding: 3px;
    }

    .nav-tab {
      display: flex;
      align-items: center;
      gap: 6px;
      background: transparent;
      border: none;
      color: #64748b;
      padding: 6px 14px;
      border-radius: 7px;
      font-size: 0.78rem;
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
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 0.6rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }

    /* ---- Center ---- */
    .bar-center {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 0 0 auto;
    }

    .status-group {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .queue-badge {
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      padding: 3px 9px;
      border-radius: 12px;
      font-size: 0.7rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }

    .queue-label { opacity: 0.65; }
    .queue-count { font-weight: 700; font-variant-numeric: tabular-nums; }

    /* ---- Right ---- */
    .bar-right {
      display: flex;
      align-items: center;
      gap: 10px;
      flex: 0 0 auto;
    }

    .market-badge {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.25);
      color: #38bdf8;
      padding: 5px 10px;
      border-radius: 8px;
      font-size: 0.72rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 5px;
      white-space: nowrap;
    }

    .market-badge.market-open {
      background: rgba(16, 185, 129, 0.12);
      border-color: rgba(16, 185, 129, 0.25);
      color: #10b981;
    }

    .market-badge.market-closed {
      background: rgba(100, 116, 139, 0.1);
      border-color: rgba(100, 116, 139, 0.2);
      color: #64748b;
    }

    .market-badge.market-premarket {
      background: rgba(139, 92, 246, 0.12);
      border-color: rgba(139, 92, 246, 0.25);
      color: #a78bfa;
    }

    .market-icon { font-size: 0.85rem; line-height: 1; }
    .market-text { font-size: 0.65rem; }

    .engine-badge {
      background: rgba(139, 92, 246, 0.12);
      border: 1px solid rgba(139, 92, 246, 0.25);
      color: #a78bfa;
      padding: 3px 9px;
      border-radius: 12px;
      font-size: 0.7rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }

    .engine-label { opacity: 0.65; }

    /* ---- Responsive ---- */
    @media (max-width: 1100px) {
      .bar-center { display: none; }
    }

    @media (max-width: 768px) {
      .top-bar { padding: 8px 12px; gap: 8px; flex-wrap: wrap; }
      .title { font-size: 1rem; }
      .subtitle { display: none; }
      .nav-tab { padding: 5px 10px; font-size: 0.72rem; }
      .nav-badge { display: none; }
      .engine-badge { display: none; }
      .market-badge { padding: 4px 8px; font-size: 0.65rem; }
    }

    @media (max-width: 480px) {
      .logo-icon { font-size: 1.3rem; }
      .title-group { display: none; }
    }
  `]
})
export class HeaderComponent implements OnInit {
  @Input()  activeView: AppView = 'watchlist';
  @Output() viewChange = new EventEmitter<AppView>();

  constructor(public appStore: AppStore) {}

  get status() { return this.appStore.status(); }
  get engineLabel() { return this.appStore.status()?.model ?? ''; }

  switchView(view: AppView): void {
    this.viewChange.emit(view);
  }

  marketState(): string {
    const hour = new Date().getHours();
    if (hour >= 9 && hour < 15) return 'open';
    if (hour >= 8 && hour < 9)  return 'premarket';
    return 'closed';
  }

  marketIcon(): string {
    switch (this.marketState()) {
      case 'open':       return '🟢';
      case 'premarket':  return '🟡';
      default:           return '🔴';
    }
  }

  ngOnInit(): void {}
}
