// Angular Signal Store for global UI state (quotes, status, etc.)

import { Injectable, signal, WritableSignal } from '@angular/core';
import { ApiService } from '../services/api.service';
import { Quote, MacroRiskShieldResponse } from '../models/stock.model';
import { Status } from '../models/status.model';

@Injectable({
  providedIn: 'root',
})
export class AppStore {
  // Signals hold the latest values; components read them directly.
  readonly quotes: WritableSignal<Quote[]> = signal([]);
  readonly status: WritableSignal<Status | null> = signal(null);
  readonly ticker: WritableSignal<any> = signal(null);
  readonly bulletin: WritableSignal<any> = signal(null);
  readonly events: WritableSignal<any> = signal(null);
  readonly marketState: WritableSignal<string> = signal('');
  readonly marketOpen: WritableSignal<boolean> = signal(false);
  readonly riskShield: WritableSignal<MacroRiskShieldResponse | null> = signal(null);

  constructor(private api: ApiService) {
    // Initial load
    this.refreshStatus().then(() => this.scheduleNextStatusPoll());
    this.refreshQuotes();
    this.refreshEvents();
    this.refreshRiskShield();

    // Periodic refresh – mimic the previous RxJS timers.
    setInterval(() => this.refreshQuotes(), 15_000); // every 15 s
    setInterval(() => this.refreshEvents(), 45_000); // every 45 s
    setInterval(() => this.refreshRiskShield(), 120_000); // every 2 min
  }

  private scheduleNextStatusPoll(): void {
    const s = this.status();
    const isBusy = Boolean(s?.scheduler?.active || (s?.running_symbols?.length ?? 0) > 0);
    const delayMs = isBusy ? 5_000 : 20_000;
    setTimeout(() => {
      this.refreshStatus().finally(() => this.scheduleNextStatusPoll());
    }, delayMs);
  }

  /** Refresh live Macro Risk Shield summary */
  async refreshRiskShield(): Promise<void> {
    try {
      const shield = await ApiService.getMacroRiskShield();
      this.riskShield.set(shield);
    } catch (e) {
      console.error('Failed to refresh macro risk shield', e);
    }
  }

  /** Refresh the server status and push into the signal */
  private async refreshStatus(): Promise<void> {
    try {
      const s = await this.api.getStatus();
      this.status.set(s);
      if (s?.bulletin) {
        this.bulletin.set(s.bulletin);
      }
    } catch (e) {
      console.error('Failed to refresh status', e);
    }
  }

  /** Refresh events data and push into the signal */
  private async refreshEvents(): Promise<void> {
    try {
      const data = await ApiService.getEvents();
      this.events.set(data);
    } catch (e) {
      console.error('Failed to refresh events', e);
    }
  }

  private async refreshQuotes(): Promise<void> {
    try {
      const resp = await ApiService.getQuotes();
      if (resp && resp.quotes) {
        // Convert the quotes map to an array for the signal
        const qArray: Quote[] = Object.values(resp.quotes);
        this.quotes.set(qArray);
      }
      if (typeof resp?.market_state === 'string') {
        this.marketState.set(resp.market_state);
      }
      if (typeof resp?.market_open === 'boolean') {
        this.marketOpen.set(resp.market_open);
      }
    } catch (e) {
      console.error('Failed to refresh quotes', e);
    }
  }
}
