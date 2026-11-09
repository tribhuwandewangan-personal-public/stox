/**
 * Candle chart: Full candlestick history with auto-scale and grid.
 * Ports canvas drawing logic from legacy static/index.html
 */

import { Component, Input, ViewChild, ElementRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Candle } from '../../core/models/stock.model';

@Component({
  selector: 'app-candle-chart',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chart-container">
      <canvas #chartCanvas class="chart-canvas"></canvas>
      <div class="chart-info" *ngIf="candles.length > 0">
        <span class="info-label">{{ candles.length }} candles</span>
        <span class="info-label">Latest: Rs. {{ latestClose | number:'1.2-2' }}</span>
      </div>
    </div>
  `,
  styles: [`
    .chart-container {
      position: relative;
      width: 100%;
      height: 300px;
      background: rgba(15, 23, 42, 0.4);
      border-radius: 8px;
      border: 1px solid rgba(56, 189, 248, 0.2);
      overflow: hidden;
    }

    .chart-canvas {
      width: 100%;
      height: 100%;
      display: block;
    }

    .chart-info {
      position: absolute;
      bottom: 8px;
      right: 12px;
      display: flex;
      gap: 16px;
      font-size: 11px;
      color: var(--text-muted);
      background: rgba(0, 0, 0, 0.3);
      padding: 6px 10px;
      border-radius: 4px;
    }

    .info-label {
      white-space: nowrap;
    }
  `]
})
export class CandleChartComponent implements OnInit, OnDestroy {
  @Input() candles: Candle[] = [];
  @ViewChild('chartCanvas', { static: false }) canvasRef!: ElementRef<HTMLCanvasElement>;

  private resizeObserver: ResizeObserver | null = null;

  get latestClose(): number {
    if (this.candles.length === 0) return 0;
    return this.candles[this.candles.length - 1].CLOSE_PRICE;
  }

  ngOnInit(): void {
    setTimeout(() => this.draw());
    this.setupResizeObserver();
  }

  ngOnDestroy(): void {
    if (this.resizeObserver) {
      this.resizeObserver.disconnect();
    }
  }

  private setupResizeObserver(): void {
    if (!this.canvasRef) return;

    this.resizeObserver = new ResizeObserver(() => {
      this.draw();
    });

    this.resizeObserver.observe(this.canvasRef.nativeElement.parentElement!);
  }

  private draw(): void {
    if (!this.canvasRef || !this.candles || this.candles.length === 0) return;

    const canvas = this.canvasRef.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.max(1, rect.width * dpr);
    canvas.height = Math.max(1, rect.height * dpr);

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);

    const width = rect.width;
    const height = rect.height;

    // Calculate price range
    let minPrice = Infinity;
    let maxPrice = -Infinity;

    for (const candle of this.candles) {
      minPrice = Math.min(minPrice, candle.LOW_PRICE);
      maxPrice = Math.max(maxPrice, candle.HIGH_PRICE);
    }

    const range = maxPrice - minPrice || 1;
    const padding = { top: 20, bottom: 30, left: 40, right: 20 };
    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;

    // Draw background grid
    ctx.fillStyle = 'rgba(56, 189, 248, 0.03)';
    ctx.fillRect(padding.left, padding.top, chartWidth, chartHeight);

    // Draw horizontal grid lines
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.1)';
    ctx.lineWidth = 0.5;
    ctx.font = '11px Inter';
    ctx.fillStyle = 'rgba(156, 163, 175, 0.6)';
    ctx.textAlign = 'right';

    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartHeight / 4) * i;
      const price = maxPrice - (range / 4) * i;

      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      ctx.fillText(price.toFixed(0), padding.left - 8, y + 4);
    }

    // Draw candlesticks
    const candleWidth = chartWidth / this.candles.length;
    const wickWidth = Math.max(1, candleWidth * 0.3);

    for (let i = 0; i < this.candles.length; i++) {
      const candle = this.candles[i];
      const x = padding.left + i * candleWidth + candleWidth / 2;

      // Price to Y coordinate
      const toY = (price: number) =>
        padding.top + chartHeight - ((price - minPrice) / range) * chartHeight;

      const highY = toY(candle.HIGH_PRICE);
      const lowY = toY(candle.LOW_PRICE);
      const openY = toY(candle.OPEN_PRICE);
      const closeY = toY(candle.CLOSE_PRICE);

      const isGreen = candle.CLOSE_PRICE >= candle.OPEN_PRICE;
      const bodyTop = Math.min(openY, closeY);
      const bodyBottom = Math.max(openY, closeY);
      const bodyHeight = Math.max(bodyBottom - bodyTop, 1);

      // Wick
      ctx.strokeStyle = isGreen
        ? 'rgba(16, 185, 129, 0.6)'
        : 'rgba(239, 68, 68, 0.6)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, highY);
      ctx.lineTo(x, lowY);
      ctx.stroke();

      // Body
      ctx.fillStyle = isGreen
        ? 'rgba(16, 185, 129, 0.8)'
        : 'rgba(239, 68, 68, 0.8)';
      ctx.fillRect(
        x - wickWidth / 2,
        bodyTop,
        wickWidth,
        bodyHeight
      );
    }

    // Draw price axis labels
    ctx.font = 'bold 12px Inter';
    ctx.fillStyle = 'var(--text-main)';
    ctx.textAlign = 'center';
    ctx.fillText('Date', width / 2, height - 8);
  }
}
