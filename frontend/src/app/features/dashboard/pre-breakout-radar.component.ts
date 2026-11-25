/**
 * Pre-Breakout Bullish Radar:
 * Surfaces stocks currently FORMING bullish patterns (VCP, Saucer, Inverse H&S, Cup & Handle, Bull Flag, Squeeze)
 * BEFORE breakout — excluding extended/late entries — with explicit Buy-Above Trigger, Entry Window, and 4-Week Target.
 *
 * ⚠️ ADVISORY ONLY — No order placement, no investment advice.
 */

import { Component, OnInit, TemplateRef, ViewChild, computed, effect, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { PatternPick, Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

type ScopeMode = 'universe' | 'monitored';
type StageFilter = 'ALL' | 'IMMINENT_BREAKOUT' | 'FORMING_PRE_BREAKOUT' | 'FRESH_BREAKOUT';

@Component({
  selector: 'app-pre-breakout-radar',
  standalone: true,
  imports: [CommonModule, StoxGridComponent],
  template: `
    <div class="stox-banner-wrap">
      <div class="stox-banner-card stox-banner-card--emerald">
        <div class="stox-banner-header">
          <div class="stox-banner-title-block">
            <span class="stox-banner-icon">🚀</span>
            <div>
              <div class="stox-banner-heading">
                Pre-Breakout Bullish Radar (4-Week Projections)
                <span class="pb-count" *ngIf="!loading()">{{ filteredPicks().length }} forming setups</span>
              </div>
              <div class="stox-banner-sub">
                Stocks forming patterns <strong>before</strong> breakout &bull; Extended/late rallies excluded &bull; Buy-above trigger &amp; 4-week price projection
              </div>
            </div>
          </div>

          <div class="stox-banner-controls">
            <button class="pb-pill" [class.active]="highConviction()" (click)="toggleHighConviction()" title="Show only positive-expectancy patterns (Darvas Box, Double Bottom, Falling Wedge, VCP, Inverse H&S Forming, Saucer)">
              🎯 High-Conviction Only
            </button>
            <div class="pill-group">
              <button class="pb-pill" [class.active]="scope() === 'universe'" (click)="setScope('universe')">
                Active Universe
              </button>
              <button class="pb-pill" [class.active]="scope() === 'monitored'" (click)="setScope('monitored')">
                All NSE Monitored
              </button>
            </div>
            <button class="pb-btn-refresh" (click)="refresh()" [disabled]="loading()">
              {{ loading() ? '⏳' : '↻' }} Refresh
            </button>
            <button class="stox-banner-toggle" (click)="collapsed.update(v => !v)">
              {{ collapsed() ? '▼ Show' : '▲ Hide' }}
            </button>
          </div>
        </div>

        <div class="stox-banner-body" *ngIf="!collapsed()">
          <!-- Stage Filter + Search Bar -->
          <div class="stage-bar">
            <button class="stage-pill" [class.active]="stageFilter() === 'ALL'" (click)="stageFilter.set('ALL')">
              All Pre-Breakout ({{ allPicks().length }})
            </button>
            <button class="stage-pill imminent" [class.active]="stageFilter() === 'IMMINENT_BREAKOUT'" (click)="stageFilter.set('IMMINENT_BREAKOUT')">
              ⚡ Near Pivot (Watch Close) ({{ countStage('IMMINENT_BREAKOUT') }})
            </button>
            <button class="stage-pill forming" [class.active]="stageFilter() === 'FORMING_PRE_BREAKOUT'" (click)="stageFilter.set('FORMING_PRE_BREAKOUT')">
              ⏳ Forming Setup (2–5d) ({{ countStage('FORMING_PRE_BREAKOUT') }})
            </button>
            <button class="stage-pill fresh" [class.active]="stageFilter() === 'FRESH_BREAKOUT'" (click)="stageFilter.set('FRESH_BREAKOUT')">
              ✅ Confirmed Close &gt; Pivot ({{ countStage('FRESH_BREAKOUT') }})
            </button>

            <div class="pb-search-wrap">
              <input
                type="text"
                class="pb-search-input"
                [value]="searchQuery()"
                (input)="onSearch($event)"
                placeholder="Filter symbol / pattern…"
              />
              <button class="pb-search-clear" *ngIf="searchQuery()" (click)="searchQuery.set('')" title="Clear search">✕</button>
            </div>
          </div>

          <div class="pb-loading" *ngIf="loading() && allPicks().length === 0">
            Scanning {{ scope() === 'monitored' ? 'all monitored NSE' : 'universe' }} charts for pre-breakout formations…
          </div>

          <div class="pb-empty" *ngIf="!loading() && filteredPicks().length === 0">
            No unextended pre-breakout bullish setups match this filter right now. Try switching to <strong>All NSE Monitored</strong>.
          </div>

          <div *ngIf="filteredPicks().length > 0">
            <app-stox-grid
              [data]="filteredPicks().slice(0, 50)"
              [columns]="gridColumns()"
              (rowClick)="openDetail($event)"
            ></app-stox-grid>
            <div class="pb-limit-note" *ngIf="filteredPicks().length > 50">
              Showing top 50 of {{ filteredPicks().length }} matching setups. Open <strong>Pattern Screener</strong> for the full list.
            </div>
          </div>

          <div class="stox-banner-tip stox-banner-tip--emerald">
            💡 <strong>Methodology:</strong> Conditional algorithmic setups — bullish confirmation requires a <em>daily close above</em> the Pivot/Trigger level with volume; invalidation is below Stop Loss. ATR-bounded 4-week projections are quantitative research estimates, not investment advice.
          </div>
        </div>
      </div>
    </div>

    <ng-template #idxTpl let-i="index"><span class="col-num">{{ i + 1 }}</span></ng-template>
    <ng-template #symTpl let-p><button class="sym-pill sym-pill--green">{{ p.symbol }} ↗</button></ng-template>
    <ng-template #ltpTpl let-p><span class="col-mono ltp-bold">Rs. {{ p.last_price | number:'1.2-2' }}</span></ng-template>
    <ng-template #patTpl let-p>
      <div class="pat-cell">
        <span class="pat-name">{{ p.pattern_name }}</span>
        <span class="stage-badge" [ngClass]="stageClass(p.setup_stage)">
          {{ stageLabel(p.setup_stage, p.entry_window) }}
        </span>
      </div>
    </ng-template>
    <ng-template #scoreTpl let-p>
      <span class="score-pill" [class.high-score]="pickScore(p) >= 75" [title]="(p.forming_evidence || []).join(' • ')">
        {{ pickScore(p) | number:'1.0-0' }}
      </span>
    </ng-template>
    <ng-template #trigTpl let-p>
      <div class="trigger-cell col-mono">
        <span class="trig-chip">Rs. {{ (p.breakout_trigger ?? p.last_price) | number:'1.2-2' }}</span>
        <small class="dist-sub"
               [class.dist-imminent]="p.distance_to_breakout_pct !== undefined && p.distance_to_breakout_pct !== null && p.distance_to_breakout_pct > 0 && p.distance_to_breakout_pct <= 1.5"
               *ngIf="p.distance_to_breakout_pct !== undefined && p.distance_to_breakout_pct !== null">
          {{ p.distance_to_breakout_pct > 0 ? ('+' + p.distance_to_breakout_pct.toFixed(1) + '% to trigger') : (p.distance_to_breakout_pct.toFixed(1) + '% vs pivot') }}
        </small>
      </div>
    </ng-template>
    <ng-template #tgtTpl let-p>
      <div class="target-cell col-mono" [title]="p.full_pattern_target ? ('Full Pattern Target: Rs. ' + p.full_pattern_target.toFixed(2)) : ''">
        <strong class="accent-green">Rs. {{ (p.week4_target ?? p.target_price ?? 0) | number:'1.2-2' }}</strong>
        <span class="upside-pill" *ngIf="p.week4_upside_pct !== undefined && p.week4_upside_pct !== null">
          +{{ p.week4_upside_pct | number:'1.1-1' }}% in 4W
        </span>
      </div>
    </ng-template>
    <ng-template #slTpl let-p><span class="col-mono sl-chip">Rs. {{ (p.stop_loss ?? 0) | number:'1.2-2' }}</span></ng-template>
    <ng-template #rrTpl let-p><span class="rr-pill">{{ p.risk_reward | number:'1.1-1' }}x</span></ng-template>
    <ng-template #projTpl let-p>
      <div class="proj-note" [title]="p.projection_summary || ''">
        <div class="proj-clamp">{{ p.projection_summary || 'Forming setup — watch breakout trigger.' }}</div>
        <div class="micro-tags" *ngIf="p.rsi_14 != null || p.rvol != null || p.up_down_vol_ratio != null || p.retest_hold_confirmed || p.confirmation_status === 'INTRADAY_CROSS' || p.regime_ok === false">
          <span class="micro-tag" *ngIf="p.rsi_14 != null">RSI {{ p.rsi_14 | number:'1.0-0' }}</span>
          <span class="micro-tag" [class.micro-tag--good]="(p.rvol ?? 0) >= 1.5" *ngIf="p.rvol != null">
            Vol {{ p.rvol | number:'1.1-1' }}x
          </span>
          <span class="micro-tag" [class.micro-tag--good]="(p.up_down_vol_ratio ?? 0) >= 1.2" *ngIf="p.up_down_vol_ratio != null">
            U/D {{ p.up_down_vol_ratio | number:'1.1-1' }}x
          </span>
          <span class="micro-tag micro-tag--good" *ngIf="p.retest_hold_confirmed">
            {{ p.confirmation_status === 'RETEST_HOLD' ? '✓ Retest Hold' : '✓ 2D Hold' }}
          </span>
          <span class="micro-tag micro-tag--warn" *ngIf="p.confirmation_status === 'INTRADAY_CROSS'">Await Close</span>
          <span class="micro-tag micro-tag--warn" *ngIf="p.regime_ok === false">⚠ Weak Sector/Mkt</span>
        </div>
      </div>
    </ng-template>
    <ng-template #sparkTpl let-p>
      <svg class="mini-spark" viewBox="0 0 60 24" preserveAspectRatio="none" *ngIf="p.sparkline?.length >= 2">
        <polyline
          [attr.points]="sparkPoints(p.sparkline)"
          fill="none"
          stroke="#10b981"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"/>
      </svg>
    </ng-template>
  `,
  styles: [`
    .pb-count {
      background: rgba(16, 185, 129, 0.16);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: #34d399;
      padding: 1px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 700;
    }

    .pill-group {
      display: flex;
      gap: 4px;
      background: rgba(255, 255, 255, 0.04);
      padding: 3px;
      border-radius: 8px;
      border: 1px solid rgba(255, 255, 255, 0.08);
    }

    .pb-pill {
      background: transparent;
      border: none;
      color: #94a3b8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.72rem;
      font-weight: 600;
      cursor: pointer;
    }

    .pb-pill.active {
      background: rgba(56, 189, 248, 0.18);
      color: #38bdf8;
    }

    .pb-btn-refresh {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #38bdf8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.73rem;
      font-weight: 600;
      cursor: pointer;
    }

    .stage-bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 6px;
    }

    .pb-search-wrap {
      margin-left: auto;
      position: relative;
      display: flex;
      align-items: center;
    }

    .pb-search-input {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #e2e8f0;
      padding: 4px 24px 4px 10px;
      border-radius: 999px;
      font-size: 0.72rem;
      width: 190px;
    }

    .pb-search-clear {
      position: absolute;
      right: 6px;
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 0.7rem;
      padding: 0 4px;
      cursor: pointer;
    }

    .pb-limit-note {
      margin-top: 6px;
      font-size: 0.7rem;
      color: #94a3b8;
      text-align: right;
    }

    .stage-pill {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
      cursor: pointer;
    }

    .stage-pill.active {
      background: rgba(16, 185, 129, 0.16);
      border-color: rgba(16, 185, 129, 0.45);
      color: #34d399;
    }

    .pb-loading, .pb-empty {
      padding: 18px;
      text-align: center;
      color: #94a3b8;
      font-size: 0.8rem;
      background: rgba(255, 255, 255, 0.02);
      border-radius: 8px;
    }

    :host-context([data-theme='light']) .pill-group {
      background: #f1f5f9;
      border-color: #cbd5e1;
    }
    :host-context([data-theme='light']) .pb-pill,
    :host-context([data-theme='light']) .stage-pill {
      color: #475569;
      background: #f8fafc;
      border-color: #cbd5e1;
    }
    :host-context([data-theme='light']) .pb-pill.active {
      background: #e0f2fe;
      color: #0284c7;
    }
    :host-context([data-theme='light']) .stage-pill.active {
      background: #dcfce7;
      border-color: #10b981;
      color: #047857;
    }
    :host-context([data-theme='light']) .pb-btn-refresh {
      background: #f8fafc;
      border-color: #cbd5e1;
      color: #0284c7;
    }
    :host-context([data-theme='light']) .pb-loading,
    :host-context([data-theme='light']) .pb-empty {
      background: #f8fafc;
      color: #475569;
    }
    :host-context([data-theme='light']) .pb-search-input {
      background: #ffffff;
      border-color: #cbd5e1;
      color: #0f172a;
    }
  `]
})
export class PreBreakoutRadarComponent implements OnInit {
  collapsed = signal<boolean>(false);
  scope = signal<ScopeMode>('universe');
  highConviction = signal<boolean>(true);
  stageFilter = signal<StageFilter>('ALL');
  searchQuery = signal<string>('');
  allPicks = signal<PatternPick[]>([]);
  loading = signal<boolean>(false);

  @ViewChild('idxTpl', { static: true }) idxTpl!: TemplateRef<any>;
  @ViewChild('symTpl', { static: true }) symTpl!: TemplateRef<any>;
  @ViewChild('ltpTpl', { static: true }) ltpTpl!: TemplateRef<any>;
  @ViewChild('patTpl', { static: true }) patTpl!: TemplateRef<any>;
  @ViewChild('scoreTpl', { static: true }) scoreTpl!: TemplateRef<any>;
  @ViewChild('trigTpl', { static: true }) trigTpl!: TemplateRef<any>;
  @ViewChild('tgtTpl', { static: true }) tgtTpl!: TemplateRef<any>;
  @ViewChild('slTpl', { static: true }) slTpl!: TemplateRef<any>;
  @ViewChild('rrTpl', { static: true }) rrTpl!: TemplateRef<any>;
  @ViewChild('projTpl', { static: true }) projTpl!: TemplateRef<any>;
  @ViewChild('sparkTpl', { static: true }) sparkTpl!: TemplateRef<any>;

  gridColumns = computed<StoxGridColumn<PatternPick>[]>(() => [
    { id: 'idx', header: '#', sortable: false, cellTemplate: this.idxTpl, cellClass: 'col-num' },
    { id: 'symbol', header: 'Symbol', accessorFn: r => r.symbol, cellTemplate: this.symTpl },
    { id: 'last_price', header: 'LTP', accessorFn: r => r.last_price ?? 0, cellTemplate: this.ltpTpl, cellClass: 'col-mono' },
    { id: 'pattern_name', header: 'Forming Pattern & Stage', accessorFn: r => r.pattern_name ?? '', cellTemplate: this.patTpl },
    { id: 'readiness_score', header: 'Score', accessorFn: r => this.pickScore(r), cellTemplate: this.scoreTpl },
    { id: 'breakout_trigger', header: 'Close Above (Trigger)', accessorFn: r => r.breakout_trigger ?? r.last_price ?? 0, cellTemplate: this.trigTpl, cellClass: 'col-mono' },
    { id: 'week4_upside_pct', header: '4-Week Target', accessorFn: r => r.week4_upside_pct ?? 0, cellTemplate: this.tgtTpl, cellClass: 'col-mono' },
    { id: 'stop_loss', header: 'Stop Loss', accessorFn: r => r.stop_loss ?? 0, cellTemplate: this.slTpl, cellClass: 'col-mono' },
    { id: 'risk_reward', header: 'R:R', accessorFn: r => r.risk_reward ?? 0, cellTemplate: this.rrTpl },
    { id: 'projection_summary', header: 'Actionable Projection', accessorFn: r => r.projection_summary ?? '', cellTemplate: this.projTpl, cellClass: 'col-proj' },
    { id: 'sparkline', header: 'Trend', sortable: false, cellTemplate: this.sparkTpl, headerClass: 'col-sparkline', cellClass: 'col-sparkline' },
  ]);

  filteredPicks = computed(() => {
    const sf = this.stageFilter();
    const q = this.searchQuery().trim().toLowerCase();
    let list = this.allPicks();
    if (sf !== 'ALL') {
      list = list.filter(p => p.setup_stage === sf);
    }
    if (q) {
      list = list.filter(p =>
        p.symbol.toLowerCase().includes(q) ||
        (p.name || '').toLowerCase().includes(q) ||
        (p.pattern_name || '').toLowerCase().includes(q)
      );
    }
    return list;
  });

  constructor() {
    effect(() => {
      const activeUniv = stocksStore.activeUniverse();
      if (this.scope() === 'universe') {
        this.loadData(activeUniv);
      }
    });
  }

  ngOnInit(): void {
    this.loadData(this.scope() === 'monitored' ? 'monitored' : stocksStore.activeUniverse());
  }

  setScope(mode: ScopeMode): void {
    this.scope.set(mode);
    const univ = mode === 'monitored' ? 'monitored' : stocksStore.activeUniverse();
    this.loadData(univ);
  }

  toggleHighConviction(): void {
    this.highConviction.update(v => !v);
    this.refresh();
  }

  refresh(): void {
    const univ = this.scope() === 'monitored' ? 'monitored' : stocksStore.activeUniverse();
    this.loadData(univ);
  }

  async loadData(universe: string): Promise<void> {
    this.loading.set(true);
    try {
      const resp = await ApiService.getPreBreakoutPicks(universe, 60, true, this.highConviction());
      this.allPicks.set(resp.picks ?? []);
    } catch {
      this.allPicks.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  countStage(stage: string): number {
    return this.allPicks().filter(p => p.setup_stage === stage).length;
  }

  onSearch(e: Event): void {
    this.searchQuery.set((e.target as HTMLInputElement).value);
  }

  pickScore(p: PatternPick): number {
    return p.readiness_score ?? p.quality_score ?? p.confidence_score ?? 0;
  }

  sparkPoints(prices?: number[]): string {
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

  stageClass(stage?: string): string {
    if (stage === 'IMMINENT_BREAKOUT') return 'stage-imminent';
    if (stage === 'FORMING_PRE_BREAKOUT') return 'stage-forming';
    return 'stage-fresh';
  }

  stageLabel(stage?: string, windowStr?: string): string {
    if (stage === 'IMMINENT_BREAKOUT') return '⚡ Near Pivot (Watch Close)';
    if (stage === 'FORMING_PRE_BREAKOUT') return '⏳ Forming Setup (2–5d)';
    if (stage === 'FRESH_BREAKOUT') return '✅ Confirmed Close > Pivot';
    return windowStr || 'Forming';
  }

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
          action_verdict: pick.action_verdict,
          confidence_score: pick.confidence_score,
          confidence_percentage: Math.round(pick.confidence_score),
          when_to_buy_entry: pick.entry_range,
          when_to_sell_target: pick.week4_target ? `Rs. ${pick.week4_target.toFixed(2)}` : (pick.target_price ? `Rs. ${pick.target_price.toFixed(2)}` : 'N/A'),
          stop_loss: pick.stop_loss ? `Rs. ${pick.stop_loss.toFixed(2)}` : 'N/A',
          risk_reward_ratio: pick.risk_reward ? `1:${pick.risk_reward.toFixed(2)}` : 'N/A',
          target_num: pick.week4_target ?? pick.target_price ?? undefined,
          stop_num: pick.stop_loss ?? undefined,
          chart_patterns: pick.pattern_name,
          key_rationale: pick.projection_summary,
        },
      },
      tech_output: null,
      patterns: [
        {
          name: pick.pattern_name,
          category: pick.pattern_category,
          direction: pick.direction,
          quality_score: pick.quality_score ?? Math.round(pick.confidence_score),
          status: pick.pattern_status,
          entry_trigger: pick.breakout_trigger ?? undefined,
          target_price: pick.week4_target ?? pick.target_price ?? undefined,
          stop_loss: pick.stop_loss ?? undefined,
          risk_reward_ratio: pick.risk_reward,
          setup_stage: pick.setup_stage,
          is_pre_breakout: pick.is_pre_breakout,
          is_late_entry: pick.is_late_entry,
          entry_window: pick.entry_window,
          breakout_trigger: pick.breakout_trigger,
          distance_to_breakout_pct: pick.distance_to_breakout_pct,
          week4_target: pick.week4_target,
          week4_upside_pct: pick.week4_upside_pct,
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
    stocksStore.selectStock(adHoc);
  }
}
