import { Component, OnInit, ViewChild, TemplateRef, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { stocksStore } from '../../core/stores/stocks.store';
import { Stock } from '../../core/models/stock.model';
import { ApiService } from '../../core/services/api.service';
import { StoxGridComponent, StoxGridColumn } from '../../shared/data-grid/stox-grid.component';

@Component({
  selector: 'app-tag-manager',
  standalone: true,
  imports: [CommonModule, FormsModule, StoxGridComponent],
  template: `
    <div class="tm-page">
      <div class="tm-header">
        <div>
          <h2 class="tm-title">🏷️ Stock Tag Manager</h2>
          <p class="tm-sub">
            Organize your unified <code>symbols.json</code> universe with logical tags. Add or remove tags on individual stocks or in bulk.
          </p>
        </div>
        <div class="tm-status" *ngIf="statusMsg()">{{ statusMsg() }}</div>
      </div>

      <!-- Existing Tags Summary -->
      <div class="tm-card">
        <div class="tm-card-title">Active Tags ({{ availableTags().length }})</div>
        <div class="tm-tags-overview">
          <button
            type="button"
            class="tm-tag-pill"
            [class.active]="filterTag() === 'ALL'"
            (click)="filterTag.set('ALL')"
          >
            All Stocks <span class="tm-count">{{ stocks().length }}</span>
          </button>
          <button
            type="button"
            class="tm-tag-pill"
            [class.active]="filterTag() === 'UNTAGGED'"
            (click)="filterTag.set('UNTAGGED')"
          >
            Untagged <span class="tm-count">{{ untaggedCount() }}</span>
          </button>
          <div class="tm-tag-chip-wrap" *ngFor="let t of availableTags()">
            <button
              type="button"
              class="tm-tag-pill"
              [class.active]="filterTag() === t.tag"
              (click)="filterTag.set(t.tag)"
            >
              {{ t.tag }} <span class="tm-count">{{ t.count }}</span>
            </button>
            <button
              type="button"
              class="tm-tag-del"
              title="Remove tag '{{ t.tag }}' from all stocks"
              (click)="deleteTagEverywhere(t.tag)"
            >🗑️</button>
          </div>
        </div>
      </div>

      <!-- Search & Bulk Tag Controls -->
      <div class="tm-card tm-toolbar">
        <div class="tm-toolbar-row">
          <input
            type="text"
            class="tm-input"
            placeholder="🔍 Filter by symbol, company, or sector..."
            [ngModel]="searchQuery()"
            (ngModelChange)="searchQuery.set($event)"
          />
          <button type="button" class="tm-btn" (click)="selectAllFiltered()">
            ☑️ Select Filtered ({{ filteredRows().length }})
          </button>
          <button type="button" class="tm-btn" (click)="clearSelection()" [disabled]="selectedCount() === 0">
            Clear ({{ selectedCount() }})
          </button>
        </div>

        <div class="tm-toolbar-row">
          <input
            type="text"
            class="tm-input"
            list="tm-existing-tags"
            placeholder="Type new or existing tag (e.g. Swing, Banking, Watchlist)..."
            [ngModel]="bulkTagInput()"
            (ngModelChange)="bulkTagInput.set($event)"
          />
          <datalist id="tm-existing-tags">
            <option *ngFor="let t of availableTags()" [value]="t.tag"></option>
          </datalist>
          <button
            type="button"
            class="tm-btn tm-btn-primary"
            [disabled]="saving() || selectedCount() === 0 || !bulkTagInput().trim()"
            (click)="applyBulkAdd()"
          >
            ➕ Add Tag to {{ selectedCount() }} Selected
          </button>
          <button
            type="button"
            class="tm-btn tm-btn-danger"
            [disabled]="saving() || selectedCount() === 0 || !bulkTagInput().trim()"
            (click)="applyBulkRemove()"
          >
            ➖ Remove Tag from {{ selectedCount() }} Selected
          </button>
        </div>
      </div>

      <!-- Cell templates placed outside @if / *ngIf per Angular ViewChild rule -->
      <ng-template #selectTpl let-row>
        <input
          type="checkbox"
          [checked]="isSelected(row.symbol)"
          (change)="toggleSelect(row.symbol)"
          aria-label="Select {{ row.symbol }}"
        />
      </ng-template>

      <ng-template #symbolTpl let-row>
        <span class="sym-pill">{{ row.symbol }}</span>
      </ng-template>

      <ng-template #tagsTpl let-row>
        <div class="tm-cell-tags">
          <span class="tm-inline-tag" *ngFor="let t of (row.tags || [])">
            {{ t }}
            <button
              type="button"
              class="tm-inline-x"
              title="Remove {{ t }} from {{ row.symbol }}"
              (click)="removeTagFromStock(row.symbol, t)"
            >×</button>
          </span>
          <span class="tm-untagged-label" *ngIf="!(row.tags?.length)">No tags</span>
        </div>
      </ng-template>

      <ng-template #quickAddTpl let-row>
        <div class="tm-quick-add">
          <select
            class="tm-quick-select"
            #tagSel
            (change)="onQuickAddSelect(row.symbol, tagSel)"
            aria-label="Add tag to {{ row.symbol }}"
          >
            <option value="">+ Add tag...</option>
            <option *ngFor="let t of availableTags()" [value]="t.tag">{{ t.tag }}</option>
          </select>
        </div>
      </ng-template>

      <!-- Stocks Grid -->
      <div class="tm-card tm-grid-card">
        <app-stox-grid
          [data]="filteredRows()"
          [columns]="columns"
          [clickable]="false"
          emptyText="No stocks match the current filter."
        ></app-stox-grid>
      </div>
    </div>
  `,
  styles: [`
    .tm-page {
      padding: 16px 24px 36px;
      max-width: 1400px;
      margin: 0 auto;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .tm-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
      flex-wrap: wrap;
    }
    .tm-title {
      margin: 0;
      font-size: 1.25rem;
      color: #f1f5f9;
    }
    .tm-sub {
      margin: 4px 0 0;
      font-size: 0.82rem;
      color: #94a3b8;
    }
    .tm-status {
      background: rgba(16, 185, 129, 0.14);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
      padding: 6px 12px;
      border-radius: 8px;
      font-size: 0.78rem;
      font-weight: 600;
    }
    .tm-card {
      background: rgba(18, 26, 43, 0.75);
      border: 1px solid rgba(255, 255, 255, 0.08);
      border-radius: 12px;
      padding: 14px 16px;
    }
    .tm-card-title {
      font-size: 0.78rem;
      font-weight: 700;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      margin-bottom: 10px;
    }
    .tm-tags-overview {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .tm-tag-chip-wrap {
      display: inline-flex;
      align-items: center;
      gap: 2px;
    }
    .tm-tag-pill {
      background: rgba(255, 255, 255, 0.06);
      border: 1px solid rgba(255, 255, 255, 0.14);
      color: #e2e8f0;
      padding: 5px 11px;
      border-radius: 999px;
      font-size: 0.76rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .tm-tag-pill.active {
      background: rgba(56, 189, 248, 0.2);
      border-color: #38bdf8;
      color: #7dd3fc;
    }
    .tm-count {
      background: rgba(15, 23, 42, 0.65);
      padding: 1px 6px;
      border-radius: 999px;
      font-size: 0.68rem;
      font-family: 'JetBrains Mono', monospace;
    }
    .tm-tag-del {
      background: transparent;
      border: none;
      cursor: pointer;
      font-size: 0.78rem;
      opacity: 0.7;
      padding: 2px 4px;
    }
    .tm-tag-del:hover { opacity: 1; }
    .tm-toolbar {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .tm-toolbar-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    .tm-input {
      flex: 1;
      min-width: 220px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.14);
      border-radius: 8px;
      padding: 7px 12px;
      color: #f1f5f9;
      font-size: 0.8rem;
      outline: none;
    }
    .tm-input:focus { border-color: #38bdf8; }
    .tm-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.16);
      color: #e2e8f0;
      padding: 7px 12px;
      border-radius: 8px;
      font-size: 0.76rem;
      font-weight: 600;
      cursor: pointer;
    }
    .tm-btn:disabled { opacity: 0.45; cursor: not-allowed; }
    .tm-btn-primary {
      background: rgba(14, 165, 233, 0.22);
      border-color: rgba(56, 189, 248, 0.5);
      color: #7dd3fc;
    }
    .tm-btn-danger {
      background: rgba(239, 68, 68, 0.16);
      border-color: rgba(239, 68, 68, 0.45);
      color: #fca5a5;
    }
    .tm-cell-tags {
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      align-items: center;
    }
    .tm-inline-tag {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: rgba(56, 189, 248, 0.14);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: #7dd3fc;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.7rem;
      font-weight: 600;
    }
    .tm-inline-x {
      background: none;
      border: none;
      color: inherit;
      cursor: pointer;
      font-size: 0.85rem;
      line-height: 1;
      padding: 0 2px;
      opacity: 0.8;
    }
    .tm-inline-x:hover { opacity: 1; color: #f87171; }
    .tm-untagged-label {
      font-size: 0.72rem;
      color: #64748b;
      font-style: italic;
    }
    .tm-quick-select {
      background: rgba(15, 23, 42, 0.8);
      border: 1px solid rgba(255, 255, 255, 0.14);
      color: #cbd5e1;
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 0.72rem;
    }
    .tm-grid-card {
      padding: 8px;
      overflow-x: auto;
    }

    :host-context([data-theme='light']) .tm-title { color: #0f172a; }
    :host-context([data-theme='light']) .tm-sub { color: #475569; }
    :host-context([data-theme='light']) .tm-card {
      background: #ffffff;
      border-color: #e2e8f0;
    }
    :host-context([data-theme='light']) .tm-tag-pill {
      background: #f1f5f9;
      border-color: #cbd5e1;
      color: #1e293b;
    }
    :host-context([data-theme='light']) .tm-tag-pill.active {
      background: #e0f2fe;
      border-color: #0284c7;
      color: #0369a1;
    }
    :host-context([data-theme='light']) .tm-count {
      background: #e2e8f0;
      color: #0f172a;
    }
    :host-context([data-theme='light']) .tm-input,
    :host-context([data-theme='light']) .tm-quick-select {
      background: #f8fafc;
      border-color: #cbd5e1;
      color: #0f172a;
    }
    :host-context([data-theme='light']) .tm-btn {
      background: #f1f5f9;
      border-color: #cbd5e1;
      color: #1e293b;
    }
    :host-context([data-theme='light']) .tm-inline-tag {
      background: #e0f2fe;
      border-color: #38bdf8;
      color: #0369a1;
    }
  `]
})
export class TagManagerComponent implements OnInit {
  @ViewChild('selectTpl', { static: true }) selectTpl!: TemplateRef<any>;
  @ViewChild('symbolTpl', { static: true }) symbolTpl!: TemplateRef<any>;
  @ViewChild('tagsTpl', { static: true }) tagsTpl!: TemplateRef<any>;
  @ViewChild('quickAddTpl', { static: true }) quickAddTpl!: TemplateRef<any>;

  stocks = stocksStore.stocks;
  availableTags = stocksStore.availableTags;

  searchQuery = signal<string>('');
  filterTag = signal<string>('ALL');
  bulkTagInput = signal<string>('');
  selectedSymbols = signal<Set<string>>(new Set());
  saving = signal<boolean>(false);
  statusMsg = signal<string>('');

  columns: StoxGridColumn<Stock>[] = [];

  untaggedCount = computed(() =>
    this.stocks().filter(s => !(s.tags && s.tags.length > 0)).length
  );

  selectedCount = computed(() => this.selectedSymbols().size);

  filteredRows = computed<Stock[]>(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const tag = this.filterTag();
    return this.stocks().filter(s => {
      if (tag === 'UNTAGGED') {
        if (s.tags && s.tags.length > 0) return false;
      } else if (tag !== 'ALL') {
        if (!(s.tags ?? []).includes(tag)) return false;
      }
      if (q) {
        const hay = `${s.symbol} ${s.name} ${s.sector} ${(s.tags ?? []).join(' ')}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  });

  ngOnInit(): void {
    this.columns = [
      { id: 'select', header: '', accessorFn: r => r.symbol, cellTemplate: this.selectTpl, sortable: false },
      { id: 'symbol', header: 'Symbol', accessorFn: r => r.symbol, cellTemplate: this.symbolTpl, sortable: true },
      { id: 'name', header: 'Company', accessorFn: r => r.name, sortable: true },
      { id: 'sector', header: 'Sector', accessorFn: r => r.sector || '-', sortable: true },
      { id: 'tags', header: 'Tags', accessorFn: r => (r.tags ?? []).join(', '), cellTemplate: this.tagsTpl, sortable: true },
      { id: 'quickAdd', header: 'Quick Add', accessorFn: r => r.symbol, cellTemplate: this.quickAddTpl, sortable: false },
    ];
  }

  isSelected(sym: string): boolean {
    return this.selectedSymbols().has(sym);
  }

  toggleSelect(sym: string): void {
    const next = new Set(this.selectedSymbols());
    if (next.has(sym)) next.delete(sym);
    else next.add(sym);
    this.selectedSymbols.set(next);
  }

  selectAllFiltered(): void {
    const next = new Set(this.selectedSymbols());
    for (const s of this.filteredRows()) next.add(s.symbol);
    this.selectedSymbols.set(next);
  }

  clearSelection(): void {
    this.selectedSymbols.set(new Set());
  }

  async applyBulkAdd(): Promise<void> {
    const tag = this.bulkTagInput().trim();
    const syms = Array.from(this.selectedSymbols());
    if (!tag || syms.length === 0) return;
    await this.runTagUpdate({ symbols: syms, add_tags: [tag] }, `Added "${tag}" to ${syms.length} stock(s).`);
  }

  async applyBulkRemove(): Promise<void> {
    const tag = this.bulkTagInput().trim();
    const syms = Array.from(this.selectedSymbols());
    if (!tag || syms.length === 0) return;
    await this.runTagUpdate({ symbols: syms, remove_tags: [tag] }, `Removed "${tag}" from ${syms.length} stock(s).`);
  }

  async removeTagFromStock(symbol: string, tag: string): Promise<void> {
    await this.runTagUpdate({ symbols: [symbol], remove_tags: [tag] }, `Removed "${tag}" from ${symbol}.`);
  }

  async onQuickAddSelect(symbol: string, sel: HTMLSelectElement): Promise<void> {
    const tag = sel.value.trim();
    sel.value = '';
    if (!tag) return;
    await this.runTagUpdate({ symbols: [symbol], add_tags: [tag] }, `Added "${tag}" to ${symbol}.`);
  }

  async deleteTagEverywhere(tag: string): Promise<void> {
    this.saving.set(true);
    try {
      const res = await ApiService.deleteTag(tag);
      this.statusMsg.set(res?.message || `Deleted tag "${tag}".`);
      if (this.filterTag() === tag) this.filterTag.set('ALL');
      await stocksStore.loadUniverse(stocksStore.activeUniverse());
    } finally {
      this.saving.set(false);
    }
  }

  private async runTagUpdate(
    payload: { symbols: string[]; add_tags?: string[]; remove_tags?: string[] },
    msg: string
  ): Promise<void> {
    this.saving.set(true);
    try {
      const res = await ApiService.updateSymbolTags(payload);
      this.statusMsg.set(res?.message || msg);
      await stocksStore.loadUniverse(stocksStore.activeUniverse());
    } finally {
      this.saving.set(false);
    }
  }
}
