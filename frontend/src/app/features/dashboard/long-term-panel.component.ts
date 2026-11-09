/**
 * Long-term analysis panel: Shows target, horizon, verdict, and peer suggestions.
 */

import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LongTermSignal } from '../../core/models/stock.model';
import { fmtPrice } from '../../core/utils/price';

@Component({
  selector: 'app-long-term-panel',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="panel">
      <h3 class="panel-title">🎯 Long-Term Analysis</h3>

      @if (signal) {
        <div class="analysis-content">
          <!-- Verdict -->
          <div class="metric">
            <span class="label">Verdict</span>
            <span class="value" [style.color]="verdictColor">
              {{ signal.long_term_verdict || 'N/A' }}
            </span>
          </div>

          <!-- Target -->
          @if (signal.long_term_target) {
            <div class="metric">
              <span class="label">Price Target</span>
              <span class="value">{{ fmtPrice(signal.long_term_target) }}</span>
            </div>
          }

          <!-- Horizon -->
          @if (signal.long_term_horizon) {
            <div class="metric">
              <span class="label">Time Horizon</span>
              <span class="value">{{ signal.long_term_horizon }}</span>
            </div>
          }

          <!-- Peers -->
          @if (signal.suggested_long_term_peers && signal.suggested_long_term_peers.length > 0) {
            <div class="metric peers">
              <span class="label">Similar Stocks</span>
              <div class="peers-list">
                @for (peer of signal.suggested_long_term_peers; track peer) {
                  <span class="peer-badge">{{ peer }}</span>
                }
              </div>
            </div>
          }
        </div>
      } @else {
        <div class="no-data">
          <p>No long-term analysis available.</p>
          <span class="hint">Re-analyze stock to generate long-term insights.</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .panel {
      background: rgba(30, 41, 59, 0.5);
      border: 1px solid rgba(56, 189, 248, 0.15);
      border-radius: 8px;
      padding: 16px;
      flex: 1;
      min-width: 250px;
    }

    .panel-title {
      font-size: 13px;
      font-weight: 700;
      color: #fff;
      margin: 0 0 12px 0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }

    .analysis-content {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .metric {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(56, 189, 248, 0.1);
      border-radius: 6px;
      padding: 10px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .metric.peers {
      flex-direction: column;
      align-items: flex-start;
      gap: 8px;
    }

    .label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.3px;
    }

    .value {
      font-size: 14px;
      font-weight: 600;
      color: #fff;
    }

    .peers-list {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      width: 100%;
    }

    .peer-badge {
      background: rgba(139, 92, 246, 0.15);
      border: 1px solid rgba(139, 92, 246, 0.3);
      color: var(--accent-purple);
      font-size: 11px;
      font-weight: 600;
      padding: 4px 8px;
      border-radius: 4px;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }

    .no-data {
      text-align: center;
      padding: 20px 12px;
      color: var(--text-muted);
    }

    .no-data p {
      font-size: 12px;
      margin: 0 0 6px 0;
    }

    .hint {
      font-size: 11px;
      color: var(--text-muted);
      opacity: 0.7;
    }
  `]
})
export class LongTermPanelComponent {
  @Input() signal: LongTermSignal | null = null;

  fmtPrice = fmtPrice;

  get verdictColor(): string {
    if (!this.signal?.long_term_verdict) return 'var(--text-muted)';
    const v = this.signal.long_term_verdict.toLowerCase();
    if (v.includes('buy')) return 'var(--accent-green)';
    if (v.includes('sell')) return 'var(--accent-red)';
    if (v.includes('hold')) return 'var(--accent-blue)';
    return 'var(--text-muted)';
  }
}
