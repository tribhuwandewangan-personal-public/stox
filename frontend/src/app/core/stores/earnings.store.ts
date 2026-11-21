// src/app/core/stores/earnings.store.ts
import { Injectable, signal, computed } from '@angular/core';
import { EarningsQualityResult } from '../models/earnings.model';
import { EarningsService } from '../services/earnings.service';

@Injectable({ providedIn: 'root' })
export class EarningsStore {
  private _data = signal<EarningsQualityResult | null>(null);
  private _loading = signal<boolean>(false);
  private _error = signal<string | null>(null);

  constructor(private earningsService: EarningsService) {}

  load(ticker: string): void {
    this._loading.set(true);
    this._error.set(null);
    this.earningsService.getEarnings(ticker).subscribe({
      next: (res) => {
        this._data.set(res);
        this._loading.set(false);
      },
      error: (err) => {
        this._error.set(err?.message ?? 'Failed to load earnings');
        this._loading.set(false);
      },
    });
  }

  // Exposed signals
  data = computed(() => this._data());
  loading = computed(() => this._loading());
  error = computed(() => this._error());
}
