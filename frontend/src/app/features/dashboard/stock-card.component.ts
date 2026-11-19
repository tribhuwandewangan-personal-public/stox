/**
 * Stock card: Rich information card matching the full analysis view.
 * Shows symbol, price, verdict, confidence, patterns, entry/target/stop, long-term, sparkline.
 */

import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';
import { getStockBucket, verdictInfo } from '../../core/utils/verdict';
import { SparklineComponent } from './sparkline.component';

@Component({
  selector: 'app-stock-card',
  standalone: true,
  imports: [CommonModule, SparklineComponent],
  template: `
    <div class="stock-card" [class.stale]="stock.is_stale" (click)="onCardClick()">

      <!-- Header: Symbol + Verdict -->
      <div class="card-header">
        <div class="symbol-row">
          <span class="symbol">{{ stock.symbol }}</span>
          <span class="long-term-pick" *ngIf="longTermVerdict">🏛 {{ longTermVerdict }}</span>
        </div>
        <div class="verdict-badge" [style.color]="verdictColor" [style.background-color]="verdictBg">
          {{ verdictLabel }}
        </div>
      </div>

      <!-- Company name -->
      <div class="card-name">{{ stock.name }}</div>

      <!-- Price row -->
      <div class="price-section">
        <span class="price">{{ formattedPrice }}</span>
        <span class="change" [ngClass]="changeClass">{{ formattedChange }}</span>
        <span class="live-dot" *ngIf="isLive">● live</span>
      </div>

      <!-- Stale warning -->
      <div class="stale-warning" *ngIf="staleMessage">
        {{ staleMessage }}
      </div>

      <!-- Top pattern badge -->
      <div class="top-pattern" *ngIf="topPattern">
        <span class="pattern-chip" [class.bearish]="topPattern.bearish">
          {{ topPattern.bearish ? '▼' : '▲' }} {{ topPattern.name }} {{ topPattern.score }}
        </span>
      </div>

      <!-- Event chips -->
      <div class="events-row" *ngIf="eventLabels.length">
        <span class="event-chip" *ngFor="let ev of eventLabels">📅 {{ ev }}</span>
      </div>

      <!-- Sparkline with label -->
      <div class="sparkline-wrap">
        <span class="sparkline-label">25-Day Price Trend</span>
        <app-sparkline [data]="stock.sparkline"></app-sparkline>
      </div>

      <!-- Confidence bar -->
      <div class="confidence-row" *ngIf="confidence !== null">
        <span class="conf-label">Confidence: <strong>{{ confidenceLabel }} ({{ confidence }}%)</strong></span>
        <div class="conf-bar-bg">
          <div class="conf-bar-fill" [style.width.%]="confidence" [style.background-color]="confBarColor"></div>
        </div>
      </div>

      <!-- Short-term swing section -->
      <div class="swing-section" *ngIf="hasSwing">
        <div class="section-title">⚡ SHORT-TERM SWING</div>
        <div class="swing-grid">
          <div class="swing-item" *ngIf="entryZone">
            <span class="item-label">🖥 ENTRY ZONE</span>
            <span class="item-value">{{ entryZone }}</span>
          </div>
          <div class="swing-item" *ngIf="swingTarget">
            <span class="item-label">🎯 SWING TARGET</span>
            <span class="item-value accent-green">{{ swingTarget }}</span>
          </div>
          <div class="swing-item" *ngIf="stopLoss">
            <span class="item-label">🛡 STOP LOSS</span>
            <span class="item-value accent-red">{{ stopLoss }}</span>
          </div>
          <div class="swing-item" *ngIf="horizon">
            <span class="item-label">⏳ HORIZON</span>
            <span class="item-value">{{ horizon }}</span>
          </div>
        </div>
      </div>

      <!-- Long-term section -->
      <div class="lt-section" *ngIf="hasLongTerm">
        <div class="section-title accent-gold">🏛 LONG-TERM WEALTH</div>
        <div class="lt-target" *ngIf="ltTarget">
          <span class="lt-price">{{ ltTarget }}</span>
          <span class="lt-gain accent-green" *ngIf="ltGainPct">+{{ ltGainPct }}%</span>
        </div>
        <div class="lt-verdict" *ngIf="ltVerdictText">Rating: <span class="accent-green">{{ ltVerdictText }}</span></div>
        <div class="lt-peers" *ngIf="ltPeers.length">
          <span class="peer-chip" *ngFor="let p of ltPeers">{{ p }} ↗</span>
        </div>
      </div>

      <!-- Footer: open view -->
      <div class="card-footer">
        <span class="footer-label">📊 Interactive Chart &amp; Patterns</span>
        <span class="open-view">Open View ↗</span>
      </div>
    </div>
  `,
  styles: [`
    .stock-card {
      background: linear-gradient(160deg, #1a2540 0%, #0f1826 100%);
      border: 1px solid rgba(56, 189, 248, 0.35);
      border-radius: 14px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      cursor: pointer;
      transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
      position: relative;
      overflow: hidden;
      box-shadow: 0 2px 10px rgba(0,0,0,0.3);
    }
    .stock-card:hover {
      border-color: rgba(56, 189, 248, 0.7);
      box-shadow: 0 8px 28px rgba(56, 189, 248, 0.18);
      transform: translateY(-3px);
    }
    .stock-card.stale { opacity: 0.55; border-color: rgba(239, 68, 68, 0.25); }

    /* Header */
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 8px;
    }
    .symbol-row {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    .symbol {
      font-size: 18px;
      font-weight: 800;
      color: #fff;
      letter-spacing: 0.5px;
    }
    .long-term-pick {
      font-size: 10px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 20px;
      border: 1px solid rgba(251, 191, 36, 0.4);
      color: #fbbf24;
      background: rgba(251, 191, 36, 0.08);
    }
    .verdict-badge {
      font-size: 11px;
      font-weight: 800;
      padding: 5px 10px;
      border-radius: 20px;
      border: 1px solid currentColor;
      white-space: nowrap;
      flex-shrink: 0;
    }

    /* Name */
    .card-name {
      font-size: 12px;
      color: rgba(148, 163, 184, 0.9);
      line-height: 1.3;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    /* Price */
    .price-section {
      display: flex;
      align-items: baseline;
      gap: 10px;
      flex-wrap: wrap;
    }
    .price { font-size: 20px; font-weight: 700; color: #fff; }
    .change { font-size: 14px; font-weight: 600; }
    .change.positive { color: #10b981; }
    .change.negative { color: #ef4444; }
    .change.neutral  { color: #94a3b8; }
    .live-dot { font-size: 10px; color: #10b981; margin-left: auto; }

    /* Stale */
    .stale-warning {
      font-size: 10px;
      color: #f59e0b;
      line-height: 1.4;
      background: rgba(245, 158, 11, 0.07);
      border-radius: 4px;
      padding: 4px 6px;
    }

    /* Pattern */
    .top-pattern { display: flex; flex-wrap: wrap; gap: 6px; }
    .pattern-chip {
      font-size: 11px;
      font-weight: 600;
      padding: 3px 10px;
      border-radius: 20px;
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .pattern-chip.bearish {
      background: rgba(239, 68, 68, 0.12);
      color: #ef4444;
      border-color: rgba(239, 68, 68, 0.3);
    }

    /* Events */
    .events-row { display: flex; flex-wrap: wrap; gap: 6px; }
    .event-chip {
      font-size: 10px;
      padding: 3px 8px;
      border-radius: 4px;
      background: rgba(245, 158, 11, 0.12);
      color: #f59e0b;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }

    /* Sparkline */
    .sparkline-wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid rgba(56, 189, 248, 0.12);
      border-radius: 8px;
      padding: 8px 10px;
    }
    .sparkline-label { font-size: 10px; color: #64748b; }

    /* Confidence */
    .confidence-row { display: flex; flex-direction: column; gap: 4px; }
    .conf-label { font-size: 11px; color: #94a3b8; }
    .conf-label strong { color: #fff; }
    .conf-bar-bg {
      height: 5px;
      background: rgba(255,255,255,0.08);
      border-radius: 3px;
      overflow: hidden;
    }
    .conf-bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }

    /* Swing section */
    .swing-section {
      background: rgba(15, 23, 42, 0.5);
      border: 1px solid rgba(56, 189, 248, 0.1);
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .section-title {
      font-size: 10px;
      font-weight: 800;
      letter-spacing: 0.5px;
      color: #f59e0b;
      text-transform: uppercase;
    }
    .swing-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }
    .swing-item { display: flex; flex-direction: column; gap: 2px; }
    .item-label { font-size: 9px; font-weight: 700; color: #64748b; letter-spacing: 0.3px; text-transform: uppercase; }
    .item-value { font-size: 12px; font-weight: 700; color: #fff; }
    .accent-green { color: #10b981 !important; }
    .accent-red   { color: #ef4444 !important; }
    .accent-gold  { color: #fbbf24 !important; }

    /* Long-term section */
    .lt-section {
      background: rgba(251, 191, 36, 0.04);
      border: 1px solid rgba(251, 191, 36, 0.15);
      border-radius: 8px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .lt-target { display: flex; align-items: baseline; gap: 10px; }
    .lt-price { font-size: 15px; font-weight: 700; color: #fff; }
    .lt-gain  { font-size: 13px; font-weight: 600; }
    .lt-verdict { font-size: 11px; color: #94a3b8; }
    .lt-peers { display: flex; flex-wrap: wrap; gap: 6px; }
    .peer-chip {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 4px;
      background: rgba(56, 189, 248, 0.1);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }

    /* Footer */
    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 6px;
      border-top: 1px solid rgba(56, 189, 248, 0.1);
      margin-top: 2px;
    }
    .footer-label { font-size: 10px; color: #64748b; }
    .open-view { font-size: 10px; color: #38bdf8; font-weight: 600; }

    @media (max-width: 480px) {
      .stock-card { padding: 12px; }
      .symbol { font-size: 16px; }
      .price { font-size: 17px; }
      .swing-grid { grid-template-columns: 1fr; }
    }
  `]
})
export class StockCardComponent {
  @Input({ required: true }) stock!: Stock;
  @Output() cardClick = new EventEmitter<Stock>();

  onCardClick(): void { this.cardClick.emit(this.stock); }

  /* ── Verdict ── */
  private get _vi() {
    const bucket = getStockBucket(this.stock);
    return verdictInfo(bucket, this.stock.synth_output?.structured_signal?.confidence_score);
  }
  get verdictLabel(): string  { return this._vi.label; }
  get verdictColor(): string  { return this._vi.color; }
  get verdictBg(): string     { return this._vi.bgColor; }

  /* ── Price ── */
  get formattedPrice(): string {
    const p = this.stock.price_info?.price;
    return p != null ? fmtPrice(p) : '--';
  }
  get formattedChange(): string {
    const c = this.stock.price_info?.change_pct;
    if (c == null) return '--';
    return `${c > 0 ? '+' : ''}${c.toFixed(2)}%`;
  }
  get changeClass(): string {
    const c = this.stock.price_info?.change_pct;
    if (c == null) return 'neutral';
    return c > 0 ? 'positive' : c < 0 ? 'negative' : 'neutral';
  }
  get isLive(): boolean { return this.stock.price_info?.source === 'quote'; }

  /* ── Stale warning ── */
  get staleMessage(): string | null {
    if (!this.stock.is_stale || !this.stock.synth_output) return null;
    const date = this.stock.synth_output.as_of_date;
    return `Levels computed at ${this.formattedPrice} (as of ${date}); price may be outdated`;
  }

  /* ── Patterns ── */
  get topPattern() {
    return this.stock.patterns?.[0] ?? null;
  }

  /* ── Events ── */
  get eventLabels(): string[] {
    const ev = this.stock.events;
    if (!ev) return [];
    const labels: string[] = [];
    if (ev.upcoming_events) {
      for (const [type, date] of Object.entries(ev.upcoming_events)) {
        labels.push(`${type}: ${date}`);
      }
    }
    if (ev.upcoming_macro_catalysts) {
      labels.push(...ev.upcoming_macro_catalysts.slice(0, 1));
    }
    return labels.slice(0, 2);
  }

  /* ── Confidence ── */
  get confidence(): number | null {
    const c = this.stock.synth_output?.structured_signal?.confidence_score;
    return c != null ? Math.round(c * 100) : null;
  }
  get confidenceLabel(): string {
    const c = this.confidence;
    if (c == null) return '';
    if (c >= 80) return 'HIGH';
    if (c >= 55) return 'MEDIUM';
    return 'LOW';
  }
  get confBarColor(): string {
    const c = this.confidence ?? 0;
    if (c >= 80) return '#10b981';
    if (c >= 55) return '#f59e0b';
    return '#ef4444';
  }

  /* ── Short-term swing ── */
  get hasSwing(): boolean {
    const s = this.stock.synth_output?.structured_signal;
    return !!(s?.entry_low || s?.target_num || s?.stop_num);
  }
  get entryZone(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    if (!s) return null;
    if (s.entry_low != null && s.entry_high != null)
      return `${fmtPrice(s.entry_low)} – ${fmtPrice(s.entry_high)}`;
    if (s.entry_low != null) return fmtPrice(s.entry_low);
    return null;
  }
  get swingTarget(): string | null {
    const t = this.stock.synth_output?.structured_signal?.target_num;
    return t != null ? fmtPrice(t) : null;
  }
  get stopLoss(): string | null {
    const s = this.stock.synth_output?.structured_signal?.stop_num;
    return s != null ? fmtPrice(s) : null;
  }
  get horizon(): string | null {
    return this.stock.synth_output?.structured_signal?.when_to_sell_target ?? null;
  }

  /* ── Long-term ── */
  get hasLongTerm(): boolean {
    return !!(this.stock.long_term_signal?.long_term_target);
  }
  get longTermVerdict(): string | null {
    return this.stock.long_term_signal?.long_term_verdict ?? null;
  }
  get ltTarget(): string | null {
    const t = this.stock.long_term_signal?.long_term_target;
    return t != null ? fmtPrice(t) : null;
  }
  get ltGainPct(): string | null {
    const t = this.stock.long_term_signal?.long_term_target;
    const p = this.stock.price_info?.price;
    if (t == null || p == null || p === 0) return null;
    return ((t - p) / p * 100).toFixed(1);
  }
  get ltVerdictText(): string | null {
    return this.stock.long_term_signal?.long_term_verdict ?? null;
  }
  get ltPeers(): string[] {
    return this.stock.long_term_signal?.suggested_long_term_peers?.slice(0, 3) ?? [];
  }

  /* ── Event existence (kept for compat) ── */
  get hasEvents(): boolean {
    const ev = this.stock.events;
    return !!(ev?.upcoming_events && Object.keys(ev.upcoming_events).length)
      || !!(ev?.upcoming_macro_catalysts?.length);
  }
}
