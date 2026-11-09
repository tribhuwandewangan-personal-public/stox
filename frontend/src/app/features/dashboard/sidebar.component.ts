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
      width: 240px;
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

    .sidebar-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid rgba(56, 189, 248, 0.1);
      padding-bottom: 12px;
    }

    .sidebar-header h3 {
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      margin: 0;
    }

    .clear-btn {
      background: none;
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: var(--accent-red);
      font-size: 11px;
      padding: 4px 8px;
      border-radius: 4px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .clear-btn:hover {
      background: rgba(239, 68, 68, 0.1);
      border-color: var(--accent-red);
    }

    .search-box {
      position: relative;
    }

    .search-input {
      width: 100%;
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(56, 189, 248, 0.2);
      border-radius: 6px;
      padding: 8px 12px 8px 30px;
      font-size: 12px;
      color: #fff;
      transition: all 0.2s;
    }

    .search-input::placeholder {
      color: var(--text-muted);
    }

    .search-input:focus {
      outline: none;
      border-color: var(--accent-blue);
      background: rgba(15, 23, 42, 0.8);
    }

    .search-icon {
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 12px;
      opacity: 0.5;
    }

    .filter-section {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .section-label {
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.3px;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .chip {
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.2);
      color: var(--accent-blue);
      font-size: 11px;
      padding: 4px 10px;
      border-radius: 12px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .chip:hover {
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--accent-blue);
    }

    .chip.active {
      background: rgba(56, 189, 248, 0.3);
      border-color: var(--accent-blue);
      color: #fff;
    }

    .verdict-tabs {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .verdict-tab {
      background: rgba(56, 189, 248, 0.08);
      border: 1px solid rgba(56, 189, 248, 0.15);
      color: var(--text-secondary);
      padding: 8px 10px;
      border-radius: 6px;
      font-size: 11px;
      cursor: pointer;
      transition: all 0.2s;
      display: flex;
      align-items: center;
      gap: 6px;
      text-align: left;
    }

    .verdict-tab:hover {
      background: rgba(56, 189, 248, 0.15);
      border-color: rgba(56, 189, 248, 0.3);
    }

    .verdict-tab.active {
      background: rgba(56, 189, 248, 0.25);
      border-color: var(--accent-blue);
      color: #fff;
    }

    .verdict-tab .icon {
      font-size: 12px;
    }

    .verdict-tab .label {
      flex: 1;
      text-transform: capitalize;
      font-weight: 600;
    }

    .verdict-tab .count {
      font-size: 10px;
      color: var(--text-muted);
    }

    .stock-list {
      display: flex;
      flex-direction: column;
      gap: 4px;
      max-height: 150px;
      overflow-y: auto;
    }

    .stock-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 6px 8px;
      border-radius: 4px;
      background: rgba(15, 23, 42, 0.4);
      font-size: 11px;
      cursor: pointer;
      transition: all 0.2s;
    }

    .stock-item:hover:not(.more) {
      background: rgba(56, 189, 248, 0.15);
    }

    .stock-item.more {
      justify-content: center;
      color: var(--text-muted);
      cursor: default;
    }

    .stock-symbol {
      font-weight: 600;
      color: #fff;
    }

    .stock-price {
      color: var(--text-secondary);
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
