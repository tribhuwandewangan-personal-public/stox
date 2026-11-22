/**
 * Stock card: Rich information card matching the full analysis view.
 * Shows symbol, price, verdict, confidence, patterns, entry/target/stop, long-term, sparkline, and rationale.
 */

import { Component, Input, Output, EventEmitter, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock, PatternResult } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';
import { getStockBucket, verdictInfo } from '../../core/utils/verdict';
import { SparklineComponent } from './sparkline.component';

@Component({
  selector: 'app-stock-card',
  standalone: true,
  imports: [CommonModule, SparklineComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="stock-card" [class.stale]="stock.is_stale" (click)="onCardClick()" [attr.data-symbol]="stock.symbol">

      <!-- Header: Symbol + Verdict -->
      <div class="card-header">
        <div class="symbol-row">
          <span class="symbol">{{ stock.symbol }}</span>
          <span class="long-term-pick" *ngIf="longTermBadge">🏛 {{ longTermBadge }}</span>
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

      <!-- Price drift / calculation note -->
      <div class="drift-note" *ngIf="driftNote" [class.warn]="isDriftWarn">
        {{ driftNote }}
      </div>

      <!-- Pattern Badges -->
      <div class="pattern-badges-row" *ngIf="patternBadges.length">
        <span *ngFor="let p of patternBadges" class="pattern-pill" [ngClass]="p.cssClass">
          {{ p.icon }} {{ p.label }}
        </span>
      </div>

      <!-- Forensic Due Diligence Badge -->
      <div class="forensic-badge-row" *ngIf="forensicBadge">
        <span class="forensic-pill">{{ forensicBadge }}</span>
      </div>

      <!-- Event chips -->
      <div class="events-row" *ngIf="eventLabels.length">
        <span class="event-chip" *ngFor="let ev of eventLabels">{{ ev }}</span>
      </div>

      <!-- Sparkline with label -->
      <div class="sparkline-wrap">
        <div class="sparkline-header">
          <span class="sparkline-label">25-Day Price Trend</span>
          <span class="sparkline-val" *ngIf="sparklineLastPrice" [class.negative]="sparklineDown" [class.positive]="!sparklineDown">
            {{ sparklineDown ? '▼' : '▲' }} {{ sparklineLastPrice }}
          </span>
        </div>
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
        <div class="section-title">⚡ SHORT-TERM SWING (1–3 WEEKS)</div>
        <div class="swing-grid">
          <div class="swing-item" *ngIf="entryZone">
            <span class="item-label">🛒 ENTRY ZONE</span>
            <span class="item-value">{{ entryZone }}</span>
          </div>
          <div class="swing-item" *ngIf="intrinsicValueDisplay">
            <span class="item-label">💎 INTRINSIC VALUE</span>
            <span class="item-value accent-cyan">
              {{ intrinsicValueDisplay }}
              <small *ngIf="marginOfSafetyPct !== null" [style.color]="marginOfSafetyPct >= 0 ? '#34d399' : '#f87171'" style="font-weight: 600;">
                ({{ marginOfSafetyPct > 0 ? '+' : '' }}{{ marginOfSafetyPct.toFixed(0) }}%)
              </small>
            </span>
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
        <div class="lt-header-row">
          <span class="section-title accent-gold">🏛 LONG-TERM WEALTH (1–3 YEARS)</span>
          <span class="lt-target-pill" *ngIf="ltTargetDisplay">
            {{ ltTargetDisplay }} <strong class="accent-green" *ngIf="ltGainPctDisplay">{{ ltGainPctDisplay }}</strong>
          </span>
        </div>
        <div class="lt-verdict" *ngIf="ltVerdictText">
          Rating: <span class="accent-green">{{ ltVerdictText }}</span>
        </div>
        <div class="lt-moat" *ngIf="ltMoatText">
          Moat: <span>{{ ltMoatText }}</span>
        </div>
        <div class="lt-peers-row" *ngIf="ltPeers.length">
          <span class="peers-label">Top Sector Peers:</span>
          <div class="lt-peers">
            <span class="peer-chip" *ngFor="let p of ltPeers">{{ p }} ↗</span>
          </div>
        </div>
      </div>

      <!-- Report Rationale Snippet -->
      <div class="report-snippet" *ngIf="reportSnippet">
        {{ reportSnippet }}
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
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      cursor: pointer;
      transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
      position: relative;
      overflow: hidden;
      box-shadow: 0 4px 14px rgba(0,0,0,0.35);
    }
    .stock-card:hover {
      border-color: rgba(56, 189, 248, 0.7);
      box-shadow: 0 8px 28px rgba(56, 189, 248, 0.22);
      transform: translateY(-3px);
    }
    .stock-card.stale { opacity: 0.65; border-color: rgba(239, 68, 68, 0.25); }

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
      font-size: 19px;
      font-weight: 800;
      color: #fff;
      letter-spacing: 0.5px;
      font-family: 'Outfit', sans-serif;
    }
    .long-term-pick {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 20px;
      background: rgba(16, 185, 129, 0.15);
      color: #10b981;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }
    .verdict-badge {
      font-size: 11px;
      font-weight: 800;
      padding: 3px 10px;
      border-radius: 20px;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      white-space: nowrap;
    }

    .card-name {
      font-size: 12px;
      color: #94a3b8;
      margin-top: -6px;
    }

    /* Price */
    .price-section {
      display: flex;
      align-items: baseline;
      gap: 8px;
    }
    .price {
      font-size: 20px;
      font-weight: 800;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
    }
    .change {
      font-size: 13px;
      font-weight: 600;
      font-family: 'JetBrains Mono', monospace;
    }
    .change.positive { color: #10b981; }
    .change.negative { color: #ef4444; }
    .change.neutral  { color: #94a3b8; }
    .live-dot {
      font-size: 10px;
      color: #10b981;
      background: rgba(16, 185, 129, 0.15);
      padding: 1px 6px;
      border-radius: 8px;
    }

    /* Drift Note */
    .drift-note {
      font-size: 10px;
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.03);
      padding: 4px 8px;
      border-radius: 6px;
      line-height: 1.35;
      border-left: 2px solid rgba(56, 189, 248, 0.4);
    }
    .drift-note.warn {
      border-left-color: #f59e0b;
      color: #f59e0b;
      background: rgba(245, 158, 11, 0.06);
    }

    /* Pattern Badges */
    .pattern-badges-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .forensic-badge-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-top: 2px;
    }
    .forensic-pill {
      font-size: 10px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 8px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(245, 158, 11, 0.35);
      color: #f1f5f9;
    }
    .pattern-pill {
      font-size: 11px;
      font-weight: 600;
      padding: 3px 9px;
      border-radius: 12px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
      line-height: 1.3;
    }
    .pattern-pill.bull {
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.35);
    }
    .pattern-pill.bear {
      background: rgba(239, 68, 68, 0.15);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.35);
    }
    .pattern-pill.saucer {
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.35);
    }
    .pattern-pill.squeeze {
      background: rgba(245, 158, 11, 0.15);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.35);
    }
    .pattern-pill.neutral {
      background: rgba(100, 116, 139, 0.2);
      color: #cbd5e1;
      border: 1px solid rgba(100, 116, 139, 0.3);
    }

    /* Event chips */
    .events-row {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }
    .event-chip {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 6px;
      background: rgba(245, 158, 11, 0.12);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.25);
    }

    /* Sparkline */
    .sparkline-wrap {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .sparkline-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .sparkline-label {
      font-size: 10px;
      color: #64748b;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }
    .sparkline-val {
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }
    .sparkline-val.positive { color: #10b981; }
    .sparkline-val.negative { color: #ef4444; }

    /* Confidence */
    .confidence-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .conf-label {
      font-size: 11px;
      color: #94a3b8;
    }
    .conf-label strong { color: #e2e8f0; }
    .conf-bar-bg {
      height: 4px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 2px;
      overflow: hidden;
    }
    .conf-bar-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease;
    }

    /* Short-term Swing */
    .swing-section {
      background: rgba(0, 0, 0, 0.25);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .section-title {
      font-size: 10px;
      font-weight: 700;
      color: #38bdf8;
      letter-spacing: 0.4px;
    }
    .section-title.accent-gold { color: #fbbf24; }
    .swing-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }
    .swing-item {
      display: flex;
      flex-direction: column;
      gap: 1px;
    }
    .item-label {
      font-size: 9px;
      color: #64748b;
      font-weight: 600;
    }
    .item-value {
      font-size: 12px;
      color: #e2e8f0;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
    }
    .accent-green { color: #10b981; }
    .accent-red   { color: #ef4444; }
    .accent-cyan  { color: #38bdf8; }

    /* Long-term */
    .lt-section {
      background: rgba(245, 158, 11, 0.04);
      border: 1px solid rgba(245, 158, 11, 0.2);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .lt-header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 6px;
    }
    .lt-target-pill {
      font-size: 12px;
      font-weight: 700;
      color: #fff;
      font-family: 'JetBrains Mono', monospace;
    }
    .lt-verdict {
      font-size: 11px;
      color: #94a3b8;
    }
    .lt-moat {
      font-size: 11px;
      color: #cbd5e1;
    }
    .lt-moat span { color: #94a3b8; }
    .lt-peers-row {
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-top: 2px;
    }
    .peers-label {
      font-size: 9px;
      color: #64748b;
      font-weight: 600;
      text-transform: uppercase;
    }
    .lt-peers { display: flex; flex-wrap: wrap; gap: 6px; }
    .peer-chip {
      font-size: 10px;
      padding: 2px 8px;
      border-radius: 4px;
      background: rgba(56, 189, 248, 0.1);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }

    /* Report Snippet */
    .report-snippet {
      font-size: 11px;
      color: #94a3b8;
      line-height: 1.45;
      background: rgba(0, 0, 0, 0.2);
      padding: 8px 10px;
      border-radius: 8px;
      border-left: 2px solid rgba(56, 189, 248, 0.3);
      max-height: 70px;
      overflow: hidden;
      text-overflow: ellipsis;
      display: -webkit-box;
      -webkit-line-clamp: 3;
      -webkit-box-orient: vertical;
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

  get forensicBadge(): string | null {
    return this.stock.fund_output?.forensic_badge || null;
  }

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
  get isLive(): boolean {
    const info = this.stock.price_info;
    return (info?.kind || info?.source) === 'quote';
  }

  /* ── Price Drift Subtitle (Levels computed at ...) ── */
  get driftNote(): string | null {
    const pi = this.stock.price_info;
    const currentPrice = pi?.price;
    const analysisPrice = pi?.analysis_price;
    const asOf = pi?.analysis_as_of || this.stock.synth_output?.as_of_date;

    if (analysisPrice && currentPrice) {
      const drift = (currentPrice - analysisPrice) / analysisPrice * 100;
      if (Math.abs(drift) >= 0.05) {
        const dir = drift >= 0 ? 'up' : 'down';
        const asOfStr = asOf ? ` (as of ${asOf})` : '';
        const warnText = Math.abs(drift) > 2 ? ' - entry/target/stop may be outdated' : '';
        return `Levels computed at ${fmtPrice(analysisPrice)}${asOfStr}; price ${dir} ${Math.abs(drift).toFixed(1)}% since${warnText}`;
      }
    }

    if (this.stock.is_stale && asOf) {
      return `Levels computed as of ${asOf}; price may be outdated`;
    }
    return null;
  }

  get isDriftWarn(): boolean {
    const pi = this.stock.price_info;
    if (pi?.price && pi?.analysis_price) {
      const drift = Math.abs((pi.price - pi.analysis_price) / pi.analysis_price * 100);
      return drift > 2;
    }
    return !!this.stock.is_stale;
  }

  /* ── Pattern Badges (Matching static/index.html renderPatternBadges) ── */
  get patternBadges(): Array<{ label: string; icon: string; cssClass: string }> {
    if (!this.stock.has_analysis) {
      return [];
    }
    const patterns = this.stock.patterns || [];
    if (!patterns.length) {
      return [{ label: 'Range Consolidation', icon: '📐', cssClass: 'neutral' }];
    }

    return patterns.slice(0, 2).map(p => {
      const name = p.name || '';
      const dir = p.direction || (p.bearish ? 'Bearish' : 'Bullish');
      const scoreStr = p.quality_score ? ` ${p.quality_score}` : (p.score ? ` ${Math.round(p.score * (p.score <= 1 ? 100 : 1))}` : '');
      let icon = '📐';
      let cssClass = 'neutral';

      if (name.includes('Saucer') || name.includes('Rounding')) {
        icon = '🥣';
        cssClass = 'saucer';
      } else if (name.includes('Cup and Handle')) {
        icon = '☕';
        cssClass = 'bull';
      } else if (name.includes('TTM') || name.includes('Squeeze') || name.includes('Bollinger')) {
        icon = '⚡';
        cssClass = 'squeeze';
      } else if (name.includes('Wyckoff')) {
        icon = '⚓';
        cssClass = dir === 'Bullish' ? 'bull' : 'bear';
      } else if (name.includes('Flag') || name.includes('Breakout')) {
        icon = '🚩';
        cssClass = dir === 'Bullish' ? 'bull' : 'bear';
      } else if (name.includes('Crossover') || name.includes('Cross')) {
        icon = '📈';
        cssClass = dir === 'Bullish' ? 'bull' : 'bear';
      } else {
        cssClass = dir === 'Bullish' ? 'bull' : (dir === 'Bearish' ? 'bear' : 'neutral');
      }

      return {
        label: `${name}${scoreStr}`,
        icon,
        cssClass
      };
    });
  }

  /* ── Events ── */
  get eventLabels(): string[] {
    const ev = this.stock.events;
    if (!ev) return [];
    const labels: string[] = [];

    if (ev.earnings_date) {
      labels.push(`📅 Results: ${ev.earnings_date}`);
    }
    if (ev.dividend_amount && ev.dividend_amount !== 'N/A') {
      labels.push(`💰 Div: ${ev.dividend_amount}`);
    }

    if (ev.upcoming_events && typeof ev.upcoming_events === 'object') {
      for (const [type, val] of Object.entries(ev.upcoming_events)) {
        if (typeof val === 'string' && !labels.some(l => l.includes(type))) {
          labels.push(`📅 ${type}: ${val}`);
        } else if (val && typeof val === 'object' && (val as any).date) {
          labels.push(`📅 ${type}: ${(val as any).date}`);
        }
      }
    }

    if (Array.isArray(ev.upcoming_macro_catalysts) && ev.upcoming_macro_catalysts.length > 0) {
      const first = ev.upcoming_macro_catalysts[0];
      if (typeof first === 'string') {
        labels.push(`🌐 ${first}`);
      } else if (first && typeof first === 'object' && first.event_name) {
        labels.push(`🌐 ${first.event_name}`);
      }
    }

    return labels.slice(0, 2);
  }

  /* ── Sparkline Trend ── */
  get sparklineLastPrice(): string | null {
    const sp = this.stock.sparkline;
    if (!sp || !sp.length) return null;
    return fmtPrice(sp[sp.length - 1]);
  }

  get sparklineDown(): boolean {
    const sp = this.stock.sparkline;
    if (!sp || sp.length < 2) return false;
    return sp[sp.length - 1] < sp[0];
  }

  /* ── Confidence ── */
  get confidence(): number | null {
    const s = this.stock.synth_output?.structured_signal;
    if (s?.confidence_percentage != null) return Math.round(s.confidence_percentage);
    const c = s?.confidence_score;
    return c != null ? Math.round(c * (c <= 1 ? 100 : 1)) : null;
  }
  get confidenceLabel(): string {
    const s = this.stock.synth_output?.structured_signal;
    if (s?.confidence_rating) {
      return s.confidence_rating.replace(/\s*\(\d+%\)/, '').trim();
    }
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
    return !!(s?.when_to_buy_entry || s?.when_to_sell_target || s?.stop_loss || s?.entry_low || s?.target_num || s?.stop_num);
  }
  get entryZone(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    if (!s) return null;
    if (s.when_to_buy_entry) return s.when_to_buy_entry;
    if (s.entry_low != null && s.entry_high != null)
      return `${fmtPrice(s.entry_low)} – ${fmtPrice(s.entry_high)}`;
    if (s.entry_low != null) return fmtPrice(s.entry_low);
    return null;
  }
  get swingTarget(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    if (!s) return null;
    if (s.when_to_sell_target) return s.when_to_sell_target;
    if (s.short_term_target) return s.short_term_target;
    if (s.target_num != null) return fmtPrice(s.target_num);
    return null;
  }
  get stopLoss(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    if (!s) return null;
    if (s.stop_loss) return s.stop_loss;
    if (s.stop_num != null) return fmtPrice(s.stop_num);
    return null;
  }
  get intrinsicValueDisplay(): string | null {
    const sig = this.stock.synth_output?.structured_signal;
    const forensic = this.stock.fund_output?.forensic_analysis;
    const fVal = sig?.intrinsic_fair_value || forensic?.fair_value || forensic?.valuation_metrics?.intrinsic_fair_value;
    if (fVal && fVal !== 'N/A') {
      const num = Number(fVal);
      if (!isNaN(num) && num > 0) return fmtPrice(num);
      return String(fVal);
    }
    return null;
  }
  get marginOfSafetyPct(): number | null {
    const sig = this.stock.synth_output?.structured_signal;
    const forensic = this.stock.fund_output?.forensic_analysis;
    const mos = sig?.margin_of_safety_pct ?? forensic?.margin_of_safety_pct ?? forensic?.valuation_metrics?.margin_of_safety_pct ?? null;
    return typeof mos === 'number' && !isNaN(mos) ? mos : null;
  }
  get horizon(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    return s?.holding_horizon || s?.short_term_horizon || 'Short-Term (1-3 Weeks)';
  }

  /* ── Long-term (Safely handles strings & numbers without NaN) ── */
  get hasLongTerm(): boolean {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    return !!(lt?.long_term_target || lt?.long_term_verdict);
  }
  get longTermBadge(): string | null {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    return lt?.is_top_wealth_pick ? 'Long-Term Pick' : null;
  }
  get ltTargetDisplay(): string | null {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    const raw = lt?.long_term_target;
    if (raw === null || raw === undefined) return null;
    if (typeof raw === 'string') {
      const trimmed = raw.trim();
      if (!trimmed || trimmed.toUpperCase() === 'N/A' || trimmed === '—' || trimmed === '-') return null;
      return trimmed.startsWith('Rs.') ? trimmed : `Rs. ${trimmed}`;
    }
    return fmtPrice(raw);
  }
  get ltGainPctDisplay(): string | null {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    if (lt?.long_term_upside_pct != null) {
      const raw = String(lt.long_term_upside_pct).trim();
      if (!raw || raw.toUpperCase() === 'N/A' || raw === '—') return null;
      return (raw.startsWith('+') || raw.startsWith('-')) ? raw : `+${raw}`;
    }
    const tNum = lt?.long_term_target_num || (typeof lt?.long_term_target === 'number' ? lt.long_term_target : null);
    const p = this.stock.price_info?.price;
    if (tNum && p && p > 0) {
      const pctNum = (tNum - p) / p * 100;
      const pct = pctNum.toFixed(1);
      return pctNum >= 0 ? `+${pct}%` : `${pct}%`;
    }
    return null;
  }
  get ltVerdictText(): string | null {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    return lt?.long_term_verdict ?? null;
  }
  get ltMoatText(): string | null {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    return lt?.long_term_moat ?? null;
  }
  get ltPeers(): string[] {
    const lt = this.stock.long_term_signal || this.stock.synth_output?.structured_signal?.long_term_signal;
    return lt?.suggested_long_term_peers?.slice(0, 4) ?? [];
  }

  /* ── Report Snippet ── */
  get reportSnippet(): string | null {
    const s = this.stock.synth_output?.structured_signal;
    if (s?.key_rationale) return s.key_rationale;
    if (s?.actionable_recommendation) return s.actionable_recommendation;
    return null;
  }
}
