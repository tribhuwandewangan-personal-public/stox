import {
  Component,
  EventEmitter,
  Input,
  Output,
  TemplateRef,
  ViewEncapsulation,
  computed,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  ColumnDef,
  FlexRender,
  RowData,
  SortingState,
  createSortedRowModel,
  injectTable,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
} from '@tanstack/angular-table';

export interface StoxGridColumn<T = any> {
  id: string;
  header: string;
  accessorFn?: (row: T, index: number) => any;
  cellTemplate?: TemplateRef<{ $implicit: T; row: T; index: number }>;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  headerClass?: string;
  cellClass?: string;
}

const features = tableFeatures({
  rowSortingFeature,
  sortedRowModel: createSortedRowModel(),
  sortFns: {
    alphanumeric: sortFn_alphanumeric,
    basic: sortFn_basic,
  },
});

@Component({
  selector: 'app-stox-grid',
  standalone: true,
  imports: [CommonModule, FlexRender],
  encapsulation: ViewEncapsulation.None,
  template: `
    <div class="stox-grid-wrap">
      <table class="stox-grid-table">
        <thead>
          @for (headerGroup of table.getHeaderGroups(); track headerGroup.id) {
            <tr>
              @for (header of headerGroup.headers; track header.id) {
                <th
                  [class]="colHeaderClass(header.id)"
                  [class.sortable]="header.column.getCanSort()"
                  [class.sorted]="!!header.column.getIsSorted()"
                  [style.text-align]="colAlign(header.id)"
                  (click)="header.column.getCanSort() && header.column.toggleSorting()"
                  [title]="header.column.getCanSort() ? 'Click to sort' : ''"
                >
                  <span class="th-inner">
                    <ng-container *flexRender="header.column.columnDef.header; props: header.getContext(); let h">
                      {{ h }}
                    </ng-container>
                    @if (header.column.getCanSort()) {
                      <span class="sort-ind">
                        {{ header.column.getIsSorted() === 'asc' ? '▲' : header.column.getIsSorted() === 'desc' ? '▼' : '⇅' }}
                      </span>
                    }
                  </span>
                </th>
              }
            </tr>
          }
        </thead>
        <tbody>
          @for (row of table.getRowModel().rows; track row.id) {
            <tr
              [class]="getRowClass(row.original, row.index)"
              [class.row-clickable]="clickable"
              [attr.data-symbol]="rowSymbolFn ? rowSymbolFn(row.original) : null"
              (click)="clickable && rowClick.emit(row.original)"
            >
              @for (cell of row.getAllCells(); track cell.id) {
                <td [style.text-align]="colAlign(cell.column.id)" [class]="colCellClass(cell.column.id)">
                  @if (colTemplate(cell.column.id); as tpl) {
                    <ng-container
                      [ngTemplateOutlet]="tpl"
                      [ngTemplateOutletContext]="{ $implicit: row.original, row: row.original, index: row.index }"
                    ></ng-container>
                  } @else {
                    <ng-container *flexRender="cell.column.columnDef.cell; props: cell.getContext(); let v">
                      {{ v }}
                    </ng-container>
                  }
                </td>
              }
            </tr>
          } @empty {
            @if (emptyText) {
              <tr>
                <td [attr.colspan]="_columns().length || 1" class="stox-grid-empty">{{ emptyText }}</td>
              </tr>
            }
          }
        </tbody>
      </table>
    </div>
  `,
})
export class StoxGridComponent<T extends RowData = any> {
  private _data = signal<T[]>([]);
  protected _columns = signal<StoxGridColumn<T>[]>([]);
  sorting = signal<SortingState>([]);

  @Input() set data(val: T[]) {
    this._data.set(val || []);
  }
  @Input() set columns(val: StoxGridColumn<T>[]) {
    this._columns.set(val || []);
  }
  @Input() set defaultSort(val: SortingState) {
    this.sorting.set(val || []);
  }
  @Input() clickable = true;
  @Input() emptyText = '';
  @Input() rowClass?: (row: T, index: number) => string;
  @Input() rowSymbolFn?: (row: T) => string | null;
  @Output() rowClick = new EventEmitter<T>();

  private colMap = computed(() => {
    const m = new Map<string, StoxGridColumn<T>>();
    for (const c of this._columns()) m.set(c.id, c);
    return m;
  });

  private tanstackColumns = computed<ColumnDef<typeof features, any, any>[]>(() =>
    this._columns().map(col => ({
      id: col.id,
      header: col.header,
      accessorFn: col.accessorFn ?? ((row: any) => row?.[col.id]),
      enableSorting: col.sortable !== false,
    }))
  );

  table = injectTable<typeof features, any>(() => ({
    features,
    data: this._data(),
    columns: this.tanstackColumns(),
    state: {
      sorting: this.sorting(),
    },
    onSortingChange: updater => {
      this.sorting.set(typeof updater === 'function' ? updater(this.sorting()) : updater);
    },
  }));

  colTemplate(id: string): TemplateRef<any> | undefined {
    return this.colMap().get(id)?.cellTemplate;
  }

  colAlign(id: string): string {
    return this.colMap().get(id)?.align || 'left';
  }

  colHeaderClass(id: string): string {
    return this.colMap().get(id)?.headerClass || '';
  }

  colCellClass(id: string): string {
    return this.colMap().get(id)?.cellClass || '';
  }

  getRowClass(row: T, index: number): string {
    return this.rowClass ? this.rowClass(row, index) : '';
  }
}
