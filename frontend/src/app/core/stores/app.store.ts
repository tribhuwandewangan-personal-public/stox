// Angular Signal Store for global UI state (quotes, status, etc.)

import { Injectable, signal, WritableSignal } from '@angular/core';
import { ApiService } from '../services/api.service';
import { Quote } from '../models/stock.model';
import { Status } from '../models/status.model';

@Injectable({
  providedIn: 'root',
})
export class AppStore {
  // Signals hold the latest values; components read them directly.
  readonly quotes: WritableSignal<Quote[]> = signal([]);
  readonly status: WritableSignal<Status | null> = signal(null);

  constructor(private api: ApiService) {
    // Initial load
    this.refreshStatus();
    this.refreshQuotes();

    // Periodic refresh – mimic the previous RxJS timers.
    setInterval(() => this.refreshStatus(), 30_000); // every 30 s
    setInterval(() => this.refreshQuotes(), 15_000); // every 15 s
  }

  /** Refresh the server status and push into the signal */
  private async refreshStatus(): Promise<void> {
    try {
      const s = await this.api.getStatus();
      this.status.set(s);
    } catch (e) {
      console.error('Failed to refresh status', e);
    }
  }

  /** Refresh live quotes and push into the signal */
  private async refreshQuotes(): Promise<void> {
    try {
      const resp = await (ApiService as any).getQuotes();
      // Convert the quotes map to an array for the signal
      const qArray: Quote[] = Object.values(resp.quotes);
      this.quotes.set(qArray);
    } catch (e) {
      console.error('Failed to refresh quotes', e);
    }
  }
}
