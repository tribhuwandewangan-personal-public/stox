/**
 * Bulletin component: Full-width live market bulletin matching Jinja UI.
 * Displays macroeconomic sentiment pill, summary rationale, and link to latest news report.
 */

import { Component, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AppStore } from '../../core/stores/app.store';

@Component({
  selector: 'app-bulletin',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="bulletin-wrapper" *ngIf="bulletinData() as b">
      <div class="bulletin-card">
        <div class="bulletin-header">
          <div class="bulletin-title">
            <span class="icon">🌐</span> LIVE COMMON MARKET BULLETIN
          </div>
          <span class="sentiment-pill" [ngClass]="sentimentClass(b.sentiment_label)">
            {{ (b.sentiment_label || 'NEUTRAL') | uppercase }} ALIGNMENT
          </span>
        </div>

        <div class="bulletin-body">
          {{ b.summary || 'Synthesizing common global market tailwinds (S&P 500 futures, Crude Oil, DXY Dollar Index)...' }}
        </div>

        <div class="bulletin-footer">
          <span class="bulletin-meta">Aggregated real-time macro telemetry, Brent crude &amp; financial news</span>
          <a href="/news_reports/latest_market_news.md" target="_blank" rel="noopener noreferrer" class="bulletin-action-link">
            <span>📄</span> Open Latest Market News Report (.md) ↗
          </a>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .bulletin-wrapper {
      padding: 12px 20px 0 20px;
    }

    .bulletin-card {
      background: rgba(18, 26, 43, 0.7);
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 12px;
      padding: 16px 20px;
      backdrop-filter: blur(12px);
      display: flex;
      flex-direction: column;
      gap: 10px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
    }

    .bulletin-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }

    .bulletin-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.88rem;
      font-weight: 700;
      color: #38bdf8;
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .sentiment-pill {
      font-size: 0.72rem;
      font-weight: 700;
      padding: 3px 10px;
      border-radius: 12px;
      letter-spacing: 0.5px;
    }
    .sentiment-pill.bullish {
      background: rgba(16, 185, 129, 0.18);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.4);
    }
    .sentiment-pill.bearish {
      background: rgba(239, 68, 68, 0.18);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .sentiment-pill.neutral {
      background: rgba(100, 116, 139, 0.2);
      color: #cbd5e1;
      border: 1px solid rgba(100, 116, 139, 0.3);
    }

    .bulletin-body {
      font-size: 0.88rem;
      color: #f1f5f9;
      line-height: 1.5;
    }

    .bulletin-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 10px;
      padding-top: 4px;
      border-top: 1px solid rgba(255, 255, 255, 0.05);
    }

    .bulletin-meta {
      font-size: 0.72rem;
      color: #64748b;
    }

    .bulletin-action-link {
      color: #38bdf8;
      text-decoration: none;
      font-size: 0.78rem;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: color 0.2s;
    }
    .bulletin-action-link:hover {
      color: #7dd3fc;
      text-decoration: underline;
    }

    @media (max-width: 768px) {
      .bulletin-wrapper { padding: 8px 12px 0 12px; }
      .bulletin-card { padding: 12px 14px; }
      .bulletin-body { font-size: 0.82rem; }
    }
  `]
})
export class BulletinComponent {
  constructor(private appStore: AppStore) {}

  bulletinData = computed(() => {
    const status = this.appStore.status();
    const b = (status as any)?.bulletin;
    if (b && typeof b === 'object') {
      return b;
    }
    if (typeof b === 'string') {
      return { summary: b, sentiment_label: 'Bullish' };
    }
    return {
      summary: 'Global macro backdrop is Favorable for Indian equities. Aggregating telemetry...',
      sentiment_label: 'Bullish'
    };
  });

  sentimentClass(label: string): string {
    const l = (label || '').toLowerCase();
    if (l.includes('bull')) return 'bullish';
    if (l.includes('bear')) return 'bearish';
    return 'neutral';
  }
}
