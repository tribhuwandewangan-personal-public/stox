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
            <div class="pattern-item" [class.bearish]="pattern.bearish">
              <div class="pattern-header">
                <span class="pattern-name">{{ pattern.name }}</span>
                <span class="pattern-icon">{{ pattern.bearish ? '📉' : '📈' }}</span>
              </div>
              <div class="pattern-score">
                <div class="score-bar">
                  <div class="score-fill" [style.width.%]="pattern.score * 100"></div>
                </div>
                <span class="score-text">{{ (pattern.score * 100).toFixed(0) }}%</span>
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
}
