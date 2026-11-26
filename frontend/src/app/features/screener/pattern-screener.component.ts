/**
 * Pattern Screener Component.
 * Shows top stocks with high-conviction technical chart patterns
 * sourced from ALL analyzed symbols in the cache DB (not just watchlist).
 *
 * ⚠️ ADVISORY ONLY — No order placement, no investment advice.
 */

import { Component, OnInit, OnDestroy, TemplateRef, ViewChild, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { PatternPick, Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

type SortKey = 'readiness_score' | 'upside_pct' | 'risk_reward' | 'confidence_score' | 'timestamp';
type ScreenerMode = 'pre_breakout' | 'all_patterns';
type StageFilter = 'ALL' | 'IMMINENT_BREAKOUT' | 'FORMING_PRE_BREAKOUT' | 'FRESH_BREAKOUT' | 'HIDE_LATE';
type VerdictFilter = 'ALL' | 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
type DirectionFilter = 'ALL' | 'Bullish' | 'Bearish';
type CategoryFilter = 'ALL' | 'Moving Average' | 'Reversal' | 'Breakout' | 'Accumulation' | 'Candlestick' | 'Classical Chart';

@Component({
  selector: 'app-pattern-screener',
  standalone: true,
  imports: [CommonModule, FormsModule, StoxGridComponent],
  template: `
    <div class="screener-wrapper">

      <!-- Page Header -->
      <div class="page-header">
        <div class="header-left">
          <div class="page-icon">📡</div>
          <div>
            <h1 class="page-title">Pattern Screener &amp; Pre-Breakout Radar</h1>
            <p class="page-subtitle">
              {{ mode() === 'pre_breakout' ? 'Stocks forming bullish patterns BEFORE breakout (4-week projections)' : 'All detected technical signals across analyzed NSE stocks' }}
              <span class="count-badge" *ngIf="!loading()">{{ filteredPicks().length }} setups</span>
            </p>
          </div>
        </div>
        <div class="header-right">
          <button
            *ngIf="mode() === 'pre_breakout'"
            class="pill hc-toggle"
            [class.active]="highConviction()"
            (click)="toggleHighConviction()"
            title="Show only positive-expectancy patterns (Darvas Box, Double Bottom, Falling Wedge, VCP, Inverse H&S Forming, Saucer)"
          >
            🎯 High-Conviction Only
          </button>
          <div class="mode-switch">
            <button class="mode-btn" [class.active]="mode() === 'pre_breakout'" (click)="setMode('pre_breakout')">
              🚀 About to Turn Bullish
            </button>
            <button class="mode-btn" [class.active]="mode() === 'all_patterns'" (click)="setMode('all_patterns')">
              📡 All Detected Patterns
            </button>
          </div>
          <span class="last-updated" *ngIf="lastUpdated()">
            Updated {{ lastUpdated() }}
          </span>
          <button class="btn-refresh" (click)="refresh()" [disabled]="loading()">
            <span [class.spinning]="loading()">↻</span> Refresh
          </button>
        </div>
      </div>

      <!-- Disclaimer Banner -->
      <div class="disclaimer-banner">
        ⚠️ <strong>Educational &amp; Research Use Only</strong> — Not SEBI registered.
        Breakout triggers and 4-week targets are algorithmic projections, not investment advice. Wait for price confirmation above the trigger level.
      </div>

      <!-- Summary KPI Strip -->
      <div class="kpi-strip" *ngIf="!loading() && allPicks().length > 0">
        <button class="kpi-chip" [class.active]="stageFilter() === 'IMMINENT_BREAKOUT'" (click)="stageFilter.set('IMMINENT_BREAKOUT')">
          <span class="kpi-label">⚡ Near Pivot</span>
          <strong class="kpi-val accent-amber">{{ countStage('IMMINENT_BREAKOUT') }}</strong>
        </button>
        <button class="kpi-chip" [class.active]="stageFilter() === 'FORMING_PRE_BREAKOUT'" (click)="stageFilter.set('FORMING_PRE_BREAKOUT')">
          <span class="kpi-label">⏳ Forming</span>
          <strong class="kpi-val accent-sky">{{ countStage('FORMING_PRE_BREAKOUT') }}</strong>
        </button>
        <button class="kpi-chip" [class.active]="stageFilter() === 'FRESH_BREAKOUT'" (click)="stageFilter.set('FRESH_BREAKOUT')">
          <span class="kpi-label">✅ Fresh Breakout</span>
          <strong class="kpi-val accent-green">{{ countStage('FRESH_BREAKOUT') }}</strong>
        </button>
        <div class="kpi-chip kpi-stat">
          <span class="kpi-label">Avg 4W Upside</span>
          <strong class="kpi-val accent-green">+{{ avgUpside() | number:'1.1-1' }}%</strong>
        </div>
        <div class="kpi-chip kpi-stat">
          <span class="kpi-label">Avg R:R</span>
          <strong class="kpi-val accent-sky">{{ avgRr() | number:'1.1-1' }}x</strong>
        </div>
      </div>

      <!-- Filter Bar -->
      <div class="filter-bar">
        <!-- Search -->
        <div class="filter-group">
          <label class="filter-label">Search</label>
          <div class="search-wrap">
            <input
              type="text"
              class="search-input"
              [value]="searchQuery()"
              (input)="onSearch($event)"
              placeholder="Symbol, name, pattern…"
            />
            <button class="search-clear" *ngIf="searchQuery()" (click)="searchQuery.set('')" title="Clear">✕</button>
          </div>
        </div>

        <!-- Sector -->
        <div class="filter-group">
          <label class="filter-label">Sector</label>
          <select class="sort-select" [value]="sectorFilter()" (change)="setSectorFilter($event)">
            <option value="ALL">All Sectors</option>
            <option *ngFor="let sec of availableSectors()" [value]="sec">{{ sec }}</option>
          </select>
        </div>

        <!-- Stage -->
        <div class="filter-group">
          <label class="filter-label">Entry Timing / Stage</label>
          <div class="pill-group">
            <button *ngFor="let st of stages" class="pill"
                    [class.active]="stageFilter() === st.key"
                    (click)="stageFilter.set(st.key)">
              {{ st.label }} ({{ stageCount(st.key) }})
            </button>
          </div>
        </div>

        <!-- Verdict -->
        <div class="filter-group">
          <label class="filter-label">Verdict</label>
          <div class="pill-group">
            <button *ngFor="let v of verdicts" class="pill"
                    [class.active]="verdictFilter() === v"
                    (click)="setVerdictFilter(v)">{{ v }}</button>
          </div>
        </div>

        <!-- Direction -->
        <div class="filter-group" *ngIf="mode() === 'all_patterns'">
          <label class="filter-label">Direction</label>
          <div class="pill-group">
            <button *ngFor="let d of directions" class="pill"
                    [class.active]="directionFilter() === d"
                    (click)="setDirectionFilter(d)">
              <span *ngIf="d==='Bullish'">🟢</span>
              <span *ngIf="d==='Bearish'">🔴</span>
              {{ d }}
            </button>
          </div>
        </div>

        <!-- Category -->
        <div class="filter-group" *ngIf="mode() === 'all_patterns'">
          <label class="filter-label">Category</label>
          <div class="pill-group">
            <button *ngFor="let c of categories" class="pill"
                    [class.active]="categoryFilter() === c"
                    (click)="setCategoryFilter(c)">{{ c }}</button>
          </div>
        </div>

        <!-- Min Upside -->
        <div class="filter-group">
          <label class="filter-label">Min 4W Upside: <strong>{{ minUpside() }}%</strong></label>
          <input type="range" min="0" max="30" step="1"
                 [value]="minUpside()"
                 (input)="setMinUpside($event)"
                 class="range-slider" />
        </div>

        <!-- Sort -->
        <div class="filter-group">
          <label class="filter-label">Sort By</label>
          <select class="sort-select" [value]="sortKey()" (change)="setSortKey($event)">
            <option value="readiness_score">Readiness Score</option>
            <option value="upside_pct">4W Upside %</option>
            <option value="risk_reward">R:R Ratio</option>
            <option value="confidence_score">Confidence</option>
            <option value="timestamp">Latest First</option>
          </select>
        </div>
      </div>

      <!-- Loading State -->
      <div class="state-loading" *ngIf="loading()">
        <div class="spinner"></div>
        <p>Scanning pattern signals…</p>
      </div>

      <!-- Error State -->
      <div class="state-error" *ngIf="error() && !loading()">
        <div class="error-icon">⚠️</div>
        <p>{{ error() }}</p>
        <button class="btn-refresh" (click)="refresh()">Retry</button>
      </div>

      <!-- Empty State -->
      <div class="state-empty" *ngIf="!loading() && !error() && filteredPicks().length === 0">
        <div class="empty-icon">🔍</div>
        <h3>No pattern signals found</h3>
        <p>Try running the analysis engine with <code>python main.py --all-nse</code>,<br>
           or relax the filters above.</p>
      </div>

      <!-- Pattern Table -->
      <div *ngIf="!loading() && !error() && filteredPicks().length > 0">
        <app-stox-grid
          [data]="filteredPicks()"
          [columns]="gridColumns()"
          [rowClass]="rowClassFn"
          (rowClick)="openDetail($event)"
        ></app-stox-grid>
      </div>

      <ng-template #psIdxTpl let-i="index"><span class="col-num">{{ i + 1 }}</span></ng-template>
      <ng-template #psSymTpl let-pick>
        <button class="sym-pill" [class.sym-pill--green]="pick.direction === 'Bullish'">
          {{ pick.symbol }}
          <span class="dir-dot" [class.bull]="pick.direction==='Bullish'" [class.bear]="pick.direction==='Bearish'">
            {{ pick.direction === 'Bullish' ? '▲' : '▼' }}
          </span>
        </button>
      </ng-template>
      <ng-template #psNameTpl let-pick>
        <div class="name-block">
          <span class="stock-name">{{ pick.name }}</span>
          <span class="stock-sector">{{ pick.sector }}</span>
        </div>
      </ng-template>
      <ng-template #psLtpTpl let-pick><span class="col-mono ltp-bold">Rs. {{ pick.last_price | number:'1.2-2' }}</span></ng-template>
      <ng-template #psPatTpl let-pick>
        <div class="pattern-block">
          <div class="pattern-top-line">
            <span class="pattern-name">{{ pick.pattern_name }}</span>
            <span class="category-badge" [class]="'cat-' + categoryClass(pick.pattern_category)">
              {{ pick.pattern_category }}
            </span>
          </div>
          <span class="proj-line" *ngIf="pick.projection_summary" [title]="pick.projection_summary">{{ pick.projection_summary }}</span>
          <div class="micro-tags" *ngIf="pick.rsi_14 != null || pick.rvol != null || pick.up_down_vol_ratio != null || pick.retest_hold_confirmed || pick.confirmation_status === 'INTRADAY_CROSS' || pick.regime_ok === false">
            <span class="micro-tag" *ngIf="pick.rsi_14 != null">RSI {{ pick.rsi_14 | number:'1.0-0' }}</span>
            <span class="micro-tag" [class.micro-tag--good]="(pick.rvol ?? 0) >= 1.5" *ngIf="pick.rvol != null">
              Vol {{ pick.rvol | number:'1.1-1' }}x
            </span>
            <span class="micro-tag" [class.micro-tag--good]="(pick.up_down_vol_ratio ?? 0) >= 1.2" *ngIf="pick.up_down_vol_ratio != null">
              U/D {{ pick.up_down_vol_ratio | number:'1.1-1' }}x
            </span>
            <span class="micro-tag micro-tag--good" *ngIf="pick.retest_hold_confirmed">
              {{ pick.confirmation_status === 'RETEST_HOLD' ? '✓ Retest Hold' : '✓ 2D Hold' }}
            </span>
            <span class="micro-tag micro-tag--warn" *ngIf="pick.confirmation_status === 'INTRADAY_CROSS'">Await Close</span>
            <span class="micro-tag micro-tag--warn" *ngIf="pick.regime_ok === false">⚠ Weak Sector/Mkt</span>
          </div>
        </div>
      </ng-template>
      <ng-template #psScoreTpl let-pick>
        <span class="score-pill" [class.high-score]="pickScore(pick) >= 75" [title]="(pick.forming_evidence || []).join(' • ')">
          {{ pickScore(pick) | number:'1.0-0' }}
        </span>
      </ng-template>
      <ng-template #psStageTpl let-pick>
        <span class="stage-badge" [ngClass]="stageClass(pick.setup_stage)">
          {{ stageLabel(pick.setup_stage, pick.entry_window) }}
        </span>
      </ng-template>
      <ng-template #psTrigTpl let-pick>
        <div class="trigger-block col-mono" *ngIf="pick.breakout_trigger; else noTrigger">
          <span class="trig-chip">Rs. {{ pick.breakout_trigger | number:'1.2-2' }}</span>
          <span class="trigger-dist"
                [class.dist-imminent]="pick.distance_to_breakout_pct !== undefined && pick.distance_to_breakout_pct !== null && pick.distance_to_breakout_pct > 0 && pick.distance_to_breakout_pct <= 1.5"
                *ngIf="pick.distance_to_breakout_pct !== undefined && pick.distance_to_breakout_pct !== null">
            {{ pick.distance_to_breakout_pct > 0 ? ('+' + pick.distance_to_breakout_pct.toFixed(1) + '% away') : (pick.distance_to_breakout_pct.toFixed(1) + '% vs pivot') }}
          </span>
        </div>
        <ng-template #noTrigger><span class="na-val">—</span></ng-template>
      </ng-template>
      <ng-template #psVerdTpl let-pick>
        <span class="verdict-badge" [class]="'verdict-' + pick.action_verdict">
          {{ pick.action_verdict }}
        </span>
      </ng-template>
      <ng-template #psTgtTpl let-pick>
        <strong class="col-mono accent-green" *ngIf="pick.week4_target || pick.target_price">
          Rs. {{ (pick.week4_target || pick.target_price) | number:'1.2-2' }}
        </strong>
        <span class="na-val" *ngIf="!pick.week4_target && !pick.target_price">—</span>
      </ng-template>
      <ng-template #psSlTpl let-pick>
        <span class="col-mono sl-chip" *ngIf="pick.stop_loss">Rs. {{ pick.stop_loss | number:'1.2-2' }}</span>
        <span class="na-val" *ngIf="!pick.stop_loss">—</span>
      </ng-template>
      <ng-template #psUpTpl let-pick>
        <span class="upside-pill" [class.upside-pill--neg]="(pick.week4_upside_pct ?? pick.upside_pct) < 0">
          {{ (pick.week4_upside_pct ?? pick.upside_pct) > 0 ? '+' : '' }}{{ (pick.week4_upside_pct ?? pick.upside_pct) | number:'1.1-1' }}%
        </span>
      </ng-template>
      <ng-template #psRrTpl let-pick>
        <span class="rr-pill">{{ pick.risk_reward | number:'1.1-1' }}x</span>
      </ng-template>
      <ng-template #psSparkTpl let-pick>
        <svg class="mini-spark" viewBox="0 0 60 24" preserveAspectRatio="none">
          <polyline
            [attr.points]="sparkPoints(pick.sparkline)"
            fill="none"
            [attr.stroke]="pick.direction === 'Bullish' ? '#10b981' : '#ef4444'"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"/>
        </svg>
      </ng-template>

      <!-- Footer note -->
      <div class="screener-footer" *ngIf="!loading() && filteredPicks().length > 0">
        <span>Showing {{ filteredPicks().length }} of {{ allPicks().length }} pattern signals from cache DB</span>
        <span>Auto-refreshes every 60s while page is open</span>
      </div>
    </div>
  `,
  styles: [`
    :host {
      display: block;
      flex: 1;
      min-height: 0;
      width: 100%;
      overflow-y: auto;
      padding: 20px 20px 48px 20px;
      box-sizing: border-box;
    }

    .screener-wrapper {
      width: 100%;
      max-width: none;
    }

    /* ---- Page Header ---- */
    .page-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 16px;
      gap: 16px;
    }
    .header-left { display: flex; align-items: center; gap: 14px; }
    .page-icon { font-size: 2.2rem; line-height: 1; }
    .page-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.5rem;
      font-weight: 700;
      color: #fff;
      margin: 0 0 2px;
    }
    .page-subtitle { font-size: 0.8rem; color: #94a3b8; margin: 0; display: flex; align-items: center; gap: 8px; }
    .count-badge {
      background: rgba(56,189,248,0.15);
      border: 1px solid rgba(56,189,248,0.3);
      color: #38bdf8;
      padding: 1px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
    }
    .header-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .mode-switch {
      display: flex;
      gap: 4px;
      background: rgba(255,255,255,0.04);
      border: 1px solid rgba(255,255,255,0.1);
      padding: 3px;
      border-radius: 9px;
    }
    .mode-btn {
      background: transparent;
      border: none;
      color: #94a3b8;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 0.76rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
    }
    .mode-btn.active {
      background: rgba(16,185,129,0.18);
      color: #34d399;
      border: 1px solid rgba(16,185,129,0.35);
    }
    .pattern-top-line { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .proj-line { font-size: 0.69rem; color: #94a3b8; line-height: 1.35; }
    .stage-pill {
      display: inline-block; padding: 2px 8px; border-radius: 999px;
      font-size: 0.66rem; font-weight: 700; white-space: nowrap;
    }
    .stage-imminent { background: rgba(245,158,11,0.18); color: #fbbf24; border: 1px solid rgba(245,158,11,0.4); }
    .stage-forming { background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.35); }
    .stage-fresh { background: rgba(16,185,129,0.16); color: #34d399; border: 1px solid rgba(16,185,129,0.38); }
    .stage-late { background: rgba(239,68,68,0.14); color: #f87171; border: 1px solid rgba(239,68,68,0.35); }
    .stage-neutral { background: rgba(100,116,139,0.15); color: #94a3b8; border: 1px solid rgba(100,116,139,0.3); }
    .trigger-block { display: flex; flex-direction: column; gap: 2px; }
    .trigger-val { font-family: 'JetBrains Mono', monospace; color: #38bdf8; font-weight: 700; font-size: 0.76rem; }
    .trigger-dist { font-size: 0.64rem; color: #94a3b8; white-space: nowrap; }
    .last-updated { font-size: 0.72rem; color: #64748b; }
    .btn-refresh {
      background: rgba(56,189,248,0.1);
      border: 1px solid rgba(56,189,248,0.3);
      color: #38bdf8;
      padding: 6px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s;
      display: flex; align-items: center; gap: 6px;
    }
    .btn-refresh:hover { background: rgba(56,189,248,0.2); }
    .btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinning { display: inline-block; animation: spin 0.9s linear infinite; }

    /* ---- Disclaimer ---- */
    .disclaimer-banner {
      background: rgba(245, 158, 11, 0.08);
      border: 1px solid rgba(245, 158, 11, 0.25);
      color: #fbbf24;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.75rem;
      margin-bottom: 16px;
      line-height: 1.5;
    }

    /* ---- Filters ---- */
    .filter-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: flex-end;
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.07);
      border-radius: 12px;
      padding: 14px 18px;
      margin-bottom: 20px;
    }
    .filter-group { display: flex; flex-direction: column; gap: 6px; }
    .filter-label { font-size: 0.7rem; color: #64748b; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; }
    .pill-group { display: flex; gap: 4px; flex-wrap: wrap; }
    .pill {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.1);
      color: #94a3b8;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
      white-space: nowrap;
    }
    .pill:hover { border-color: rgba(56,189,248,0.4); color: #38bdf8; }
    .pill.active { background: rgba(56,189,248,0.15); border-color: rgba(56,189,248,0.4); color: #38bdf8; }
    .range-slider { width: 140px; accent-color: #38bdf8; cursor: pointer; }
    .sort-select {
      background: rgba(255,255,255,0.05);
      border: 1px solid rgba(255,255,255,0.12);
      color: #e2e8f0;
      padding: 5px 10px;
      border-radius: 8px;
      font-size: 0.75rem;
      cursor: pointer;
    }

    /* ---- States ---- */
    .state-loading, .state-error, .state-empty {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 60px 20px; gap: 12px; color: #64748b; text-align: center;
    }
    .spinner {
      width: 36px; height: 36px;
      border: 3px solid rgba(56,189,248,0.2);
      border-top-color: #38bdf8;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    .error-icon, .empty-icon { font-size: 2.5rem; }
    .state-error { color: #ef4444; }
    .state-empty h3 { color: #94a3b8; font-size: 1rem; margin: 0; }
    .state-empty p { font-size: 0.8rem; color: #64748b; margin: 0; line-height: 1.6; }
    .state-empty code { background: rgba(255,255,255,0.08); padding: 1px 6px; border-radius: 4px; font-size: 0.75rem; }

    /* ---- Footer ---- */
    .screener-footer {
      display: flex;
      justify-content: space-between;
      padding: 10px 4px;
      font-size: 0.7rem;
      color: #334155;
    }

    /* Responsive */
    @media (max-width: 1024px) {
      .col-name, .col-sparkline { display: none; }
    }
    @media (max-width: 768px) {
      :host { padding: 12px; }
      .page-header { flex-direction: column; }
      .col-rr, .col-target, .col-sl { display: none; }
      .filter-bar { gap: 10px; padding: 10px; }
    }

    /* KPI Strip & Search */
    .kpi-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
    }
    .kpi-chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px;
      padding: 6px 12px;
      cursor: pointer;
      color: #cbd5e1;
      font-size: 0.74rem;
    }
    .kpi-chip.kpi-stat { cursor: default; }
    .kpi-chip.active {
      border-color: #38bdf8;
      background: rgba(56, 189, 248, 0.14);
    }
    .kpi-label { color: #94a3b8; font-size: 0.7rem; font-weight: 600; }
    .kpi-val { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; }
    .accent-amber { color: #fbbf24; }

    .search-wrap { position: relative; display: flex; align-items: center; }
    .search-input {
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      padding: 4px 24px 4px 10px;
      border-radius: 6px;
      font-size: 0.74rem;
      width: 185px;
    }
    .search-clear {
      position: absolute;
      right: 5px;
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 0.7rem;
      padding: 0 4px;
      cursor: pointer;
    }
    .hc-toggle { font-size: 0.72rem; }
    :host-context([data-theme='light']) .kpi-chip {
      background: #ffffff;
      border-color: #cbd5e1;
      color: #0f172a;
    }
    :host-context([data-theme='light']) .kpi-label { color: #475569; }
    :host-context([data-theme='light']) .accent-amber { color: #b45309; }
    :host-context([data-theme='light']) .search-input {
      background: #ffffff;
      border-color: #cbd5e1;
      color: #0f172a;
    }
  `]
})
export class PatternScreenerComponent implements OnInit, OnDestroy {

  // ---- Signals ----
  mode          = signal<ScreenerMode>('pre_breakout');
  highConviction = signal<boolean>(true);
  allPicks      = signal<PatternPick[]>([]);
  loading       = signal<boolean>(false);
  error         = signal<string | null>(null);
  lastUpdated   = signal<string | null>(null);

  searchQuery     = signal<string>('');
  sectorFilter    = signal<string>('ALL');
  stageFilter     = signal<StageFilter>('ALL');
  verdictFilter   = signal<VerdictFilter>('ALL');
  directionFilter = signal<DirectionFilter>('ALL');
  categoryFilter  = signal<CategoryFilter>('ALL');
  minUpside       = signal<number>(0);
  sortKey         = signal<SortKey>('readiness_score');

  @ViewChild(StoxGridComponent) stoxGrid?: StoxGridComponent<PatternPick>;
  @ViewChild('psIdxTpl', { static: true }) psIdxTpl!: TemplateRef<any>;
  @ViewChild('psSymTpl', { static: true }) psSymTpl!: TemplateRef<any>;
  @ViewChild('psNameTpl', { static: true }) psNameTpl!: TemplateRef<any>;
  @ViewChild('psLtpTpl', { static: true }) psLtpTpl!: TemplateRef<any>;
  @ViewChild('psPatTpl', { static: true }) psPatTpl!: TemplateRef<any>;
  @ViewChild('psScoreTpl', { static: true }) psScoreTpl!: TemplateRef<any>;
  @ViewChild('psStageTpl', { static: true }) psStageTpl!: TemplateRef<any>;
  @ViewChild('psTrigTpl', { static: true }) psTrigTpl!: TemplateRef<any>;
  @ViewChild('psVerdTpl', { static: true }) psVerdTpl!: TemplateRef<any>;
  @ViewChild('psTgtTpl', { static: true }) psTgtTpl!: TemplateRef<any>;
  @ViewChild('psSlTpl', { static: true }) psSlTpl!: TemplateRef<any>;
  @ViewChild('psUpTpl', { static: true }) psUpTpl!: TemplateRef<any>;
  @ViewChild('psRrTpl', { static: true }) psRrTpl!: TemplateRef<any>;
  @ViewChild('psSparkTpl', { static: true }) psSparkTpl!: TemplateRef<any>;

  rowClassFn = (p: PatternPick) =>
    p.direction === 'Bullish' ? 'row-bullish' : (p.direction === 'Bearish' ? 'row-bearish' : '');

  gridColumns = computed<StoxGridColumn<PatternPick>[]>(() => [
    { id: 'idx', header: '#', sortable: false, cellTemplate: this.psIdxTpl, headerClass: 'col-num', cellClass: 'col-num' },
    { id: 'symbol', header: 'Symbol', accessorFn: r => r.symbol, cellTemplate: this.psSymTpl },
    { id: 'name', header: 'Name / Sector', accessorFn: r => r.name, cellTemplate: this.psNameTpl, headerClass: 'col-name', cellClass: 'col-name' },
    { id: 'last_price', header: 'LTP', accessorFn: r => r.last_price ?? 0, cellTemplate: this.psLtpTpl, cellClass: 'col-mono' },
    { id: 'pattern_name', header: 'Pattern & Projection', accessorFn: r => r.pattern_name ?? '', cellTemplate: this.psPatTpl, headerClass: 'col-pattern', cellClass: 'col-pattern' },
    { id: 'readiness_score', header: 'Score', accessorFn: r => this.pickScore(r), cellTemplate: this.psScoreTpl },
    { id: 'setup_stage', header: 'Timing / Stage', accessorFn: r => r.setup_stage ?? '', cellTemplate: this.psStageTpl },
    { id: 'breakout_trigger', header: 'Buy Above', accessorFn: r => r.breakout_trigger ?? 0, cellTemplate: this.psTrigTpl, cellClass: 'col-mono' },
    { id: 'action_verdict', header: 'Verdict', accessorFn: r => r.action_verdict ?? '', cellTemplate: this.psVerdTpl },
    { id: 'target_price', header: '4W Target', accessorFn: r => r.week4_target ?? r.target_price ?? 0, cellTemplate: this.psTgtTpl, headerClass: 'col-target', cellClass: 'col-target col-mono' },
    { id: 'stop_loss', header: 'Stop Loss', accessorFn: r => r.stop_loss ?? 0, cellTemplate: this.psSlTpl, headerClass: 'col-sl', cellClass: 'col-sl col-mono' },
    { id: 'upside_pct', header: '4W Upside%', accessorFn: r => r.week4_upside_pct ?? r.upside_pct ?? 0, cellTemplate: this.psUpTpl, cellClass: 'col-mono' },
    { id: 'risk_reward', header: 'R:R', accessorFn: r => r.risk_reward ?? 0, cellTemplate: this.psRrTpl, headerClass: 'col-rr', cellClass: 'col-rr col-mono' },
    { id: 'sparkline', header: 'Trend', sortable: false, cellTemplate: this.psSparkTpl, headerClass: 'col-sparkline', cellClass: 'col-sparkline' },
  ]);

  // ---- Filter options ----
  stages: { key: StageFilter; label: string }[] = [
    { key: 'ALL', label: 'All Stages' },
    { key: 'IMMINENT_BREAKOUT', label: '⚡ Near Pivot (Watch Close)' },
    { key: 'FORMING_PRE_BREAKOUT', label: '⏳ Forming Setup (2–5d)' },
    { key: 'FRESH_BREAKOUT', label: '✅ Confirmed Close > Pivot' },
    { key: 'HIDE_LATE', label: '🚫 Hide Extended/Late' },
  ];
  verdicts: VerdictFilter[]    = ['ALL', 'BUY', 'ACCUMULATE', 'HOLD', 'REDUCE', 'SELL'];
  directions: DirectionFilter[] = ['ALL', 'Bullish', 'Bearish'];
  categories: CategoryFilter[]  = ['ALL', 'Moving Average', 'Reversal', 'Breakout', 'Accumulation', 'Candlestick', 'Classical Chart'];

  // ---- Computed: sectors, KPIs, filtered + sorted picks ----
  availableSectors = computed(() => {
    const set = new Set<string>();
    for (const p of this.allPicks()) {
      if (p.sector && p.sector.trim()) set.add(p.sector.trim());
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  });

  avgUpside = computed(() => {
    const list = this.filteredPicks();
    if (!list.length) return 0;
    const sum = list.reduce((acc, p) => acc + (p.week4_upside_pct ?? p.upside_pct ?? 0), 0);
    return sum / list.length;
  });

  avgRr = computed(() => {
    const list = this.filteredPicks();
    if (!list.length) return 0;
    const sum = list.reduce((acc, p) => acc + (p.risk_reward ?? 0), 0);
    return sum / list.length;
  });

  filteredPicks = computed(() => {
    let picks = [...this.allPicks()];

    const q = this.searchQuery().trim().toLowerCase();
    if (q) {
      picks = picks.filter(p =>
        p.symbol.toLowerCase().includes(q) ||
        (p.name || '').toLowerCase().includes(q) ||
        (p.pattern_name || '').toLowerCase().includes(q)
      );
    }

    const sec = this.sectorFilter();
    if (sec !== 'ALL') {
      picks = picks.filter(p => (p.sector || '').trim() === sec);
    }

    const st = this.stageFilter();
    if (st === 'HIDE_LATE') {
      picks = picks.filter(p => !p.is_late_entry && p.setup_stage !== 'EXTENDED_LATE');
    } else if (st !== 'ALL') {
      picks = picks.filter(p => p.setup_stage === st);
    }

    if (this.verdictFilter() !== 'ALL') {
      picks = picks.filter(p => p.action_verdict === this.verdictFilter());
    }
    if (this.directionFilter() !== 'ALL') {
      picks = picks.filter(p => p.direction === this.directionFilter());
    }
    if (this.categoryFilter() !== 'ALL') {
      const cat = this.categoryFilter();
      picks = picks.filter(p => (p.pattern_category || '') === cat || (p.pattern_category || '').startsWith(cat));
    }
    if (this.minUpside() > 0) {
      picks = picks.filter(p => (p.week4_upside_pct ?? p.upside_pct) >= this.minUpside());
    }

    const key = this.sortKey();
    picks.sort((a, b) => {
      if (key === 'timestamp') return b.timestamp.localeCompare(a.timestamp);
      if (key === 'readiness_score') return this.pickScore(b) - this.pickScore(a);
      if (key === 'upside_pct') return (b.week4_upside_pct ?? b.upside_pct) - (a.week4_upside_pct ?? a.upside_pct);
      return ((b[key] as number) ?? 0) - ((a[key] as number) ?? 0);
    });

    return picks;
  });

  private refreshTimer: any;

  ngOnInit(): void {
    this.loadPicks();
    // Auto-refresh every 60 s while page is open
    this.refreshTimer = setInterval(() => this.loadPicks(), 60_000);
  }

  ngOnDestroy(): void {
    if (this.refreshTimer) clearInterval(this.refreshTimer);
  }

  setMode(m: ScreenerMode): void {
    if (this.mode() === m) return;
    this.mode.set(m);
    this.stageFilter.set('ALL');
    this.loadPicks();
  }

  toggleHighConviction(): void {
    this.highConviction.update(v => !v);
    this.loadPicks();
  }

  async loadPicks(): Promise<void> {
    const activeMode = this.mode();
    const hc = this.highConviction();
    const cacheKey = activeMode === 'pre_breakout' ? `pre_${hc ? 'hc' : 'all'}` : 'all_patterns';
    const cached = PatternScreenerComponent.cache[cacheKey];
    if (cached && this.allPicks().length === 0) {
      this.allPicks.set(cached.picks);
      this.lastUpdated.set(cached.at);
    }
    const silent = (PatternScreenerComponent.cache[cacheKey]?.picks?.length ?? 0) > 0;
    if (!silent) this.loading.set(true);
    this.error.set(null);
    try {
      const resp = activeMode === 'pre_breakout'
        ? await ApiService.getPreBreakoutPicks('monitored', 100, true, hc)
        : await ApiService.getPatternPicks(0);
      const picks = resp.picks ?? [];
      const at = new Date().toLocaleTimeString('en-IN');
      PatternScreenerComponent.cache[cacheKey] = { picks, at };
      if (this.mode() === activeMode && this.highConviction() === hc) {
        this.allPicks.set(picks);
        this.lastUpdated.set(at);
      }
    } catch (err: any) {
      if (!silent) this.error.set(err?.message ?? 'Failed to load pattern data');
    } finally {
      this.loading.set(false);
    }
  }

  private static cache: Record<string, { picks: PatternPick[]; at: string } | null> = {};

  refresh(): void { this.loadPicks(); }

  openDetail(pick: PatternPick): void {
    const existing = stocksStore.stocks().find(s => s.symbol === pick.symbol);
    if (existing) {
      stocksStore.selectSymbol(existing.symbol);
      return;
    }
    const adHoc: Stock = {
      symbol: pick.symbol,
      name: pick.name || pick.symbol,
      sector: pick.sector || 'Indian Equities',
      queue_status: 'completed',
      is_stale: false,
      has_analysis: true,
      synth_output: {
        as_of_date: pick.timestamp || '',
        structured_signal: {
          action_verdict: pick.action_verdict as any,
          confidence_score: pick.confidence_score,
          confidence_percentage: Math.round(pick.confidence_score),
          when_to_buy_entry: pick.entry_range,
          when_to_sell_target: pick.target_price ? `Rs. ${pick.target_price.toFixed(2)}` : 'N/A',
          stop_loss: pick.stop_loss ? `Rs. ${pick.stop_loss.toFixed(2)}` : 'N/A',
          risk_reward_ratio: pick.risk_reward ? `1:${pick.risk_reward.toFixed(2)}` : 'N/A',
          target_num: pick.target_price ?? undefined,
          stop_num: pick.stop_loss ?? undefined,
          chart_patterns: pick.pattern_name,
        },
      },
      tech_output: null,
      patterns: [
        {
          name: pick.pattern_name,
          category: pick.pattern_category,
          direction: pick.direction,
          quality_score: Math.round(pick.confidence_score),
          target_price: pick.target_price ?? undefined,
          stop_loss: pick.stop_loss ?? undefined,
          risk_reward_ratio: pick.risk_reward,
          setup_stage: pick.setup_stage,
          entry_window: pick.entry_window,
          breakout_trigger: pick.breakout_trigger,
          week4_target: pick.week4_target,
          week4_upside_pct: pick.week4_upside_pct,
          rvol: pick.rvol,
          confirmation_status: pick.confirmation_status,
          daily_close_confirmed: pick.daily_close_confirmed,
          volume_confirmed: pick.volume_confirmed,
          retest_hold_confirmed: pick.retest_hold_confirmed,
          regime_ok: pick.regime_ok,
          projection_summary: pick.projection_summary,
        },
      ],
      events: {},
      sparkline: pick.sparkline || [],
      price_info: {
        price: pick.last_price,
        change_pct: null,
        source: 'Cache',
      },
      long_term_signal: {
        long_term_target: 'N/A',
        long_term_verdict: 'N/A',
      },
    };
    adHoc.tech_output = {
      raw_indicators: {
        last_price: pick.last_price,
        rsi_14: pick.rsi_14 ?? null,
        rvol: pick.rvol ?? null,
        up_down_vol_ratio: pick.up_down_vol_ratio ?? null,
      },
    };
    stocksStore.selectStock(adHoc);
  }

  // ---- Filter setters ----
  onSearch(e: Event): void { this.searchQuery.set((e.target as HTMLInputElement).value); }
  setSectorFilter(e: Event): void { this.sectorFilter.set((e.target as HTMLSelectElement).value); }
  setVerdictFilter(v: VerdictFilter)     { this.verdictFilter.set(v); }
  setDirectionFilter(d: DirectionFilter) { this.directionFilter.set(d); }
  setCategoryFilter(c: CategoryFilter)   { this.categoryFilter.set(c); }
  setMinUpside(event: Event): void {
    this.minUpside.set(+(event.target as HTMLInputElement).value);
  }
  setSortKey(event: Event): void {
    this.sortKey.set((event.target as HTMLSelectElement).value as SortKey);
    this.stoxGrid?.sorting.set([]);
  }
  toggleSort(key: SortKey): void {
    this.sortKey.set(key);
    this.stoxGrid?.sorting.set([]);
  }

  countStage(stage: string): number {
    return this.allPicks().filter(p => p.setup_stage === stage).length;
  }

  stageCount(key: StageFilter): number {
    const all = this.allPicks();
    if (key === 'ALL') return all.length;
    if (key === 'HIDE_LATE') return all.filter(p => !p.is_late_entry && p.setup_stage !== 'EXTENDED_LATE').length;
    return all.filter(p => p.setup_stage === key).length;
  }

  pickScore(p: PatternPick): number {
    return p.readiness_score ?? p.quality_score ?? p.confidence_score ?? 0;
  }

  // ---- Helpers ----
  stageClass(stage?: string): string {
    if (stage === 'IMMINENT_BREAKOUT') return 'stage-imminent';
    if (stage === 'FORMING_PRE_BREAKOUT') return 'stage-forming';
    if (stage === 'FRESH_BREAKOUT') return 'stage-fresh';
    if (stage === 'EXTENDED_LATE') return 'stage-late';
    return 'stage-neutral';
  }

  stageLabel(stage?: string, windowStr?: string): string {
    if (stage === 'IMMINENT_BREAKOUT') return '⚡ Near Pivot (Watch Close)';
    if (stage === 'FORMING_PRE_BREAKOUT') return '⏳ Forming Setup (2–5d)';
    if (stage === 'FRESH_BREAKOUT') return '✅ Confirmed Close > Pivot';
    if (stage === 'EXTENDED_LATE') return '⚠️ Extended (Wait Pullback)';
    if (stage === 'EARLY_BASE') return '👀 Early Base';
    return windowStr || 'Signal';
  }

  categoryClass(cat: string): string {
    const c = (cat || '').trim();
    if (c.startsWith('Moving Average')) return 'ma';
    if (c.startsWith('Reversal')) return 'reversal';
    if (c.startsWith('Breakout')) return 'breakout';
    if (c.startsWith('Accumulation')) return 'accumulation';
    if (c.startsWith('Candlestick')) return 'candlestick';
    return 'other';
  }

  sparkPoints(prices: number[]): string {
    if (!prices || prices.length < 2) return '';
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || 1;
    const W = 60, H = 22;
    return prices.map((p, i) => {
      const x = (i / (prices.length - 1)) * W;
      const y = H - ((p - min) / range) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }
}
