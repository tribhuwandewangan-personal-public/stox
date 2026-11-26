/**
 * Macro Catalysts Banner component: Shows high-impact market catalysts & economic calendar.
 * Matches the horizontal card ribbon from Jinja UI (Image 1).
 */

import { Component, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { stocksStore } from '../../core/stores/stocks.store';
import { compareDateStrings, formatDate } from '../../core/utils/date';

interface MacroCatalyst {
  date: string;
  impact: 'High' | 'Critical' | 'Medium' | 'Normal';
  event_name: string;
  affected_sectors: string[];
}

@Component({
  selector: 'app-macro-catalysts-banner',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="events-banner-wrapper" *ngIf="catalysts().length">
      <div class="events-banner-card">
        <div class="events-banner-header">
          <div class="events-banner-title">
            <span>📅</span> UPCOMING HIGH-IMPACT MARKET CATALYSTS &amp; ECONOMIC CALENDAR
          </div>
          <span class="events-counter-badge">Scheduled Releases</span>
        </div>

        <div class="events-scroll-grid">
          @for (c of catalysts(); track c.event_name + c.date) {
            <div class="event-card-item">
              <div class="event-item-top">
                <span class="event-date-chip">{{ formatDate(c.date) }}</span>
                <span class="event-impact-chip" [ngClass]="'impact-' + c.impact.toLowerCase()">
                  {{ c.impact }}
                </span>
              </div>
              <div class="event-item-name">{{ c.event_name }}</div>
              <div class="event-item-sectors">{{ c.affected_sectors.join(', ') }}</div>
            </div>
          }
        </div>
      </div>
    </div>
  `,
  styles: [`
    .events-banner-wrapper {
      padding: 12px 20px 0 20px;
    }

    .events-banner-card {
      background: rgba(18, 26, 43, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 14px 18px;
      backdrop-filter: blur(12px);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .events-banner-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }

    .events-banner-title {
      font-family: 'Outfit', sans-serif;
      font-size: 0.82rem;
      font-weight: 700;
      color: #38bdf8;
      letter-spacing: 0.5px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .events-counter-badge {
      font-size: 0.68rem;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 10px;
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.25);
    }

    .events-scroll-grid {
      display: flex;
      gap: 12px;
      overflow-x: auto;
      padding-bottom: 4px;
      scrollbar-width: thin;
    }

    .event-card-item {
      flex: 0 0 200px;
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 10px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
      transition: border-color 0.2s;
    }
    .event-card-item:hover {
      border-color: rgba(56, 189, 248, 0.35);
    }

    .event-item-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .event-date-chip {
      font-size: 0.72rem;
      font-family: 'JetBrains Mono', monospace;
      color: #38bdf8;
      font-weight: 600;
    }

    .event-impact-chip {
      font-size: 0.65rem;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 6px;
      text-transform: uppercase;
    }
    .impact-critical {
      background: rgba(239, 68, 68, 0.2);
      color: #f87171;
      border: 1px solid rgba(239, 68, 68, 0.4);
    }
    .impact-high {
      background: rgba(245, 158, 11, 0.2);
      color: #fbbf24;
      border: 1px solid rgba(245, 158, 11, 0.4);
    }
    .impact-medium {
      background: rgba(56, 189, 248, 0.2);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.4);
    }
    .impact-normal {
      background: rgba(100, 116, 139, 0.2);
      color: #94a3b8;
      border: 1px solid rgba(100, 116, 139, 0.4);
    }

    .event-item-name {
      font-size: 0.8rem;
      font-weight: 600;
      color: #f1f5f9;
      line-height: 1.3;
    }

    .event-item-sectors {
      font-size: 0.68rem;
      color: #64748b;
    }

    @media (max-width: 768px) {
      .events-banner-wrapper { padding: 8px 12px 0 12px; }
      .event-card-item { flex: 0 0 170px; }
    }
  `]
})
export class MacroCatalystsBannerComponent {
  stocksStore = stocksStore;
  formatDate = formatDate;

  catalysts = computed<MacroCatalyst[]>(() => {
    const stocks = this.stocksStore.stocks();
    const map = new Map<string, MacroCatalyst>();

    for (const s of stocks) {
      const macroList = s.events?.upcoming_macro_catalysts;
      if (Array.isArray(macroList)) {
        for (const item of macroList) {
          if (item && typeof item === 'object' && item.event_name) {
            const key = `${item.event_name}_${item.date}`;
            if (!map.has(key)) {
              map.set(key, {
                event_name: item.event_name,
                date: item.date || 'TBD',
                impact: (item.impact || 'High') as any,
                affected_sectors: Array.isArray(item.affected_sectors) ? item.affected_sectors : ['Broad Market']
              });
            }
          }
        }
      }
    }

    // Default macro calendar fallback matching the screenshot if stocks haven't loaded yet
    const list = map.size === 0
      ? [
          { date: 'Nov 30, 2026', impact: 'High' as const, event_name: 'India Q2 GDP Growth Data Release', affected_sectors: ['All Sectors', 'Capital Goods'] },
          { date: 'Dec 06, 2026', impact: 'Critical' as const, event_name: 'RBI MPC Rate Decision & Stance', affected_sectors: ['Banking', 'Real Estate', 'Auto'] },
          { date: 'Dec 11, 2026', impact: 'Critical' as const, event_name: 'US Fed FOMC Rate Decision & Powell', affected_sectors: ['IT & Tech', 'Pharma', 'FII'] },
          { date: 'Dec 15, 2026', impact: 'High' as const, event_name: 'OPEC+ Oil Production Review', affected_sectors: ['Energy', 'Paints', 'Chemicals'] }
        ]
      : Array.from(map.values());

    return [...list].sort((a, b) => compareDateStrings(a.date, b.date));
  });
}
