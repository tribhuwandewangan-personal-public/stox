/**
 * Root component: Initializes WebSocket and core services.
 * Delegates layout to ShellComponent.
 */

import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ws } from './app/core/services/ws.service';
import { stocksStore } from './app/core/stores/stocks.store';
import { ShellComponent } from './app/features/shell/shell.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ShellComponent],
  template: `<app-shell></app-shell>`,
  styles: []
})
export class AppComponent implements OnInit, OnDestroy {
  constructor() {
    ws.setUniverseProvider(() => stocksStore.activeUniverse());

    // Set up WebSocket event handlers
    ws.on('snapshot', (data) => {
      console.log('[App] Received snapshot:', data);
      // Only overwrite if active universe is curated and no load is currently in flight
      if (!stocksStore.loading() && stocksStore.activeUniverse() === 'curated' && Array.isArray(data)) {
        stocksStore.setStocks(data);
      }
    });

    ws.on('stocks', (data) => {
      console.log('[App] Received stocks:', data);
      if (stocksStore.loading()) return;
      if (data && !Array.isArray(data) && Array.isArray(data.stocks)) {
        if (data.universe === stocksStore.activeUniverse()) {
          stocksStore.setStocks(data.stocks);
        }
      } else if (Array.isArray(data) && stocksStore.activeUniverse() === 'curated') {
        stocksStore.setStocks(data);
      }
    });

    ws.on('analysis_done', (data) => {
      console.log('[App] Analysis done:', data);
      // Refresh stocks for current active universe without resetting filters/modal
      stocksStore.refreshCurrentUniverse();
    });

    ws.onStateChange((state) => {
      console.log('[App] WebSocket state changed:', state);
    });
  }

  ngOnInit(): void {
    console.log('[App] Initializing...');
    // Start WebSocket
    ws.connect();
    // Load initial stocks through sequence-guarded store action
    stocksStore.loadUniverse(stocksStore.activeUniverse());
  }

  ngOnDestroy(): void {
    ws.disconnect();
  }
}
