/**
 * Header component: Top navigation bar with market badge, queue status, engine label.
 */

import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { stocksStore } from '../../core/stores/stocks.store';

interface Status {
  model: string;
  timestamp: string;
  queue_status: {
    pending_count: number;
    in_progress_count: number;
    completed_count: number;
  };
  bulletin?: string;
  macro_items?: any[];
}

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="top-bar">
      <div class="bar-left">
        <div class="logo-icon">📊</div>
        <div class="title-group">
          <h1 class="title">NSE Stock Predictor</h1>
          <div class="subtitle">Real-time Analysis Engine</div>
        </div>
      </div>

      <div class="bar-center">
        <div class="status-group" *ngIf="status$ | async as status">
          <div class="queue-badge">
            <span class="queue-label">Pending:</span>
            <span class="queue-count">{{ status.queue_status.pending_count }}</span>
          </div>
          <div class="queue-badge">
            <span class="queue-label">Running:</span>
            <span class="queue-count">{{ status.queue_status.in_progress_count }}</span>
          </div>
          <div class="queue-badge">
            <span class="queue-label">Done:</span>
            <span class="queue-count">{{ status.queue_status.completed_count }}</span>
          </div>
        </div>
      </div>

      <div class="bar-right">
        <div class="market-badge" [ngClass]="'market-' + marketState()">
          <span class="market-icon">{{ marketIcon() }}</span>
          <span class="market-text">{{ marketState() | uppercase }}</span>
        </div>

        <div class="engine-badge">
          <span class="engine-label">Engine:</span>
          <span class="engine-value">{{ engineLabel$ | async }}</span>
        </div>

        <button class="btn-icon" title="Settings">⚙️</button>
        <button class="btn-icon" title="Help">❓</button>
      </div>
    </div>
  `,
  styles: [`
    .top-bar {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(10, 15, 26, 0.92);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding: 14px 20px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 20px;
    }

    .bar-left {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 0 0 auto;
    }

    .logo-icon {
      font-size: 1.8rem;
      line-height: 1;
    }

    .title-group {
      display: flex;
      flex-direction: column;
      gap: 0;
    }

    .title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      margin: 0;
      line-height: 1.2;
    }

    .subtitle {
      font-size: 0.7rem;
      color: var(--text-muted);
      font-weight: 500;
    }

    .bar-center {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 1;
    }

    .status-group {
      display: flex;
      gap: 12px;
      align-items: center;
    }

    .queue-badge {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent-blue);
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }

    .queue-label {
      opacity: 0.7;
    }

    .queue-count {
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }

    .bar-right {
      display: flex;
      align-items: center;
      gap: 12px;
      flex: 0 0 auto;
    }

    .market-badge {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent-blue);
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.75rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 6px;
      white-space: nowrap;
    }

    .market-badge.market-open {
      background: rgba(16, 185, 129, 0.15);
      border-color: rgba(16, 185, 129, 0.3);
      color: var(--accent-green);
    }

    .market-badge.market-closed {
      background: rgba(156, 163, 175, 0.15);
      border-color: rgba(156, 163, 175, 0.3);
      color: var(--text-muted);
    }

    .market-badge.market-premarket {
      background: rgba(139, 92, 246, 0.15);
      border-color: rgba(139, 92, 246, 0.3);
      color: var(--accent-purple);
    }

    .market-icon {
      font-size: 1rem;
      line-height: 1;
    }

    .market-text {
      font-size: 0.7rem;
    }

    .engine-badge {
      background: rgba(139, 92, 246, 0.15);
      border: 1px solid rgba(139, 92, 246, 0.3);
      color: var(--accent-purple);
      padding: 4px 10px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 4px;
      white-space: nowrap;
    }

    .engine-label {
      opacity: 0.7;
    }

    .btn-icon {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #e5e7eb;
      padding: 6px 8px;
      border-radius: 6px;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.2s;
      line-height: 1;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .btn-icon:hover {
      background: rgba(255, 255, 255, 0.12);
      border-color: rgba(56, 189, 248, 0.3);
      color: #fff;
    }

    @media (max-width: 1024px) {
      .bar-center {
        display: none;
      }
    }

    @media (max-width: 768px) {
      .top-bar {
        flex-wrap: wrap;
        gap: 10px;
        padding: 10px;
      }

      .title {
        font-size: 1rem;
      }

      .subtitle {
        display: none;
      }

      .market-badge,
      .engine-badge {
        font-size: 0.65rem;
        padding: 3px 8px;
      }

      .btn-icon {
        padding: 4px 6px;
        font-size: 0.9rem;
      }
    }
  `]
})
export class HeaderComponent implements OnInit {
  status$ = this.apiService.getStatus();
  engineLabel$ = this.apiService.getStatus().then(s => s.model);

  marketState() {
    const hour = new Date().getHours();
    if (hour >= 9 && hour < 15) return 'open';
    if (hour >= 8 && hour < 9) return 'premarket';
    return 'closed';
  }

  marketIcon() {
    const state = this.marketState();
    switch (state) {
      case 'open':
        return '🟢';
      case 'premarket':
        return '🟡';
      default:
        return '🔴';
    }
  }

  constructor(private apiService: ApiService) {}

  ngOnInit(): void {
    // Auto-refresh status every 30 seconds
    setInterval(() => {
      this.status$ = this.apiService.getStatus();
    }, 30000);
  }
}
