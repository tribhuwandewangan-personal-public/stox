/**
 * Sparkline: Mini canvas chart for last 25 candles.
 * Auto-scales and responds to window resize.
 */

import { Component, Input, ViewChild, ElementRef, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-sparkline',
  standalone: true,
  imports: [CommonModule],
  template: `
    <canvas #sparklineCanvas class="sparkline-canvas"></canvas>
  `,
  styles: [`
    .sparkline-canvas {
      width: 100%;
      height: 40px;
      display: block;
      opacity: 0.8;
    }
  `]
})
export class SparklineComponent implements OnInit, OnDestroy {
  @Input() data: number[] = [];
  @ViewChild('sparklineCanvas', { static: false }) canvasRef!: ElementRef<HTMLCanvasElement>;

  private resizeObserver: ResizeObserver | null = null;

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
    if (!this.canvasRef || !this.data || this.data.length === 0) return;

    const canvas = this.canvasRef.nativeElement;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;

    canvas.width = Math.max(1, rect.width * dpr);
    canvas.height = Math.max(1, rect.height * dpr);

    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, rect.width, rect.height);

    if (this.data.length < 2) return;

    const width = rect.width;
    const height = rect.height;
    const min = Math.min(...this.data);
    const max = Math.max(...this.data);
    const range = max - min || 1;

    const candleWidth = width / this.data.length;
    const padding = 2;

    // Draw background (optional)
    ctx.fillStyle = 'rgba(56, 189, 248, 0.05)';
    ctx.fillRect(0, 0, width, height);

    // Draw line
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.6)';
    ctx.lineWidth = 1.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();

    for (let i = 0; i < this.data.length; i++) {
      const x = i * candleWidth + candleWidth / 2;
      const y = height - ((this.data[i] - min) / range) * (height - padding * 2) - padding;

      if (i === 0) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
    }

    ctx.stroke();

    // Draw area fill
    ctx.lineTo(width, height);
    ctx.lineTo(0, height);
    ctx.closePath();
    ctx.fillStyle = 'rgba(56, 189, 248, 0.1)';
    ctx.fill();
  }
}
