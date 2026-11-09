/**
 * Dashboard component: Main content area with grid, sidebar, and modal.
 */

import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { StockGridComponent } from './stock-grid.component';
import { SidebarComponent } from './sidebar.component';
import { StockDetailModalComponent } from './stock-detail-modal.component';
import { Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    StockGridComponent,
    SidebarComponent,
    StockDetailModalComponent
  ],
  template: `
    <div class="dashboard-container">
      <app-sidebar></app-sidebar>
      <app-stock-grid (selectStock)="onStockSelect($event)"></app-stock-grid>
    </div>

    <!-- Stock detail modal (Level 3) -->
    <app-stock-detail-modal></app-stock-detail-modal>
  `,
  styles: [`
    .dashboard-container {
      display: flex;
      flex: 1;
      gap: 0;
      overflow: hidden;
    }

    @media (max-width: 768px) {
      .dashboard-container {
        flex-direction: column;
      }
    }
  `]
})
export class DashboardComponent {
  onStockSelect(stock: Stock): void {
    stocksStore.selectSymbol(stock.symbol);
  }
}
