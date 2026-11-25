/**
 * Pre-Breakout Bullish Radar:
 * Surfaces stocks currently FORMING bullish patterns (VCP, Saucer, Inverse H&S, Cup & Handle, Bull Flag, Squeeze)
 * BEFORE breakout — excluding extended/late entries — with explicit Buy-Above Trigger, Entry Window, and 4-Week Target.
 *
 * ⚠️ ADVISORY ONLY — No order placement, no investment advice.
 */

import { Component, OnInit, computed, effect, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { PatternPick, Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';

type ScopeMode = 'universe' | 'monitored';
type StageFilter = 'ALL' | 'IMMINENT_BREAKOUT' | 'FORMING_PRE_BREAKOUT' | 'FRESH_BREAKOUT';

@Component({
  selector: 'app-pre-breakout-radar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="pb-wrapper">
      <div class="pb-card">
        <div class="pb-header">
          <div class="pb-title-block">
            <span class="pb-icon">🚀</span>
            <div>
              <div class="pb-heading">
                Pre-Breakout Bullish Radar (4-Week Projections)
                <span class="pb-count" *ngIf="!loading()">{{ filteredPicks().length }} forming setups</span>
              </div>
              <div class="pb-sub">
                Stocks forming patterns <strong>before</strong> breakout &bull; Extended/late rallies excluded &bull; Buy-above trigger &amp; 4-week price projection
              </div>
            </div>
          </div>

          <div class="pb-controls">
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
            <button class="pb-toggle-btn" (click)="collapsed.update(v => !v)">
              {{ collapsed() ? '▼ Show' : '▲ Hide' }}
            </button>
          </div>
        </div>

        <div class="pb-body" *ngIf="!collapsed()">
          <!-- Stage Filter Bar -->
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
          </div>

          <div class="pb-loading" *ngIf="loading() && allPicks().length === 0">
            Scanning {{ scope() === 'monitored' ? 'all monitored NSE' : 'universe' }} charts for pre-breakout formations…
          </div>

          <div class="pb-empty" *ngIf="!loading() && filteredPicks().length === 0">
            No unextended pre-breakout bullish setups match this filter right now. Try switching to <strong>All NSE Monitored</strong>.
          </div>

          <div class="table-wrap" *ngIf="filteredPicks().length > 0">
            <table class="pb-table">
              <thead>
                <tr>
                  <th class="col-num">#</th>
                  <th>SYMBOL</th>
                  <th>LTP</th>
                  <th>FORMING PATTERN &amp; STAGE</th>
                  <th>CLOSE ABOVE (TRIGGER)</th>
                  <th>4-WEEK TARGET</th>
                  <th>STOP LOSS</th>
                  <th>R:R</th>
                  <th>ACTIONABLE PROJECTION</th>
                </tr>
              </thead>
              <tbody>
                @for (p of filteredPicks().slice(0, 20); track p.symbol; let i = $index) {
                  <tr (click)="openDetail(p)">
                    <td class="col-num">{{ i + 1 }}</td>
                    <td>
                      <button class="sym-pill">{{ p.symbol }} ↗</button>
                    </td>
                    <td class="col-mono">Rs. {{ p.last_price | number:'1.2-2' }}</td>
                    <td>
                      <div class="pat-cell">
                        <span class="pat-name">{{ p.pattern_name }}</span>
                        <span class="stage-badge" [ngClass]="stageClass(p.setup_stage)">
                          {{ stageLabel(p.setup_stage, p.entry_window) }}
                        </span>
                      </div>
                    </td>
                    <td class="col-mono">
                      <div class="trigger-cell">
                        <strong class="accent-sky">Rs. {{ (p.breakout_trigger ?? p.last_price) | number:'1.2-2' }}</strong>
                        <small class="dist-sub" *ngIf="p.distance_to_breakout_pct !== undefined && p.distance_to_breakout_pct !== null">
                          {{ p.distance_to_breakout_pct > 0 ? ('+' + p.distance_to_breakout_pct.toFixed(1) + '% to trigger') : (p.distance_to_breakout_pct.toFixed(1) + '% vs pivot') }}
                        </small>
                      </div>
                    </td>
                    <td class="col-mono">
                      <div class="target-cell">
                        <strong class="accent-green">Rs. {{ (p.week4_target ?? p.target_price ?? 0) | number:'1.2-2' }}</strong>
                        <small class="upside-sub" *ngIf="p.week4_upside_pct !== undefined && p.week4_upside_pct !== null">
                          +{{ p.week4_upside_pct | number:'1.1-1' }}% in 4W
                        </small>
                      </div>
                    </td>
                    <td class="col-mono accent-red">
                      Rs. {{ (p.stop_loss ?? 0) | number:'1.2-2' }}
                    </td>
                    <td>
                      <span class="rr-pill">{{ p.risk_reward | number:'1.1-1' }}x</span>
                    </td>
                    <td class="col-proj">
                      {{ p.projection_summary || 'Forming setup — watch breakout trigger.' }}
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <div class="pb-tip">
            💡 <strong>Methodology:</strong> Conditional algorithmic setups — bullish confirmation requires a <em>daily close above</em> the Pivot/Trigger level with volume; invalidation is below Stop Loss. ATR-bounded 4-week projections are quantitative research estimates, not investment advice.
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .pb-wrapper {
      padding: 12px 20px 0 20px;
    }

    .pb-card {
      background: linear-gradient(155deg, rgba(16, 28, 48, 0.85), rgba(13, 20, 36, 0.9));
      border: 1px solid rgba(16, 185, 129, 0.35);
      border-radius: 12px;
      padding: 14px 18px;
      backdrop-filter: blur(12px);
    }

    .pb-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }

    .pb-title-block {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .pb-icon { font-size: 1.4rem; }

    .pb-heading {
      font-family: 'Outfit', sans-serif;
      font-size: 0.98rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .pb-count {
      background: rgba(16, 185, 129, 0.16);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: #34d399;
      padding: 1px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 700;
    }

    .pb-sub {
      font-size: 0.72rem;
      color: #94a3b8;
    }

    .pb-controls {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
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

    .pb-btn-refresh, .pb-toggle-btn {
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #38bdf8;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 0.73rem;
      font-weight: 600;
      cursor: pointer;
    }

    .pb-body {
      margin-top: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .stage-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
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

    .table-wrap { overflow-x: auto; }

    .pb-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.77rem;
    }

    .pb-table th {
      text-align: left;
      padding: 8px 10px;
      color: #64748b;
      font-size: 0.67rem;
      font-weight: 700;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      white-space: nowrap;
    }

    .pb-table td {
      padding: 9px 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      vertical-align: middle;
      color: #e2e8f0;
    }

    .pb-table tr:hover td {
      background: rgba(16, 185, 129, 0.06);
      cursor: pointer;
    }

    .col-num { color: #64748b; font-size: 0.7rem; width: 28px; }
    .col-mono { font-family: 'JetBrains Mono', monospace; white-space: nowrap; }
    .accent-sky { color: #38bdf8; }
    .accent-green { color: #34d399; }
    .accent-red { color: #f87171; }

    .sym-pill {
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.35);
      color: #34d399;
      padding: 3px 8px;
      border-radius: 6px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.74rem;
      cursor: pointer;
    }

    .pat-cell, .trigger-cell, .target-cell {
      display: flex;
      flex-direction: column;
      gap: 2px;
    }

    .pat-name { font-weight: 600; color: #e2e8f0; font-size: 0.74rem; }
    .dist-sub { color: #94a3b8; font-size: 0.66rem; }
    .upside-sub { color: #10b981; font-size: 0.67rem; font-weight: 700; }

    .stage-badge {
      display: inline-block;
      width: fit-content;
      padding: 1px 7px;
      border-radius: 999px;
      font-size: 0.63rem;
      font-weight: 700;
    }

    .stage-imminent {
      background: rgba(245, 158, 11, 0.18);
      border: 1px solid rgba(245, 158, 11, 0.45);
      color: #fbbf24;
    }

    .stage-forming {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: #38bdf8;
    }

    .stage-fresh {
      background: rgba(16, 185, 129, 0.16);
      border: 1px solid rgba(16, 185, 129, 0.38);
      color: #34d399;
    }

    .rr-pill {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
      padding: 2px 8px;
      border-radius: 10px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.71rem;
    }

    .col-proj {
      min-width: 260px;
      max-width: 420px;
      font-size: 0.72rem;
      color: #cbd5e1;
      line-height: 1.4;
    }

    .pb-tip {
      font-size: 0.71rem;
      color: #94a3b8;
      background: rgba(16, 185, 129, 0.06);
      border-left: 2px solid #10b981;
      padding: 6px 10px;
      border-radius: 4px;
      line-height: 1.4;
    }

    @media (max-width: 768px) {
      .pb-wrapper { padding: 8px 12px 0 12px; }
    }
  `]
})
export class PreBreakoutRadarComponent implements OnInit {
  collapsed = signal<boolean>(false);
  scope = signal<ScopeMode>('universe');
  highConviction = signal<boolean>(true);
  stageFilter = signal<StageFilter>('ALL');
  allPicks = signal<PatternPick[]>([]);
  loading = signal<boolean>(false);

  filteredPicks = computed(() => {
    const sf = this.stageFilter();
    const list = this.allPicks();
    if (sf === 'ALL') return list;
    return list.filter(p => p.setup_stage === sf);
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
