/**
 * Events panel: Shows upcoming macro catalysts and corporate events.
 */

import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { EventsData } from '../../core/models/stock.model';

@Component({
  selector: 'app-events-panel',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="panel">
      <h3 class="panel-title">📅 Upcoming Events</h3>

      @if (hasMacroCatalysts || hasEvents) {
        <div class="events-list">
          @if (macroCatalysts.length > 0) {
            <div class="event-section">
              <h4 class="section-label">Macro Catalysts</h4>
              @for (catalyst of macroCatalysts; track catalyst) {
                <div class="event-item macro">
                  <span class="event-icon">🌍</span>
                  <span class="event-text">{{ catalyst }}</span>
                </div>
              }
            </div>
          }

          @if (eventsList.length > 0) {
            <div class="event-section">
              <h4 class="section-label">Corporate Events</h4>
              @for (event of eventsList; track event.name) {
                <div class="event-item corporate">
                  <span class="event-icon">{{ event.emoji }}</span>
                  <div class="event-details">
                    <span class="event-name">{{ event.name }}</span>
                    <span class="event-date" *ngIf="event.date">{{ event.date }}</span>
                  </div>
                </div>
              }
            </div>
          }
        </div>
      } @else {
        <div class="no-data">
          <p>No upcoming events.</p>
          <span class="hint">Check back later for new events.</span>
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

    .events-list {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .event-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .section-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.3px;
      margin: 0;
    }

    .event-item {
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(56, 189, 248, 0.1);
      border-radius: 6px;
      padding: 8px 10px;
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12px;
    }

    .event-item.macro {
      border-color: rgba(245, 158, 11, 0.2);
      background: rgba(245, 158, 11, 0.05);
    }

    .event-item.corporate {
      border-color: rgba(139, 92, 246, 0.2);
      background: rgba(139, 92, 246, 0.05);
    }

    .event-icon {
      font-size: 14px;
      flex-shrink: 0;
    }

    .event-text {
      color: #fff;
      flex: 1;
      line-height: 1.3;
    }

    .event-details {
      display: flex;
      flex-direction: column;
      gap: 2px;
      flex: 1;
    }

    .event-name {
      color: #fff;
      font-weight: 600;
    }

    .event-date {
      font-size: 11px;
      color: var(--text-muted);
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
export class EventsPanelComponent {
  @Input() events: EventsData = {};

  get macroCatalysts(): string[] {
    const catalysts = this.events?.upcoming_macro_catalysts || [];
    return catalysts.map(c => {
      if (typeof c === 'string') return c;
      if (c && typeof c === 'object') {
        const name = c.event_name || c.name || '';
        const date = c.date ? ` (${c.date})` : '';
        const note = c.note ? `: ${c.note}` : '';
        return `${name}${date}${note}`.trim();
      }
      return String(c);
    }).filter(Boolean);
  }

  get eventsList(): Array<{ name: string; emoji: string; date?: string }> {
    const list: Array<{ name: string; emoji: string; date?: string }> = [];

    if (this.events?.earnings_date) {
      list.push({
        name: `Quarterly Results (${this.events.earnings_quarter || 'Earnings'})`,
        emoji: '📊',
        date: this.events.earnings_date
      });
    }

    if (this.events?.dividend_amount && this.events.dividend_amount !== 'N/A') {
      list.push({
        name: `Dividend: ${this.events.dividend_amount}`,
        emoji: '💰',
        date: this.events.dividend_ex_date || undefined
      });
    }

    if (this.events?.corporate_action) {
      list.push({
        name: this.events.corporate_action,
        emoji: '📢'
      });
    }

    const events = this.events?.upcoming_events || {};
    if (typeof events === 'object') {
      for (const [name, details] of Object.entries(events)) {
        const d = details as any;
        const dateStr = typeof d === 'string' ? d : (d?.date || undefined);
        list.push({
          name,
          emoji: this.getEmojiForEvent(name),
          date: dateStr
        });
      }
    }

    return list;
  }

  get hasMacroCatalysts(): boolean {
    return this.macroCatalysts.length > 0;
  }

  get hasEvents(): boolean {
    return this.eventsList.length > 0;
  }

  private getEmojiForEvent(eventName: string): string {
    const name = eventName.toLowerCase();
    if (name.includes('dividend')) return '💰';
    if (name.includes('split')) return '🔀';
    if (name.includes('bonus')) return '🎁';
    if (name.includes('result')) return '📊';
    if (name.includes('announcement')) return '📢';
    if (name.includes('meeting')) return '👥';
    return '📌';
  }
}
