import { Component, OnInit, OnDestroy, signal, computed, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { apiService } from '../../core/services/api.service';
import { stocksStore } from '../../core/stores/stocks.store';

interface FeedMessage {
  id: string;
  category: 'verdict' | 'catalyst' | 'info' | 'system';
  icon: string;
  symbol?: string;
  title: string;
  detail: string;
  time: string;
}

@Component({
  selector: 'app-activity-chat',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="chat-dock">
      <!-- Floating Toggle Pill -->
      <button
        type="button"
        class="chat-fab"
        (click)="toggleOpen()"
        title="View live changes detected by Stox tools"
      >
        <span>💬 Live Changes</span>
        <span class="unread-badge" *ngIf="unreadCount() > 0">{{ unreadCount() }}</span>
      </button>

      <!-- Floating Chat-Box Window -->
      <div class="chat-window" *ngIf="isOpen()">
        <div class="chat-header">
          <div class="chat-title">
            <span class="live-dot"></span>
            <strong>Tool Change Feed</strong>
          </div>
          <div class="chat-actions">
            <button type="button" class="hdr-btn" (click)="pollFeed()" title="Refresh now">🔄</button>
            <button type="button" class="hdr-btn" (click)="clearMessages()" title="Clear feed">🗑️</button>
            <button type="button" class="hdr-btn" (click)="toggleOpen()" title="Minimize">✕</button>
          </div>
        </div>

        <div class="chat-filters">
          <button type="button" class="flt-btn" [class.active]="filter() === 'all'" (click)="filter.set('all')">All</button>
          <button type="button" class="flt-btn" [class.active]="filter() === 'verdict'" (click)="filter.set('verdict')">Verdicts</button>
          <button type="button" class="flt-btn" [class.active]="filter() === 'catalyst'" (click)="filter.set('catalyst')">Catalysts</button>
          <button type="button" class="flt-btn" [class.active]="filter() === 'info'" (click)="filter.set('info')">Info</button>
          <button type="button" class="flt-btn" [class.active]="filter() === 'system'" (click)="filter.set('system')">System</button>
        </div>

        <div class="chat-body">
          <div class="empty-chat" *ngIf="filteredMessages().length === 0">
            No new changes detected yet. As Catalyst Radar, Scheduler, or Re-Analyze finds updates, they will appear here automatically.
          </div>

          <div
            class="chat-bubble"
            *ngFor="let m of filteredMessages()"
            [ngClass]="'cat-' + m.category"
          >
            <div class="bubble-top">
              <span class="bubble-tag">
                {{ m.icon }}
                <button
                  *ngIf="m.symbol"
                  type="button"
                  class="sym-link"
                  (click)="openStock(m.symbol)"
                  title="Open stock details"
                >{{ m.symbol }}</button>
                <strong>{{ m.title }}</strong>
              </span>
              <span class="bubble-time">{{ m.time }}</span>
            </div>
            <div class="bubble-msg">{{ m.detail }}</div>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .chat-dock {
      position: fixed;
      right: 20px;
      bottom: 36px;
      z-index: 900;
      display: flex;
      flex-direction: column;
      align-items: flex-end;
      gap: 10px;
    }
    .chat-fab {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: #fff;
      border: 1px solid rgba(125, 211, 252, 0.45);
      border-radius: 999px;
      padding: 9px 16px;
      font-size: 0.8rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 10px 25px rgba(2, 6, 23, 0.6);
    }
    .chat-fab:hover { filter: brightness(1.08); }
    .unread-badge {
      background: #ef4444;
      color: #fff;
      border-radius: 999px;
      padding: 1px 7px;
      font-size: 0.7rem;
      font-weight: 800;
    }
    .chat-window {
      width: 380px;
      max-width: calc(100vw - 32px);
      height: 460px;
      max-height: calc(100vh - 120px);
      background: rgba(15, 23, 42, 0.96);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 14px;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.65);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .chat-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 14px;
      background: rgba(2, 6, 23, 0.75);
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      font-size: 0.82rem;
      color: #f8fafc;
    }
    .chat-title { display: flex; align-items: center; gap: 8px; }
    .live-dot {
      width: 8px; height: 8px; border-radius: 50%;
      background: #10b981;
      box-shadow: 0 0 8px #10b981;
    }
    .chat-actions { display: flex; gap: 4px; }
    .hdr-btn {
      background: transparent; border: none; color: #94a3b8;
      cursor: pointer; font-size: 0.82rem; padding: 3px 6px; border-radius: 6px;
    }
    .hdr-btn:hover { background: rgba(255, 255, 255, 0.08); color: #fff; }
    .chat-filters {
      display: flex; gap: 6px; padding: 8px 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }
    .flt-btn {
      background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8; padding: 3px 9px; border-radius: 6px; font-size: 0.7rem; font-weight: 600; cursor: pointer;
    }
    .flt-btn.active { background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; color: #fff; }
    .chat-body {
      flex: 1;
      overflow-y: auto;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .empty-chat {
      color: #64748b; font-size: 0.76rem; text-align: center;
      margin: auto 12px; line-height: 1.5;
    }
    .chat-bubble {
      background: rgba(30, 41, 59, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.07);
      border-left: 3px solid #38bdf8;
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 0.75rem;
    }
    .chat-bubble.cat-catalyst { border-left-color: #10b981; }
    .chat-bubble.cat-info { border-left-color: #64748b; }
    .chat-bubble.cat-system { border-left-color: #f59e0b; }
    .bubble-top {
      display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 4px;
    }
    .bubble-tag { display: inline-flex; align-items: center; gap: 5px; color: #e2e8f0; flex-wrap: wrap; }
    .sym-link {
      background: rgba(56, 189, 248, 0.18); border: 1px solid rgba(56, 189, 248, 0.35);
      color: #7dd3fc; font-weight: 700; font-size: 0.7rem; padding: 1px 6px; border-radius: 4px; cursor: pointer;
    }
    .bubble-time { font-size: 0.66rem; color: #64748b; flex-shrink: 0; }
    .bubble-msg { color: #cbd5e1; line-height: 1.4; }

    :host-context([data-theme='light']) .chat-window {
      background: #ffffff;
      border-color: #cbd5e1;
      box-shadow: 0 14px 35px rgba(15, 23, 42, 0.18);
    }
    :host-context([data-theme='light']) .chat-header {
      background: #f8fafc;
      border-bottom-color: #e2e8f0;
      color: #0f172a;
    }
    :host-context([data-theme='light']) .chat-filters { border-bottom-color: #e2e8f0; }
    :host-context([data-theme='light']) .flt-btn {
      background: #f1f5f9;
      border-color: #cbd5e1;
      color: #475569;
    }
    :host-context([data-theme='light']) .flt-btn.active {
      background: #e0f2fe;
      border-color: #0284c7;
      color: #0369a1;
    }
    :host-context([data-theme='light']) .chat-bubble {
      background: #f8fafc;
      border-color: #e2e8f0;
    }
    :host-context([data-theme='light']) .bubble-tag { color: #0f172a; }
    :host-context([data-theme='light']) .bubble-msg { color: #334155; }
    :host-context([data-theme='light']) .sym-link {
      background: #e0f2fe;
      border-color: #38bdf8;
      color: #0369a1;
    }
    :host-context([data-theme='light']) .hdr-btn { color: #475569; }
    :host-context([data-theme='light']) .hdr-btn:hover { background: #e2e8f0; color: #0f172a; }
  `]
})
export class ActivityChatComponent implements OnInit, OnDestroy {
  isOpen = signal<boolean>(false);
  filter = signal<'all' | 'verdict' | 'catalyst' | 'info' | 'system'>('all');
  messages = signal<FeedMessage[]>([]);
  unreadCount = signal<number>(0);

  filteredMessages = computed(() => {
    const f = this.filter();
    const list = this.messages();
    return f === 'all' ? list : list.filter(m => m.category === f);
  });

  private lastEventId = 0;
  private pollHandle: any = null;
  private lastVerdicts = new Map<string, string>();

  constructor() {
    // Also detect live verdict changes in stocksStore across polls
    effect(() => {
      const stocks = stocksStore.stocks();
      if (!stocks || stocks.length === 0) return;
      const newChanges: FeedMessage[] = [];
      for (const s of stocks) {
        const sym = s.symbol;
        const v = s.synth_output?.structured_signal?.action_verdict;
        if (!sym || !v) continue;
        const prev = this.lastVerdicts.get(sym);
        if (prev && prev !== v) {
          newChanges.push({
            id: `local-${sym}-${Date.now()}`,
            category: 'verdict',
            icon: '📈',
            symbol: sym,
            title: 'Verdict Updated',
            detail: `${sym} changed from ${prev} to ${v}`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          });
        }
        this.lastVerdicts.set(sym, v);
      }
      if (newChanges.length > 0) {
        this.appendMessages(newChanges);
      }
    });
  }

  ngOnInit(): void {
    this.pollFeed();
    this.pollHandle = setInterval(() => this.pollFeed(), 15000);
  }

  ngOnDestroy(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
  }

  toggleOpen(): void {
    const next = !this.isOpen();
    this.isOpen.set(next);
    if (next) this.unreadCount.set(0);
  }

  clearMessages(): void {
    this.messages.set([]);
    this.unreadCount.set(0);
  }

  openStock(symbol: string): void {
    if (symbol && symbol !== 'GOVT_POLICY') {
      stocksStore.selectSymbol(symbol);
    }
  }

  async pollFeed(): Promise<void> {
    try {
      const res = await apiService.getActivityFeed(this.lastEventId, 60);
      if (res.latest_id > this.lastEventId) {
        this.lastEventId = res.latest_id;
      }
      const mapped: FeedMessage[] = (res.events || [])
        .filter((ev: any) => String(ev.type || '') !== 'analysis_done' || Boolean(ev.payload?.message))
        .map((ev: any) => this.mapEvent(ev));
      if (mapped.length > 0) {
        this.appendMessages(mapped);
      }
    } catch {
      // Ignore transient poll errors
    }
  }

  private appendMessages(incoming: FeedMessage[]): void {
    this.messages.update(prev => [...incoming.reverse(), ...prev].slice(0, 120));
    if (!this.isOpen()) {
      const importantCount = incoming.filter(m => m.category !== 'info').length;
      if (importantCount > 0) {
        this.unreadCount.update(c => c + importantCount);
      }
    }
  }

  private mapEvent(ev: any): FeedMessage {
    const t = String(ev.type || '');
    const p = ev.payload || {};
    const timeStr = String(ev.timestamp || '').slice(11, 16) || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (t === 'catalyst_early_warning') {
      return {
        id: `srv-${ev.id}`,
        category: 'catalyst',
        icon: p.pre_breakout_match ? '🚀' : '⚡',
        symbol: p.symbol,
        title: `Tier ${p.tier || 'A'} Catalyst (${p.score ?? ''}/100)`,
        detail: p.title || p.message || 'New corporate catalyst detected',
        time: timeStr,
      };
    }
    if (t === 'symbol_added') {
      return {
        id: `srv-${ev.id}`,
        category: 'verdict',
        icon: '➕',
        symbol: p.symbol,
        title: 'Watchlist Added',
        detail: p.message || `Added ${p.symbol} to Watchlist`,
        time: timeStr,
      };
    }
    if (t === 'symbol_removed') {
      return {
        id: `srv-${ev.id}`,
        category: 'system',
        icon: '➖',
        symbol: p.symbol,
        title: 'Watchlist Removed',
        detail: p.message || `Removed ${p.symbol} from Watchlist`,
        time: timeStr,
      };
    }
    if (t === 'sector_research_done') {
      return {
        id: `srv-${ev.id}`,
        category: 'catalyst',
        icon: '🧭',
        symbol: p.symbol,
        title: 'Sector Research',
        detail: p.message || `Sector research completed for ${p.sector}`,
        time: timeStr,
      };
    }
    if (t === 'market_scan_done') {
      return {
        id: `srv-${ev.id}`,
        category: 'catalyst',
        icon: '🔍',
        symbol: p.symbol,
        title: 'Market Scanner',
        detail: p.message || `Found ${p.count || 0} strength leaders`,
        time: timeStr,
      };
    }
    if (t === 'catalyst_scan_done') {
      return {
        id: `srv-${ev.id}`,
        category: 'info',
        icon: 'ℹ️',
        title: 'Catalyst Scan Info',
        detail: p.message || 'Primary disclosure scan finished',
        time: timeStr,
      };
    }
    if (t === 'prebreakout_stage_change') {
      return {
        id: `srv-${ev.id}`,
        category: 'verdict',
        icon: '🚀',
        symbol: p.symbol,
        title: 'Pre-Breakout Stage Changed',
        detail: p.message || `${p.symbol}: ${p.old_stage || 'NONE'} -> ${p.new_stage || 'CLEARED'}`,
        time: timeStr,
      };
    }
    if (t === 'pattern_projection_change') {
      return {
        id: `srv-${ev.id}`,
        category: 'verdict',
        icon: '📐',
        symbol: p.symbol,
        title: 'Pattern / Projection Updated',
        detail: p.message || `${p.symbol} pattern/projection updated`,
        time: timeStr,
      };
    }
    if (t === 'fundamental_change') {
      return {
        id: `srv-${ev.id}`,
        category: 'verdict',
        icon: '🏛️',
        symbol: p.symbol,
        title: 'Fundamental Verdict Changed',
        detail: p.message || `${p.symbol} fundamental verdict: ${p.old_verdict} -> ${p.new_verdict}`,
        time: timeStr,
      };
    }
    if (t === 'verdict_change') {
      return {
        id: `srv-${ev.id}`,
        category: 'verdict',
        icon: '📊',
        symbol: p.symbol,
        title: 'Verdict Changed',
        detail: p.message || `${p.symbol} -> ${p.new_verdict || p.verdict}`,
        time: timeStr,
      };
    }
    if (t === 'analysis_done') {
      return {
        id: `srv-${ev.id}`,
        category: 'info',
        icon: 'ℹ️',
        symbol: p.symbol,
        title: 'Analysis Info',
        detail: p.message || `${p.symbol} analysis completed`,
        time: timeStr,
      };
    }
    return {
      id: `srv-${ev.id}`,
      category: t === 'scheduler' && p.level !== 'warning' ? 'info' : 'system',
      icon: p.level === 'warning' ? '⚠️' : 'ℹ️',
      title: t === 'scheduler' ? 'Scheduler Info' : 'System Alert',
      detail: p.message || JSON.stringify(p),
      time: timeStr,
    };
  }
}
