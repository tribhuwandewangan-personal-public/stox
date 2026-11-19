/**
 * Candle chart: Interactive candlestick chart with Moving Average (MA) trend analysis,
 * fast/slow SMA curves (SMA 20 & SMA 50), automatic Golden/Death & 20/50 crossover detection,
 * trend regime badges, crosshairs, and inspection tooltips.
 */

import {
  Component,
  Input,
  ViewChild,
  ElementRef,
  OnInit,
  AfterViewInit,
  OnDestroy,
  OnChanges,
  SimpleChanges
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { Candle } from '../../core/models/stock.model';

export interface NormalizedCandle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  sma20: number | null;
  sma50: number | null;
  sma200: number | null;
  bbUpper?: number | null;
  bbLower?: number | null;
  crossover?: 'bullish' | 'bearish' | null;
}

export interface CrossoverEvent {
  type: 'bullish' | 'bearish';
  date: string;
  barsAgo: number;
}

export type TrendRegime = 'STRONG_BULLISH' | 'BULLISH' | 'BEARISH' | 'STRONG_BEARISH' | 'NEUTRAL';

@Component({
  selector: 'app-candle-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chart-wrapper">
      <!-- Trend & MA Crossover Header -->
      <div class="chart-header" *ngIf="normalizedCandles.length > 0">
        <div class="trend-badge-group">
          <!-- Trend Badge -->
          <div class="trend-pill" [ngClass]="'trend-' + trend.toLowerCase()">
            <span class="trend-icon">{{ getTrendIcon() }}</span>
            <span class="trend-text">{{ getTrendLabel() }}</span>
          </div>

          <!-- Latest Crossover Badge -->
          <div
            class="crossover-badge"
            *ngIf="latestCrossover"
            [ngClass]="'cross-' + latestCrossover.type"
            [title]="'MA Crossover occurred on ' + latestCrossover.date"
          >
            <span class="cross-icon">{{ latestCrossover.type === 'bullish' ? '▲' : '▼' }}</span>
            <span class="cross-label">
              {{ latestCrossover.type === 'bullish' ? 'Bullish Cross' : 'Bearish Cross' }}
              ({{ latestCrossover.barsAgo === 0 ? 'Today' : latestCrossover.barsAgo + ' bars ago' }})
            </span>
          </div>
        </div>

        <!-- MA Value Chips -->
        <div class="ma-metrics" *ngIf="latestCandle">
          <div class="metric-chip">
            <span class="metric-label">LTP:</span>
            <span class="metric-val">₹{{ latestCandle.close | number:'1.2-2' }}</span>
          </div>
          <div class="metric-chip chip-sma20" *ngIf="showSma20 && latestCandle.sma20">
            <span class="dot dot-sma20"></span>
            <span class="metric-label">SMA 20:</span>
            <span class="metric-val">₹{{ latestCandle.sma20 | number:'1.2-2' }}</span>
          </div>
          <div class="metric-chip chip-sma50" *ngIf="showSma50 && latestCandle.sma50">
            <span class="dot dot-sma50"></span>
            <span class="metric-label">SMA 50:</span>
            <span class="metric-val">₹{{ latestCandle.sma50 | number:'1.2-2' }}</span>
          </div>
          <div class="metric-chip" *ngIf="maSpread !== null">
            <span class="metric-label">Spread:</span>
            <span class="metric-val" [ngClass]="maSpread >= 0 ? 'text-green' : 'text-red'">
              {{ maSpread >= 0 ? '+' : '' }}{{ maSpread | number:'1.2-2' }}%
            </span>
          </div>
        </div>

        <!-- Chart Toggles -->
        <div class="chart-toggles">
          <button
            type="button"
            class="toggle-btn"
            [class.active]="showSma20"
            (click)="toggleSma20()"
            title="Toggle 20-Day Simple Moving Average"
          >
            <span class="toggle-dot sma20-color"></span> SMA 20
          </button>
          <button
            type="button"
            class="toggle-btn"
            [class.active]="showSma50"
            (click)="toggleSma50()"
            title="Toggle 50-Day Simple Moving Average"
          >
            <span class="toggle-dot sma50-color"></span> SMA 50
          </button>
          <button
            type="button"
            class="toggle-btn"
            [class.active]="showCrossovers"
            (click)="toggleCrossovers()"
            title="Toggle Crossover Markers on chart"
          >
            🎯 Cross Marks
          </button>
        </div>
      </div>

      <!-- Main Canvas Container -->
      <div class="chart-canvas-container" #containerRef>
        <canvas
          #chartCanvas
          class="chart-canvas"
          (mousemove)="onMouseMove($event)"
          (mouseleave)="onMouseLeave()"
        ></canvas>

        <!-- Floating HUD Tooltip on Hover -->
        <div class="chart-hud" *ngIf="hoveredCandle">
          <div class="hud-item date">
            <strong>{{ hoveredCandle.date }}</strong>
          </div>
          <div class="hud-item">
            <span>O:</span> {{ hoveredCandle.open | number:'1.2-2' }}
          </div>
          <div class="hud-item">
            <span>H:</span> <span class="text-green">{{ hoveredCandle.high | number:'1.2-2' }}</span>
          </div>
          <div class="hud-item">
            <span>L:</span> <span class="text-red">{{ hoveredCandle.low | number:'1.2-2' }}</span>
          </div>
          <div class="hud-item">
            <span>C:</span> <strong class="text-sky">{{ hoveredCandle.close | number:'1.2-2' }}</strong>
          </div>
          <div class="hud-item" *ngIf="hoveredCandle.sma20">
            <span class="text-sma20">SMA20:</span> {{ hoveredCandle.sma20 | number:'1.2-2' }}
          </div>
          <div class="hud-item" *ngIf="hoveredCandle.sma50">
            <span class="text-sma50">SMA50:</span> {{ hoveredCandle.sma50 | number:'1.2-2' }}
          </div>
          <div class="hud-item cross-pill" *ngIf="hoveredCandle.crossover" [ngClass]="'cross-' + hoveredCandle.crossover">
            {{ hoveredCandle.crossover === 'bullish' ? '▲ Bullish Cross' : '▼ Bearish Cross' }}
          </div>
        </div>
      </div>

      <!-- Footer Legend -->
      <div class="chart-legend">
        <div class="legend-item">
          <span class="legend-color candle-bull"></span> Bull Candle
        </div>
        <div class="legend-item">
          <span class="legend-color candle-bear"></span> Bear Candle
        </div>
        <div class="legend-item" *ngIf="showSma20">
          <span class="legend-color sma20-line"></span> SMA 20 (Fast Trend)
        </div>
        <div class="legend-item" *ngIf="showSma50">
          <span class="legend-color sma50-line"></span> SMA 50 (Slow Trend)
        </div>
        <div class="legend-item" *ngIf="showCrossovers">
          <span class="legend-marker cross-bull">▲</span> Bullish Crossover
        </div>
        <div class="legend-item" *ngIf="showCrossovers">
          <span class="legend-marker cross-bear">▼</span> Bearish Crossover
        </div>
      </div>
    </div>
  `,
  styles: [`
    .chart-wrapper {
      display: flex;
      flex-direction: column;
      width: 100%;
      height: 100%;
      background: rgba(15, 23, 42, 0.5);
      border-radius: 8px;
      border: 1px solid rgba(56, 189, 248, 0.2);
      overflow: hidden;
      box-sizing: border-box;
    }

    /* Top Trend Header */
    .chart-header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 8px 14px;
      background: rgba(15, 23, 42, 0.7);
      border-bottom: 1px solid rgba(56, 189, 248, 0.15);
      font-size: 11px;
    }

    .trend-badge-group {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .trend-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 6px;
      font-weight: 700;
      letter-spacing: 0.3px;
      font-size: 11px;
      text-transform: uppercase;
    }

    .trend-strong_bullish {
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid #10b981;
      color: #34d399;
    }

    .trend-bullish {
      background: rgba(56, 189, 248, 0.2);
      border: 1px solid #38bdf8;
      color: #7dd3fc;
    }

    .trend-bearish {
      background: rgba(245, 158, 11, 0.2);
      border: 1px solid #f59e0b;
      color: #fbbf24;
    }

    .trend-strong_bearish {
      background: rgba(239, 68, 68, 0.2);
      border: 1px solid #ef4444;
      color: #f87171;
    }

    .trend-neutral {
      background: rgba(148, 163, 184, 0.15);
      border: 1px solid #64748b;
      color: #cbd5e1;
    }

    .crossover-badge {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 4px 8px;
      border-radius: 6px;
      font-weight: 600;
      font-size: 10.5px;
    }

    .crossover-badge.cross-bullish {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.5);
      color: #10b981;
    }

    .crossover-badge.cross-bearish {
      background: rgba(239, 68, 68, 0.15);
      border: 1px solid rgba(239, 68, 68, 0.5);
      color: #ef4444;
    }

    .ma-metrics {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .metric-chip {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      background: rgba(0, 0, 0, 0.35);
      padding: 3px 8px;
      border-radius: 4px;
      border: 1px solid rgba(255, 255, 255, 0.06);
    }

    .metric-label {
      color: #94a3b8;
    }

    .metric-val {
      font-family: 'JetBrains Mono', monospace;
      font-weight: 600;
      color: #f1f5f9;
    }

    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
    }

    .dot-sma20 {
      background: #38bdf8;
    }

    .dot-sma50 {
      background: #f59e0b;
    }

    .text-green { color: #10b981; }
    .text-red { color: #ef4444; }
    .text-sky { color: #38bdf8; }
    .text-sma20 { color: #38bdf8; }
    .text-sma50 { color: #f59e0b; }

    /* Chart Controls */
    .chart-toggles {
      display: flex;
      gap: 6px;
    }

    .toggle-btn {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 600;
      background: rgba(30, 41, 59, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8;
      cursor: pointer;
      transition: all 0.15s ease;
    }

    .toggle-btn:hover {
      border-color: rgba(56, 189, 248, 0.4);
      color: #f1f5f9;
    }

    .toggle-btn.active {
      background: rgba(56, 189, 248, 0.15);
      border-color: #38bdf8;
      color: #38bdf8;
    }

    .toggle-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
    }

    .sma20-color { background: #38bdf8; }
    .sma50-color { background: #f59e0b; }

    /* Canvas Area */
    .chart-canvas-container {
      position: relative;
      flex: 1;
      width: 100%;
      min-height: 260px;
    }

    .chart-canvas {
      width: 100%;
      height: 100%;
      display: block;
      cursor: crosshair;
    }

    /* Floating Tooltip */
    .chart-hud {
      position: absolute;
      top: 10px;
      left: 14px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 10px;
      padding: 5px 10px;
      background: rgba(15, 23, 42, 0.88);
      backdrop-filter: blur(8px);
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 6px;
      font-size: 11px;
      pointer-events: none;
      z-index: 10;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }

    .hud-item {
      font-family: 'JetBrains Mono', monospace;
      color: #cbd5e1;
    }

    .hud-item span {
      color: #94a3b8;
      font-size: 10px;
    }

    .cross-pill {
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
    }

    .cross-pill.cross-bullish {
      background: rgba(16, 185, 129, 0.2);
      color: #34d399;
      border: 1px solid #10b981;
    }

    .cross-pill.cross-bearish {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid #ef4444;
    }

    /* Footer Legend */
    .chart-legend {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 16px;
      padding: 6px 14px;
      background: rgba(15, 23, 42, 0.7);
      border-top: 1px solid rgba(255, 255, 255, 0.05);
      font-size: 10.5px;
      color: #94a3b8;
    }

    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }

    .legend-color {
      width: 10px;
      height: 10px;
      border-radius: 2px;
      display: inline-block;
    }

    .candle-bull { background: #10b981; }
    .candle-bear { background: #ef4444; }

    .sma20-line {
      width: 14px;
      height: 2px;
      background: #38bdf8;
    }

    .sma50-line {
      width: 14px;
      height: 2px;
      background: #f59e0b;
    }

    .legend-marker {
      font-size: 11px;
      font-weight: bold;
    }

    .cross-bull { color: #10b981; }
    .cross-bear { color: #ef4444; }
  `]
})
export class CandleChartComponent implements OnInit, AfterViewInit, OnDestroy, OnChanges {
  @Input() candles: Candle[] = [];
  @ViewChild('chartCanvas', { static: false }) canvasRef!: ElementRef<HTMLCanvasElement>;
  @ViewChild('containerRef', { static: false }) containerRef!: ElementRef<HTMLDivElement>;

  normalizedCandles: NormalizedCandle[] = [];
  trend: TrendRegime = 'NEUTRAL';
  latestCrossover: CrossoverEvent | null = null;
  hoveredCandle: NormalizedCandle | null = null;
  hoveredIndex: number | null = null;

  showSma20: boolean = true;
  showSma50: boolean = true;
  showCrossovers: boolean = true;

  private resizeObserver: ResizeObserver | null = null;
  private mousePos: { x: number; y: number } | null = null;

  get latestCandle(): NormalizedCandle | null {
    if (this.normalizedCandles.length === 0) return null;
    return this.normalizedCandles[this.normalizedCandles.length - 1];
  }

  get latestClose(): number {
    return this.latestCandle ? this.latestCandle.close : 0;
  }

  get maSpread(): number | null {
    const c = this.latestCandle;
    if (!c || c.sma20 == null || c.sma50 == null || c.sma50 === 0) return null;
    return ((c.sma20 - c.sma50) / c.sma50) * 100;
  }

  ngOnInit(): void {
    this.processCandles();
    setTimeout(() => this.draw(), 50);
  }

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['candles']) {
      this.processCandles();
      setTimeout(() => this.draw(), 20);
    }
  }

  ngAfterViewInit(): void {
    this.setupResizeObserver();
    setTimeout(() => this.draw(), 0);
  }

  ngOnDestroy(): void {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
  }

  toggleSma20(): void {
    this.showSma20 = !this.showSma20;
    this.draw();
  }

  toggleSma50(): void {
    this.showSma50 = !this.showSma50;
    this.draw();
  }

  toggleCrossovers(): void {
    this.showCrossovers = !this.showCrossovers;
    this.draw();
  }

  getTrendIcon(): string {
    switch (this.trend) {
      case 'STRONG_BULLISH': return '🚀';
      case 'BULLISH': return '📈';
      case 'STRONG_BEARISH': return '🔻';
      case 'BEARISH': return '📉';
      default: return '⚖️';
    }
  }

  getTrendLabel(): string {
    switch (this.trend) {
      case 'STRONG_BULLISH': return 'Strong Bullish (Price > SMA20 > SMA50)';
      case 'BULLISH': return 'Bullish MA Trend (SMA20 > SMA50)';
      case 'STRONG_BEARISH': return 'Strong Bearish (Price < SMA20 < SMA50)';
      case 'BEARISH': return 'Bearish MA Trend (SMA20 < SMA50)';
      default: return 'Consolidation / Neutral Trend';
    }
  }

  private processCandles(): void {
    if (!this.candles || this.candles.length === 0) {
      this.normalizedCandles = [];
      this.trend = 'NEUTRAL';
      this.latestCrossover = null;
      return;
    }

    // 1. Normalize candles from uppercase or lowercase properties
    const list: NormalizedCandle[] = this.candles.map(c => {
      const open = Number(c.OPEN_PRICE ?? c.open ?? 0);
      const close = Number(c.CLOSE_PRICE ?? c.close ?? open);
      const high = Number(c.HIGH_PRICE ?? c.high ?? Math.max(open, close));
      const low = Number(c.LOW_PRICE ?? c.low ?? Math.min(open, close));
      const volume = Number(c.VOLUME ?? c.volume ?? 0);
      const date = String(c.DATE ?? c.date ?? '');

      return {
        date,
        open,
        high,
        low,
        close,
        volume,
        sma20: c.sma_20 != null ? Number(c.sma_20) : null,
        sma50: c.sma_50 != null ? Number(c.sma_50) : null,
        sma200: c.sma_200 != null ? Number(c.sma_200) : null,
        bbUpper: c.bb_upper != null ? Number(c.bb_upper) : null,
        bbLower: c.bb_lower != null ? Number(c.bb_lower) : null,
        crossover: null
      };
    });

    // 2. Fallback client-side SMA calculation if missing from source
    const closes = list.map(c => c.close);
    const needSma20 = list.some(c => c.sma20 === null) && list.length >= 20;
    const needSma50 = list.some(c => c.sma50 === null) && list.length >= 50;

    if (needSma20) {
      const calc20 = this.calculateRollingSMA(closes, 20);
      for (let i = 0; i < list.length; i++) {
        if (list[i].sma20 === null) list[i].sma20 = calc20[i];
      }
    }

    if (needSma50) {
      const calc50 = this.calculateRollingSMA(closes, 50);
      for (let i = 0; i < list.length; i++) {
        if (list[i].sma50 === null) list[i].sma50 = calc50[i];
      }
    }

    // 3. Detect MA Crossovers across the history
    this.latestCrossover = null;
    for (let i = 1; i < list.length; i++) {
      const prev = list[i - 1];
      const curr = list[i];

      if (prev.sma20 != null && prev.sma50 != null && curr.sma20 != null && curr.sma50 != null) {
        if (prev.sma20 <= prev.sma50 && curr.sma20 > curr.sma50) {
          curr.crossover = 'bullish';
        } else if (prev.sma20 >= prev.sma50 && curr.sma20 < curr.sma50) {
          curr.crossover = 'bearish';
        }
      }
    }

    // Identify latest crossover
    for (let i = list.length - 1; i >= 0; i--) {
      if (list[i].crossover) {
        this.latestCrossover = {
          type: list[i].crossover!,
          date: list[i].date,
          barsAgo: list.length - 1 - i
        };
        break;
      }
    }

    // 4. Determine current trend regime
    const last = list[list.length - 1];
    if (last && last.sma20 != null && last.sma50 != null) {
      if (last.close > last.sma20 && last.sma20 > last.sma50) {
        this.trend = 'STRONG_BULLISH';
      } else if (last.sma20 > last.sma50) {
        this.trend = 'BULLISH';
      } else if (last.close < last.sma20 && last.sma20 < last.sma50) {
        this.trend = 'STRONG_BEARISH';
      } else if (last.sma20 < last.sma50) {
        this.trend = 'BEARISH';
      } else {
        this.trend = 'NEUTRAL';
      }
    } else {
      this.trend = 'NEUTRAL';
    }

    this.normalizedCandles = list;
  }

  private calculateRollingSMA(data: number[], window: number): (number | null)[] {
    const res: (number | null)[] = [];
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      sum += data[i];
      if (i >= window) {
        sum -= data[i - window];
      }
      if (i >= window - 1) {
        res.push(Number((sum / window).toFixed(2)));
      } else {
        res.push(null);
      }
    }
    return res;
  }

  private setupResizeObserver(): void {
    if (!this.containerRef) return;

    this.resizeObserver = new ResizeObserver(() => {
      this.draw();
    });

    this.resizeObserver.observe(this.containerRef.nativeElement);
  }

  onMouseMove(e: MouseEvent): void {
    if (!this.canvasRef || this.normalizedCandles.length === 0) return;
    const canvas = this.canvasRef.nativeElement;
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    this.mousePos = { x: mouseX, y: mouseY };

    const padding = { top: 20, bottom: 26, left: 45, right: 20 };
    const chartWidth = rect.width - padding.left - padding.right;
    const n = this.normalizedCandles.length;

    if (mouseX >= padding.left && mouseX <= rect.width - padding.right) {
      const idx = Math.min(n - 1, Math.max(0, Math.round(((mouseX - padding.left) / chartWidth) * (n - 1))));
      this.hoveredIndex = idx;
      this.hoveredCandle = this.normalizedCandles[idx];
    } else {
      this.hoveredIndex = null;
      this.hoveredCandle = null;
    }

    this.draw();
  }

  onMouseLeave(): void {
    this.mousePos = null;
    this.hoveredIndex = null;
    this.hoveredCandle = null;
    this.draw();
  }

  private draw(): void {
    if (!this.canvasRef || this.normalizedCandles.length === 0) return;

    const canvas = this.canvasRef.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const rawWidth = rect.width || canvas.parentElement?.offsetWidth || 600;
    const rawHeight = rect.height || canvas.parentElement?.offsetHeight || 300;

    if (rawWidth < 20 || rawHeight < 20) {
      setTimeout(() => this.draw(), 60);
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, rawWidth * dpr);
    canvas.height = Math.max(1, rawHeight * dpr);

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rawWidth, rawHeight);

    const width = rawWidth;
    const height = rawHeight;
    const candles = this.normalizedCandles;
    const n = candles.length;

    // Price scaling
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    for (const c of candles) {
      if (c.low > 0 && c.low < minPrice) minPrice = c.low;
      if (c.high > maxPrice) maxPrice = c.high;
      if (this.showSma20 && c.sma20) {
        if (c.sma20 < minPrice) minPrice = c.sma20;
        if (c.sma20 > maxPrice) maxPrice = c.sma20;
      }
      if (this.showSma50 && c.sma50) {
        if (c.sma50 < minPrice) minPrice = c.sma50;
        if (c.sma50 > maxPrice) maxPrice = c.sma50;
      }
    }

    if (!isFinite(minPrice) || minPrice <= 0) minPrice = 100;
    if (!isFinite(maxPrice) || maxPrice <= minPrice) maxPrice = minPrice * 1.1;

    // Margin padding for chart aesthetics
    const pad = (maxPrice - minPrice) * 0.08 || 5;
    minPrice -= pad;
    maxPrice += pad;
    const range = Math.max(maxPrice - minPrice, 0.01);

    const padding = { top: 20, bottom: 26, left: 45, right: 20 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    const toX = (i: number) => padding.left + (i / Math.max(1, n - 1)) * chartWidth;
    const toY = (price: number) => padding.top + chartHeight - ((price - minPrice) / range) * chartHeight;

    // 1. Background Grid & Shading
    ctx.fillStyle = 'rgba(56, 189, 248, 0.02)';
    ctx.fillRect(padding.left, padding.top, chartWidth, chartHeight);

    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 0.8;
    ctx.font = '10px JetBrains Mono, monospace';
    ctx.fillStyle = 'rgba(148, 163, 184, 0.7)';
    ctx.textAlign = 'right';

    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
      const y = padding.top + (chartHeight / gridLines) * i;
      const price = maxPrice - (range / gridLines) * i;

      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + chartWidth, y);
      ctx.stroke();

      ctx.fillText(price.toFixed(1), padding.left - 6, y + 3);
    }

    // 2. Draw Candlesticks
    const candleWidth = Math.max(2.5, (chartWidth / n) * 0.65);
    const wickWidth = Math.max(1, candleWidth * 0.25);

    for (let i = 0; i < n; i++) {
      const c = candles[i];
      const x = toX(i);
      const isUp = c.close >= c.open;
      const color = isUp ? '#10b981' : '#ef4444';

      const highY = toY(c.high);
      const lowY = toY(c.low);
      const openY = toY(c.open);
      const closeY = toY(c.close);

      // Wick
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      const bodyTop = Math.min(openY, closeY);
      const bodyHeight = Math.max(Math.abs(closeY - openY), 1.5);

      ctx.fillStyle = isUp ? 'rgba(16, 185, 129, 0.85)' : 'rgba(239, 68, 68, 0.85)';
      ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
    }

    // 3. Draw Moving Average Lines
    // SMA 50 Line (Amber / Gold)
    if (this.showSma50) {
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = '#f59e0b';
      ctx.beginPath();
      let started50 = false;
      for (let i = 0; i < n; i++) {
        if (candles[i].sma50 != null) {
          const x = toX(i);
          const y = toY(candles[i].sma50!);
          if (!started50) {
            ctx.moveTo(x, y);
            started50 = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    }

    // SMA 20 Line (Sky Blue / Cyan)
    if (this.showSma20) {
      ctx.lineWidth = 1.8;
      ctx.strokeStyle = '#38bdf8';
      ctx.beginPath();
      let started20 = false;
      for (let i = 0; i < n; i++) {
        if (candles[i].sma20 != null) {
          const x = toX(i);
          const y = toY(candles[i].sma20!);
          if (!started20) {
            ctx.moveTo(x, y);
            started20 = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      }
      ctx.stroke();
    }

    // 4. Draw Crossover Markers on Canvas
    if (this.showCrossovers) {
      for (let i = 0; i < n; i++) {
        const c = candles[i];
        if (!c.crossover) continue;

        const x = toX(i);
        const isBull = c.crossover === 'bullish';

        if (isBull) {
          // Bullish Golden Cross marker below the low
          const y = toY(c.low) + 14;

          // Glowing circular badge
          ctx.beginPath();
          ctx.arc(x, y, 7, 0, Math.PI * 2);
          ctx.fillStyle = '#10b981';
          ctx.shadowColor = 'rgba(16, 185, 129, 0.7)';
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0;

          // Inner arrow
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 9px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('▲', x, y + 3);

          // Annotation tag
          ctx.font = 'bold 8.5px Inter, sans-serif';
          ctx.fillStyle = '#34d399';
          ctx.fillText('MA Cross', x, y + 15);
        } else {
          // Bearish Death Cross marker above the high
          const y = toY(c.high) - 14;

          // Glowing circular badge
          ctx.beginPath();
          ctx.arc(x, y, 7, 0, Math.PI * 2);
          ctx.fillStyle = '#ef4444';
          ctx.shadowColor = 'rgba(239, 68, 68, 0.7)';
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0;

          // Inner arrow
          ctx.fillStyle = '#ffffff';
          ctx.font = 'bold 9px sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText('▼', x, y + 3);

          // Annotation tag
          ctx.font = 'bold 8.5px Inter, sans-serif';
          ctx.fillStyle = '#f87171';
          ctx.fillText('MA Cross', x, y - 9);
        }
      }
    }

    // 5. Interactive Crosshair & Highlight
    if (this.hoveredIndex !== null && this.mousePos) {
      const idx = this.hoveredIndex;
      const c = candles[idx];
      const hX = toX(idx);
      const hY = toY(c.close);

      // Vertical guideline
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 3]);

      ctx.beginPath();
      ctx.moveTo(hX, padding.top);
      ctx.lineTo(hX, padding.top + chartHeight);
      ctx.stroke();

      // Horizontal guideline
      ctx.beginPath();
      ctx.moveTo(padding.left, hY);
      ctx.lineTo(padding.left + chartWidth, hY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Highlight point on Close
      ctx.beginPath();
      ctx.arc(hX, hY, 4, 0, Math.PI * 2);
      ctx.fillStyle = '#38bdf8';
      ctx.fill();

      // Highlight point on SMA 20
      if (this.showSma20 && c.sma20) {
        ctx.beginPath();
        ctx.arc(hX, toY(c.sma20), 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#38bdf8';
        ctx.fill();
      }

      // Highlight point on SMA 50
      if (this.showSma50 && c.sma50) {
        ctx.beginPath();
        ctx.arc(hX, toY(c.sma50), 3.5, 0, Math.PI * 2);
        ctx.fillStyle = '#f59e0b';
        ctx.fill();
      }
    }

    // 6. Date Axis Labels
    ctx.font = '10px Inter, sans-serif';
    ctx.fillStyle = 'rgba(148, 163, 184, 0.7)';
    ctx.textAlign = 'center';

    const dateStep = Math.max(1, Math.floor(n / 6));
    for (let i = 0; i < n; i += dateStep) {
      const x = toX(i);
      const d = candles[i].date ? candles[i].date.substring(5) : '';
      ctx.fillText(d, x, height - 8);
    }
    // Also draw the last date
    if (n > 1 && (n - 1) % dateStep !== 0) {
      const x = toX(n - 1);
      const d = candles[n - 1].date ? candles[n - 1].date.substring(5) : '';
      ctx.fillText(d, x, height - 8);
    }
  }
}
