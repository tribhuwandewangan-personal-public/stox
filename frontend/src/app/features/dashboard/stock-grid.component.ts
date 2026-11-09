/**
 * Stock grid: 4-column responsive layout with trackBy for performance.
 */

import { Component, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Stock } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';
import { StockCardComponent } from './stock-card.component';

@Component({
  selector: 'app-stock-grid',
  standalone: true,
  imports: [CommonModule, StockCardComponent],
  template: `
    <div class="stock-grid">
      @for (stock of stocksStore.filteredStocks(); track stock.symbol) {
        <app-stock-card
          [stock]="stock"
          (cardClick)="onStockSelect($event)">
        </app-stock-card>
      }
      @empty {
        <div class="no-stocks">No stocks found</div>
      }
    </div>
  `,
  styles: [`
    .stock-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      gap: 16px;
      flex: 1;
      overflow-y: auto;
    }

    @media (max-width: 1024px) {
      .stock-grid {
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
      }
    }

    @media (max-width: 768px) {
      .stock-grid {
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
      }
    }

    @media (max-width: 480px) {
      .stock-grid {
        grid-template-columns: 1fr;
        gap: 12px;
      }
    }

    .no-stocks {
      grid-column: 1 / -1;
      text-align: center;
      color: var(--text-muted);
      padding: 40px 20px;
      font-size: 14px;
    }
  `]
})
export class StockGridComponent {
  @Output() selectStock = new EventEmitter<Stock>();

  stocksStore = stocksStore;

  onStockSelect(stock: Stock): void {
    this.selectStock.emit(stock);
    stocksStore.selectSymbol(stock.symbol);
  }
}
