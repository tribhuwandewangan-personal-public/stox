import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { apiService } from '../../core/services/api.service';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-sector-research',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="sector-page">
      <!-- Top Search & Action Bar -->
      <div class="sector-hero">
        <div>
          <h2 class="hero-title">🧭 Dynamic Sector &amp; Value-Chain Research</h2>
          <p class="hero-sub">
            Google Gemini decomposes any industry into value-chain components (Market Leaders, Bottlenecks, Critical Beneficiaries)
            and stores them in SQLite &mdash; then Stox's deterministic Fundamental &amp; Technical engines rank the best stocks.
          </p>
        </div>

        <div class="search-bar">
          <input
            type="text"
            class="sector-input"
            [value]="sectorQuery()"
            (input)="onQueryInput($event)"
            (keyup.enter)="runResearch()"
            placeholder="e.g. Data Centers &amp; Power Grid, Indian Defence Electronics, Railway Electrification..."
          />
          <button class="btn-primary" [disabled]="isRunning() || !sectorQuery().trim()" (click)="runResearch()">
            {{ isRunning() ? '⏳ Researching...' : '🔬 Research Sector' }}
          </button>
        </div>
      </div>

      <!-- Missing API Key / Error Notice -->
      <div class="alert-banner warning" *ngIf="activeRun()?.status === 'missing_api_key'">
        <strong>⚠️ Gemini API Key Not Configured:</strong>
        {{ activeRun().error_message || 'Set GEMINI_API_KEY in .env or environment variables to enable LLM sector discovery.' }}
      </div>
      <div class="alert-banner error" *ngIf="activeRun()?.status === 'error' || errorMsg()">
        <strong>❌ Error:</strong> {{ errorMsg() || activeRun()?.error_message }}
      </div>

      <div class="sector-layout">
        <!-- Saved Research Runs (SQLite) -->
        <aside class="runs-sidebar">
          <div class="sidebar-head">Saved Research Runs ({{ runs().length }})</div>
          <div class="empty-runs" *ngIf="runs().length === 0">
            No sector runs saved yet. Enter a sector above to start.
          </div>
          <div
            class="run-item"
            *ngFor="let r of runs()"
            [class.active]="activeRun()?.id === r.id"
            (click)="selectRun(r.id)"
          >
            <div class="run-title">{{ r.normalized_sector || r.sector_query }}</div>
            <div class="run-meta">
              <span class="status-pill" [ngClass]="'st-' + r.status">{{ r.status }}</span>
              <span>{{ r.stock_count }} stocks</span>
              <button class="btn-del" title="Delete run" (click)="deleteRun(r.id, $event)">✕</button>
            </div>
          </div>
        </aside>

        <!-- Active Run Details -->
        <section class="run-detail" *ngIf="activeRun() as run">
          <div class="detail-head">
            <div>
              <h3>{{ run.normalized_sector || run.sector_query }}</h3>
              <div class="detail-meta">
                Model: <code>{{ run.model_used || 'gemini' }}</code> &bull;
                Stored in SQLite &bull;
                {{ run.stocks?.length || 0 }} value-chain companies
              </div>
            </div>
            <div class="detail-actions" *ngIf="run.stocks && run.stocks.length > 0">
              <button class="btn-secondary" [disabled]="isRescoring()" (click)="rescoreActiveRun()">
                {{ isRescoring() ? '⏳ Re-scoring...' : '⚡ Re-Score with Stox Quant' }}
              </button>
            </div>
          </div>

          <!-- Sector Overview -->
          <div class="overview-card" *ngIf="run.overview?.thesis">
            <div class="ov-thesis">{{ run.overview.thesis }}</div>
            <div class="bn-callout" *ngIf="run.overview.bottleneck_summary">
              <strong>🔒 Primary Value-Chain Chokepoint:</strong> {{ run.overview.bottleneck_summary }}
            </div>
            <div class="ov-grid">
              <div *ngIf="run.overview.capex_cycle_stage">
                <span class="ov-label">Capex Cycle:</span>
                <span class="ov-val">{{ run.overview.capex_cycle_stage }}</span>
              </div>
              <div *ngIf="run.overview.tam_and_growth">
                <span class="ov-label">TAM &amp; Growth:</span>
                <span class="ov-val">{{ run.overview.tam_and_growth }}</span>
              </div>
              <div *ngIf="run.overview.unit_economics">
                <span class="ov-label">Unit Economics:</span>
                <span class="ov-val">{{ run.overview.unit_economics }}</span>
              </div>
              <div *ngIf="run.overview.policy_and_regulatory_tailwinds?.length">
                <span class="ov-label">Policy Tailwinds:</span>
                <span class="ov-val">{{ run.overview.policy_and_regulatory_tailwinds.join(' • ') }}</span>
              </div>
              <div *ngIf="run.overview.demand_drivers?.length">
                <span class="ov-label">Drivers:</span>
                <span class="ov-val">{{ run.overview.demand_drivers.join(' • ') }}</span>
              </div>
              <div *ngIf="run.overview.key_risks?.length">
                <span class="ov-label">Risks:</span>
                <span class="ov-val">{{ run.overview.key_risks.join(' • ') }}</span>
              </div>
              <div *ngIf="run.overview.bear_case_triggers?.length">
                <span class="ov-label">Bear Triggers:</span>
                <span class="ov-val">{{ run.overview.bear_case_triggers.join(' • ') }}</span>
              </div>
            </div>
          </div>

          <!-- Value-Chain Components Breakdown -->
          <div class="section-title" *ngIf="run.components?.length">Value-Chain Component Breakdown</div>
          <div class="components-grid" *ngIf="run.components?.length">
            <div class="comp-card" *ngFor="let comp of run.components" [class.bottleneck-layer]="comp.is_bottleneck_layer">
              <div class="comp-head">
                <strong>{{ comp.name }}</strong>
                <div class="comp-badges">
                  <span class="pp-badge" *ngIf="comp.pricing_power">Pricing: {{ comp.pricing_power }}</span>
                  <span class="bn-badge" *ngIf="comp.is_bottleneck_layer">🔒 Bottleneck</span>
                </div>
              </div>
              <p class="comp-desc">{{ comp.description }}</p>
              <div class="comp-meta" *ngIf="comp.entry_barriers || comp.capacity_bottleneck_reason">
                <div *ngIf="comp.entry_barriers"><b>Barriers:</b> {{ comp.entry_barriers }}</div>
                <div *ngIf="comp.capacity_bottleneck_reason && comp.capacity_bottleneck_reason !== 'N/A'">
                  <b>Scarcity:</b> {{ comp.capacity_bottleneck_reason }}
                </div>
              </div>
              <div class="comp-companies">
                <div class="co-chip" *ngFor="let co of comp.companies" (click)="openStock(co.symbol)">
                  <div class="co-top">
                    <span class="co-sym">{{ co.symbol }}</span>
                    <span class="role-badge" [ngClass]="'role-' + co.role_tag">{{ roleLabel(co.role_tag) }}</span>
                  </div>
                  <div class="co-name">{{ co.company_name }}</div>
                  <div class="co-tags" *ngIf="co.moat_type || co.revenue_purity">
                    <span class="mini-tag" *ngIf="co.moat_type">{{ co.moat_type }}</span>
                    <span class="mini-tag purity" *ngIf="co.revenue_purity">{{ co.revenue_purity }}</span>
                  </div>
                  <div class="co-rat">{{ co.rationale }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- Ranked Stocks Table (Existing Stox Fundamental + Technical Engines) -->
          <div class="section-title" *ngIf="run.stocks?.length">
            Best Stocks Ranked by Stox Fundamental &amp; Technical Engines
          </div>
          <div class="table-wrap" *ngIf="run.stocks?.length">
            <table class="stocks-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Symbol</th>
                  <th>Component</th>
                  <th>Role</th>
                  <th>Verdict</th>
                  <th>Composite</th>
                  <th>Fundamental</th>
                  <th>Technical</th>
                  <th>Price</th>
                </tr>
              </thead>
              <tbody>
                <tr *ngFor="let st of run.stocks; let i = index" (click)="openStock(st.symbol)" class="clickable-row">
                  <td>{{ i + 1 }}</td>
                  <td>
                    <strong>{{ st.symbol }}</strong>
                    <div class="sub-name">{{ st.company_name }}</div>
                  </td>
                  <td>{{ st.component_name }}</td>
                  <td><span class="role-badge" [ngClass]="'role-' + st.role_tag">{{ roleLabel(st.role_tag) }}</span></td>
                  <td><span class="verdict-pill">{{ st.verdict }}</span></td>
                  <td><strong>{{ st.composite_score != null ? (st.composite_score | number:'1.1-1') : 'N/A' }}</strong></td>
                  <td>{{ st.fundamental_score != null ? (st.fundamental_score | number:'1.1-1') : 'N/A' }}</td>
                  <td>{{ st.technical_score != null ? (st.technical_score | number:'1.1-1') : 'N/A' }}</td>
                  <td>{{ st.quant_snapshot?.last_price != null ? ('Rs.' + st.quant_snapshot.last_price) : 'N/A' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  `,
  styles: [`
    .sector-page { padding: 18px 24px; color: #e2e8f0; max-width: 1480px; margin: 0 auto; }
    .sector-hero {
      display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px;
      background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 12px; padding: 16px 20px; margin-bottom: 16px;
    }
    .hero-title { margin: 0 0 4px; font-size: 1.15rem; color: #f8fafc; }
    .hero-sub { margin: 0; font-size: 0.78rem; color: #94a3b8; max-width: 680px; }
    .search-bar { display: flex; gap: 8px; flex: 1; min-width: 320px; max-width: 560px; }
    .sector-input {
      flex: 1; background: rgba(2, 6, 23, 0.7); border: 1px solid rgba(148, 163, 184, 0.25);
      color: #f8fafc; padding: 9px 12px; border-radius: 8px; font-size: 0.82rem;
    }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border: none;
      padding: 9px 16px; border-radius: 8px; font-weight: 600; font-size: 0.8rem; cursor: pointer;
    }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-secondary {
      background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4);
      color: #7dd3fc; padding: 7px 12px; border-radius: 8px; font-weight: 600; font-size: 0.76rem; cursor: pointer;
    }
    .alert-banner { padding: 10px 14px; border-radius: 8px; font-size: 0.8rem; margin-bottom: 14px; }
    .alert-banner.warning { background: rgba(245, 158, 11, 0.14); border: 1px solid rgba(245, 158, 11, 0.4); color: #fcd34d; }
    .alert-banner.error { background: rgba(239, 68, 68, 0.14); border: 1px solid rgba(239, 68, 68, 0.4); color: #fca5a5; }
    .sector-layout { display: grid; grid-template-columns: 260px 1fr; gap: 16px; align-items: start; }
    @media (max-width: 960px) { .sector-layout { grid-template-columns: 1fr; } }
    .runs-sidebar {
      background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px; padding: 12px;
    }
    .sidebar-head { font-size: 0.78rem; font-weight: 700; color: #94a3b8; margin-bottom: 10px; text-transform: uppercase; }
    .empty-runs { font-size: 0.76rem; color: #64748b; }
    .run-item {
      padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 6px;
      border: 1px solid transparent; background: rgba(255, 255, 255, 0.02);
    }
    .run-item.active, .run-item:hover { background: rgba(56, 189, 248, 0.1); border-color: rgba(56, 189, 248, 0.3); }
    .run-title { font-size: 0.82rem; font-weight: 600; color: #f1f5f9; margin-bottom: 4px; }
    .run-meta { display: flex; align-items: center; justify-content: space-between; font-size: 0.7rem; color: #94a3b8; }
    .status-pill { padding: 1px 6px; border-radius: 4px; font-weight: 600; text-transform: uppercase; font-size: 0.65rem; }
    .st-ready { background: rgba(16, 185, 129, 0.18); color: #34d399; }
    .st-missing_api_key { background: rgba(245, 158, 11, 0.18); color: #fbbf24; }
    .st-error { background: rgba(239, 68, 68, 0.18); color: #f87171; }
    .btn-del { background: transparent; border: none; color: #64748b; cursor: pointer; font-size: 0.75rem; }
    .btn-del:hover { color: #f87171; }
    .run-detail {
      background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px; padding: 16px 20px;
    }
    .detail-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
    .detail-head h3 { margin: 0; font-size: 1.1rem; color: #f8fafc; }
    .detail-meta { font-size: 0.74rem; color: #94a3b8; margin-top: 2px; }
    .overview-card {
      background: rgba(2, 6, 23, 0.45); border: 1px solid rgba(56, 189, 248, 0.18);
      border-radius: 8px; padding: 12px; margin-bottom: 16px; font-size: 0.8rem;
    }
    .ov-thesis { color: #e2e8f0; margin-bottom: 8px; line-height: 1.45; }
    .bn-callout {
      background: rgba(245, 158, 11, 0.12); border: 1px solid rgba(245, 158, 11, 0.35);
      color: #fde68a; padding: 8px 10px; border-radius: 6px; font-size: 0.76rem; margin-bottom: 8px;
    }
    .ov-grid { display: flex; flex-direction: column; gap: 4px; font-size: 0.75rem; color: #94a3b8; }
    .ov-label { color: #7dd3fc; font-weight: 600; margin-right: 6px; }
    .section-title { font-size: 0.85rem; font-weight: 700; color: #7dd3fc; margin: 14px 0 10px; text-transform: uppercase; letter-spacing: 0.4px; }
    .components-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin-bottom: 18px; }
    .comp-card {
      background: rgba(2, 6, 23, 0.5); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 8px; padding: 12px;
    }
    .comp-card.bottleneck-layer { border-color: rgba(245, 158, 11, 0.4); }
    .comp-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; }
    .comp-badges { display: inline-flex; gap: 4px; align-items: center; flex-wrap: wrap; }
    .pp-badge { font-size: 0.64rem; background: rgba(56, 189, 248, 0.15); color: #7dd3fc; padding: 2px 6px; border-radius: 4px; font-weight: 600; }
    .bn-badge { font-size: 0.65rem; background: rgba(245, 158, 11, 0.2); color: #fbbf24; padding: 2px 6px; border-radius: 4px; font-weight: 700; }
    .comp-desc { font-size: 0.74rem; color: #94a3b8; margin: 0 0 8px; }
    .comp-meta { font-size: 0.7rem; color: #cbd5e1; background: rgba(15, 23, 42, 0.6); padding: 6px 8px; border-radius: 6px; margin-bottom: 8px; display: flex; flex-direction: column; gap: 3px; }
    .comp-companies { display: flex; flex-direction: column; gap: 8px; }
    .co-chip {
      background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(255, 255, 255, 0.07);
      border-radius: 6px; padding: 8px; cursor: pointer;
    }
    .co-chip:hover { border-color: rgba(56, 189, 248, 0.4); }
    .co-top { display: flex; justify-content: space-between; align-items: center; }
    .co-sym { font-weight: 700; color: #38bdf8; font-size: 0.8rem; }
    .co-name { font-size: 0.72rem; color: #cbd5e1; margin: 2px 0; }
    .co-tags { display: flex; gap: 4px; flex-wrap: wrap; margin: 4px 0; }
    .mini-tag { font-size: 0.62rem; padding: 1px 5px; border-radius: 4px; background: rgba(148, 163, 184, 0.14); color: #cbd5e1; }
    .mini-tag.purity { background: rgba(16, 185, 129, 0.14); color: #6ee7b7; }
    .co-rat { font-size: 0.7rem; color: #94a3b8; }
    .role-badge { font-size: 0.65rem; padding: 2px 6px; border-radius: 4px; font-weight: 700; }
    .role-bottleneck { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    .role-critical_beneficiary { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }
    .role-market_leader { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .role-challenger { background: rgba(56, 189, 248, 0.2); color: #7dd3fc; }
    .table-wrap { overflow-x: auto; }
    .stocks-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; }
    .stocks-table th, .stocks-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); text-align: left; }
    .stocks-table th { color: #94a3b8; font-size: 0.72rem; text-transform: uppercase; }
    .clickable-row { cursor: pointer; }
    .clickable-row:hover { background: rgba(56, 189, 248, 0.08); }
    .sub-name { font-size: 0.68rem; color: #94a3b8; }
    .verdict-pill { padding: 2px 7px; border-radius: 4px; background: rgba(56, 189, 248, 0.15); color: #7dd3fc; font-weight: 600; font-size: 0.7rem; }
  `]
})
export class SectorResearchComponent implements OnInit {
  sectorQuery = signal<string>('');
  runs = signal<any[]>([]);
  activeRun = signal<any | null>(null);
  isRunning = signal<boolean>(false);
  isRescoring = signal<boolean>(false);
  errorMsg = signal<string>('');

  ngOnInit(): void {
    this.loadRuns();
  }

  onQueryInput(e: Event): void {
    this.sectorQuery.set((e.target as HTMLInputElement).value);
  }

  async loadRuns(): Promise<void> {
    try {
      const res = await apiService.listSectorResearch();
      const list = res.runs || [];
      this.runs.set(list);
      if (list.length > 0 && !this.activeRun()) {
        await this.selectRun(list[0].id);
      }
    } catch (e: any) {
      this.errorMsg.set(e?.message || 'Failed to load sector research runs');
    }
  }

  async runResearch(): Promise<void> {
    const q = this.sectorQuery().trim();
    if (!q || this.isRunning()) return;
    this.isRunning.set(true);
    this.errorMsg.set('');
    try {
      const result = await apiService.runSectorResearch(q);
      this.activeRun.set(result);
      await this.loadRuns();
    } catch (e: any) {
      this.errorMsg.set(e?.message || 'Sector research failed');
    } finally {
      this.isRunning.set(false);
    }
  }

  async selectRun(runId: number): Promise<void> {
    try {
      const run = await apiService.getSectorResearch(runId);
      this.activeRun.set(run);
    } catch (e: any) {
      this.errorMsg.set(e?.message || 'Failed to load run details');
    }
  }

  async rescoreActiveRun(): Promise<void> {
    const run = this.activeRun();
    if (!run || this.isRescoring()) return;
    this.isRescoring.set(true);
    this.errorMsg.set('');
    try {
      const updated = await apiService.rescoreSectorResearch(run.id);
      this.activeRun.set(updated);
      await this.loadRuns();
    } catch (e: any) {
      this.errorMsg.set(e?.message || 'Re-score failed');
    } finally {
      this.isRescoring.set(false);
    }
  }

  async deleteRun(runId: number, event: Event): Promise<void> {
    event.stopPropagation();
    try {
      await apiService.deleteSectorResearch(runId);
      if (this.activeRun()?.id === runId) {
        this.activeRun.set(null);
      }
      await this.loadRuns();
    } catch (e: any) {
      this.errorMsg.set(e?.message || 'Delete failed');
    }
  }

  openStock(symbol: string): void {
    if (symbol) {
      stocksStore.selectSymbol(symbol);
    }
  }

  roleLabel(role: string): string {
    switch (role) {
      case 'market_leader': return '👑 Leader';
      case 'bottleneck': return '🔒 Bottleneck';
      case 'critical_beneficiary': return '⚡ Critical Beneficiary';
      default: return 'Challenger';
    }
  }
}
