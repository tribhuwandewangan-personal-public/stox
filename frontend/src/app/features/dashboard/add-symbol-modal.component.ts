/**
 * Add Symbol Modal: Interactive partial-search stock selector & watchlist manager.
 * Allows searching across 2,200+ NSE equities by partial ticker, company name, or sector,
 * selecting a stock, customizing its metadata if needed, and adding (or adding + analyzing) it.
 */

import {
  Component,
  OnInit,
  OnDestroy,
  Output,
  EventEmitter,
  HostListener,
  ViewChild,
  ElementRef,
  AfterViewInit,
  signal,
  computed,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { SearchResult } from '../../core/models/stock.model';
import { stocksStore } from '../../core/stores/stocks.store';

@Component({
  selector: 'app-add-symbol-modal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="modal-overlay" (click)="close.emit()">
      <div class="modal-card" (click)="$event.stopPropagation()">

        <!-- Modal Header -->
        <div class="modal-header">
          <div class="header-title-wrap">
            <div class="header-icon">🌐</div>
            <div>
              <h2 class="modal-title">Add Stock to Watchlist</h2>
              <p class="modal-subtitle">
                Partial search by ticker symbol, company name, or sector across 2,200+ NSE equities
              </p>
            </div>
          </div>
          <button class="btn-close" (click)="close.emit()" title="Close (Esc)">✕</button>
        </div>

        <!-- Search Input & Quick Category Chips -->
        <div class="search-section">
          <div class="search-input-wrap">
            <span class="search-icon">🔍</span>
            <input
              #searchInput
              type="text"
              class="search-input"
              placeholder="Type partial symbol, company name, or sector (e.g. TATA, Bajaj, Defence, HAL, Bank)..."
              [ngModel]="query()"
              (ngModelChange)="onQueryChange($event)"
              (keydown)="onInputKeydown($event)"
            />
            <span class="search-spinner" *ngIf="loading()">⏳</span>
            <button *ngIf="query()" class="btn-clear" (click)="clearSearch()" title="Clear search">✕</button>
          </div>

          <!-- Quick Partial Search Filter Pills -->
          <div class="quick-chips">
            <span class="chips-label">Quick Filter:</span>
            <button
              *ngFor="let chip of quickChips"
              class="quick-chip"
              [class.active]="query().toLowerCase() === chip.query.toLowerCase()"
              (click)="applyQuickChip(chip.query)">
              {{ chip.label }}
            </button>
          </div>
        </div>

        <!-- Status / Feedback Banner -->
        <div
          *ngIf="feedbackMsg()"
          class="feedback-banner"
          [class.success]="feedbackType() === 'success'"
          [class.error]="feedbackType() === 'error'"
          [class.info]="feedbackType() === 'info'">
          <span>{{ feedbackMsg() }}</span>
          <button class="feedback-dismiss" (click)="feedbackMsg.set('')">✕</button>
        </div>

        <!-- Results Header Bar -->
        <div class="results-meta-bar">
          <span>
            Showing <strong>{{ results().length }}</strong> matching NSE stocks
            <ng-container *ngIf="query()"> for "<strong>{{ query() }}</strong>"</ng-container>
          </span>
          <span class="hint-text">Click a row to select &bull; Use ↑/↓ arrows &amp; Enter</span>
        </div>

        <!-- Scrollable Partial Search Results List -->
        <div class="results-list" *ngIf="results().length > 0; else emptyState">
          <div
            *ngFor="let item of results(); let i = index"
            class="result-row"
            [class.selected]="selectedItem()?.symbol === item.symbol"
            [class.already-added]="item.is_added"
            (click)="selectStock(item, i)">

            <div class="row-left">
              <div class="sym-line">
                <span class="sym-code">{{ item.symbol }}</span>
                <span class="exch-pill">{{ item.exchange || 'NSE' }}</span>
                <span class="sec-pill">{{ item.sector || 'Indian Equities' }}</span>
                <span class="src-pill" *ngIf="item.source">{{ item.source }}</span>
              </div>
              <div class="company-name">{{ item.name }}</div>
            </div>

            <div class="row-right" (click)="$event.stopPropagation()">
              <ng-container *ngIf="!item.is_added; else addedControls">
                <button
                  class="btn-row-add"
                  [disabled]="submittingSymbol() === item.symbol"
                  (click)="quickAdd(item, false)"
                  title="Add to Watchlist">
                  {{ submittingSymbol() === item.symbol ? '⏳ Adding...' : '➕ Add' }}
                </button>
                <button
                  class="btn-row-analyze"
                  [disabled]="submittingSymbol() === item.symbol"
                  (click)="quickAdd(item, true)"
                  title="Add to Watchlist & Run Analysis Immediately">
                  ⚡ Add &amp; Analyze
                </button>
              </ng-container>

              <ng-template #addedControls>
                <span class="added-badge">✓ In Watchlist</span>
                <button
                  class="btn-row-remove"
                  [disabled]="submittingSymbol() === item.symbol"
                  (click)="removeStock(item)"
                  title="Remove from Watchlist">
                  Remove
                </button>
              </ng-template>
            </div>
          </div>
        </div>

        <ng-template #emptyState>
          <div class="empty-results">
            <span *ngIf="loading()">⏳ Searching NSE catalog...</span>
            <span *ngIf="!loading()">No stocks found matching "{{ query() }}". Try a shorter partial name or ticker.</span>
          </div>
        </ng-template>

        <!-- Selected Stock Configuration & Primary Action Footer -->
        <div class="selected-footer" *ngIf="selectedItem() as sel">
          <div class="selected-header">
            <span class="selected-title">
              Selected Stock: <strong class="text-sky">{{ sel.symbol }}</strong>
              <span class="selected-status" *ngIf="sel.is_added">(Already in Watchlist)</span>
            </span>
          </div>

          <div class="selected-fields-grid">
            <div class="field-box">
              <label>Symbol</label>
              <input type="text" [value]="sel.symbol" readonly class="field-input readonly" />
            </div>
            <div class="field-box">
              <label>Company Name</label>
              <input
                type="text"
                [ngModel]="editName()"
                (ngModelChange)="editName.set($event)"
                class="field-input"
              />
            </div>
            <div class="field-box">
              <label>Sector</label>
              <input
                type="text"
                [ngModel]="editSector()"
                (ngModelChange)="editSector.set($event)"
                class="field-input"
              />
            </div>
          </div>

          <div class="footer-actions">
            <button class="btn-cancel" (click)="close.emit()">Close</button>
            <ng-container *ngIf="!sel.is_added">
              <button
                class="btn-primary-add"
                [disabled]="submittingSymbol() !== null"
                (click)="confirmSelectedAdd(false)">
                ➕ Add {{ sel.symbol }} to Watchlist
              </button>
              <button
                class="btn-primary-analyze"
                [disabled]="submittingSymbol() !== null"
                (click)="confirmSelectedAdd(true)">
                ⚡ Add &amp; Run Analysis
              </button>
            </ng-container>
          </div>
        </div>

      </div>
    </div>
  `,
  styles: [`
    .modal-overlay {
      position: fixed;
      inset: 0;
      background: rgba(2, 6, 23, 0.84);
      backdrop-filter: blur(10px);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 2200;
      padding: 20px;
    }

    .modal-card {
      background: linear-gradient(165deg, #0f172a 0%, #090f1d 100%);
      border: 1px solid rgba(56, 189, 248, 0.4);
      border-radius: 16px;
      width: 100%;
      max-width: 780px;
      max-height: 88vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 24px 60px rgba(0, 0, 0, 0.85), 0 0 30px rgba(56, 189, 248, 0.12);
      overflow: hidden;
    }

    .modal-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 18px 22px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      background: rgba(15, 23, 42, 0.6);
    }

    .header-title-wrap {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .header-icon {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.35);
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 1.2rem;
    }

    .modal-title {
      font-family: 'Outfit', sans-serif;
      font-size: 1.2rem;
      font-weight: 700;
      color: #fff;
      margin: 0;
    }

    .modal-subtitle {
      font-size: 0.76rem;
      color: #94a3b8;
      margin: 2px 0 0 0;
    }

    .btn-close {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.12);
      color: #94a3b8;
      width: 32px;
      height: 32px;
      border-radius: 8px;
      cursor: pointer;
      font-size: 1rem;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.18s;
    }
    .btn-close:hover {
      background: rgba(239, 68, 68, 0.2);
      border-color: #ef4444;
      color: #fff;
    }

    .search-section {
      padding: 16px 22px 12px 22px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.06);
    }

    .search-input-wrap {
      position: relative;
      display: flex;
      align-items: center;
    }

    .search-icon {
      position: absolute;
      left: 14px;
      font-size: 0.95rem;
      pointer-events: none;
    }

    .search-input {
      width: 100%;
      background: rgba(0, 0, 0, 0.35);
      border: 1.5px solid rgba(56, 189, 248, 0.35);
      border-radius: 10px;
      padding: 11px 40px 11px 40px;
      color: #f8fafc;
      font-size: 0.9rem;
      outline: none;
      transition: border-color 0.2s, box-shadow 0.2s;
    }
    .search-input:focus {
      border-color: #38bdf8;
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.18);
    }

    .search-spinner {
      position: absolute;
      right: 36px;
      font-size: 0.85rem;
    }

    .btn-clear {
      position: absolute;
      right: 12px;
      background: none;
      border: none;
      color: #94a3b8;
      cursor: pointer;
      font-size: 0.85rem;
      padding: 4px;
    }
    .btn-clear:hover { color: #fff; }

    .quick-chips {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .chips-label {
      font-size: 0.7rem;
      color: #64748b;
      font-weight: 600;
      margin-right: 2px;
    }

    .quick-chip {
      background: rgba(255, 255, 255, 0.04);
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #94a3b8;
      padding: 3px 10px;
      border-radius: 14px;
      font-size: 0.7rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .quick-chip:hover, .quick-chip.active {
      background: rgba(56, 189, 248, 0.16);
      border-color: rgba(56, 189, 248, 0.45);
      color: #38bdf8;
    }

    .feedback-banner {
      margin: 10px 22px 0 22px;
      padding: 9px 14px;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .feedback-banner.success {
      background: rgba(16, 185, 129, 0.16);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
    }
    .feedback-banner.error {
      background: rgba(239, 68, 68, 0.16);
      border: 1px solid rgba(239, 68, 68, 0.4);
      color: #f87171;
    }
    .feedback-banner.info {
      background: rgba(56, 189, 248, 0.16);
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: #38bdf8;
    }
    .feedback-dismiss {
      background: none;
      border: none;
      color: inherit;
      cursor: pointer;
      font-size: 0.85rem;
    }

    .results-meta-bar {
      padding: 8px 22px;
      font-size: 0.72rem;
      color: #64748b;
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: rgba(0, 0, 0, 0.2);
    }
    .results-meta-bar strong { color: #cbd5e1; }
    .hint-text { font-size: 0.68rem; color: #475569; }

    .results-list {
      flex: 1;
      min-height: 220px;
      max-height: 360px;
      overflow-y: auto;
      padding: 8px 16px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .result-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 10px 14px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.025);
      border: 1px solid rgba(255, 255, 255, 0.06);
      cursor: pointer;
      transition: all 0.15s;
    }
    .result-row:hover {
      background: rgba(56, 189, 248, 0.08);
      border-color: rgba(56, 189, 248, 0.3);
    }
    .result-row.selected {
      background: rgba(56, 189, 248, 0.14);
      border-color: #38bdf8;
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.12);
    }
    .result-row.already-added {
      opacity: 0.85;
    }

    .row-left {
      display: flex;
      flex-direction: column;
      gap: 3px;
      min-width: 0;
      flex: 1;
    }

    .sym-line {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }

    .sym-code {
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.9rem;
      font-weight: 800;
      color: #fff;
    }

    .exch-pill {
      font-size: 0.62rem;
      font-weight: 700;
      padding: 1px 6px;
      border-radius: 4px;
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }

    .sec-pill {
      font-size: 0.64rem;
      font-weight: 600;
      padding: 1px 7px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.06);
      color: #cbd5e1;
    }

    .src-pill {
      font-size: 0.6rem;
      color: #64748b;
    }

    .company-name {
      font-size: 0.78rem;
      color: #94a3b8;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .row-right {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }

    .btn-row-add {
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
      padding: 5px 11px;
      border-radius: 7px;
      font-size: 0.74rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-row-add:hover:not(:disabled) {
      background: #10b981;
      color: #090f1d;
    }

    .btn-row-analyze {
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.4);
      color: #38bdf8;
      padding: 5px 11px;
      border-radius: 7px;
      font-size: 0.74rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-row-analyze:hover:not(:disabled) {
      background: #38bdf8;
      color: #090f1d;
    }

    .added-badge {
      font-size: 0.72rem;
      font-weight: 700;
      color: #10b981;
      background: rgba(16, 185, 129, 0.12);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 3px 9px;
      border-radius: 6px;
    }

    .btn-row-remove {
      background: rgba(239, 68, 68, 0.12);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #f87171;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 0.68rem;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-row-remove:hover:not(:disabled) {
      background: rgba(239, 68, 68, 0.25);
    }

    .empty-results {
      padding: 40px 20px;
      text-align: center;
      color: #64748b;
      font-size: 0.85rem;
    }

    .selected-footer {
      padding: 14px 22px 18px 22px;
      background: rgba(15, 23, 42, 0.85);
      border-top: 1px solid rgba(56, 189, 248, 0.25);
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .selected-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.78rem;
      color: #cbd5e1;
    }

    .text-sky { color: #38bdf8; font-family: 'JetBrains Mono', monospace; }
    .selected-status { color: #10b981; font-size: 0.72rem; margin-left: 6px; }

    .selected-fields-grid {
      display: grid;
      grid-template-columns: 120px 1fr 180px;
      gap: 10px;
    }

    .field-box {
      display: flex;
      flex-direction: column;
      gap: 3px;
    }
    .field-box label {
      font-size: 0.66rem;
      color: #64748b;
      font-weight: 600;
      text-transform: uppercase;
    }

    .field-input {
      background: rgba(0, 0, 0, 0.35);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 6px;
      padding: 6px 9px;
      color: #f1f5f9;
      font-size: 0.78rem;
      outline: none;
    }
    .field-input:focus { border-color: #38bdf8; }
    .field-input.readonly {
      color: #38bdf8;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      background: rgba(56, 189, 248, 0.08);
    }

    .footer-actions {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 10px;
      margin-top: 2px;
    }

    .btn-cancel {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #cbd5e1;
      padding: 7px 14px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
    }

    .btn-primary-add {
      background: rgba(16, 185, 129, 0.2);
      border: 1px solid #10b981;
      color: #34d399;
      padding: 7px 16px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.18s;
    }
    .btn-primary-add:hover:not(:disabled) {
      background: #10b981;
      color: #090f1d;
    }

    .btn-primary-analyze {
      background: linear-gradient(135deg, #0284c7, #6366f1);
      border: none;
      color: #fff;
      padding: 8px 18px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 2px 12px rgba(2, 132, 199, 0.35);
      transition: all 0.18s;
    }
    .btn-primary-analyze:hover:not(:disabled) {
      transform: translateY(-1px);
      opacity: 0.95;
    }

    @media (max-width: 640px) {
      .selected-fields-grid {
        grid-template-columns: 1fr;
      }
      .result-row {
        flex-direction: column;
        align-items: flex-start;
      }
      .row-right {
        width: 100%;
        justify-content: flex-end;
      }
    }
  `],
})
export class AddSymbolModalComponent implements OnInit, AfterViewInit, OnDestroy {
  @Output() close = new EventEmitter<void>();
  @ViewChild('searchInput') searchInputRef!: ElementRef<HTMLInputElement>;

  query = signal<string>('');
  results = signal<SearchResult[]>([]);
  loading = signal<boolean>(false);
  selectedIndex = signal<number>(0);
  selectedItem = computed<SearchResult | null>(() => {
    const list = this.results();
    const idx = this.selectedIndex();
    return list.length > 0 && idx >= 0 && idx < list.length ? list[idx] : null;
  });

  editName = signal<string>('');
  editSector = signal<string>('');
  submittingSymbol = signal<string | null>(null);
  feedbackMsg = signal<string>('');
  feedbackType = signal<'success' | 'error' | 'info'>('info');

  private debounceTimer: any = null;
  private searchSeq = 0;

  quickChips = [
    { label: 'Popular NSE', query: '' },
    { label: 'Defence', query: 'Defence' },
    { label: 'Capital Markets', query: 'Capital Markets' },
    { label: 'Banking', query: 'Bank' },
    { label: 'IT & Tech', query: 'Technology' },
    { label: 'Pharma', query: 'Pharma' },
    { label: 'Auto', query: 'Auto' },
    { label: 'Tata Group', query: 'TATA' },
  ];

  @HostListener('window:keydown.escape')
  onEscape(): void {
    this.close.emit();
  }

  ngOnInit(): void {
    this.performSearch('');
  }

  ngAfterViewInit(): void {
    setTimeout(() => {
      this.searchInputRef?.nativeElement?.focus();
    }, 30);
  }

  ngOnDestroy(): void {
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
  }

  onQueryChange(val: string): void {
    this.query.set(val);
    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
    }
    this.debounceTimer = setTimeout(() => {
      this.performSearch(val);
    }, 150);
  }

  clearSearch(): void {
    this.query.set('');
    this.performSearch('');
    this.searchInputRef?.nativeElement?.focus();
  }

  applyQuickChip(q: string): void {
    this.query.set(q);
    this.performSearch(q);
    this.searchInputRef?.nativeElement?.focus();
  }

  onInputKeydown(event: KeyboardEvent): void {
    const list = this.results();
    if (!list.length) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      const next = Math.min(list.length - 1, this.selectedIndex() + 1);
      this.selectStock(list[next], next);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      const prev = Math.max(0, this.selectedIndex() - 1);
      this.selectStock(list[prev], prev);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const sel = this.selectedItem();
      if (sel && !sel.is_added) {
        this.confirmSelectedAdd(true);
      }
    }
  }

  selectStock(item: SearchResult, index: number): void {
    this.selectedIndex.set(index);
    this.editName.set(item.name || item.symbol);
    this.editSector.set(item.sector || 'Indian Equities');
  }

  private static readonly FALLBACK_NSE_CATALOG: Array<{ symbol: string; name: string; sector: string }> = [
    { symbol: 'HAL', name: 'Hindustan Aeronautics Limited', sector: 'Aerospace & Defence' },
    { symbol: 'BDL', name: 'Bharat Dynamics Limited', sector: 'Aerospace & Defence' },
    { symbol: 'COCHINSHIP', name: 'Cochin Shipyard Limited', sector: 'Aerospace & Defence' },
    { symbol: 'PARAS', name: 'Paras Defence and Space Technologies Limited', sector: 'Aerospace & Defence' },
    { symbol: 'MCX', name: 'Multi Commodity Exchange of India Limited', sector: 'Capital Markets' },
    { symbol: 'ANGELONE', name: 'Angel One Limited', sector: 'Capital Markets' },
    { symbol: '360ONE', name: '360 ONE WAM Limited', sector: 'Capital Markets' },
    { symbol: 'CAMS', name: 'Computer Age Management Services Limited', sector: 'Capital Markets' },
    { symbol: 'KFINTECH', name: 'KFin Technologies Limited', sector: 'Capital Markets' },
    { symbol: 'HDFCAMC', name: 'HDFC Asset Management Company Limited', sector: 'Capital Markets' },
    { symbol: 'TCS', name: 'Tata Consultancy Services Limited', sector: 'Information Technology' },
    { symbol: 'INFY', name: 'Infosys Limited', sector: 'Information Technology' },
    { symbol: 'HCLTECH', name: 'HCL Technologies Limited', sector: 'Information Technology' },
    { symbol: 'PERSISTENT', name: 'Persistent Systems Limited', sector: 'Information Technology' },
    { symbol: 'LTIM', name: 'LTIMindtree Limited', sector: 'Information Technology' },
    { symbol: 'BAJFINANCE', name: 'Bajaj Finance Limited', sector: 'Banking & Financial Services' },
    { symbol: 'CHOLAFIN', name: 'Cholamandalam Investment and Finance Company Limited', sector: 'Banking & Financial Services' },
    { symbol: 'AXISBANK', name: 'Axis Bank Limited', sector: 'Banking & Financial Services' },
    { symbol: 'PFC', name: 'Power Finance Corporation Limited', sector: 'Banking & Financial Services' },
    { symbol: 'RECLTD', name: 'REC Limited', sector: 'Banking & Financial Services' },
    { symbol: 'SUNPHARMA', name: 'Sun Pharmaceutical Industries Limited', sector: 'Healthcare & Pharmaceuticals' },
    { symbol: 'CIPLA', name: 'Cipla Limited', sector: 'Healthcare & Pharmaceuticals' },
    { symbol: 'DIVISLAB', name: "Divi's Laboratories Limited", sector: 'Healthcare & Pharmaceuticals' },
    { symbol: 'APOLLOHOSP', name: 'Apollo Hospitals Enterprise Limited', sector: 'Healthcare & Pharmaceuticals' },
    { symbol: 'MARUTI', name: 'Maruti Suzuki India Limited', sector: 'Automobile' },
    { symbol: 'M&M', name: 'Mahindra & Mahindra Limited', sector: 'Automobile' },
    { symbol: 'BAJAJ-AUTO', name: 'Bajaj Auto Limited', sector: 'Automobile' },
    { symbol: 'EICHERMOT', name: 'Eicher Motors Limited', sector: 'Automobile' },
    { symbol: 'SONACOMS', name: 'Sona BLW Precision Forgings Limited', sector: 'Auto Ancillaries' },
    { symbol: 'SIEMENS', name: 'Siemens Limited', sector: 'Capital Goods & Electricals' },
    { symbol: 'CUMMINSIND', name: 'Cummins India Limited', sector: 'Capital Goods & Electricals' },
    { symbol: 'BHEL', name: 'Bharat Heavy Electricals Limited', sector: 'Capital Goods & Electricals' },
    { symbol: 'TATAPOWER', name: 'The Tata Power Company Limited', sector: 'Energy, Oil & Power' },
    { symbol: 'NTPC', name: 'NTPC Limited', sector: 'Energy, Oil & Power' },
    { symbol: 'POWERGRID', name: 'Power Grid Corporation of India Limited', sector: 'Energy, Oil & Power' },
    { symbol: 'TITAN', name: 'Titan Company Limited', sector: 'FMCG & Consumer' },
    { symbol: 'ITC', name: 'ITC Limited', sector: 'FMCG & Consumer' },
    { symbol: 'HINDUNILVR', name: 'Hindustan Unilever Limited', sector: 'FMCG & Consumer' },
    { symbol: 'TRENT', name: 'Trent Limited', sector: 'FMCG & Consumer' },
    { symbol: 'ZOMATO', name: 'Zomato Limited', sector: 'Consumer & Fintech' },
    { symbol: 'PIDILITIND', name: 'Pidilite Industries Limited', sector: 'Chemicals & Materials' },
    { symbol: 'SRF', name: 'SRF Limited', sector: 'Chemicals & Materials' },
    { symbol: 'DEEPAKNTR', name: 'Deepak Nitrite Limited', sector: 'Chemicals & Materials' },
  ];

  private buildLocalFallbackResults(q: string): SearchResult[] {
    const existingSet = new Set(stocksStore.stocks().map(s => s.symbol.toUpperCase()));
    const combinedMap = new Map<string, SearchResult>();

    for (const item of AddSymbolModalComponent.FALLBACK_NSE_CATALOG) {
      combinedMap.set(item.symbol, {
        symbol: item.symbol,
        name: item.name,
        sector: item.sector,
        exchange: 'NSE',
        is_added: existingSet.has(item.symbol),
        source: 'NSE Catalog',
      });
    }
    for (const s of stocksStore.stocks()) {
      const sym = s.symbol.toUpperCase();
      if (!combinedMap.has(sym)) {
        combinedMap.set(sym, {
          symbol: sym,
          name: s.name || sym,
          sector: s.sector || 'Indian Equities',
          exchange: 'NSE',
          is_added: true,
          source: 'Active Universe',
        });
      }
    }

    const allItems = Array.from(combinedMap.values());
    const clean = q.trim().toLowerCase();
    if (!clean) {
      return allItems.sort((a, b) => Number(a.is_added) - Number(b.is_added)).slice(0, 30);
    }
    const tokens = clean.split(/\s+/).filter(Boolean);
    const filtered = allItems.filter(it => {
      const hay = `${it.symbol} ${it.name} ${it.sector}`.toLowerCase();
      return tokens.every(t => hay.includes(t));
    });
    const qUp = q.trim().toUpperCase();
    if (qUp.length >= 2 && !combinedMap.has(qUp) && /^[A-Z0-9&-]+$/.test(qUp)) {
      filtered.push({
        symbol: qUp,
        name: `${qUp} Limited`,
        sector: 'Indian Equities',
        exchange: 'NSE',
        is_added: existingSet.has(qUp),
        source: 'Custom NSE Symbol',
      });
    }
    return filtered.slice(0, 30);
  }

  private async performSearch(q: string): Promise<void> {
    const seq = ++this.searchSeq;
    // Show instant local matches immediately while backend query runs
    const localMatches = this.buildLocalFallbackResults(q);
    if (this.results().length === 0 && localMatches.length > 0) {
      this.results.set(localMatches);
      this.selectStock(localMatches[0], 0);
    }

    this.loading.set(true);
    try {
      const items = await ApiService.searchSymbol(q.trim());
      if (seq !== this.searchSeq) return;
      const finalItems = items && items.length > 0 ? items : localMatches;
      this.results.set(finalItems);
      if (finalItems.length > 0) {
        this.selectStock(finalItems[0], 0);
      } else {
        this.selectedIndex.set(-1);
      }
    } catch {
      if (seq !== this.searchSeq) return;
      this.results.set(localMatches);
      if (localMatches.length > 0) {
        this.selectStock(localMatches[0], 0);
      } else {
        this.selectedIndex.set(-1);
      }
    } finally {
      if (seq === this.searchSeq) {
        this.loading.set(false);
      }
    }
  }

  async quickAdd(item: SearchResult, runAnalysis: boolean): Promise<void> {
    await this.executeAdd(item.symbol, item.name, item.sector, item.exchange || 'NSE', runAnalysis);
  }

  async confirmSelectedAdd(runAnalysis: boolean): Promise<void> {
    const sel = this.selectedItem();
    if (!sel) return;
    await this.executeAdd(
      sel.symbol,
      this.editName().trim() || sel.name || sel.symbol,
      this.editSector().trim() || sel.sector || 'Indian Equities',
      sel.exchange || 'NSE',
      runAnalysis,
    );
  }

  private async executeAdd(
    symbol: string,
    name: string,
    sector: string,
    exchange: string,
    runAnalysis: boolean,
  ): Promise<void> {
    this.submittingSymbol.set(symbol);
    this.feedbackMsg.set('');
    try {
      const res = await ApiService.addSymbol(symbol, name, sector, exchange);
      const updatedList = this.results().map(r =>
        r.symbol === symbol ? { ...r, is_added: true, name, sector } : r
      );
      this.results.set(updatedList);

      if (runAnalysis) {
        try {
          await ApiService.triggerAnalysis(symbol);
          this.feedbackType.set('success');
          this.feedbackMsg.set(`✅ Added ${symbol} (${name}) and started multi-agent analysis!`);
        } catch {
          this.feedbackType.set('info');
          this.feedbackMsg.set(`✅ Added ${symbol} (${name}) to Watchlist (queued for analysis).`);
        }
      } else {
        this.feedbackType.set('success');
        this.feedbackMsg.set(res?.message || `✅ Added ${symbol} (${name}) to Watchlist!`);
      }

      await stocksStore.loadUniverse(stocksStore.activeUniverse());
    } catch (err: any) {
      this.feedbackType.set('error');
      this.feedbackMsg.set(`❌ Could not add ${symbol}: ${err?.message || err}`);
    } finally {
      this.submittingSymbol.set(null);
    }
  }

  async removeStock(item: SearchResult): Promise<void> {
    this.submittingSymbol.set(item.symbol);
    this.feedbackMsg.set('');
    try {
      await ApiService.removeSymbol(item.symbol);
      const updatedList = this.results().map(r =>
        r.symbol === item.symbol ? { ...r, is_added: false } : r
      );
      this.results.set(updatedList);
      this.feedbackType.set('info');
      this.feedbackMsg.set(`Removed ${item.symbol} from Curated Watchlist.`);
      await stocksStore.loadUniverse(stocksStore.activeUniverse());
    } catch (err: any) {
      this.feedbackType.set('error');
      this.feedbackMsg.set(`❌ Could not remove ${item.symbol}: ${err?.message || err}`);
    } finally {
      this.submittingSymbol.set(null);
    }
  }
}
