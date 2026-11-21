// src/app/core/stores/company.store.ts
/**
 * Store for the Company profile and related data.
 * It loads data on demand via CompanyService and exposes Signals
 * for reactive consumption in the UI.
 */

import { Injectable, signal, computed } from '@angular/core';
import { Company } from '../models/company.model';
import { CompanyService } from '../services/company.service';

@Injectable({ providedIn: 'root' })
export class CompanyStore {
  private _company = signal<Company | null>(null);
  private _loading = signal<boolean>(false);
  private _error = signal<string | null>(null);

  constructor(private companyService: CompanyService) {}

  /** Load a company profile by ticker */
  load(ticker: string): void {
    this._loading.set(true);
    this._error.set(null);
    this.companyService.getCompany(ticker).subscribe({
      next: (data) => {
        this._company.set(data);
        this._loading.set(false);
      },
      error: (err) => {
        this._error.set(err?.message ?? 'Failed to load company');
        this._loading.set(false);
      }
    });
  }

  // Exposed signals
  company = computed(() => this._company());
  loading = computed(() => this._loading());
  error = computed(() => this._error());
}
