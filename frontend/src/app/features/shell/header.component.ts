/**
 * Header component: Top navigation bar with action buttons, market badge, queue status, engine label.
 * Includes nav tabs to switch between Watchlist and Pattern Screener views.
 */

import { Component, OnInit, Output, EventEmitter, Input, signal, HostListener, ElementRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppStore } from '../../core/stores/app.store';
import { stocksStore, StockUniverse } from '../../core/stores/stocks.store';

export type AppView = 'watchlist' | 'screener' | 'sector' | 'catalysts' | 'tags';

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

        <!-- Views Dropdown -->
        <div class="menu-dropdown">
          <button
            type="button"
            class="header-btn menu-trigger"
            [class.active-menu]="openMenu() === 'views'"
            (click)="toggleMenu('views', $event)"
            title="Switch primary views"
          >
            <span>{{ activeViewLabel() }}</span> <span class="caret">▾</span>
          </button>
          <div class="dropdown-panel dropdown-panel-left" *ngIf="openMenu() === 'views'">
            <div class="dropdown-group-label">Views</div>
            <button type="button" class="dropdown-item" [class.active-item]="activeView === 'watchlist'" (click)="selectUniverse('curated'); closeMenu()">
              <span>📋</span> All Stocks
              <span class="nav-badge" *ngIf="totalStocksCount() > 0">{{ totalStocksCount() }}</span>
            </button>
            <button type="button" class="dropdown-item" [class.active-item]="activeView === 'sector'" (click)="switchView('sector'); closeMenu()">
              <span>🧭</span> Sector Research
              <span class="nav-badge">GEMINI + QUANT</span>
            </button>
            <button type="button" class="dropdown-item" [class.active-item]="activeView === 'catalysts'" (click)="switchView('catalysts'); closeMenu()">
              <span>⚡</span> Catalyst Radar
              <span class="nav-badge">EARLY WARNING</span>
            </button>
            <button type="button" class="dropdown-item" [class.active-item]="activeView === 'tags'" (click)="switchView('tags'); closeMenu()">
              <span>🏷️</span> Manage Tags
            </button>
          </div>
        </div>
      </div>

      <div class="bar-right">
        <!-- Grouped Tools & Research Dropdown -->
        <div class="menu-dropdown">
          <button
            type="button"
            class="header-btn menu-trigger"
            [class.active-menu]="openMenu() === 'tools'"
            (click)="toggleMenu('tools', $event)"
            title="Portfolio, Scanner, Risk & Accuracy tools"
          >
            <span>🧰</span> Tools &amp; Analytics <span class="caret">▾</span>
          </button>
          <div class="dropdown-panel" *ngIf="openMenu() === 'tools'">
            <div class="dropdown-group-label">Portfolio &amp; Discovery</div>
            <button type="button" class="dropdown-item" (click)="openPortfolio.emit(); closeMenu()">
              <span>💼</span> My Portfolio
            </button>
            <button type="button" class="dropdown-item" (click)="switchView('screener'); closeMenu()">
              <span>🔍</span> Market Scanner
            </button>
            <div class="dropdown-divider"></div>
            <div class="dropdown-group-label">Diagnostics &amp; Safeguards</div>
            <button type="button" class="dropdown-item" title="View Global Shock Safeguards & Risk Shield Playbook" (click)="closeMenu()">
              <span>🛡️</span> Risk Shield: <strong class="risk-val">LOW</strong>
            </button>
            <button type="button" class="dropdown-item" title="Past verdict performance tracking" (click)="closeMenu()">
              <span>🎯</span> Accuracy
            </button>
            <button type="button" class="dropdown-item" title="View Multi-Agent Architecture & Pipeline" (click)="closeMenu()">
              <span>🕸️</span> Multi-Agent Graph
            </button>
          </div>
        </div>

        <!-- Grouped Reports Dropdown -->
        <div class="menu-dropdown">
          <button
            type="button"
            class="header-btn menu-trigger"
            [class.active-menu]="openMenu() === 'reports'"
            (click)="toggleMenu('reports', $event)"
            title="Daily generated Markdown reports"
          >
            <span>📰</span> Reports <span class="caret">▾</span>
          </button>
          <div class="dropdown-panel" *ngIf="openMenu() === 'reports'">
            <div class="dropdown-group-label">Daily News Digests</div>
            <a href="/news_reports/latest_market_news.md" target="_blank" rel="noopener noreferrer" class="dropdown-item" (click)="closeMenu()">
              <span>📰</span> Market News (.md) ↗
            </a>
            <a href="/news_reports/latest_stocks_news.md" target="_blank" rel="noopener noreferrer" class="dropdown-item" (click)="closeMenu()">
              <span>📊</span> Stocks News (.md) ↗
            </a>
          </div>
        </div>

        <div class="status-badge engine-badge" [title]="engineLabel || 'Rule-based engine (no LLM)'">
          <div class="pulse-dot"></div>
          <span>Rule-based</span>
        </div>

        <!-- Market status badge -->
        <div class="status-badge market-badge" [ngClass]="'market-' + marketState()">
          <span class="pulse-dot-market"></span>
          <span>{{ marketState() }}<ng-container *ngIf="isMarketOpen()"> &bull; live</ng-container></span>
        </div>

        <!-- Valkey / Queue / Live Analysis status -->
        <div
          class="status-badge queue-badge"
          [class.queue-active]="isAnalyzing()"
          *ngIf="status?.queue_status as q"
          [title]="status.scheduler?.last_summary || ((q.engine ?? 'Queue') + ': ' + (q.pending ?? q.pending_count ?? 0) + ' Pending | ' + (q.completed ?? q.completed_count ?? 0) + ' Done')"
        >
          <span class="pulse-dot-active" *ngIf="isAnalyzing()"></span>
          <ng-container *ngIf="status.scheduler as sched; else manualOrDefaultQueue">
            <ng-container *ngIf="sched.active; else manualOrDefaultQueue">
              <span>{{ sched.completed }}/{{ sched.total }}</span>
            </ng-container>
          </ng-container>
          <ng-template #manualOrDefaultQueue>
            <ng-container *ngIf="(status.running_symbols?.length ?? 0) > 0; else defaultQueue">
              <span>{{ status.running_symbols?.length }} running</span>
            </ng-container>
            <ng-template #defaultQueue>
              <span>{{ q.pending ?? q.pending_count ?? 0 }}P / {{ q.completed ?? q.completed_count ?? 0 }}D</span>
            </ng-template>
          </ng-template>
        </div>

        <!-- Theme Toggle pinned on the far right -->
        <button class="header-btn btn-theme" (click)="toggleTheme()" title="Switch between Light and Dark mode">
          <span>{{ theme() === 'light' ? '🌙' : '☀️' }}</span>
          <span>{{ theme() === 'light' ? 'Dark' : 'Light' }}</span>
        </button>
      </div>
    </header>
  `,
  styles: [`
    .top-bar {
      position: relative;
      z-index: 100;
      background: rgba(10, 15, 26, 0.95);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 6px 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .bar-left {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-shrink: 0;
    }

    .brand-logo {
      width: 28px;
      height: 28px;
      border-radius: 7px;
      background: linear-gradient(135deg, #38bdf8, #818cf8);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 0.95rem;
      color: #0f172a;
      flex-shrink: 0;
    }

    .title-group {
      display: flex;
      flex-direction: column;
    }

    .title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
      color: #fff;
      margin: 0;
      line-height: 1.15;
    }

    .subtitle {
      display: none;
    }

    /* ---- Nav Tabs ---- */
    .nav-tabs {
      display: flex;
      align-items: center;
      gap: 2px;
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 2px;
      margin-left: 4px;
    }

    .nav-tab {
      display: flex;
      align-items: center;
      gap: 4px;
      background: transparent;
      border: none;
      color: #64748b;
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 0.71rem;
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

    .queue-badge.queue-active {
      color: #38bdf8;
      border-color: rgba(56, 189, 248, 0.35);
      background: rgba(56, 189, 248, 0.1);
    }

    .menu-dropdown {
      position: relative;
      display: inline-flex;
    }

    .menu-trigger .caret {
      font-size: 0.65rem;
      opacity: 0.8;
    }

    .active-menu {
      background: rgba(56, 189, 248, 0.16);
      border-color: rgba(56, 189, 248, 0.45);
      color: #7dd3fc;
    }

    .dropdown-panel {
      position: absolute;
      top: calc(100% + 6px);
      right: 0;
      min-width: 220px;
      background: rgba(15, 23, 42, 0.98);
      border: 1px solid rgba(148, 163, 184, 0.25);
      border-radius: 10px;
      padding: 6px;
      box-shadow: 0 14px 30px rgba(2, 6, 23, 0.65);
      z-index: 300;
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .dropdown-group-label {
      font-size: 0.64rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #64748b;
      padding: 4px 8px 2px;
    }

    .dropdown-divider {
      height: 1px;
      background: rgba(255, 255, 255, 0.08);
      margin: 4px 2px;
    }

    .dropdown-item {
      display: flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      text-align: left;
      background: transparent;
      border: none;
      color: #e2e8f0;
      padding: 7px 10px;
      border-radius: 7px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      box-sizing: border-box;
    }

    .dropdown-item:hover {
      background: rgba(56, 189, 248, 0.15);
      color: #ffffff;
    }

    .dropdown-panel-left {
      left: 0;
      right: auto;
    }

    .dropdown-item.active-item {
      background: rgba(56, 189, 248, 0.16);
      color: #7dd3fc;
    }

    :host-context([data-theme='light']) .dropdown-panel {
      background: #ffffff;
      border-color: #cbd5e1;
      box-shadow: 0 14px 30px rgba(15, 23, 42, 0.15);
    }

    :host-context([data-theme='light']) .dropdown-item {
      color: #1e293b;
    }

    :host-context([data-theme='light']) .dropdown-item:hover {
      background: #e0f2fe;
      color: #0369a1;
    }

    :host-context([data-theme='light']) .dropdown-item.active-item {
      background: #e0f2fe;
      color: #0369a1;
    }

    :host-context([data-theme='light']) .dropdown-divider {
      background: #e2e8f0;
    }

    .pulse-dot-active {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: #38bdf8;
      animation: pulse 1.2s infinite;
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

  constructor(public appStore: AppStore, private elRef: ElementRef) {
    this.applyTheme(this.theme());
  }

  currentUniverse = stocksStore.activeUniverse;
  totalStocksCount = () => stocksStore.stocks().length;
  theme = signal<'dark' | 'light'>(HeaderComponent.readStoredTheme());
  openMenu = signal<'views' | 'tools' | 'reports' | null>(null);

  toggleMenu(menu: 'views' | 'tools' | 'reports', event: Event): void {
    event.stopPropagation();
    this.openMenu.set(this.openMenu() === menu ? null : menu);
  }

  activeViewLabel(): string {
    switch (this.activeView) {
      case 'sector':
        return '🧭 Sector Research';
      case 'catalysts':
        return '⚡ Catalyst Radar';
      case 'tags':
        return '🏷️ Manage Tags';
      case 'screener':
        return '🔍 Market Scanner';
      case 'watchlist':
      default: {
        const count = this.totalStocksCount();
        return count > 0 ? `📋 All Stocks (${count})` : '📋 All Stocks';
      }
    }
  }

  closeMenu(): void {
    this.openMenu.set(null);
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: Event): void {
    if (this.openMenu() && !this.elRef.nativeElement.contains(event.target)) {
      this.openMenu.set(null);
    }
  }

  private static readStoredTheme(): 'dark' | 'light' {
    try {
      return localStorage.getItem('stox_theme') === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  }

  private applyTheme(mode: 'dark' | 'light'): void {
    try {
      document.documentElement.setAttribute('data-theme', mode);
    } catch {}
  }

  toggleTheme(): void {
    const next: 'dark' | 'light' = this.theme() === 'light' ? 'dark' : 'light';
    this.theme.set(next);
    this.applyTheme(next);
    try {
      localStorage.setItem('stox_theme', next);
    } catch {}
  }

  get status() { return this.appStore.status(); }
  get engineLabel() { return this.appStore.status()?.model ?? ''; }

  isAnalyzing(): boolean {
    const s = this.appStore.status();
    return Boolean(s?.scheduler?.active || (s?.running_symbols?.length ?? 0) > 0);
  }

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

  isMarketOpen(): boolean {
    const apiState = this.appStore.marketState().trim().toLowerCase();
    if (apiState) {
      return this.appStore.marketOpen();
    }
    return this.marketState() === 'open';
  }

  marketState(): string {
    const apiState = this.appStore.marketState().trim().toLowerCase();
    if (apiState) return apiState;
    // IST fallback (UTC+5:30)
    const now = new Date();
    const istDate = new Date(now.getTime() + 330 * 60_000);
    const day = istDate.getUTCDay();
    if (day === 0 || day === 6) return 'closed';
    const istMinutes = istDate.getUTCHours() * 60 + istDate.getUTCMinutes();
    if (istMinutes >= 9 * 60 + 15 && istMinutes <= 15 * 60 + 30) return 'open';
    if (istMinutes >= 9 * 60 && istMinutes < 9 * 60 + 15) return 'premarket';
    return 'closed';
  }

  ngOnInit(): void {}
}
