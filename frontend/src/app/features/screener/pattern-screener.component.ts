/**
 * Pattern Screener Component.
 * Shows top stocks with high-conviction technical chart patterns
 * sourced from ALL analyzed symbols in the cache DB (not just watchlist).
 *
 * ⚠️ ADVISORY ONLY — No order placement, no investment advice.
 */

import { Component, OnInit, OnDestroy, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { PatternPick, Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';

type SortKey = 'upside_pct' | 'risk_reward' | 'confidence_score' | 'timestamp';
type VerdictFilter = 'ALL' | 'BUY' | 'ACCUMULATE' | 'HOLD' | 'REDUCE' | 'SELL';
type DirectionFilter = 'ALL' | 'Bullish' | 'Bearish';
type CategoryFilter = 'ALL' | 'Moving Average' | 'Reversal' | 'Breakout' | 'Accumulation' | 'Candlestick' | 'Classical Chart';

@Component({
  selector: 'app-pattern-screener',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="screener-wrapper">

      <!-- Page Header -->
      <div class="page-header">
        <div class="header-left">
          <div class="page-icon">📡</div>
          <div>
            <h1 class="page-title">Pattern Screener</h1>
            <p class="page-subtitle">
              High-conviction technical signals across all analyzed NSE stocks
              <span class="count-badge" *ngIf="!loading()">{{ filteredPicks().length }} patterns</span>
            </p>
          </div>
        </div>
        <div class="header-right">
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
        Patterns shown are algorithmic signals, not investment advice. Always do your own research.
      </div>

      <!-- Filter Bar -->
      <div class="filter-bar">
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
        <div class="filter-group">
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
        <div class="filter-group">
          <label class="filter-label">Category</label>
          <div class="pill-group">
            <button *ngFor="let c of categories" class="pill"
                    [class.active]="categoryFilter() === c"
                    (click)="setCategoryFilter(c)">{{ c }}</button>
          </div>
        </div>

        <!-- Min Upside -->
        <div class="filter-group">
          <label class="filter-label">Min Upside: <strong>{{ minUpside() }}%</strong></label>
          <input type="range" min="0" max="30" step="1"
                 [value]="minUpside()"
                 (input)="setMinUpside($event)"
                 class="range-slider" />
        </div>

        <!-- Sort -->
        <div class="filter-group">
          <label class="filter-label">Sort By</label>
          <select class="sort-select" [value]="sortKey()" (change)="setSortKey($event)">
            <option value="upside_pct">Upside %</option>
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
      <div class="table-wrapper" *ngIf="!loading() && !error() && filteredPicks().length > 0">
        <table class="pattern-table">
          <thead>
            <tr>
              <th class="col-rank">#</th>
              <th class="col-symbol">Symbol</th>
              <th class="col-name">Name / Sector</th>
              <th class="col-ltp">LTP</th>
              <th class="col-pattern">Pattern</th>
              <th class="col-verdict">Verdict</th>
              <th class="col-target">Target</th>
              <th class="col-sl">Stop Loss</th>
              <th class="col-upside" (click)="toggleSort('upside_pct')" style="cursor:pointer">
                Upside% {{ sortKey()==='upside_pct' ? '▼' : '' }}
              </th>
              <th class="col-rr" (click)="toggleSort('risk_reward')" style="cursor:pointer">
                R:R {{ sortKey()==='risk_reward' ? '▼' : '' }}
              </th>
              <th class="col-sparkline">Trend</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let pick of filteredPicks(); let i = index"
                class="pattern-row"
                [class.bullish]="pick.direction === 'Bullish'"
                [class.bearish]="pick.direction === 'Bearish'"
                (click)="openDetail(pick)">

              <!-- Rank -->
              <td class="col-rank">
                <span class="rank-num">{{ i + 1 }}</span>
              </td>

              <!-- Symbol -->
              <td class="col-symbol">
                <div class="symbol-block">
                  <span class="symbol-ticker">{{ pick.symbol }}</span>
                  <span class="dir-dot" [class.bull]="pick.direction==='Bullish'" [class.bear]="pick.direction==='Bearish'">
                    {{ pick.direction === 'Bullish' ? '▲' : '▼' }}
                  </span>
                </div>
              </td>

              <!-- Name / Sector -->
              <td class="col-name">
                <div class="name-block">
                  <span class="stock-name">{{ pick.name }}</span>
                  <span class="stock-sector">{{ pick.sector }}</span>
                </div>
              </td>

              <!-- LTP -->
              <td class="col-ltp">
                <span class="ltp-val">₹{{ pick.last_price | number:'1.2-2' }}</span>
              </td>

              <!-- Pattern -->
              <td class="col-pattern">
                <div class="pattern-block">
                  <span class="pattern-name">{{ pick.pattern_name }}</span>
                  <span class="category-badge" [class]="'cat-' + categoryClass(pick.pattern_category)">
                    {{ pick.pattern_category }}
                  </span>
                </div>
              </td>

              <!-- Verdict -->
              <td class="col-verdict">
                <span class="verdict-badge" [class]="'verdict-' + pick.action_verdict">
                  {{ pick.action_verdict }}
                </span>
              </td>

              <!-- Target -->
              <td class="col-target">
                <span class="target-val" *ngIf="pick.target_price">
                  ₹{{ pick.target_price | number:'1.2-2' }}
                </span>
                <span class="na-val" *ngIf="!pick.target_price">—</span>
              </td>

              <!-- Stop Loss -->
              <td class="col-sl">
                <span class="sl-val" *ngIf="pick.stop_loss">
                  ₹{{ pick.stop_loss | number:'1.2-2' }}
                </span>
                <span class="na-val" *ngIf="!pick.stop_loss">—</span>
              </td>

              <!-- Upside % -->
              <td class="col-upside">
                <span class="upside-val" [class.positive]="pick.upside_pct > 0" [class.negative]="pick.upside_pct < 0">
                  {{ pick.upside_pct > 0 ? '+' : '' }}{{ pick.upside_pct | number:'1.1-1' }}%
                </span>
              </td>

              <!-- R:R -->
              <td class="col-rr">
                <span class="rr-val" [class.good-rr]="pick.risk_reward >= 2">
                  {{ pick.risk_reward | number:'1.1-1' }}x
                </span>
              </td>

              <!-- Mini Sparkline -->
              <td class="col-sparkline">
                <svg class="mini-spark" viewBox="0 0 60 24" preserveAspectRatio="none">
                  <polyline
                    [attr.points]="sparkPoints(pick.sparkline)"
                    fill="none"
                    [attr.stroke]="pick.direction === 'Bullish' ? '#10b981' : '#ef4444'"
                    stroke-width="1.5"
                    stroke-linecap="round"
                    stroke-linejoin="round"/>
                </svg>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

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
      max-width: 1400px;
      margin: 0 auto;
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
    .header-right { display: flex; align-items: center; gap: 10px; }
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

    /* ---- Table ---- */
    .table-wrapper {
      overflow-x: auto;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.07);
    }
    .pattern-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
    }
    .pattern-table thead th {
      background: rgba(255,255,255,0.04);
      color: #64748b;
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      padding: 10px 12px;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.07);
      white-space: nowrap;
    }
    .pattern-row {
      border-bottom: 1px solid rgba(255,255,255,0.04);
      cursor: pointer;
      transition: background 0.15s;
    }
    .pattern-row:hover { background: rgba(56,189,248,0.06); }
    .pattern-row.bullish { border-left: 2px solid rgba(16,185,129,0.4); }
    .pattern-row.bearish { border-left: 2px solid rgba(239,68,68,0.4); }
    .pattern-row td { padding: 10px 12px; vertical-align: middle; }

    /* Rank */
    .rank-num { color: #475569; font-size: 0.72rem; font-weight: 700; font-variant-numeric: tabular-nums; }

    /* Symbol */
    .symbol-block { display: flex; align-items: center; gap: 5px; }
    .symbol-ticker { font-family: 'JetBrains Mono', monospace; color: #e2e8f0; font-weight: 700; font-size: 0.82rem; }
    .dir-dot { font-size: 0.65rem; }
    .dir-dot.bull { color: #10b981; }
    .dir-dot.bear { color: #ef4444; }

    /* Name/sector */
    .name-block { display: flex; flex-direction: column; gap: 2px; }
    .stock-name { color: #cbd5e1; font-size: 0.75rem; white-space: nowrap; max-width: 180px; overflow: hidden; text-overflow: ellipsis; }
    .stock-sector { color: #475569; font-size: 0.65rem; }

    /* LTP */
    .ltp-val { font-family: 'JetBrains Mono', monospace; color: #e2e8f0; font-weight: 600; }

    /* Pattern */
    .pattern-block { display: flex; flex-direction: column; gap: 4px; }
    .pattern-name { color: #cbd5e1; font-size: 0.75rem; }
    .category-badge {
      display: inline-block;
      padding: 1px 7px;
      border-radius: 999px;
      font-size: 0.62rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .cat-ma { background: rgba(56,189,248,0.15); color: #38bdf8; }
    .cat-reversal { background: rgba(139,92,246,0.15); color: #a78bfa; }
    .cat-breakout { background: rgba(245,158,11,0.15); color: #fbbf24; }
    .cat-accumulation { background: rgba(16,185,129,0.15); color: #10b981; }
    .cat-candlestick { background: rgba(236,72,153,0.15); color: #f472b6; }
    .cat-other { background: rgba(100,116,139,0.15); color: #94a3b8; }

    /* Verdict */
    .verdict-badge {
      display: inline-block;
      padding: 3px 9px;
      border-radius: 999px;
      font-size: 0.68rem;
      font-weight: 700;
      text-transform: uppercase;
    }
    .verdict-BUY { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
    .verdict-ACCUMULATE { background: rgba(56,189,248,0.15); color: #38bdf8; border: 1px solid rgba(56,189,248,0.3); }
    .verdict-HOLD { background: rgba(100,116,139,0.15); color: #94a3b8; border: 1px solid rgba(100,116,139,0.3); }
    .verdict-REDUCE { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.3); }
    .verdict-SELL { background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); }

    /* Target / SL */
    .target-val { font-family: 'JetBrains Mono', monospace; color: #10b981; font-size: 0.75rem; }
    .sl-val { font-family: 'JetBrains Mono', monospace; color: #ef4444; font-size: 0.75rem; }
    .na-val { color: #334155; }

    /* Upside */
    .upside-val { font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.8rem; }
    .upside-val.positive { color: #10b981; }
    .upside-val.negative { color: #ef4444; }

    /* R:R */
    .rr-val { font-family: 'JetBrains Mono', monospace; color: #94a3b8; font-size: 0.78rem; }
    .rr-val.good-rr { color: #10b981; }

    /* Sparkline */
    .mini-spark { width: 60px; height: 24px; display: block; }

    /* Footer */
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
  `]
})
export class PatternScreenerComponent implements OnInit, OnDestroy {

  // ---- Signals ----
  allPicks   = signal<PatternPick[]>([]);
  loading    = signal<boolean>(false);
  error      = signal<string | null>(null);
  lastUpdated = signal<string | null>(null);

  verdictFilter   = signal<VerdictFilter>('ALL');
  directionFilter = signal<DirectionFilter>('ALL');
  categoryFilter  = signal<CategoryFilter>('ALL');
  minUpside       = signal<number>(0);
  sortKey         = signal<SortKey>('upside_pct');

  // ---- Filter options ----
  verdicts: VerdictFilter[]    = ['ALL', 'BUY', 'ACCUMULATE', 'HOLD', 'REDUCE', 'SELL'];
  directions: DirectionFilter[] = ['ALL', 'Bullish', 'Bearish'];
  categories: CategoryFilter[]  = ['ALL', 'Moving Average', 'Reversal', 'Breakout', 'Accumulation', 'Candlestick', 'Classical Chart'];

  // ---- Computed: filtered + sorted picks ----
  filteredPicks = computed(() => {
    let picks = [...this.allPicks()];

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
      picks = picks.filter(p => p.upside_pct >= this.minUpside());
    }

    const key = this.sortKey();
    picks.sort((a, b) => {
      if (key === 'timestamp') return b.timestamp.localeCompare(a.timestamp);
      return (b[key] as number) - (a[key] as number);
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

  async loadPicks(): Promise<void> {
    // Serve cached picks instantly (filters/sorts run client-side); refresh silently in background.
    const cached = PatternScreenerComponent.cache;
    if (cached && this.allPicks().length === 0) {
      this.allPicks.set(cached.picks);
      this.lastUpdated.set(cached.at);
    }
    const silent = this.allPicks().length > 0;
    if (!silent) this.loading.set(true);
    this.error.set(null);
    try {
      const resp = await ApiService.getPatternPicks(0);
      const picks = resp.picks ?? [];
      const at = new Date().toLocaleTimeString('en-IN');
      PatternScreenerComponent.cache = { picks, at };
      this.allPicks.set(picks);
      this.lastUpdated.set(at);
    } catch (err: any) {
      if (!silent) this.error.set(err?.message ?? 'Failed to load pattern data');
    } finally {
      this.loading.set(false);
    }
  }

  private static cache: { picks: PatternPick[]; at: string } | null = null;

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
    stocksStore.selectStock(adHoc);
  }

  // ---- Filter setters ----
  setVerdictFilter(v: VerdictFilter)     { this.verdictFilter.set(v); }
  setDirectionFilter(d: DirectionFilter) { this.directionFilter.set(d); }
  setCategoryFilter(c: CategoryFilter)   { this.categoryFilter.set(c); }
  setMinUpside(event: Event): void {
    this.minUpside.set(+(event.target as HTMLInputElement).value);
  }
  setSortKey(event: Event): void {
    this.sortKey.set((event.target as HTMLSelectElement).value as SortKey);
  }
  toggleSort(key: SortKey): void { this.sortKey.set(key); }

  // ---- Helpers ----
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
