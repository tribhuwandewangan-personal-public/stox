import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { apiService } from '../../core/services/api.service';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-catalyst-radar',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="cat-page">
      <div class="cat-hero">
        <div>
          <h2 class="hero-title">⚡ Stock Catalyst Early-Warning System</h2>
          <p class="hero-sub">
            Detects primary-source NSE/BSE/PIB corporate announcements, scores financial impact vs TTM revenue (0&ndash;100),
            and fuses pre-breakout accumulation signals (52W High proximity, RVOL, Delivery %, SMA20/50).
          </p>
        </div>
        <div class="hero-actions">
          <button class="btn-primary" [disabled]="isScanning()" (click)="runScan()">
            {{ isScanning() ? '⏳ Scanning Feeds...' : '📡 Scan NSE / BSE / PIB' }}
          </button>
          <button class="btn-secondary" [disabled]="isBacktesting()" (click)="runBacktest()">
            {{ isBacktesting() ? '⏳ Backtesting...' : '📊 Historical Backtest' }}
          </button>
        </div>
      </div>

      <!-- Custom Announcement Scorer -->
      <div class="tester-card">
        <div class="tester-title">Test / Score Any Announcement Deterministically</div>
        <div class="tester-row">
          <input type="text" class="inp sym" [value]="testSym()" (input)="onSym($event)" placeholder="Symbol (e.g. JWL)" />
          <input type="text" class="inp title" [value]="testTitle()" (input)="onTitle($event)" placeholder="Announcement headline (e.g. Bagged Rs 500 Cr railway wagon order + JV)" />
          <input type="number" class="inp rev" [value]="testRev()" (input)="onRev($event)" placeholder="TTM Rev Cr (opt)" />
          <button class="btn-primary" [disabled]="!testSym().trim() || !testTitle().trim() || isAnalyzing()" (click)="analyzeCustom()">
            {{ isAnalyzing() ? '⏳ Scoring...' : '🎯 Score & Save' }}
          </button>
        </div>
      </div>

      <div class="status-msg" *ngIf="statusMsg()">{{ statusMsg() }}</div>

      <!-- Tier Filter Tabs -->
      <div class="filter-bar">
        <button class="tab-btn" [class.active]="tierFilter() === ''" (click)="setTier('')">All ({{ events().length }})</button>
        <button class="tab-btn tier-a" [class.active]="tierFilter() === 'A'" (click)="setTier('A')">Tier A (80+)</button>
        <button class="tab-btn tier-b" [class.active]="tierFilter() === 'B'" (click)="setTier('B')">Tier B (65–79)</button>
        <button class="tab-btn" [class.active]="tierFilter() === 'C'" (click)="setTier('C')">Tier C (&lt;65)</button>
      </div>

      <!-- Backtest Summary Panel -->
      <div class="bt-card" *ngIf="backtest() as bt">
        <div class="bt-head">
          <strong>📊 Historical Catalyst Backtest</strong>
          <span>{{ bt.total_evaluated }} evaluated against SQLite candles</span>
        </div>
        <div class="bt-metrics" *ngIf="bt.summary">
          <div><span>Avg 5D:</span> <b>{{ bt.summary.avg_ret_5d_pct ?? 'N/A' }}%</b></div>
          <div><span>Avg 20D:</span> <b>{{ bt.summary.avg_ret_20d_pct ?? 'N/A' }}%</b></div>
          <div><span>Avg 60D:</span> <b>{{ bt.summary.avg_ret_60d_pct ?? 'N/A' }}%</b></div>
          <div><span>+10% Breakout Hit Rate:</span> <b>{{ bt.summary.breakout_hit_rate_pct }}%</b></div>
          <div><span>Sustained Rally Rate:</span> <b>{{ bt.summary.sustained_rally_rate_pct }}%</b></div>
        </div>
      </div>

      <!-- Catalyst Feed -->
      <div class="empty-box" *ngIf="events().length === 0">
        No catalyst events stored yet. Click <strong>Scan NSE / BSE / PIB</strong> or score an announcement above.
      </div>

      <div class="events-grid" *ngIf="events().length > 0">
        <div class="ev-card" *ngFor="let ev of events()" [class.pre-breakout]="ev.pre_breakout_match">
          <div class="ev-top">
            <div class="ev-sym-group" (click)="openStock(ev.symbol)">
              <span class="ev-sym">{{ ev.symbol }}</span>
              <span class="tier-pill" [ngClass]="'t-' + ev.tier">Tier {{ ev.tier }} &bull; {{ ev.total_score }}/100</span>
              <span class="pb-pill" *ngIf="ev.pre_breakout_match">🚀 Pre-Breakout Match</span>
            </div>
            <div class="ev-meta">
              <span class="src-badge">{{ ev.source }}</span>
              <span>{{ ev.announced_at }}</span>
            </div>
          </div>

          <div class="ev-title">{{ ev.title }}</div>
          <div class="ev-cat-row">
            <span class="cat-badge">{{ ev.category }}</span>
            <span *ngIf="ev.deal_value_cr">Deal: <b>₹{{ ev.deal_value_cr }} Cr</b></span>
            <span *ngIf="ev.annual_revenue_cr">TTM Rev: <b>₹{{ ev.annual_revenue_cr }} Cr</b></span>
          </div>

          <div class="breakdown-row" *ngIf="ev.score_breakdown as b">
            <span>Fin: {{ b.financial_impact }}/25</span>
            <span>Growth: {{ b.business_growth }}/20</span>
            <span>Novelty: {{ b.news_novelty }}/15</span>
            <span>Vis: {{ b.revenue_visibility }}/15</span>
            <span>Cred: {{ b.source_credibility }}/10</span>
            <span>Mkt: {{ b.market_reaction }}/15</span>
          </div>

          <div class="pb-signals" *ngIf="ev.pre_breakout_signals?.length">
            <span class="sig-chip" *ngFor="let sig of ev.pre_breakout_signals">{{ sig }}</span>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .cat-page { padding: 18px 24px; color: #e2e8f0; max-width: 1440px; margin: 0 auto; }
    .cat-hero {
      display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 14px;
      background: rgba(15, 23, 42, 0.72); border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 12px; padding: 16px 20px; margin-bottom: 14px;
    }
    .hero-title { margin: 0 0 4px; font-size: 1.15rem; color: #f8fafc; }
    .hero-sub { margin: 0; font-size: 0.78rem; color: #94a3b8; max-width: 720px; }
    .hero-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7, #2563eb); color: #fff; border: none;
      padding: 8px 14px; border-radius: 8px; font-weight: 600; font-size: 0.78rem; cursor: pointer;
    }
    .btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-secondary {
      background: rgba(56, 189, 248, 0.14); border: 1px solid rgba(56, 189, 248, 0.35);
      color: #7dd3fc; padding: 8px 14px; border-radius: 8px; font-weight: 600; font-size: 0.78rem; cursor: pointer;
    }
    .tester-card {
      background: rgba(15, 23, 42, 0.65); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px; padding: 12px 16px; margin-bottom: 12px;
    }
    .tester-title { font-size: 0.76rem; font-weight: 700; color: #94a3b8; margin-bottom: 8px; text-transform: uppercase; }
    .tester-row { display: flex; gap: 8px; flex-wrap: wrap; }
    .inp {
      background: rgba(2, 6, 23, 0.75); border: 1px solid rgba(148, 163, 184, 0.25);
      color: #f8fafc; padding: 8px 10px; border-radius: 7px; font-size: 0.78rem;
    }
    .inp.sym { width: 130px; }
    .inp.title { flex: 1; min-width: 240px; }
    .inp.rev { width: 140px; }
    .status-msg { font-size: 0.78rem; color: #7dd3fc; margin-bottom: 10px; }
    .filter-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
    .tab-btn {
      background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8; padding: 5px 12px; border-radius: 6px; font-size: 0.74rem; font-weight: 600; cursor: pointer;
    }
    .tab-btn.active { background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; color: #fff; }
    .bt-card {
      background: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3);
      border-radius: 10px; padding: 12px 16px; margin-bottom: 14px; font-size: 0.78rem;
    }
    .bt-head { display: flex; justify-content: space-between; margin-bottom: 8px; color: #6ee7b7; }
    .bt-metrics { display: flex; gap: 18px; flex-wrap: wrap; color: #cbd5e1; }
    .empty-box { padding: 28px; text-align: center; color: #94a3b8; background: rgba(15, 23, 42, 0.5); border-radius: 10px; font-size: 0.82rem; }
    .events-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 12px; }
    .ev-card {
      background: rgba(15, 23, 42, 0.7); border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px; padding: 12px 14px;
    }
    .ev-card.pre-breakout { border-color: rgba(16, 185, 129, 0.45); }
    .ev-top { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
    .ev-sym-group { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; flex-wrap: wrap; }
    .ev-sym { font-weight: 800; color: #38bdf8; font-size: 0.9rem; }
    .tier-pill { font-size: 0.68rem; padding: 2px 7px; border-radius: 5px; font-weight: 700; }
    .t-A { background: rgba(16, 185, 129, 0.22); color: #34d399; }
    .t-B { background: rgba(245, 158, 11, 0.22); color: #fbbf24; }
    .t-C { background: rgba(148, 163, 184, 0.18); color: #cbd5e1; }
    .pb-pill { font-size: 0.66rem; padding: 2px 6px; border-radius: 5px; background: rgba(16, 185, 129, 0.18); color: #6ee7b7; font-weight: 700; }
    .ev-meta { display: inline-flex; gap: 6px; font-size: 0.7rem; color: #94a3b8; align-items: center; }
    .src-badge { background: rgba(56, 189, 248, 0.15); color: #7dd3fc; padding: 1px 6px; border-radius: 4px; font-weight: 700; }
    .ev-title { font-size: 0.82rem; font-weight: 600; color: #f1f5f9; margin-bottom: 6px; line-height: 1.35; }
    .ev-cat-row { display: flex; gap: 10px; font-size: 0.72rem; color: #cbd5e1; margin-bottom: 6px; flex-wrap: wrap; align-items: center; }
    .cat-badge { background: rgba(168, 85, 247, 0.18); color: #d8b4fe; padding: 1px 6px; border-radius: 4px; font-size: 0.66rem; font-weight: 700; }
    .breakdown-row { display: flex; gap: 8px; flex-wrap: wrap; font-size: 0.68rem; color: #94a3b8; margin-bottom: 6px; }
    .pb-signals { display: flex; gap: 4px; flex-wrap: wrap; }
    .sig-chip { font-size: 0.65rem; background: rgba(56, 189, 248, 0.12); color: #7dd3fc; padding: 2px 6px; border-radius: 4px; }
  `]
})
export class CatalystRadarComponent implements OnInit {
  events = signal<any[]>([]);
  tierFilter = signal<string>('');
  isScanning = signal<boolean>(false);
  isAnalyzing = signal<boolean>(false);
  isBacktesting = signal<boolean>(false);
  backtest = signal<any | null>(null);
  statusMsg = signal<string>('');

  testSym = signal<string>('');
  testTitle = signal<string>('');
  testRev = signal<string>('');

  ngOnInit(): void {
    this.loadEvents();
  }

  onSym(e: Event): void { this.testSym.set((e.target as HTMLInputElement).value); }
  onTitle(e: Event): void { this.testTitle.set((e.target as HTMLInputElement).value); }
  onRev(e: Event): void { this.testRev.set((e.target as HTMLInputElement).value); }

  async loadEvents(): Promise<void> {
    try {
      const res = await apiService.getCatalystEarlyWarning(this.tierFilter());
      this.events.set(res.events || []);
    } catch (e: any) {
      this.statusMsg.set(e?.message || 'Failed to load catalyst events');
    }
  }

  setTier(tier: string): void {
    this.tierFilter.set(tier);
    this.loadEvents();
  }

  async runScan(): Promise<void> {
    if (this.isScanning()) return;
    this.isScanning.set(true);
    this.statusMsg.set('');
    try {
      const res = await apiService.scanCatalysts();
      this.statusMsg.set(`Scanned ${res.scanned_raw} primary disclosures -> ${res.saved_catalysts} catalysts saved (${res.tier_a_count} Tier A, ${res.tier_b_count} Tier B).`);
      await this.loadEvents();
    } catch (e: any) {
      this.statusMsg.set(e?.message || 'Scan failed');
    } finally {
      this.isScanning.set(false);
    }
  }

  async analyzeCustom(): Promise<void> {
    const sym = this.testSym().trim().toUpperCase();
    const title = this.testTitle().trim();
    if (!sym || !title || this.isAnalyzing()) return;
    this.isAnalyzing.set(true);
    this.statusMsg.set('');
    try {
      const rev = this.testRev().trim() ? Number(this.testRev()) : null;
      const ev = await apiService.analyzeCatalyst({ symbol: sym, title, annual_revenue_cr: rev });
      this.statusMsg.set(`Scored ${ev.symbol}: ${ev.total_score}/100 (Tier ${ev.tier}, ${ev.category})`);
      await this.loadEvents();
    } catch (e: any) {
      this.statusMsg.set(e?.message || 'Scoring failed');
    } finally {
      this.isAnalyzing.set(false);
    }
  }

  async runBacktest(): Promise<void> {
    if (this.isBacktesting()) return;
    this.isBacktesting.set(true);
    try {
      const bt = await apiService.getCatalystBacktest();
      this.backtest.set(bt);
    } catch (e: any) {
      this.statusMsg.set(e?.message || 'Backtest failed');
    } finally {
      this.isBacktesting.set(false);
    }
  }

  openStock(symbol: string): void {
    if (symbol && symbol !== 'GOVT_POLICY') {
      stocksStore.selectSymbol(symbol);
    }
  }
}
