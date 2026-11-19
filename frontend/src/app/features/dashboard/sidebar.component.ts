/**
 * Sidebar: search, sector filter, verdict tabs.
 */

import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { stocksStore } from '../../core/stores/stocks.store';
import { VerdictBucket, verdictInfo } from '../../core/utils/verdict';

const VERDICTS: VerdictBucket[] = ['buy', 'accumulate', 'hold', 'reduce', 'sell', 'pending'];

@Component({
  selector: 'app-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="sidebar">
      <!-- Header -->
      <div class="sidebar-header">
        <h3>Filters</h3>
        <button class="clear-btn" (click)="clearFilters()">Clear</button>
      </div>

      <!-- Search -->
      <div class="search-box">
        <input
          type="text"
          placeholder="Search symbol or name..."
          [(ngModel)]="searchTerm"
          (ngModelChange)="onSearchChange($event)"
          class="search-input">
        <span class="search-icon">🔍</span>
      </div>

      <!-- Sectors -->
      <div class="filter-section">
        <label class="section-label">Sectors</label>
        <div class="chips">
          @for (sector of stocksStore.sectors(); track sector) {
            <button
              class="chip"
              [class.active]="stocksStore.filter().sector === sector"
              (click)="onSectorClick(sector)">
              {{ sector }}
            </button>
          }
        </div>
      </div>

      <!-- Verdict Tabs -->
      <div class="filter-section">
        <label class="section-label">Verdict</label>
        <div class="verdict-tabs">
          @for (verdict of verdicts; track verdict) {
            <button
              class="verdict-tab"
              [class.active]="stocksStore.filter().verdict === verdict"
              (click)="onVerdictClick(verdict)">
              <span class="icon">{{ verdictInfo(verdict).icon }}</span>
              <span class="label">{{ verdict }}</span>
              <span class="count">({{ verdictCounts[verdict] }})</span>
            </button>
          }
        </div>
      </div>

      <!-- Stock List (optional) -->
      <div class="filter-section">
        <label class="section-label">All Stocks ({{ totalStocks }})</label>
        <div class="stock-list">
          @for (stock of stocksStore.filteredStocks() | slice:0:10; track stock.symbol) {
            <div class="stock-item">
              <span class="stock-symbol">{{ stock.symbol }}</span>
              <span class="stock-price">Rs. {{ stock.price_info.price | number:'1.2-2' }}</span>
            </div>
          }
          @if (totalStocks > 10) {
            <div class="stock-item more">+{{ totalStocks - 10 }} more</div>
          }
        </div>
      </div>
    </div>
  `,
  styles: [`
  .sidebar {
    width: 180px;
    flex-shrink: 0;
    background: linear-gradient(180deg, rgba(30, 41, 59, 0.6), rgba(18, 26, 43, 0.8));
    border-right: 1px solid rgba(56, 189, 248, 0.15);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    overflow-y: auto;
    border-radius: 12px 0 0 12px;
  }

  @media (max-width: 768px) {
    .sidebar {
      width: 100%;
      border-right: none;
      border-bottom: 1px solid rgba(56, 189, 248, 0.15);
      border-radius: 0;
      padding: 12px;
      gap: 16px;
    }
  }
`]
})
export class SidebarComponent {
  searchTerm = signal('');
  verdicts = VERDICTS;
  stocksStore = stocksStore;

  verdictInfo(bucket: VerdictBucket) {
    return verdictInfo(bucket);
  }

  get verdictCounts() {
    return stocksStore.verdictCounts();
  }

  get totalStocks(): number {
    return stocksStore.filteredStocks().length;
  }

  onSearchChange(query: string): void {
    stocksStore.setSearchFilter(query.trim());
  }

  onSectorClick(sector: string): void {
    const current = stocksStore.filter().sector;
    stocksStore.setSectorFilter(current === sector ? null : sector);
  }

  onVerdictClick(verdict: VerdictBucket): void {
    const current = stocksStore.filter().verdict;
    stocksStore.setVerdictFilter(current === verdict ? null : verdict);
  }

  clearFilters(): void {
    this.searchTerm.set('');
    stocksStore.clearFilters();
  }
}
