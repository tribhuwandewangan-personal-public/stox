/**
 * Root component placeholder.
 * This will be replaced with the full component structure in Phase 3.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from './app/core/services/api.service';
import { ws } from './app/core/services/ws.service';
import { stocksStore } from './app/core/stores/stocks.store';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="root-container">
      <div class="top-bar">
        <h1>🚀 NSE Stock Predictor (Angular 22)</h1>
        <div class="ws-status" [class.connected]="wsConnected()">
          {{ wsConnected() ? '🟢 Connected' : '🔴 Connecting...' }}
        </div>
      </div>

      <div class="content">
        <div class="status-card">
          <h2>Status</h2>
          <p>Loading: {{ loading() }}</p>
          <p>Total Stocks: {{ (stocksStore.stocks()?.length || 0) }}</p>
          <p>Buy: {{ (stocksStore.verdictCounts().buy || 0) }}</p>
          <p>Accumulate: {{ (stocksStore.verdictCounts().accumulate || 0) }}</p>
          <p>Hold: {{ (stocksStore.verdictCounts().hold || 0) }}</p>
          <p>Sell: {{ (stocksStore.verdictCounts().sell || 0) }}</p>
          <p>Last Updated: {{ lastUpdated() | date:'short' }}</p>
        </div>

        <div class="debug-card">
          <h3>Debug</h3>
          <p>Phase 2: Angular scaffold and core services ready</p>
          <p>WebSocket: {{ ws.getState() }}</p>
          <button (click)="loadStocks()">Load Stocks</button>
          <button (click)="testWs()">Test WebSocket</button>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .root-container {
      padding: 20px;
      font-family: Inter, sans-serif;
    }
    .top-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding: 15px;
      background: rgba(18, 26, 43, 0.75);
      border-radius: 10px;
    }
    .ws-status {
      padding: 8px 12px;
      border-radius: 6px;
      background: rgba(239, 68, 68, 0.15);
      color: #ef4444;
    }
    .ws-status.connected {
      background: rgba(16, 185, 129, 0.15);
      color: #10b981;
    }
    .content {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 20px;
    }
    .status-card, .debug-card {
      padding: 20px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 10px;
      background: rgba(18, 26, 43, 0.75);
    }
    .debug-card button {
      display: block;
      margin-top: 10px;
      padding: 8px 16px;
      background: var(--accent-blue, #38bdf8);
      color: white;
      border: none;
      border-radius: 6px;
      cursor: pointer;
    }
  `]
})
export class AppComponent implements OnInit, OnDestroy {
  loading = stocksStore.loading;
  lastUpdated = stocksStore.stocks().at(0)?.price_info?.as_of_date;
  wsConnected = () => ws.isConnected();

  constructor() {
    // Set up WebSocket event handlers
    ws.on('snapshot', (data) => {
      console.log('[App] Received snapshot:', data);
      stocksStore.setStocks(data);
    });

    ws.on('stocks', (data) => {
      console.log('[App] Received stocks:', data);
      stocksStore.setStocks(Array.isArray(data) ? data : []);
    });

    ws.onStateChange((state) => {
      console.log('[App] WebSocket state changed:', state);
    });
  }

  ngOnInit(): void {
    console.log('[App] Initializing...');
    // Start WebSocket
    ws.connect();
    // Load initial stocks
    this.loadStocks();
  }

  ngOnDestroy(): void {
    ws.disconnect();
  }

  async loadStocks(): Promise<void> {
    stocksStore.setLoading(true);
    try {
      const stocks = await ApiService.getStocks();
      stocksStore.setStocks(stocks);
      console.log('[App] Loaded', stocks.length, 'stocks');
    } catch (error) {
      stocksStore.setError(String(error));
      console.error('[App] Error loading stocks:', error);
    }
  }

  testWs(): void {
    console.log('[App] Testing WebSocket...');
    ws.send({ type: 'ping' });
  }

  get stocksStore() {
    return stocksStore;
  }
}
