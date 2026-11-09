/**
 * Root component: Initializes WebSocket and core services.
 * Delegates layout to ShellComponent.
 */

import { Component, OnInit, OnDestroy, effect } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet, provideRouter } from '@angular/router';
import { ApiService } from './app/core/services/api.service';
import { ws } from './app/core/services/ws.service';
import { stocksStore } from './app/core/stores/stocks.store';
import { ShellComponent } from './app/features/shell/shell.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, ShellComponent],
  template: `<app-shell></app-shell>`,
  styles: []
})
export class AppComponent implements OnInit, OnDestroy {
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

    ws.on('analysis_done', (data) => {
      console.log('[App] Analysis done:', data);
      // Refresh stocks to get updated analysis
      this.loadStocks();
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

  private async loadStocks(): Promise<void> {
    stocksStore.setLoading(true);
    try {
      const stocks = await ApiService.getStocks();
      stocksStore.setStocks(stocks);
      console.log('[App] Loaded', stocks.length, 'stocks');
    } catch (error) {
      stocksStore.setError(String(error));
      console.error('[App] Error loading stocks:', error);
    } finally {
      stocksStore.setLoading(false);
    }
  }
}
