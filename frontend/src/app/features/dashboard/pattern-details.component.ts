/**
 * Pattern details panel: Shows all detected patterns with scores.
 */

import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { PatternResult } from '../../core/models/stock.model';

@Component({
  selector: 'app-pattern-details',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="panel">
      <h3 class="panel-title">📊 Technical Patterns</h3>

      @if (patterns.length > 0) {
        <div class="pattern-list">
          @for (pattern of patterns; track pattern.name) {
            <div class="pattern-item" [class.bearish]="isBearish(pattern)">
              <div class="pattern-header">
                <div class="name-box">
                  <span class="pattern-name">{{ pattern.name }}</span>
                  <span class="pattern-type" *ngIf="pattern.type">{{ pattern.type }}</span>
                </div>
                <span class="pattern-icon">{{ isBearish(pattern) ? '📉' : '📈' }}</span>
              </div>
              <div class="pattern-score">
                <div class="score-bar">
                  <div class="score-fill" [style.width.%]="getScorePercent(pattern)"></div>
                </div>
                <span class="score-text">{{ getScorePercent(pattern) }}%</span>
              </div>
              <p class="pattern-desc" *ngIf="pattern.description">{{ pattern.description }}</p>
              <div class="pattern-levels" *ngIf="pattern.target_price || pattern.stop_loss">
                <span *ngIf="pattern.target_price">Target: <strong class="accent-green">Rs. {{ pattern.target_price }}</strong></span>
                <span *ngIf="pattern.stop_loss">SL: <strong class="accent-red">Rs. {{ pattern.stop_loss }}</strong></span>
                <span *ngIf="pattern.risk_reward_ratio">R:R: <strong>{{ pattern.risk_reward_ratio }}</strong></span>
              </div>
            </div>
          }
        </div>
      } @else {
        <div class="no-data">
          <p>No patterns detected yet.</p>
          <span class="hint">Re-analyze stock to detect patterns.</span>
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

    .pattern-list {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .pattern-item {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(56, 189, 248, 0.1);
      border-radius: 6px;
      padding: 10px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .pattern-item.bearish {
      border-color: rgba(239, 68, 68, 0.2);
      background: rgba(239, 68, 68, 0.05);
    }

    .pattern-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .pattern-name {
      font-size: 12px;
      font-weight: 600;
      color: #fff;
      flex: 1;
    }

    .pattern-icon {
      font-size: 14px;
    }

    .pattern-score {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .score-bar {
      flex: 1;
      height: 4px;
      background: rgba(56, 189, 248, 0.1);
      border-radius: 2px;
      overflow: hidden;
    }

    .score-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
      transition: width 0.3s ease;
    }

    .pattern-item.bearish .score-fill {
      background: linear-gradient(90deg, var(--accent-red), var(--accent-amber));
    }

    .score-text {
      font-size: 11px;
      color: var(--text-muted);
      min-width: 30px;
      text-align: right;
    }

    .name-box {
      display: flex;
      align-items: baseline;
      gap: 6px;
      flex-wrap: wrap;
    }
    .pattern-type {
      font-size: 10px;
      color: #94a3b8;
      background: rgba(255, 255, 255, 0.05);
      padding: 1px 6px;
      border-radius: 4px;
    }
    .pattern-desc {
      font-size: 11px;
      color: #cbd5e1;
      margin: 4px 0 2px 0;
      line-height: 1.35;
    }
    .pattern-levels {
      display: flex;
      gap: 10px;
      font-size: 10px;
      color: #94a3b8;
      margin-top: 2px;
      font-family: 'JetBrains Mono', monospace;
    }
    .accent-green { color: #10b981; }
    .accent-red   { color: #ef4444; }

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
export class PatternDetailsComponent {
  @Input() patterns: PatternResult[] = [];

  isBearish(p: PatternResult): boolean {
    if (p.direction) return p.direction === 'Bearish';
    return !!p.bearish;
  }

  getScorePercent(p: PatternResult): number {
    if (p.quality_score != null) return Math.round(p.quality_score);
    if (p.score != null) return Math.round(p.score * (p.score <= 1 ? 100 : 1));
    return 70;
  }
}
